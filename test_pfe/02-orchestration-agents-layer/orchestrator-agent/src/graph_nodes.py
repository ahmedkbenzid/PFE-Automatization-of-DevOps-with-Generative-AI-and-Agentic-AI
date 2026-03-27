"""
LangGraph Node Functions for the Orchestrator.

Each function represents a node in the orchestration graph.
Nodes receive the current state and return updates to be merged.
"""

import json
import os
import subprocess
import sys
import time
from typing import Any, Dict

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
        raise ValueError("GROQ_API_KEY is missing from environment. Cannot initialize orchestrator.")

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
            "local": "local",
            "prompt-only": "none"
        }.get(repo_context.analysis_mode, "none")

        # Print error details if analysis failed
        if repo_context.error:
            print(f"[Orchestrator] ⚠️  Analysis error: {repo_context.error}")

        context_dict: RepoContextDict = {
            "is_available": is_available,
            "source": source,
            "path": repo_path or "",
            "languages": repo_context.languages,
            "build_system": repo_context.build_system,
            "package_managers": repo_context.package_managers,
            "frameworks": repo_context.frameworks,
            "has_dockerfile": repo_context.has_dockerfile,
            "has_docker_compose": repo_context.has_docker_compose,
            "has_ci_workflows": repo_context.has_github_actions,
            "existing_workflows": repo_context.ci_workflows,
            "config_files": {},
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
            }
        }


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
    """
    global _config

    if _config is None:
        initialize_components()

    target_agents = state.get("target_agents", [])
    user_prompt = state.get("user_prompt", "")
    repo_context = state.get("repo_context", {})
    repository_path = state.get("repository_path") or _config.DEFAULT_REPOSITORY_PATH

    agent_outputs = dict(state.get("agent_outputs", {}))
    errors = list(state.get("errors", []))

    print("[Orchestrator] Dispatching to Target Agents...")

    for agent in target_agents:
        if agent == "cicd-agent":
            result = _execute_cicd_agent(user_prompt, repository_path, repo_context)
            agent_outputs["cicd-agent"] = result
            if result.get("status") == "error":
                errors.append(f"cicd-agent failed: {result.get('message', 'Unknown error')}")

        elif agent == "docker-agent":
            result = _execute_docker_agent(user_prompt, repository_path, repo_context)
            agent_outputs["docker-agent"] = result
            if result.get("status") == "error":
                errors.append(f"docker-agent failed: {result.get('message', 'Unknown error')}")

        elif agent == "iac-agent":
            result = _execute_iac_agent(user_prompt, repository_path, repo_context)
            agent_outputs["iac-agent"] = result
            if result.get("status") == "error":
                errors.append(f"iac-agent failed: {result.get('message', 'Unknown error')}")

        else:
            print(f"[Orchestrator] Agent '{agent}' is not yet integrated. Skipping execution.")
            agent_outputs[agent] = {"status": "skipped", "message": "Not integrated"}

    return {
        "agent_outputs": agent_outputs,
        "errors": errors,
        "status": "completed",
    }


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
) -> Dict[str, Any]:
    """
    Invoke a Python agent as a subprocess and collect results.

    Args:
        timeout: Maximum seconds to wait for agent completion (default: 120s)
    """
    agent_path = _resolve_agent_path(agent_folder_name)
    if not os.path.exists(agent_path):
        raise FileNotFoundError(f"Could not find {agent_name} at: {agent_path}")

    try:
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
            env=env,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{agent_name} timed out after {timeout}s. Agent may be overloaded or stuck.")

    # Debug: print stderr if there's an error
    if completed.returncode != 0:
        error_msg = completed.stderr.strip() if completed.stderr else completed.stdout.strip()
        if not error_msg:
            error_msg = f"Unknown {agent_name} error (exit code {completed.returncode})"
        raise RuntimeError(error_msg)

    # Parse result from stdout
    for line in (completed.stdout or "").splitlines():
        if line.startswith(result_prefix):
            try:
                return json.loads(line[len(result_prefix):])
            except json.JSONDecodeError as e:
                raise RuntimeError(f"{agent_name} returned invalid JSON: {str(e)}")

    raise RuntimeError(f"{agent_name} returned no structured result. Output: {completed.stdout}")


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
            timeout=120,
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
    print(f"[Orchestrator] -> Invoking {agent} locally (timeout: 120s)")

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

        docker_result = _invoke_python_agent(
            agent_name="docker-agent",
            agent_folder_name="docker-agent",
            run_code=run_code,
            args=[user_prompt, repo_path or "", repo_context_json],
            result_prefix="DOCKER_RESULT_JSON=",
            timeout=120,
        )

        print(f"[Orchestrator] <- Result received from {agent}")
        return {"status": "success", "data": docker_result}

    except Exception as e:
        print(f"[Orchestrator] Error executing {agent}: {str(e)}")
        return {"status": "error", "message": str(e)}


def _execute_iac_agent(
    user_prompt: str,
    repo_path: str,
    repo_context: Dict[str, Any]
) -> Dict[str, Any]:
    """Execute the IAC (Terraform) agent."""
    agent = "iac-agent"
    print(f"[Orchestrator] -> Invoking {agent} locally")

    try:
        repo_context_json = json.dumps(repo_context) if repo_context.get("is_available") else "{}"

        run_code = (
            "import json,sys; "
            "from dataclasses import asdict; "
            "from src.pipeline import run_pipeline; "
            "repo_ctx=json.loads(sys.argv[3]) if sys.argv[3] != '{}' else None; "
            "result=run_pipeline(sys.argv[1], sys.argv[2], repo_ctx, False); "
            "print('IAC_RESULT_JSON=' + json.dumps(asdict(result), default=str))"
        )

        iac_result = _invoke_python_agent(
            agent_name="iac-agent",
            agent_folder_name="iac-agent",
            run_code=run_code,
            args=[user_prompt, repo_path or "", repo_context_json],
            result_prefix="IAC_RESULT_JSON=",
        )

        print(f"[Orchestrator] <- Result received from {agent}")
        return {"status": "success", "data": iac_result}

    except Exception as e:
        print(f"[Orchestrator] Error executing {agent}: {str(e)}")
        return {"status": "error", "message": str(e)}
