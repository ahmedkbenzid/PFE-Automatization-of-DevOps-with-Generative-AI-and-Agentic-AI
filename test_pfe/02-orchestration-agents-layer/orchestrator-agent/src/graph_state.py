"""
LangGraph State Definition for the Orchestrator.

This module defines the TypedDict that represents the state
flowing through the orchestration graph.
"""

from typing import Any, Dict, List, Optional, TypedDict


class RepoContextDict(TypedDict, total=False):
    """Repository context information"""
    is_available: bool
    source: str  # "local", "github", "none"
    path: str
    languages: List[str]
    build_system: Optional[str]
    package_managers: List[str]
    frameworks: List[str]
    has_dockerfile: bool
    has_docker_compose: bool
    has_ci_workflows: bool
    existing_workflows: List[str]
    config_files: Dict[str, bool]


class OrchestratorState(TypedDict, total=False):
    """
    The state that flows through the LangGraph orchestrator.

    This replaces the manual StateManager class with a declarative
    state definition that LangGraph manages automatically.
    """
    # Input fields (set at the beginning)
    user_prompt: str
    repository_path: Optional[str]
    github_url: Optional[str]

    # Guardrails results
    guardrails_passed: bool
    guardrails_reason: str

    # Repository analysis results
    repo_context: RepoContextDict

    # Routing results
    primary_agent: str
    secondary_agents: List[str]
    routing_reasoning: str
    target_agents: List[str]  # Combined list of agents to execute

    # Agent execution results
    agent_outputs: Dict[str, Any]
    current_agent_index: int  # Track which agent we're executing

    # Final status
    status: str  # "pending", "blocked", "completed", "error"
    errors: List[str]

    # Intent (for backward compatibility)
    user_intent: str


def create_initial_state(
    user_prompt: str,
    repository_path: Optional[str] = None,
    github_url: Optional[str] = None
) -> OrchestratorState:
    """
    Create the initial state for a new orchestration request.

    Args:
        user_prompt: The user's request text
        repository_path: Optional local path to repository
        github_url: Optional GitHub URL to clone

    Returns:
        Initial OrchestratorState with default values
    """
    return OrchestratorState(
        user_prompt=user_prompt,
        repository_path=repository_path,
        github_url=github_url,
        guardrails_passed=False,
        guardrails_reason="",
        repo_context={
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
        },
        primary_agent="",
        secondary_agents=[],
        routing_reasoning="",
        target_agents=[],
        agent_outputs={},
        current_agent_index=0,
        status="pending",
        errors=[],
        user_intent="",
    )


def state_to_legacy_format(state: OrchestratorState) -> Dict[str, Any]:
    """
    Convert LangGraph state to the legacy format expected by run_orchestrator.py

    This ensures backward compatibility with the existing CLI interface.
    """
    return {
        "status": state.get("status", "pending"),
        "state": {
            "user_intent": state.get("user_intent", state.get("routing_reasoning", "")),
            "target_agents": state.get("target_agents", []),
            "guardrail_status": "approved" if state.get("guardrails_passed") else "blocked",
            "repo_context": state.get("repo_context", {}),
            "agent_outputs": state.get("agent_outputs", {}),
            "errors": state.get("errors", []),
        }
    }
