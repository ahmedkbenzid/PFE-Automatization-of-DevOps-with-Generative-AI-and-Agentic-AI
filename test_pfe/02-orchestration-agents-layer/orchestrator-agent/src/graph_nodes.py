"""
LangGraph Node Functions for the Orchestrator.

Each function represents a node in the orchestration graph.
Nodes receive the current state and return updates to be merged.
"""

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import copy
from typing import Any, Dict
from pathlib import Path

from .graph_state import OrchestratorState, RepoContextDict
from .config import OrchestratorConfig
from .guardrails import Guardrails
from .intent_router import IntentRouter
from .repo_analyzer import RepoAnalyzer, RepoContext


# Initialize shared components (will be set up by the graph builder)
_config: OrchestratorConfig = None
_guardrails: Guardrails = None
_router: IntentRouter = None
_repo_analyzer: RepoAnalyzer = None


def initialize_components():
    """Initialize the shared components for all nodes."""
    global _config, _guardrails, _router, _repo_analyzer

    _config = OrchestratorConfig()

    api_key = _config.LLM_API_KEY
    if not api_key:
        print("[Orchestrator] GROQ_API_KEY not set. Running with fast-path/fallback routing.")

    _guardrails = Guardrails(api_key=api_key, model_name=_config.MODEL_NAME)
    _router = IntentRouter(api_key=api_key, model_name=_config.MODEL_NAME)
    _repo_analyzer = RepoAnalyzer()


def get_config() -> OrchestratorConfig:
    """Get the config, initializing if needed."""
    global _config
    if _config is None:
        initialize_components()
    return _config


def cleanup_repo_analyzer():
    """Cleanup temporary directories from repo analyzer."""
    global _repo_analyzer
    if _repo_analyzer:
        _repo_analyzer.cleanup()


def _calculate_complexity(user_prompt: str, repo_context: Dict[str, Any] = None) -> int:
    """Calculate complexity score for planner gating."""
    score = 0
    prompt_lower = (user_prompt or "").lower()

    artifact_keywords = {
        "docker": ["docker", "dockerfile", "container"],
        "cicd": ["ci/cd", "cicd", "pipeline", "github actions", "workflow"],
        "iac": ["infrastructure", "terraform", "cloudformation"],
        "k8s": ["kubernetes", "k8s", "kubectl", "helm"],
    }

    artifacts_count = 0
    for keywords in artifact_keywords.values():
        if any(kw in prompt_lower for kw in keywords):
            artifacts_count += 1
    if artifacts_count > 1:
        score += artifacts_count * 2

    if any(kw in prompt_lower for kw in ["deploy", "production", "infrastructure", "setup", "complete", "full stack", "end-to-end"]):
        score += 3
    if "microservice" in prompt_lower or "multi-service" in prompt_lower:
        score += 2
    if any(kw in prompt_lower for kw in ["aws", "azure", "gcp", "ecs", "eks", "aks", "gke"]):
        score += 2
    if any(kw in prompt_lower for kw in ["if", "when", "based on", "depending on"]):
        score += 2
    if repo_context and repo_context.get("multiple_repos", False):
        score += 3

    return score


def _requested_agent_count(user_prompt: str) -> int:
    """Estimate how many specialized agents are explicitly needed by the prompt."""
    prompt_lower = (user_prompt or "").lower()
    requested_agents = set()

    keyword_map = {
        "cicd-agent": [
            "github actions", "workflow", "ci/cd", "cicd", "ci cd", "pipeline",
            "jenkins", "gitlab", "circleci", "continuous integration", "continuous deployment",
        ],
        "docker-agent": [
            "docker", "dockerfile", "container", "docker compose", "image", "deployment", "deploy",
        ],
        "iac-agent": [
            "terraform", "iac", "infrastructure", "ansible", "cloudformation", "aws", "azure", "gcp",
        ],
        "k8s-agent": [
            "kubernetes", "k8s", "helm", "kubectl",
        ],
    }

    for agent_name, keywords in keyword_map.items():
        if any(keyword in prompt_lower for keyword in keywords):
            requested_agents.add(agent_name)

    # Explicit complete DevOps requests imply both Docker and CI/CD at minimum.
    if any(
        keyword in prompt_lower
        for keyword in [
            "complete devops",
            "full devops",
            "devops configuration",
            "end-to-end devops",
            "deploy automatically",
            "automated deployment",
        ]
    ):
        requested_agents.update({"docker-agent", "cicd-agent"})

    return len(requested_agents)


def _should_use_planner(user_prompt: str, repo_context: Dict[str, Any], enabled: bool, threshold: int, skip_planner: bool) -> bool:
    """Determine planner usage."""
    if skip_planner or not enabled:
        return False

    # Product requirement: any request that needs multiple agents must go through planner.
    if _requested_agent_count(user_prompt) > 1:
        return True

    prompt_lower = (user_prompt or "").lower()
    force_keywords = ["production setup", "complete deployment", "end-to-end", "full stack setup", "microservices", "complete ci/cd"]
    if any(kw in prompt_lower for kw in force_keywords):
        return True

    skip_keywords = ["just", "only", "simple", "single"]
    if any(kw in prompt_lower for kw in skip_keywords):
        return False

    return _calculate_complexity(user_prompt, repo_context) >= threshold


def _invoke_planner(user_prompt: str, repo_context: Dict[str, Any], max_retries: int = 2) -> Dict[str, Any]:
    """Invoke planner-agent subprocess."""
    print("[Orchestrator] 🧠 Complex request detected - Invoking Planner Agent...")
    planner_root = Path(__file__).parent.parent.parent / "planner-agent"
    planner_path = planner_root / "src" / "pipeline.py"

    if not planner_path.exists():
        return {"status": "error", "message": f"Planner not available at {planner_path}"}

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            current_timeout = 60 * (attempt + 1)
            env = os.environ.copy()
            env["PYTHONPATH"] = str(planner_root) + os.pathsep + env.get("PYTHONPATH", "")
            env["PYTHONIOENCODING"] = "utf-8"
            env["LLM_PROVIDER"] = "groq"

            result = subprocess.run(
                [sys.executable, str(planner_path), user_prompt, json.dumps(repo_context or {})],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=current_timeout,
                cwd=str(planner_root),
                env=env,
            )
            if result.returncode != 0:
                last_error = result.stderr.strip() or "Planner failed"
                if attempt == max_retries:
                    return {"status": "error", "message": last_error}
                continue

            output = result.stdout or ""
            if "=== PLANNER OUTPUT ===" in output:
                json_part = output.split("=== PLANNER OUTPUT ===", 1)[1].strip()
                return json.loads(json_part)
            return json.loads(output)
        except Exception as e:
            last_error = str(e)
            if attempt == max_retries:
                return {"status": "error", "message": last_error}

    return {"status": "error", "message": last_error or "Planner failed"}


# =============================================================================
# NODE FUNCTIONS
# =============================================================================

def guardrails_node(state: OrchestratorState) -> Dict[str, Any]:
    """
    Validate the user input through security guardrails.

    This node checks if the request is allowed by the security policies.
    """
    global _guardrails

    if _guardrails is None:
        initialize_components()

    user_prompt = state.get("user_prompt", "")
    print("[Orchestrator] Running Guardrails Check...")

    try:
        result = _guardrails.validate_input(user_prompt)
        is_allowed = result.get("is_allowed", False)
        reason = result.get("reason", "Unknown")

        if is_allowed:
            print("[Orchestrator] Guardrails Passed.")
            return {
                "guardrails_passed": True,
                "guardrails_reason": reason,
            }
        else:
            print(f"[Orchestrator] Blocked by Guardrails: {reason}")
            return {
                "guardrails_passed": False,
                "guardrails_reason": reason,
                "status": "blocked",
                "errors": [reason],
            }

    except Exception as e:
        error_msg = f"Guardrail evaluation error: {str(e)}"
        print(f"[Orchestrator] {error_msg}")
        return {
            "guardrails_passed": False,
            "guardrails_reason": error_msg,
            "status": "error",
            "errors": [error_msg],
        }


def repo_analysis_node(state: OrchestratorState) -> Dict[str, Any]:
    """
    Analyze the repository if provided.

    This node extracts context from local repos or GitHub URLs.
    """
    global _repo_analyzer, _config

    if _repo_analyzer is None:
        initialize_components()

    repo_path = state.get("repository_path")
    github_url = state.get("github_url")

    # Use config default if no path provided
    if not repo_path:
        repo_path = _config.DEFAULT_REPOSITORY_PATH

    # Check if we should analyze
    should_analyze = (
        (repo_path and os.path.isdir(repo_path)) or
        github_url
    )

    if not should_analyze:
        print("[Orchestrator] No repository provided - using prompt-only mode")
        return {
            "repo_context": {
                "is_available": False,
                "source": "none",
                "path": "",
                "languages": [],
                "build_system": None,
                "package_managers": [],
                "frameworks": [],
                "has_dockerfile": False,
                "has_docker_compose": False,
                "has_ci_workflows": False,
                "existing_workflows": [],
                "config_files": {},
            }
        }

    print("[Orchestrator] Analyzing Repository...")
    try:
        # Use config setting for deep analysis (default: fast shallow mode)
        repo_context: RepoContext = _repo_analyzer.analyze(
            repo_path, github_url, deep=_config.DEEP_REPO_ANALYSIS
        )

        # Map new RepoContext to old RepoContextDict for backward compatibility
        is_available = repo_context.error is None and repo_context.analysis_mode != "prompt-only"
        source = {
            "mcp": "github",
            "github": "github",
            "local": "local",
            "prompt-only": "none"
        }.get(repo_context.analysis_mode, "none")

        context_path = repo_path or ""
        if source == "github":
            context_path = repo_context.github_url or github_url or ""

        # Print error details if analysis failed
        if repo_context.error:
            print(f"[Orchestrator] ⚠️  Analysis error: {repo_context.error}")

        context_dict: RepoContextDict = {
            "is_available": is_available,
            "source": source,
            "path": context_path,
            "github_url": repo_context.github_url or github_url or "",
            "languages": repo_context.languages,
            "build_system": repo_context.build_system,
            "package_managers": repo_context.package_managers,
            "frameworks": repo_context.frameworks,
            "has_dockerfile": repo_context.has_dockerfile,
            "has_docker_compose": repo_context.has_docker_compose,
            "has_ci_workflows": repo_context.has_github_actions,
            "existing_workflows": repo_context.ci_workflows,
            "config_files": {},
            # Add version information for project-aware CI/CD workflows
            "python_version": repo_context.python_version,
            "java_version": repo_context.java_version,
            "node_version": repo_context.node_version,
            "go_version": repo_context.go_version,
            "django_version": repo_context.django_version,
            "fastapi_version": repo_context.fastapi_version,
            "flask_version": repo_context.flask_version,
            "spring_boot_version": repo_context.spring_boot_version,
            "express_version": repo_context.express_version,
            "maven_version": repo_context.maven_version,
            "gradle_version": repo_context.gradle_version,
            "npm_version": repo_context.npm_version,
            "pip_version": repo_context.pip_version,
            # Add dependency analysis metadata
            "critical_packages": repo_context.critical_packages,
            "has_version_conflicts": repo_context.has_version_conflicts,
            "dependency_warnings": repo_context.dependency_warnings,
            "dependency_recommendations": repo_context.dependency_recommendations,
        }

        if is_available:
            print(f"[Orchestrator] Repo Analysis Complete:")
            print(f"    - Source: {source}")
            print(f"    - Languages: {repo_context.languages}")
            print(f"    - Build System: {repo_context.build_system or 'unknown'}")
            print(f"    - Frameworks: {repo_context.frameworks}")
            print(f"    - Has Dockerfile: {repo_context.has_dockerfile}")
            print(f"    - Has GitHub Actions: {repo_context.has_github_actions}")
        else:
            print("[Orchestrator] Repository not accessible - using prompt-only mode")

        return {"repo_context": context_dict}

    except Exception as e:
        print(f"[Orchestrator] Error analyzing repo: {e} - falling back to prompt-only mode")
        return {
            "repo_context": {
                "is_available": False,
                "source": "none",
                "path": "",
                "languages": [],
                "build_system": None,
                "package_managers": [],
                "frameworks": [],
                "has_dockerfile": False,
                "has_docker_compose": False,
                "has_ci_workflows": False,
                "existing_workflows": [],
                "config_files": {},
                # Version fields (empty on error)
                "python_version": None,
                "java_version": None,
                "node_version": None,
                "go_version": None,
                "django_version": None,
                "fastapi_version": None,
                "flask_version": None,
                "spring_boot_version": None,
                "express_version": None,
                "maven_version": None,
                "gradle_version": None,
                "npm_version": None,
                "pip_version": None,
                "critical_packages": {},
                "has_version_conflicts": False,
                "dependency_warnings": [],
                "dependency_recommendations": [],
            }
        }


def complexity_assessment_node(state: OrchestratorState) -> Dict[str, Any]:
    """Assess complexity and decide if planner path should be used."""
    user_prompt = state.get("user_prompt", "")
    repo_context = state.get("repo_context", {})
    threshold = state.get("planner_complexity_threshold", 4)
    enabled = state.get("planner_enabled", True)
    skip_planner = state.get("skip_planner", False)
    approved_execution_plan = state.get("approved_execution_plan")

    complexity = _calculate_complexity(user_prompt, repo_context)
    use_planner = bool(approved_execution_plan) or _should_use_planner(
        user_prompt=user_prompt,
        repo_context=repo_context,
        enabled=enabled,
        threshold=threshold,
        skip_planner=skip_planner,
    )
    return {
        "complexity_score": complexity,
        "used_planner": use_planner,
    }


def planner_node(state: OrchestratorState) -> Dict[str, Any]:
    """Generate execution plan for complex requests."""
    approved_execution_plan = state.get("approved_execution_plan")
    if approved_execution_plan:
        return {
            "execution_plan": approved_execution_plan,
            "planner_reasoning": "Using pre-approved execution plan",
            "planner_error": "",
        }

    planner_result = _invoke_planner(
        user_prompt=state.get("user_prompt", ""),
        repo_context=state.get("repo_context", {}),
    )
    if planner_result.get("status") == "success":
        return {
            "execution_plan": planner_result.get("plan", {}),
            "planner_reasoning": planner_result.get("reasoning", ""),
            "planner_error": "",
        }
    return {
        "execution_plan": {},
        "planner_reasoning": "",
        "planner_error": planner_result.get("message", "Planner failed"),
        "status": "error",
        "errors": state.get("errors", []) + [planner_result.get("message", "Planner failed")],
    }


def man_in_the_loop_node(state: OrchestratorState) -> Dict[str, Any]:
    """Human approval stage."""
    has_plan = bool(state.get("execution_plan"))
    if not has_plan:
        return {"plan_approved": False}

    # Plan-only mode: stop and wait for explicit approval in a follow-up call.
    if state.get("plan_only", False) and not state.get("approved_execution_plan"):
        return {
            "plan_approved": False,
            "plan_only_waiting_approval": True,
            "status": "plan_ready",
        }

    return {"plan_approved": True, "plan_only_waiting_approval": False}


def plan_confirmed_node(state: OrchestratorState) -> Dict[str, Any]:
    """Materialize approved execution DAG/plan."""
    plan = state.get("execution_plan") or state.get("approved_execution_plan") or {}
    execution_order = plan.get("execution_order", [])
    return {
        "approved_execution_plan": plan,
        "dag_execution_order": execution_order,
        "status": "pending",
    }


def dag_execution_node(state: OrchestratorState) -> Dict[str, Any]:
    """DAG orchestration stage before agent execution."""
    return {"status": "pending"}


def routing_direct_node(state: OrchestratorState) -> Dict[str, Any]:
    """
    Non-complex direct path:
    route request and execute target agents directly (mapped to single node in requested diagram).
    """
    route_updates = routing_node(state)
    merged_state = dict(state)
    merged_state.update(route_updates)
    exec_updates = agent_execution_node(merged_state)
    route_updates.update(exec_updates)
    return route_updates


def routing_node(state: OrchestratorState) -> Dict[str, Any]:
    """
    Route the request to appropriate agents based on intent analysis.

    This node uses the IntentRouter to determine which agents should handle the request.
    """
    global _router

    if _router is None:
        initialize_components()

    user_prompt = state.get("user_prompt", "")
    print("[Orchestrator] Analyzing User Intent & Routing...")

    try:
        route_result = _router.route(user_prompt)

        primary_agent = route_result.get("primary_agent", "")
        secondary_agents = route_result.get("secondary_agents", [])
        reasoning = route_result.get("reasoning", "Routing execution")

        # Build target agents list
        target_agents = []
        if primary_agent and primary_agent != "error":
            target_agents.append(primary_agent)
        target_agents.extend(secondary_agents)

        print(f"[Orchestrator] Assigned to: Primary -> {primary_agent} | Secondary -> {secondary_agents}")
        print(f"[Orchestrator] Reasoning: {reasoning}")

        return {
            "primary_agent": primary_agent,
            "secondary_agents": secondary_agents,
            "routing_reasoning": reasoning,
            "target_agents": target_agents,
            "user_intent": reasoning,
            "agent_outputs": {"intent_router": route_result},
        }

    except Exception as e:
        error_msg = f"Routing failed: {str(e)}"
        print(f"[Orchestrator] {error_msg}")
        return {
            "primary_agent": "error",
            "secondary_agents": [],
            "routing_reasoning": error_msg,
            "target_agents": [],
            "errors": state.get("errors", []) + [error_msg],
        }


def agent_execution_node(state: OrchestratorState) -> Dict[str, Any]:
    """
    Execute all target agents and collect their outputs.

    This node dispatches work to specialized agents (cicd, docker, iac).
    If an approved execution plan is provided, follows the plan's order and parallelization.
    """
    global _config

    if _config is None:
        initialize_components()

    target_agents = state.get("target_agents", [])
    user_prompt = state.get("user_prompt", "")
    repo_context = state.get("repo_context", {})
    repository_path = state.get("repository_path") or _config.DEFAULT_REPOSITORY_PATH
    github_url = state.get("github_url") or ""
    if not github_url and isinstance(repo_context, dict):
        repo_ctx_url = repo_context.get("github_url")
        if isinstance(repo_ctx_url, str) and repo_ctx_url.strip():
            github_url = repo_ctx_url.strip()
        elif repo_context.get("source") == "github":
            repo_ctx_path = repo_context.get("path")
            if isinstance(repo_ctx_path, str) and repo_ctx_path.startswith("http"):
                github_url = repo_ctx_path
    
    # FIXED: Use GitHub URL for agent execution when available
    # This ensures docker-agent analyzes the correct repository instead of the orchestrator's directory
    agent_repo_path = github_url if github_url else repository_path
    
    approved_plan = state.get("approved_execution_plan")

    agent_outputs = dict(state.get("agent_outputs", {}))
    errors = list(state.get("errors", []))

    print("[Orchestrator] Dispatching to Target Agents...")
    
    # Enhance repo_context if Docker agent is being executed
    enhanced_repo_context = dict(repo_context) if repo_context else {}
    if "docker-agent" in target_agents:
        print("[Orchestrator] Docker agent detected - enhancing context for CI/CD agent...")
        enhanced_repo_context["dockerfile_being_generated"] = True
        enhanced_repo_context["dockerfile_path"] = "Dockerfile"
        enhanced_repo_context["docker_context_path"] = "."
    
    # If approved plan exists, execute according to plan order
    if approved_plan and "execution_order" in approved_plan:
        print("[Orchestrator] Following approved execution plan order...")
        execution_order = approved_plan["execution_order"]
        
        for step_idx, step in enumerate(execution_order, 1):
            if isinstance(step, list):
                # Parallel execution group
                print(f"[Orchestrator] Step {step_idx}: Parallel execution of {len(step)} agents")
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=len(step)) as executor:
                    futures = {}
                    for agent in step:
                        future = executor.submit(_execute_single_agent, agent, user_prompt, agent_repo_path, enhanced_repo_context)
                        futures[future] = agent
                    
                    for future in concurrent.futures.as_completed(futures):
                        agent = futures[future]
                        try:
                            result = future.result()
                            agent_outputs[agent] = result
                            if result.get("status") == "error":
                                errors.append(f"{agent} failed: {result.get('message', 'Unknown error')}")
                        except Exception as e:
                            errors.append(f"{agent} execution error: {str(e)}")
            else:
                # Sequential execution
                print(f"[Orchestrator] Step {step_idx}: Executing {step}")
                result = _execute_single_agent(step, user_prompt, agent_repo_path, enhanced_repo_context)
                agent_outputs[step] = result
                if result.get("status") == "error":
                    errors.append(f"{step} failed: {result.get('message', 'Unknown error')}")
    else:
        # Default execution (no plan) - execute all agents in parallel
        for agent in target_agents:
            result = _execute_single_agent(agent, user_prompt, agent_repo_path, enhanced_repo_context)
            agent_outputs[agent] = result
            if result.get("status") == "error":
                errors.append(f"{agent} failed: {result.get('message', 'Unknown error')}")

    # DISABLED: Automatic pipeline execution moved to separate execution agent
    # Users must explicitly trigger validation via UI after reviewing artifacts
    # pipeline_execution = _execute_pipeline_with_self_repair(
    #     agent_outputs=agent_outputs,
    #     user_prompt=user_prompt,
    #     repository_path=repository_path,
    #     github_url=github_url,
    #     repo_context=repo_context,
    # )
    # agent_outputs["pipeline_execution"] = pipeline_execution
    # if pipeline_execution.get("status") == "error":
    #     errors.append(pipeline_execution.get("message", "Local pipeline execution failed"))

    return {
        "agent_outputs": agent_outputs,
        "errors": errors,
        "status": "error" if errors else "completed",
    }


def user_feedback_node(state: OrchestratorState) -> Dict[str, Any]:
    """Collect/record user feedback state (accept by default in non-interactive graph run)."""
    feedback = (state.get("user_feedback") or "accept").lower()
    if feedback not in {"accept", "reject", "not"}:
        feedback = "accept"
    return {"user_feedback": feedback}


def _execute_single_agent(agent: str, user_prompt: str, repository_path: str, repo_context: Dict[str, Any]) -> Dict[str, Any]:
    """Helper to execute a single agent"""
    if agent == "cicd-agent":
        return _execute_cicd_agent(user_prompt, repository_path, repo_context)
    elif agent == "docker-agent":
        return _execute_docker_agent(user_prompt, repository_path, repo_context)
    elif agent == "iac-agent":
        return _execute_iac_agent(user_prompt, repository_path, repo_context)
    else:
        print(f"[Orchestrator] Agent '{agent}' is not yet integrated. Skipping execution.")
        return {"status": "skipped", "message": "Not integrated"}


def create_pr_node(state: OrchestratorState) -> Dict[str, Any]:
    """
    Create a pull request with generated artifacts (optional, user-triggered).

    This node creates a PR if the user requested it via --create-pr flag.
    It uses the GitHub MCP client for PR creation with fallback to PyGithub.
    """
    from .github_manager import GitHubMCPClient

    # Check if PR creation was requested
    create_pr = state.get("create_pr", False)
    if not create_pr:
        print("[Orchestrator] PR creation skipped (--create-pr not specified)")
        return {"pr_details": None}

    # Extract PR parameters
    github_url = state.get("github_url", "")
    branch_name = state.get("branch_name", "")
    pr_title = state.get("pr_title", "Auto-generated PR from Orchestrator")
    pr_body = state.get("pr_body", "Generated by Orchestrator Agent")

    if not github_url or not branch_name:
        error_msg = "Missing github_url or branch_name for PR creation"
        print(f"[Orchestrator] ERROR: {error_msg}")
        return {
            "pr_details": {
                "success": False,
                "error": error_msg,
            }
        }

    print("[Orchestrator] Creating Pull Request...")

    try:
        # Parse GitHub URL
        from .github_manager import GitHubURLParser

        parser = GitHubURLParser(github_url)
        if not parser.is_valid():
            raise ValueError(f"Invalid GitHub URL: {github_url}")

        owner = parser.owner
        repo = parser.repo

        # Initialize MCP client and create PR
        config = get_config()
        token = config.GITHUB_TOKEN
        if not token:
            raise ValueError("GITHUB_TOKEN not configured")

        mcp_config = {
            "mcp_enabled": config.GITHUB_MCP_ENABLED,
            "strict_mode": config.MCP_GITHUB_STRICT,
            "timeout": config.MCP_GITHUB_CALL_TIMEOUT,
            "server_command": config.MCP_GITHUB_SERVER_COMMAND,
            "server_args": config.MCP_GITHUB_SERVER_ARGS.split(),
        }

        client = GitHubMCPClient(token=token, mcp_config=mcp_config)

        pr_result = client.create_pull_request(
            owner=owner,
            repo=repo,
            title=pr_title,
            body=pr_body,
            head=branch_name,
            base="main",  # Default to main, could be parameterized
        )

        if pr_result.get("success"):
            print(f"[Orchestrator] PR Created: {pr_result.get('pr_url')}")
        else:
            print(f"[Orchestrator] PR Creation Failed: {pr_result.get('error')}")

        return {"pr_details": pr_result}

    except Exception as e:
        error_msg = f"PR creation error: {str(e)}"
        print(f"[Orchestrator] ERROR: {error_msg}")
        return {
            "pr_details": {
                "success": False,
                "error": error_msg,
                "error_type": type(e).__name__,
            }
        }


def cleanup_node(state: OrchestratorState) -> Dict[str, Any]:
    """
    Cleanup temporary resources.

    This node cleans up any temporary directories created during processing.
    """
    cleanup_repo_analyzer()
    return {}


# =============================================================================
# AGENT EXECUTION HELPERS
# =============================================================================

def _resolve_agent_path(agent_folder_name: str) -> str:
    """Get the absolute path to an agent folder."""
    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", agent_folder_name)
    )


def _invoke_python_agent(
    agent_name: str,
    agent_folder_name: str,
    run_code: str,
    args: list,
    result_prefix: str,
    timeout: int = 120,
    max_retries: int = 2,
) -> Dict[str, Any]:
    """
    Invoke a Python agent as a subprocess and collect results with retry logic.

    Args:
        timeout: Maximum seconds to wait for agent completion (default: 120s)
        max_retries: Number of retry attempts on timeout/failure (default: 2)
    """
    agent_path = _resolve_agent_path(agent_folder_name)
    if not os.path.exists(agent_path):
        raise FileNotFoundError(f"Could not find {agent_name} at: {agent_path}")

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            current_timeout = timeout * (attempt + 1)  # Exponential timeout: 120s, 240s, 360s
            
            if attempt > 0:
                print(f"[Orchestrator] Retrying {agent_name} (attempt {attempt + 1}/{max_retries + 1}, timeout: {current_timeout}s)...")
            
            # Prepare environment with PYTHONPATH
            env = os.environ.copy()
            env["PYTHONPATH"] = agent_path + os.pathsep + os.environ.get("PYTHONPATH", "")
            env["PYTHONIOENCODING"] = "utf-8"

            # Pass arguments as JSON to avoid shell escaping issues
            args_json = json.dumps(args)

            # Modified run_code: deserialize args from JSON
            safe_run_code = (
                f"import json, sys; "
                f"args = json.loads({repr(args_json)}); "
                f"sys.argv = [''] + args; "
                f"{run_code}"
            )

            completed = subprocess.run(
                [sys.executable, "-c", safe_run_code],
                cwd=agent_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                check=False,
                timeout=current_timeout,
            )
            
            # Check if subprocess succeeded
            if completed.returncode != 0:
                error_msg = completed.stderr.strip() if completed.stderr else completed.stdout.strip()
                if not error_msg:
                    error_msg = f"Unknown {agent_name} error (exit code {completed.returncode})"
                
                # If it's the last attempt, raise the error
                if attempt == max_retries:
                    raise RuntimeError(error_msg)
                
                # Otherwise, log and retry
                print(f"[Orchestrator] {agent_name} failed: {error_msg[:100]}... (will retry)")
                last_error = error_msg
                continue
            
            # Parse result from stdout
            for line in (completed.stdout or "").splitlines():
                if line.startswith(result_prefix):
                    try:
                        return json.loads(line[len(result_prefix):])
                    except json.JSONDecodeError as e:
                        if attempt == max_retries:
                            raise RuntimeError(f"{agent_name} returned invalid JSON: {str(e)}")
                        print(f"[Orchestrator] {agent_name} JSON parse error (will retry)")
                        last_error = str(e)
                        continue
            
            # No structured result found
            if attempt == max_retries:
                raise RuntimeError(f"{agent_name} returned no structured result. Output: {completed.stdout}")
            print(f"[Orchestrator] {agent_name} returned no result (will retry)")
            last_error = "No structured result"
            
        except subprocess.TimeoutExpired:
            if attempt == max_retries:
                raise RuntimeError(f"{agent_name} timed out after {current_timeout}s (all retries exhausted)")
            print(f"[Orchestrator] {agent_name} timeout at {current_timeout}s (will retry with longer timeout)")
            last_error = f"Timeout at {current_timeout}s"
            continue
    
    # Should never reach here, but just in case
    raise RuntimeError(f"{agent_name} failed after {max_retries + 1} attempts. Last error: {last_error}")


def _execute_cicd_agent(
    user_prompt: str,
    repo_path: str,
    repo_context: Dict[str, Any]
) -> Dict[str, Any]:
    """Execute the CICD agent."""
    agent = "cicd-agent"
    print(f"[Orchestrator] -> Invoking {agent} locally (timeout: 120s)")

    try:
        repo_context_json = json.dumps(repo_context) if repo_context.get("is_available") else "{}"

        # Simplified run_code - args are now injected via JSON
        run_code = (
            "from dataclasses import asdict; "
            "from src.pipeline import CICDPipeline; "
            "from src.models.types import UserRequest; "
            "user_prompt = args[0]; "
            "repo_path = args[1]; "
            "repo_ctx = __import__('json').loads(args[2]) if args[2] != '{}' else None; "
            "req = UserRequest(text=user_prompt); "
            "result = CICDPipeline().process_request(req, repo_path=repo_path, repo_context=repo_ctx); "
            "print('CICD_RESULT_JSON=' + __import__('json').dumps(asdict(result), default=str))"
        )

        cicd_result = _invoke_python_agent(
            agent_name="cicd-agent",
            agent_folder_name="cicd-agent",
            run_code=run_code,
            args=[user_prompt, repo_path or "", repo_context_json],
            result_prefix="CICD_RESULT_JSON=",
            timeout=180,  # 3 minutes base, up to 9 minutes with retries
            max_retries=2,
        )

        print(f"[Orchestrator] <- Result received from {agent}")
        return {"status": "success", "data": cicd_result}

    except subprocess.TimeoutExpired as e:
        print(f"[Orchestrator] Timeout executing {agent}: {str(e)}")
        return {"status": "error", "message": f"{agent} timed out"}
    except Exception as e:
        print(f"[Orchestrator] Error executing {agent}: {str(e)}")
        return {"status": "error", "message": str(e)}


def _execute_docker_agent(
    user_prompt: str,
    repo_path: str,
    repo_context: Dict[str, Any]
) -> Dict[str, Any]:
    """Execute the Docker agent."""
    agent = "docker-agent"
    print(f"[Orchestrator] -> Invoking {agent} locally (timeout: 150s base)")

    try:
        repo_context_json = json.dumps(repo_context) if repo_context.get("is_available") else "{}"

        run_code = (
            "from dataclasses import asdict; "
            "from src.pipeline import run_pipeline; "
            "user_prompt = args[0]; "
            "repo_path = args[1]; "
            "repo_ctx = __import__('json').loads(args[2]) if args[2] != '{}' else None; "
            "result = run_pipeline(user_prompt, repo_path, False, repo_ctx); "
            "print('DOCKER_RESULT_JSON=' + __import__('json').dumps(asdict(result), default=str))"
        )

        deployment_request = _is_deployment_request(user_prompt)
        max_react_retries = 2
        react_trace: list[Dict[str, Any]] = []

        current_prompt = user_prompt
        current_result = _invoke_python_agent(
            agent_name="docker-agent",
            agent_folder_name="docker-agent",
            run_code=run_code,
            args=[current_prompt, repo_path or "", repo_context_json],
            result_prefix="DOCKER_RESULT_JSON=",
            timeout=150,
            max_retries=2,
        )

        if not deployment_request:
            print(f"[Orchestrator] <- Result received from {agent}")
            return {"status": "success", "data": current_result}

        print("[Orchestrator] Deployment request detected - running Docker ReAct loop until image build succeeds")

        for attempt in range(1, max_react_retries + 2):
            build_check = _validate_generated_docker_image(
                docker_agent_result=current_result,
                repository_path=repo_path,
            )
            react_trace.append(
                {
                    "attempt": attempt,
                    "generation_prompt": current_prompt,
                    "build_check": copy.deepcopy(build_check),
                }
            )

            if build_check.get("success"):
                current_result["react_validation"] = {
                    "deployment_request": True,
                    "image_build_verified": True,
                    "attempts": react_trace,
                    "final_image_name": build_check.get("image_name", ""),
                }
                print(f"[Orchestrator] <- Result received from {agent} with verified image build")
                return {"status": "success", "data": current_result}

            if attempt > max_react_retries:
                break

            failure_summary = _summarize_docker_build_failure(build_check)
            current_prompt = (
                f"{user_prompt}\n\n"
                f"ReAct repair attempt {attempt}: regenerate Dockerfile so docker build succeeds.\n"
                f"Build failure details:\n{failure_summary}"
            )
            print(f"[Orchestrator] Docker ReAct retry {attempt}/{max_react_retries}")
            current_result = _invoke_python_agent(
                agent_name="docker-agent",
                agent_folder_name="docker-agent",
                run_code=run_code,
                args=[current_prompt, repo_path or "", repo_context_json],
                result_prefix="DOCKER_RESULT_JSON=",
                timeout=180,
                max_retries=2,
            )

        return {
            "status": "error",
            "message": "Deployment request requires a successful Docker image build, but all ReAct attempts failed.",
            "data": current_result,
            "react_validation": {
                "deployment_request": True,
                "image_build_verified": False,
                "attempts": react_trace,
            },
        }

    except Exception as e:
        print(f"[Orchestrator] Error executing {agent}: {str(e)}")
        return {"status": "error", "message": str(e)}


def _is_deployment_request(user_prompt: str) -> bool:
    prompt_lower = (user_prompt or "").lower()
    deployment_keywords = [
        "deploy",
        "deployment",
        "production",
        "release",
        "go live",
        "ship",
    ]
    return any(keyword in prompt_lower for keyword in deployment_keywords)


def _extract_dockerfile_from_agent_result(docker_agent_result: Dict[str, Any]) -> str:
    configuration = (docker_agent_result.get("configuration") or {}) if isinstance(docker_agent_result, dict) else {}
    dockerfile_raw = configuration.get("dockerfile_content") or ""
    return _sanitize_generated_dockerfile(dockerfile_raw)


def _validate_generated_docker_image(docker_agent_result: Dict[str, Any], repository_path: str) -> Dict[str, Any]:
    dockerfile_content = _extract_dockerfile_from_agent_result(docker_agent_result)
    if not dockerfile_content:
        return {
            "success": False,
            "message": "Dockerfile content is empty; cannot build image.",
            "docker_build": {"exit_code": -1, "timed_out": False, "logs": []},
        }

    workspace = tempfile.mkdtemp(prefix="orchestrator-docker-react-")
    workspace_path = Path(workspace)

    copy_result = _copy_repo_source_to_workspace(repository_path, workspace_path)
    if not copy_result.get("copied"):
        return {
            "success": False,
            "message": f"Failed to prepare workspace for Docker build: {copy_result.get('reason', 'unknown reason')}",
            "workspace": str(workspace_path),
            "repo_copy": copy_result,
            "docker_build": {"exit_code": -1, "timed_out": False, "logs": []},
        }

    dockerfile_path = workspace_path / "Dockerfile"
    dockerfile_path.write_text(dockerfile_content, encoding="utf-8")

    image_name = f"orchestrator-react-{int(time.time())}"
    docker_build = _stream_command_with_timeout(
        command=["docker", "build", "-t", f"{image_name}:latest", "."],
        cwd=str(workspace_path),
        timeout_seconds=600,
        step_name="docker-react-build",
    )

    return {
        "success": docker_build.get("success", False),
        "message": "Docker image build succeeded" if docker_build.get("success") else "Docker image build failed",
        "workspace": str(workspace_path),
        "repo_copy": copy_result,
        "image_name": image_name,
        "docker_build": docker_build,
    }


def _summarize_docker_build_failure(build_check: Dict[str, Any]) -> str:
    docker_build = build_check.get("docker_build") or {}
    lines = [
        f"exit_code={docker_build.get('exit_code')}",
        f"timed_out={docker_build.get('timed_out')}",
    ]

    raw_logs = docker_build.get("logs", [])
    tail_lines = []
    for entry in raw_logs[-30:]:
        if isinstance(entry, dict):
            tail_lines.append(entry.get("line", ""))
        else:
            tail_lines.append(str(entry))

    if tail_lines:
        lines.append("recent_logs:")
        lines.extend(f"- {line}" for line in tail_lines)

    return "\n".join(lines)


def _execute_iac_agent(
    user_prompt: str,
    repo_path: str,
    repo_context: Dict[str, Any]
) -> Dict[str, Any]:
    """Execute the IAC (Terraform) agent."""
    agent = "iac-agent"
    print(f"[Orchestrator] -> Invoking {agent} locally (timeout: 200s base)")

    try:
        repo_context_json = json.dumps(repo_context) if repo_context.get("is_available") else "{}"

        run_code = (
            "from dataclasses import asdict; "
            "from src.pipeline import run_pipeline; "
            "user_prompt = args[0]; "
            "repo_path = args[1]; "
            "repo_ctx = __import__('json').loads(args[2]) if args[2] != '{}' else None; "
            "result = run_pipeline(user_prompt, repo_path, repo_ctx, False); "
            "print('IAC_RESULT_JSON=' + __import__('json').dumps(asdict(result), default=str))"
        )

        iac_result = _invoke_python_agent(
            agent_name="iac-agent",
            agent_folder_name="iac-agent",
            run_code=run_code,
            args=[user_prompt, repo_path or "", repo_context_json],
            result_prefix="IAC_RESULT_JSON=",
            timeout=200,  # 3.3 minutes base, up to 10 minutes with retries
            max_retries=2,
        )

        print(f"[Orchestrator] <- Result received from {agent}")
        return {"status": "success", "data": iac_result}

    except Exception as e:
        print(f"[Orchestrator] Error executing {agent}: {str(e)}")
        return {"status": "error", "message": str(e)}


def _extract_generated_dockerfile(agent_outputs: Dict[str, Any]) -> str:
    docker_output = (agent_outputs.get("docker-agent") or {}).get("data") or {}
    configuration = docker_output.get("configuration") or {}
    raw_dockerfile = configuration.get("dockerfile_content") or ""
    return _sanitize_generated_dockerfile(raw_dockerfile)


def _extract_generated_cicd_workflow(agent_outputs: Dict[str, Any]) -> str:
    cicd_output = (agent_outputs.get("cicd-agent") or {}).get("data") or {}
    raw_workflow = cicd_output.get("workflow_yaml") or ""
    return _sanitize_generated_workflow_yaml(raw_workflow)


def _extract_fenced_blocks(text: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    pattern = re.compile(r"```([a-zA-Z0-9_+\-]*)[ \t]*\n(.*?)```", re.DOTALL)
    for match in pattern.finditer(text):
        language = (match.group(1) or "").strip().lower()
        content = (match.group(2) or "").strip()
        if content:
            blocks.append((language, content))
    return blocks


def _dockerfile_score(content: str) -> int:
    if not content:
        return 0

    instructions = (
        "FROM ", "RUN ", "COPY ", "ADD ", "WORKDIR ", "CMD ", "ENTRYPOINT ",
        "EXPOSE ", "ENV ", "ARG ", "USER ", "LABEL ", "HEALTHCHECK ",
        "SHELL ", "STOPSIGNAL ", "VOLUME ", "ONBUILD ",
    )

    score = 0
    from_count = 0
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        upper_line = line.upper()
        if upper_line.startswith("FROM "):
            score += 6
            from_count += 1
        elif upper_line.startswith(instructions):
            score += 2

    lower_content = content.lower()
    if "pipeline {" in lower_content:
        score -= 8
    if "stages:" in lower_content and "jobs:" not in lower_content:
        score -= 4
    if any(token in lower_content for token in ["github actions", "jenkins", "gitlab"]):
        score -= 2

    if from_count == 0:
        return 0
    return score


def _github_actions_score(content: str) -> int:
    if not content:
        return 0

    lower_content = content.lower()
    score = 0

    if "jobs:" in lower_content:
        score += 6
    if "\non:" in lower_content or lower_content.startswith("on:") or "'on':" in lower_content or '"on":' in lower_content:
        score += 4
    if "uses: actions/" in lower_content:
        score += 2
    if "pipeline {" in lower_content:
        score -= 8
    if "stages:" in lower_content and "jobs:" not in lower_content:
        score -= 4

    return score


def _sanitize_generated_dockerfile(raw_content: str) -> str:
    text = (raw_content or "").replace("\r\n", "\n").strip()
    if not text:
        return ""

    fenced_blocks = _extract_fenced_blocks(text)
    docker_candidates: list[tuple[int, str]] = []
    for language, block in fenced_blocks:
        if language in {"dockerfile", "docker", "", "text", "plaintext"}:
            score = _dockerfile_score(block)
            if score > 0:
                docker_candidates.append((score, block))

    if docker_candidates:
        best_block = max(docker_candidates, key=lambda item: item[0])[1]
        return best_block.strip() + "\n"

    no_fence_lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
    no_fence_text = "\n".join(no_fence_lines).strip()
    if _dockerfile_score(no_fence_text) > 0:
        return no_fence_text + "\n"

    instruction_prefixes = (
        "FROM ", "RUN ", "COPY ", "ADD ", "WORKDIR ", "CMD ", "ENTRYPOINT ",
        "EXPOSE ", "ENV ", "ARG ", "USER ", "LABEL ", "HEALTHCHECK ",
        "SHELL ", "STOPSIGNAL ", "VOLUME ", "ONBUILD ",
    )
    lines = no_fence_text.splitlines()
    for index, line in enumerate(lines):
        if line.strip().upper().startswith(instruction_prefixes):
            candidate = "\n".join(lines[index:]).strip()
            if candidate:
                return candidate + "\n"

    return no_fence_text + "\n"


def _sanitize_generated_workflow_yaml(raw_content: str) -> str:
    text = (raw_content or "").replace("\r\n", "\n").strip()
    if not text:
        return ""

    fenced_blocks = _extract_fenced_blocks(text)
    workflow_candidates: list[tuple[int, str]] = []
    for language, block in fenced_blocks:
        if language in {"yaml", "yml", "", "text", "plaintext", "github-actions"}:
            score = _github_actions_score(block)
            if score > 0:
                workflow_candidates.append((score, block))

    if workflow_candidates:
        best_block = max(workflow_candidates, key=lambda item: item[0])[1]
        return best_block.strip() + "\n"

    no_fence_lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
    no_fence_text = "\n".join(no_fence_lines).strip()
    if _github_actions_score(no_fence_text) > 0:
        return no_fence_text + "\n"

    return no_fence_text + "\n"


def _tail_lines(lines: list[str], max_lines: int = 60) -> list[str]:
    if len(lines) <= max_lines:
        return lines
    return lines[-max_lines:]


def _summarize_pipeline_failure(execution_result: Dict[str, Any]) -> str:
    docker_result = execution_result.get("docker_build") or {}
    act_result = execution_result.get("act") or {}

    summary_lines = [
        "Previous local pipeline execution failed.",
        f"docker build exit_code={docker_result.get('exit_code')} timed_out={docker_result.get('timed_out')}",
        f"act exit_code={act_result.get('exit_code')} timed_out={act_result.get('timed_out')}",
        "Recent docker log lines:",
    ]

    docker_logs = [entry.get("line", "") for entry in docker_result.get("logs", []) if isinstance(entry, dict)]
    for line in _tail_lines(docker_logs, max_lines=20):
        summary_lines.append(f"- {line}")

    summary_lines.append("Recent act log lines:")
    act_logs = [entry.get("line", "") for entry in act_result.get("logs", []) if isinstance(entry, dict)]
    for line in _tail_lines(act_logs, max_lines=20):
        summary_lines.append(f"- {line}")

    return "\n".join(summary_lines)


def _copy_repo_source_to_workspace(repository_path: str, workspace_path: Path, github_url: str = "") -> Dict[str, Any]:
    if not github_url and isinstance(repository_path, str):
        repo_path_candidate = repository_path.strip()
        if repo_path_candidate.startswith("http://") or repo_path_candidate.startswith("https://"):
            github_url = repo_path_candidate

    if github_url:
        clone = subprocess.run(
            ["git", "clone", "--depth", "1", github_url, str(workspace_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if clone.returncode == 0:
            copied_entries = len(list(workspace_path.iterdir()))
            return {
                "copied": True,
                "source": github_url,
                "destination": str(workspace_path),
                "copied_entries": copied_entries,
                "mode": "git-clone",
            }

        clone_error = (clone.stderr or clone.stdout or "git clone failed").strip()
        return {
            "copied": False,
            "reason": f"Failed to clone GitHub repository: {clone_error}",
            "source": github_url,
            "destination": str(workspace_path),
            "mode": "git-clone",
        }

    if not repository_path:
        return {"copied": False, "reason": "No repository path provided"}

    source_path = Path(repository_path)
    if not source_path.exists() or not source_path.is_dir():
        return {
            "copied": False,
            "reason": f"Repository path not found or not a directory: {repository_path}",
        }

    ignore_dirs = {
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".venv",
        "venv",
        "node_modules",
    }

    copied_entries = 0
    for child in source_path.iterdir():
        if child.name in ignore_dirs:
            continue

        target = workspace_path / child.name
        if child.is_dir():
            shutil.copytree(child, target, dirs_exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child, target)
        copied_entries += 1

    return {
        "copied": True,
        "source": str(source_path),
        "destination": str(workspace_path),
        "copied_entries": copied_entries,
    }


def _stream_command_with_timeout(command: list[str], cwd: str, timeout_seconds: int, step_name: str) -> Dict[str, Any]:
    """Run a command with real-time stdout/stderr streaming and hard timeout."""
    print(f"[Orchestrator] [{step_name}] Running: {' '.join(command)}")

    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    output_queue: queue.Queue[tuple[str, str]] = queue.Queue()
    collected_logs = []

    def _reader(pipe, stream_name: str) -> None:
        if pipe is None:
            return
        try:
            for line in iter(pipe.readline, ""):
                if line:
                    output_queue.put((stream_name, line.rstrip("\n")))
        except Exception as exc:
            output_queue.put(("stderr", f"[{step_name}] log reader error ({stream_name}): {exc}"))
        finally:
            try:
                pipe.close()
            except Exception:
                pass

    stdout_thread = threading.Thread(target=_reader, args=(process.stdout, "stdout"), daemon=True)
    stderr_thread = threading.Thread(target=_reader, args=(process.stderr, "stderr"), daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    start = time.monotonic()
    timed_out = False

    while True:
        if (time.monotonic() - start) > timeout_seconds:
            timed_out = True
            process.kill()
            break

        try:
            stream_name, line = output_queue.get(timeout=0.1)
            print(f"[Orchestrator] [{step_name}][{stream_name}] {line}")
            if len(collected_logs) < 2000:
                collected_logs.append({"stream": stream_name, "line": line})
        except queue.Empty:
            pass

        if process.poll() is not None and output_queue.empty() and not stdout_thread.is_alive() and not stderr_thread.is_alive():
            break

    # Drain any residual buffered lines.
    while True:
        try:
            stream_name, line = output_queue.get_nowait()
            print(f"[Orchestrator] [{step_name}][{stream_name}] {line}")
            if len(collected_logs) < 2000:
                collected_logs.append({"stream": stream_name, "line": line})
        except queue.Empty:
            break

    exit_code = process.wait()
    if timed_out:
        print(f"[Orchestrator] [{step_name}] Timed out after {timeout_seconds}s")

    return {
        "step": step_name,
        "command": command,
        "cwd": cwd,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "logs": collected_logs,
        "success": (not timed_out and exit_code == 0),
    }


def _execute_generated_pipeline(agent_outputs: Dict[str, Any], repository_path: str, github_url: str = "") -> Dict[str, Any]:
    """Build and run generated CI/CD artifacts in a temp workspace."""
    docker_agent = agent_outputs.get("docker-agent") or {}
    cicd_agent = agent_outputs.get("cicd-agent") or {}

    if docker_agent.get("status") != "success" or cicd_agent.get("status") != "success":
        return {
            "status": "skipped",
            "message": "Skipped pipeline execution because docker-agent or cicd-agent did not succeed.",
            "should_self_repair": False,
        }

    dockerfile_content = _extract_generated_dockerfile(agent_outputs)
    ci_workflow_content = _extract_generated_cicd_workflow(agent_outputs)

    # Keep downstream consumers (UI/JSON output) aligned with sanitized artifacts.
    docker_data = docker_agent.get("data") if isinstance(docker_agent, dict) else None
    if isinstance(docker_data, dict):
        configuration = docker_data.get("configuration")
        if isinstance(configuration, dict) and dockerfile_content:
            configuration["dockerfile_content"] = dockerfile_content

    cicd_data = cicd_agent.get("data") if isinstance(cicd_agent, dict) else None
    if isinstance(cicd_data, dict) and ci_workflow_content:
        cicd_data["workflow_yaml"] = ci_workflow_content

    if not dockerfile_content or not ci_workflow_content:
        return {
            "status": "error",
            "message": "Generated Dockerfile or CI workflow is missing.",
            "should_self_repair": True,
            "docker_build": {"exit_code": -1, "timed_out": False},
            "act": {"exit_code": -1, "timed_out": False},
        }

    temp_workspace = tempfile.mkdtemp(prefix="orchestrator-exec-")
    workspace_path = Path(temp_workspace)

    try:
        copy_result = _copy_repo_source_to_workspace(repository_path, workspace_path, github_url=github_url)
        print(f"[Orchestrator] [workspace] Copy result: {copy_result}")
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to copy repository source into workspace: {str(e)}",
            "should_self_repair": True,
            "workspace": str(workspace_path),
            "docker_build": {"exit_code": -1, "timed_out": False, "logs": []},
            "act": {"exit_code": -1, "timed_out": False, "logs": []},
        }

    if not copy_result.get("copied"):
        return {
            "status": "error",
            "message": f"Failed to prepare execution workspace: {copy_result.get('reason', 'unknown reason')}",
            "should_self_repair": True,
            "workspace": str(workspace_path),
            "repo_copy": copy_result,
            "docker_build": {"exit_code": -1, "timed_out": False, "logs": []},
            "act": {"exit_code": -1, "timed_out": False, "logs": []},
        }

    dockerfile_path = workspace_path / "Dockerfile"
    workflow_path = workspace_path / ".github" / "workflows" / "ci.yml"
    workflow_path.parent.mkdir(parents=True, exist_ok=True)

    dockerfile_path.write_text(dockerfile_content, encoding="utf-8")
    workflow_path.write_text(ci_workflow_content, encoding="utf-8")

    image_name = f"orchestrator-generated-{int(time.time())}"

    docker_build_result = _stream_command_with_timeout(
        command=["docker", "build", "-t", f"{image_name}:latest", "."],
        cwd=str(workspace_path),
        timeout_seconds=600,  # Increased from 300s to 600s (10 minutes) for large base images
        step_name="docker-build",
    )

    act_result = _stream_command_with_timeout(
        command=["act", "-W", ".github/workflows/ci.yml"],
        cwd=str(workspace_path),
        timeout_seconds=600,
        step_name="act-run",
    )

    pipeline_success = docker_build_result.get("success") and act_result.get("success")
    should_self_repair = not pipeline_success

    return {
        "status": "success" if pipeline_success else "error",
        "message": "Local pipeline execution completed" if pipeline_success else "Local pipeline execution failed",
        "workspace": str(workspace_path),
        "repo_copy": copy_result,
        "image_name": image_name,
        "docker_build": docker_build_result,
        "act": act_result,
        "should_self_repair": should_self_repair,
    }


def _execute_pipeline_with_self_repair(
    agent_outputs: Dict[str, Any],
    user_prompt: str,
    repository_path: str,
    github_url: str,
    repo_context: Dict[str, Any],
    max_self_repair_retries: int = 2,
) -> Dict[str, Any]:
    """Execute generated pipeline and retry with self-repair if local execution fails."""
    attempts = []

    execution_result = _execute_generated_pipeline(
        agent_outputs,
        repository_path=repository_path,
        github_url=github_url,
    )
    attempts.append({"attempt_number": 1, "kind": "initial", "result": copy.deepcopy(execution_result)})

    if not execution_result.get("should_self_repair"):
        execution_result["attempts"] = attempts
        execution_result["repair_retry_count"] = 0
        execution_result["max_self_repair_retries"] = max_self_repair_retries
        return execution_result

    for retry_idx in range(1, max_self_repair_retries + 1):
        failure_summary = _summarize_pipeline_failure(execution_result)
        repair_prompt = (
            f"{user_prompt}\n\n"
            f"Self-repair attempt {retry_idx}: fix generated Dockerfile and CI workflow so local execution succeeds.\n"
            f"{failure_summary}"
        )

        print(f"[Orchestrator] Triggering self-repair attempt {retry_idx}/{max_self_repair_retries}")
        repaired_docker = _execute_docker_agent(repair_prompt, repository_path, repo_context)
        repaired_cicd = _execute_cicd_agent(repair_prompt, repository_path, repo_context)

        if repaired_docker.get("status") == "success":
            agent_outputs["docker-agent"] = repaired_docker
        if repaired_cicd.get("status") == "success":
            agent_outputs["cicd-agent"] = repaired_cicd

        execution_result = _execute_generated_pipeline(
            agent_outputs,
            repository_path=repository_path,
            github_url=github_url,
        )
        attempts.append(
            {
                "attempt_number": retry_idx + 1,
                "kind": "self_repair",
                "repair_prompt": repair_prompt,
                "result": copy.deepcopy(execution_result),
            }
        )

        if execution_result.get("status") == "success":
            execution_result["attempts"] = attempts
            execution_result["repair_retry_count"] = retry_idx
            execution_result["max_self_repair_retries"] = max_self_repair_retries
            return execution_result

    execution_result["attempts"] = attempts
    execution_result["repair_retry_count"] = max_self_repair_retries
    execution_result["max_self_repair_retries"] = max_self_repair_retries
    return execution_result
