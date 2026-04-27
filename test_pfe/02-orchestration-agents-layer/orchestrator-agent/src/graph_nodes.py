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
from typing import Any, Dict, List, Optional, Mapping, cast
from pathlib import Path

from .graph_state import OrchestratorState, RepoContextDict
from .config import OrchestratorConfig
from .guardrails import Guardrails
from .intent_router import IntentRouter
from .repo_analyzer import RepoAnalyzer, RepoContext


# Initialize shared components (will be set up by the graph builder)
_config: Optional[OrchestratorConfig] = None
_guardrails: Optional[Guardrails] = None
_router: Optional[IntentRouter] = None
_repo_analyzer: Optional[RepoAnalyzer] = None


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
    assert _config is not None
    return _config


def cleanup_repo_analyzer():
    """Cleanup temporary directories from repo analyzer."""
    global _repo_analyzer
    if _repo_analyzer:
        _repo_analyzer.cleanup()


def _calculate_complexity(user_prompt: str, repo_context: Optional[Mapping[str, Any]] = None) -> int:
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


def _should_use_planner(
    user_prompt: str,
    repo_context: Optional[Mapping[str, Any]],
    enabled: bool,
    threshold: int,
    skip_planner: bool,
) -> bool:
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


def _invoke_planner(
    user_prompt: str,
    repo_context: Optional[Mapping[str, Any]],
    max_retries: int = 2,
) -> Dict[str, Any]:
    """Invoke planner-agent subprocess."""
    print("[Orchestrator] 🧠 Complex request detected - Invoking Planner Agent...")
    planner_root = Path(__file__).parent.parent.parent / "planner-agent"
    planner_path = planner_root / "src" / "pipeline.py"

    if not planner_path.exists():
        return {"status": "error", "message": f"Planner not available at {planner_path}"}

    last_error = None
    for attempt in range(max_retries + 1):
        args_file_path: str | None = None
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

    # Any planner-generated plan should pause for review unless an approved
    # execution plan is already being replayed.
    if not state.get("approved_execution_plan"):
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
    exec_updates = agent_execution_node(cast(OrchestratorState, merged_state))
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

    # Ensure k8s generation has a Docker image source when possible.
    repo_has_docker_image = False
    if isinstance(repo_context, dict):
        docker_output_ctx = repo_context.get("docker_output")
        if isinstance(docker_output_ctx, dict) and docker_output_ctx.get("image_name"):
            repo_has_docker_image = True
        elif repo_context.get("docker_image"):
            repo_has_docker_image = True

    existing_docker_success = (
        isinstance(agent_outputs.get("docker-agent"), dict)
        and (agent_outputs.get("docker-agent") or {}).get("status") == "success"
    )

    should_bootstrap_docker_for_k8s = (
        "k8s-agent" in target_agents
        and "docker-agent" not in target_agents
        and not repo_has_docker_image
        and not existing_docker_success
    )

    if should_bootstrap_docker_for_k8s:
        print("[Orchestrator] k8s-agent requested without docker image context; auto-adding docker-agent dependency")
        target_agents = ["docker-agent", *target_agents]

        if isinstance(approved_plan, dict):
            execution_order = approved_plan.get("execution_order")
            if isinstance(execution_order, list):
                flat_agents = set()
                for step in execution_order:
                    if isinstance(step, list):
                        flat_agents.update(agent for agent in step if isinstance(agent, str))
                    elif isinstance(step, str):
                        flat_agents.add(step)

                if "docker-agent" not in flat_agents:
                    approved_plan["execution_order"] = ["docker-agent", *execution_order]

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
                parallel_agents = [agent for agent in step if isinstance(agent, str)]

                # If IaC and CI/CD are grouped in parallel, run IaC first so CI/CD can
                # honor the no-Terraform-runtime rule when IaC artifacts already exist.
                if "iac-agent" in parallel_agents and "cicd-agent" in parallel_agents and not enhanced_repo_context.get("iac_output_available"):
                    print(f"[Orchestrator] Step {step_idx}: Running iac-agent before parallel group to enrich cicd-agent context")
                    iac_result = _execute_single_agent("iac-agent", user_prompt, agent_repo_path, enhanced_repo_context)
                    agent_outputs["iac-agent"] = iac_result
                    if iac_result.get("status") == "error":
                        errors.append(f"iac-agent failed: {iac_result.get('message', 'Unknown error')}")
                    else:
                        print("[Orchestrator] IaC agent succeeded - CI/CD workflow will avoid Terraform runtime commands by default")
                        enhanced_repo_context["iac_output_available"] = True

                    parallel_agents = [agent for agent in parallel_agents if agent != "iac-agent"]

                if not parallel_agents:
                    continue

                print(f"[Orchestrator] Step {step_idx}: Parallel execution of {len(parallel_agents)} agents")
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=len(parallel_agents)) as executor:
                    futures = {}
                    for agent in parallel_agents:
                        future = executor.submit(_execute_single_agent, agent, user_prompt, agent_repo_path, enhanced_repo_context)
                        futures[future] = agent
                    
                    for future in concurrent.futures.as_completed(futures):
                        agent = futures[future]
                        try:
                            result = future.result()
                            agent_outputs[agent] = result
                            if result.get("status") == "error":
                                errors.append(f"{agent} failed: {result.get('message', 'Unknown error')}")
                            if agent == "docker-agent" and result.get("status") == "success":
                                enhanced_repo_context["dockerfile_built_successfully"] = True
                                _inject_docker_output_into_repo_context(enhanced_repo_context, result)
                            if agent == "iac-agent" and result.get("status") == "success":
                                print("[Orchestrator] IaC agent succeeded - CI/CD workflow will avoid Terraform runtime commands by default")
                                enhanced_repo_context["iac_output_available"] = True
                        except Exception as e:
                            errors.append(f"{agent} execution error: {str(e)}")
            else:
                # Sequential execution
                print(f"[Orchestrator] Step {step_idx}: Executing {step}")
                result = _execute_single_agent(step, user_prompt, agent_repo_path, enhanced_repo_context)
                agent_outputs[step] = result
                if result.get("status") == "error":
                    errors.append(f"{step} failed: {result.get('message', 'Unknown error')}")
                
                # FIXED: Set flag if docker-agent succeeds, so cicd-agent knows to build image in workflow
                if step == "docker-agent" and result.get("status") == "success":
                    print(f"[Orchestrator] Docker agent succeeded - workflow will build image during execution")
                    enhanced_repo_context["dockerfile_built_successfully"] = True
                    _inject_docker_output_into_repo_context(enhanced_repo_context, result)
                if step == "iac-agent" and result.get("status") == "success":
                    print("[Orchestrator] IaC agent succeeded - CI/CD workflow will avoid Terraform runtime commands by default")
                    enhanced_repo_context["iac_output_available"] = True
    else:
        # Default execution (no plan) - execute in deterministic order
        ordered_agents = sorted(target_agents, key=_execution_priority)
        for agent in ordered_agents:
            result = _execute_single_agent(agent, user_prompt, agent_repo_path, enhanced_repo_context)
            agent_outputs[agent] = result
            if result.get("status") == "error":
                errors.append(f"{agent} failed: {result.get('message', 'Unknown error')}")
            
            # FIXED: Set flag if docker-agent succeeds, so cicd-agent knows to build image in workflow
            if agent == "docker-agent" and result.get("status") == "success":
                print(f"[Orchestrator] Docker agent succeeded - workflow will build image during execution")
                enhanced_repo_context["dockerfile_built_successfully"] = True
                _inject_docker_output_into_repo_context(enhanced_repo_context, result)
            if agent == "iac-agent" and result.get("status") == "success":
                print("[Orchestrator] IaC agent succeeded - CI/CD workflow will avoid Terraform runtime commands by default")
                enhanced_repo_context["iac_output_available"] = True

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
    elif agent == "k8s-agent":
        return _execute_k8s_agent(user_prompt, repository_path, repo_context)
    elif agent == "iac-agent":
        return _execute_iac_agent(user_prompt, repository_path, repo_context)
    else:
        print(f"[Orchestrator] Agent '{agent}' is not yet integrated. Skipping execution.")
        return {"status": "skipped", "message": "Not integrated"}


def _execution_priority(agent: str) -> int:
    """Execution priority for direct-path agent orchestration."""
    priorities = {
        "docker-agent": 1,
        "k8s-agent": 2,
        "iac-agent": 3,
        "cicd-agent": 4,
    }
    return priorities.get(agent, 99)


def _inject_docker_output_into_repo_context(repo_context: Dict[str, Any], docker_result: Dict[str, Any]) -> None:
    """Persist docker-agent output in shared context for downstream agents like k8s-agent."""
    if not isinstance(repo_context, dict) or not isinstance(docker_result, dict):
        return

    docker_data = docker_result.get("data") if isinstance(docker_result.get("data"), dict) else {}
    configuration = docker_data.get("configuration") if isinstance(docker_data.get("configuration"), dict) else {}
    metadata = configuration.get("metadata") if isinstance(configuration.get("metadata"), dict) else {}

    image_name = (
        metadata.get("image_name")
        or configuration.get("image_name")
        or metadata.get("repository")
        or configuration.get("repository")
    )

    repo_context["docker-agent"] = docker_result
    repo_context["docker_output"] = {
        "image_name": image_name,
        "configuration": configuration,
    }
    if image_name:
        repo_context["docker_image"] = image_name


def _infer_workflow_filename_for_pr(agent_outputs: Dict[str, Any]) -> str:
    cicd_output = (agent_outputs.get("cicd-agent") or {}).get("data") or {}
    lock_file = cicd_output.get("lock_file") if isinstance(cicd_output, dict) else None

    candidate = ""
    if isinstance(lock_file, dict):
        candidate = str(lock_file.get("workflow_name") or "").strip()

    if not candidate:
        candidate = "ci-cd"

    candidate = os.path.basename(candidate.replace("\\", "/"))
    candidate = re.sub(r"[^A-Za-z0-9._-]", "-", candidate).strip("-._")
    if not candidate:
        candidate = "ci-cd"
    if not candidate.endswith((".yml", ".yaml")):
        candidate = f"{candidate}.yml"
    return candidate


def _collect_artifacts_for_pr(agent_outputs: Dict[str, Any]) -> List[Dict[str, str]]:
    files: List[Dict[str, str]] = []

    dockerfile_content = _extract_generated_dockerfile(agent_outputs).strip()
    if dockerfile_content:
        files.append({"path": "Dockerfile", "content": dockerfile_content + "\n"})

    workflow_yaml = _extract_generated_cicd_workflow(agent_outputs).strip()
    if workflow_yaml:
        workflow_name = _infer_workflow_filename_for_pr(agent_outputs)
        files.append({"path": f".github/workflows/{workflow_name}", "content": workflow_yaml + "\n"})

    iac_data = (agent_outputs.get("iac-agent") or {}).get("data") or {}
    terraform_config = iac_data.get("terraform_config") if isinstance(iac_data, dict) else {}
    if isinstance(terraform_config, dict):
        terraform_mapping = {
            "main_tf": "terraform/main.tf",
            "variables_tf": "terraform/variables.tf",
            "outputs_tf": "terraform/outputs.tf",
            "providers_tf": "terraform/providers.tf",
        }
        for key, path in terraform_mapping.items():
            content = terraform_config.get(key)
            if content is None:
                continue
            text = str(content).strip()
            if not text:
                continue
            files.append({"path": path, "content": text + "\n"})

    k8s_data = (agent_outputs.get("k8s-agent") or {}).get("data") or {}
    k8s_manifests = k8s_data.get("k8s_manifests") if isinstance(k8s_data, dict) else {}
    if isinstance(k8s_manifests, dict):
        k8s_mapping = {
            "namespace_yaml": "kubernetes/namespace.yaml",
            "configmap_yaml": "kubernetes/configmap.yaml",
            "secret_yaml": "kubernetes/secret.yaml",
            "deployment_yaml": "kubernetes/deployment.yaml",
            "service_yaml": "kubernetes/service.yaml",
            "ingress_yaml": "kubernetes/ingress.yaml",
            "hpa_yaml": "kubernetes/hpa.yaml",
        }
        for key, path in k8s_mapping.items():
            content = k8s_manifests.get(key)
            if content is None:
                continue
            text = str(content).strip()
            if not text:
                continue
            files.append({"path": path, "content": text + "\n"})

    return files


def _build_pr_body_with_artifacts(pr_body: str, artifact_files: List[Dict[str, str]]) -> str:
    artifact_paths = [file_entry.get("path", "") for file_entry in artifact_files if file_entry.get("path")]
    if not artifact_paths:
        return pr_body

    lines = [pr_body.strip(), "", "### Generated Artifacts", ""]
    for path in artifact_paths:
        lines.append(f"- {path}")
    return "\n".join(lines).strip() + "\n"


def _scan_artifacts_for_hardcoded_secrets(artifact_files: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Best-effort scan for hardcoded credentials before publishing artifacts."""
    secret_patterns = [
        (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "GitHub personal access token"),
        (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key ID"),
        (re.compile(r"\bASIA[0-9A-Z]{16}\b"), "AWS temporary access key ID"),
        (re.compile(r"\bxox[pboa]-[A-Za-z0-9-]{10,}\b"), "Slack token"),
        (
            re.compile(
                r"(?i)\b(?:api[_-]?key|token|secret|password|private[_-]?key)\b\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{12,}[\"']?"
            ),
            "hardcoded credential assignment",
        ),
    ]

    findings: List[Dict[str, Any]] = []
    safe_markers = ["your_token", "example", "changeme", "<token>", "<secret>"]

    for artifact in artifact_files:
        path = str(artifact.get("path", "") or "")
        content = str(artifact.get("content", "") or "")
        if not path or not content:
            continue

        for line_number, raw_line in enumerate(content.splitlines(), 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            lowered = line.lower()
            if "${{ secrets." in lowered or "${{ github.token" in lowered:
                continue
            if any(marker in lowered for marker in safe_markers):
                continue

            for pattern, label in secret_patterns:
                if pattern.search(line):
                    findings.append(
                        {
                            "path": path,
                            "line": line_number,
                            "severity": "critical",
                            "description": f"Potential {label} detected. Use secure secret references instead.",
                        }
                    )

    return findings


def create_pr_node(state: OrchestratorState) -> Dict[str, Any]:
    """
    Create a pull request with generated artifacts (optional, user-triggered).

    This node creates a PR if the user requested it via --create-pr flag.
    It uses the GitHub MCP client for PR creation with fallback to PyGithub.
    """
    from .github_manager import GitHubMCPClient, GitHubURLParser

    # Check if PR creation was requested
    create_pr = state.get("create_pr", False)
    if not create_pr:
        print("[Orchestrator] PR creation skipped (--create-pr not specified)")
        return {"pr_details": None}

    # Extract PR parameters
    github_url = state.get("github_url", "")
    repo_context = state.get("repo_context") or {}
    if not github_url and isinstance(repo_context, dict):
        ctx_url = repo_context.get("github_url") or repo_context.get("path")
        if isinstance(ctx_url, str):
            github_url = ctx_url

    requested_branch = (state.get("branch_name", "") or "devops/auto-generated").replace("refs/heads/", "").strip()
    branch_name = re.sub(r"[^A-Za-z0-9._/\-]", "-", requested_branch).strip("/.-") or "devops/auto-generated"
    pr_title = state.get("pr_title", "Auto-generated PR from Orchestrator")
    pr_body = state.get("pr_body", "Generated by Orchestrator Agent")

    if not github_url:
        error_msg = "Missing github_url for PR creation"
        print(f"[Orchestrator] ERROR: {error_msg}")
        return {
            "pr_details": {
                "success": False,
                "error": error_msg,
            }
        }

    artifact_files = _collect_artifacts_for_pr(state.get("agent_outputs", {}))
    if not artifact_files:
        error_msg = "No generated artifacts found to publish before PR creation"
        print(f"[Orchestrator] ERROR: {error_msg}")
        return {
            "pr_details": {
                "success": False,
                "error": error_msg,
            }
        }

    secret_findings = _scan_artifacts_for_hardcoded_secrets(artifact_files)
    if secret_findings:
        error_msg = "Potential hardcoded secrets detected in generated artifacts. Aborting publish/PR creation."
        print(f"[Orchestrator] ERROR: {error_msg}")
        return {
            "pr_details": {
                "success": False,
                "error": error_msg,
                "security_findings": secret_findings,
            }
        }

    print(f"[Orchestrator] Publishing {len(artifact_files)} artifact(s) and creating Pull Request...")

    try:
        repo_info = GitHubURLParser.parse(github_url)
        owner = repo_info.owner
        repo = repo_info.repo

        config = get_config()
        token = config.GITHUB_TOKEN
        if not token:
            raise ValueError("GITHUB_TOKEN not configured")

        client = GitHubMCPClient(
            token=token,
            server_command=config.MCP_GITHUB_SERVER_COMMAND,
            server_args=config.MCP_GITHUB_SERVER_ARGS,
            call_timeout=config.MCP_GITHUB_CALL_TIMEOUT,
        )

        with client:
            base_branch = client.get_default_branch(owner=owner, repo=repo, fallback=repo_info.branch or "main")

            branch_result = client.ensure_branch(
                owner=owner,
                repo=repo,
                branch=branch_name,
                base_branch=base_branch,
            )
            if not branch_result.get("success"):
                return {
                    "pr_details": {
                        "success": False,
                        "error": f"Failed to ensure branch '{branch_name}': {branch_result.get('error', 'Unknown error')}",
                        "branch_result": branch_result,
                    }
                }

            publish_result = client.upsert_files(
                owner=owner,
                repo=repo,
                branch=branch_name,
                files=artifact_files,
                commit_message="chore(devops): apply orchestrator-generated artifacts",
            )
            if not publish_result.get("success"):
                return {
                    "pr_details": {
                        "success": False,
                        "error": f"Failed to publish artifacts to '{branch_name}': {publish_result.get('error', 'Unknown error')}",
                        "publish_result": publish_result,
                    }
                }

            no_artifact_changes = not publish_result.get("has_changes", True)
            if no_artifact_changes:
                print(
                    "[Orchestrator] No new artifact file changes detected on target branch; "
                    "attempting PR creation in case an existing branch PR already exists."
                )

            pr_body_with_artifacts = _build_pr_body_with_artifacts(pr_body, artifact_files)
            pr_result = client.create_pull_request(
                owner=owner,
                repo=repo,
                title=pr_title,
                body=pr_body_with_artifacts,
                head=branch_name,
                base=base_branch,
            )

        pr_error_text = str(pr_result.get("error", ""))
        if (not pr_result.get("success")) and "already exists" in pr_error_text.lower():
            pr_result = {
                "success": True,
                "message": pr_error_text,
                "head": branch_name,
                "base": base_branch,
                "existing_pr": True,
            }
        elif (not pr_result.get("success")) and no_artifact_changes:
            pr_result["error"] = (
                pr_result.get("error")
                or "No artifact changes were published and PR creation did not succeed."
            )

        if pr_result.get("success"):
            print(f"[Orchestrator] PR Ready: {pr_result.get('pr_url') or pr_result.get('message', 'created/updated')}")
        else:
            print(f"[Orchestrator] PR Creation Failed: {pr_result.get('error')}")

        pr_result["published_files"] = [file_entry.get("path", "") for file_entry in artifact_files]
        pr_result["published_file_count"] = len(artifact_files)
        pr_result["branch_name"] = branch_name
        pr_result["base_branch"] = base_branch
        pr_result["branch_result"] = branch_result
        pr_result["publish_result"] = publish_result
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


def _get_int_env(name: str, default: int, minimum: int = 0) -> int:
    """Read a positive integer environment variable with a safe fallback."""
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default

    try:
        value = int(raw)
    except ValueError:
        print(f"[Orchestrator] Invalid integer env {name}={raw!r}; using default {default}.")
        return default

    if value < minimum:
        print(f"[Orchestrator] Env {name}={value} below minimum {minimum}; using default {default}.")
        return default

    return value


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
        timeout: Base timeout in seconds for first attempt (default: 120s)
        max_retries: Number of retry attempts on timeout/failure (default: 2)
    """
    agent_path = _resolve_agent_path(agent_folder_name)
    if not os.path.exists(agent_path):
        raise FileNotFoundError(f"Could not find {agent_name} at: {agent_path}")

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            current_timeout = timeout * (attempt + 1)  # Progressive timeout: base, 2x base, 3x base
            print(
                f"[Orchestrator] Starting {agent_name} attempt {attempt + 1}/{max_retries + 1} "
                f"(timeout: {current_timeout}s)"
            )
            
            if attempt > 0:
                print(f"[Orchestrator] Retrying {agent_name} (attempt {attempt + 1}/{max_retries + 1}, timeout: {current_timeout}s)...")
            
            # Prepare environment with PYTHONPATH
            env = os.environ.copy()
            env["PYTHONPATH"] = agent_path + os.pathsep + os.environ.get("PYTHONPATH", "")
            env["PYTHONIOENCODING"] = "utf-8"
            env.setdefault("PYTHONUNBUFFERED", "1")

            # Persist args to a temp file to avoid Windows command-line length limits.
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json", delete=False) as args_file:
                json.dump(args, args_file)
                args_file_path = args_file.name

            env["ORCH_AGENT_ARGS_FILE"] = args_file_path

            # Keep -c payload short; load args from temp file at runtime.
            safe_run_code = (
                "import json, os, sys; "
                "args_path = os.environ.get('ORCH_AGENT_ARGS_FILE', ''); "
                "args = json.load(open(args_path, 'r', encoding='utf-8')) if args_path else []; "
                "sys.argv = [''] + args; "
                f"{run_code}"
            )

            process = subprocess.Popen(
                [sys.executable, "-u", "-c", safe_run_code],
                cwd=agent_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                bufsize=1,
            )

            output_lines: list[str] = []
            parse_error: str | None = None
            parsed_result: Dict[str, Any] | None = None

            def _read_output_stream() -> None:
                nonlocal parse_error, parsed_result
                if process.stdout is None:
                    return

                while True:
                    line = process.stdout.readline()
                    if line == "" and process.poll() is not None:
                        break
                    if not line:
                        continue

                    stripped = line.rstrip("\n")
                    output_lines.append(stripped)
                    if len(output_lines) > 8000:
                        del output_lines[:2000]

                    if stripped.startswith(result_prefix):
                        print(f"[Orchestrator] [{agent_name}] Structured result received")
                        try:
                            parsed_result = json.loads(stripped[len(result_prefix):])
                        except json.JSONDecodeError as e:
                            parse_error = str(e)
                        continue

                    print(f"[Orchestrator] [{agent_name}] {stripped}")

            reader_thread = threading.Thread(target=_read_output_stream, daemon=True)
            reader_thread.start()

            timed_out = False
            try:
                process.wait(timeout=current_timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                process.kill()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass

            if process.stdout is not None:
                try:
                    process.stdout.close()
                except Exception:
                    pass
            reader_thread.join(timeout=1.0)

            if args_file_path and os.path.exists(args_file_path):
                try:
                    os.remove(args_file_path)
                except OSError:
                    pass

            partial_output = "\n".join(output_lines[-12:]).strip()

            if timed_out:
                if attempt == max_retries:
                    if partial_output:
                        raise RuntimeError(
                            f"{agent_name} timed out after {current_timeout}s (all retries exhausted). "
                            f"Last output:\n{partial_output}"
                        )
                    raise RuntimeError(f"{agent_name} timed out after {current_timeout}s (all retries exhausted)")
                if partial_output:
                    print(
                        f"[Orchestrator] {agent_name} timeout at {current_timeout}s "
                        f"(will retry with longer timeout). Last output:\n{partial_output}"
                    )
                else:
                    print(f"[Orchestrator] {agent_name} timeout at {current_timeout}s (will retry with longer timeout)")
                last_error = f"Timeout at {current_timeout}s"
                continue

            return_code = process.returncode if process.returncode is not None else -1

            if return_code != 0:
                error_msg = partial_output or f"Unknown {agent_name} error (exit code {return_code})"
                if attempt == max_retries:
                    raise RuntimeError(error_msg)
                print(f"[Orchestrator] {agent_name} failed: {error_msg[:100]}... (will retry)")
                last_error = error_msg
                continue

            if parsed_result is not None:
                return parsed_result

            if parse_error:
                if attempt == max_retries:
                    raise RuntimeError(f"{agent_name} returned invalid JSON: {parse_error}")
                print(f"[Orchestrator] {agent_name} JSON parse error (will retry)")
                last_error = parse_error
                continue

            if attempt == max_retries:
                final_output = "\n".join(output_lines)
                raise RuntimeError(f"{agent_name} returned no structured result. Output: {final_output}")
            print(f"[Orchestrator] {agent_name} returned no result (will retry)")
            last_error = "No structured result"

        except Exception as e:
            if args_file_path and os.path.exists(args_file_path):
                try:
                    os.remove(args_file_path)
                except OSError:
                    pass
            if attempt == max_retries:
                raise
            error_text = str(e)
            print(f"[Orchestrator] {agent_name} execution error: {error_text[:180]}... (will retry)")
            last_error = error_text
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
        repo_context_json = json.dumps(repo_context) if isinstance(repo_context, dict) and repo_context else "{}"

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

    build_validation_timeout = _get_int_env("DOCKER_BUILD_VALIDATION_TIMEOUT_SEC", default=300, minimum=30)
    docker_timeout_default = max(240, build_validation_timeout + 90)
    docker_timeout_base = _get_int_env("ORCHESTRATOR_DOCKER_AGENT_TIMEOUT_SEC", default=docker_timeout_default, minimum=60)
    docker_timeout_retries = _get_int_env("ORCHESTRATOR_DOCKER_AGENT_MAX_RETRIES", default=1, minimum=0)

    print(
        f"[Orchestrator] -> Invoking {agent} locally "
        f"(timeout: {docker_timeout_base}s base, retries: {docker_timeout_retries}, "
        f"docker-build-validation: {build_validation_timeout}s)"
    )

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
            timeout=docker_timeout_base,
            max_retries=docker_timeout_retries,
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
                timeout=max(docker_timeout_base, 180),
                max_retries=docker_timeout_retries,
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
    build_validation_timeout = _get_int_env("DOCKER_BUILD_VALIDATION_TIMEOUT_SEC", default=600, minimum=60)

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
        timeout_seconds=build_validation_timeout,
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

    iac_timeout_base = _get_int_env("ORCHESTRATOR_IAC_AGENT_TIMEOUT_SEC", default=180, minimum=60)
    iac_timeout_retries = _get_int_env("ORCHESTRATOR_IAC_AGENT_MAX_RETRIES", default=1, minimum=0)

    print(
        f"[Orchestrator] -> Invoking {agent} locally "
        f"(timeout: {iac_timeout_base}s base, retries: {iac_timeout_retries})"
    )

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
            timeout=iac_timeout_base,
            max_retries=iac_timeout_retries,
        )

        print(f"[Orchestrator] <- Result received from {agent}")
        return {"status": "success", "data": iac_result}

    except Exception as e:
        print(f"[Orchestrator] Error executing {agent}: {str(e)}")
        return {"status": "error", "message": str(e)}


def _execute_k8s_agent(
    user_prompt: str,
    repo_path: str,
    repo_context: Dict[str, Any]
) -> Dict[str, Any]:
    """Execute the Kubernetes manifest agent."""
    agent = "k8s-agent"

    k8s_timeout_base = _get_int_env("ORCHESTRATOR_K8S_AGENT_TIMEOUT_SEC", default=180, minimum=60)
    k8s_timeout_retries = _get_int_env("ORCHESTRATOR_K8S_AGENT_MAX_RETRIES", default=1, minimum=0)

    print(
        f"[Orchestrator] -> Invoking {agent} locally "
        f"(timeout: {k8s_timeout_base}s base, retries: {k8s_timeout_retries})"
    )

    try:
        repo_context_json = json.dumps(repo_context) if repo_context.get("is_available") else "{}"

        run_code = (
            "from dataclasses import asdict; "
            "from src.pipeline import run_pipeline; "
            "user_prompt = args[0]; "
            "repo_path = args[1]; "
            "repo_ctx = __import__('json').loads(args[2]) if args[2] != '{}' else None; "
            "result = run_pipeline(user_prompt, repo_path, False, repo_ctx); "
            "print('K8S_RESULT_JSON=' + __import__('json').dumps(asdict(result), default=str))"
        )

        k8s_result = _invoke_python_agent(
            agent_name="k8s-agent",
            agent_folder_name="k8s-agent",
            run_code=run_code,
            args=[user_prompt, repo_path or "", repo_context_json],
            result_prefix="K8S_RESULT_JSON=",
            timeout=k8s_timeout_base,
            max_retries=k8s_timeout_retries,
        )

        print(f"[Orchestrator] <- Result received from {agent}")
        return {"status": "success", "data": k8s_result}

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


def _stream_command_with_timeout(
    command: list[str],
    cwd: str,
    timeout_seconds: int,
    step_name: str,
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Run a command with real-time stdout/stderr streaming and hard timeout."""
    print(f"[Orchestrator] [{step_name}] Running: {' '.join(command)}")

    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
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

    act_temp_dir = workspace_path / ".act-temp"
    act_temp_dir.mkdir(parents=True, exist_ok=True)
    act_env = os.environ.copy()
    act_env["TEMP"] = str(act_temp_dir)
    act_env["TMP"] = str(act_temp_dir)
    act_env["TMPDIR"] = str(act_temp_dir)
    act_env["RUNNER_TEMP"] = str(act_temp_dir)

    act_command = ["act", "-W", ".github/workflows/ci.yml"]
    act_use_bind = os.getenv("ACT_USE_BIND")
    if (act_use_bind is None and os.name == "nt") or (
        act_use_bind is not None and act_use_bind.strip().lower() in {"1", "true", "yes", "on"}
    ):
        act_command.append("--bind")

    act_result = _stream_command_with_timeout(
        command=act_command,
        cwd=str(workspace_path),
        timeout_seconds=600,
        step_name="act-run",
        env=act_env,
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
