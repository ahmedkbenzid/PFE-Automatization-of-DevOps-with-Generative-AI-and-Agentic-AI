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
    plan_only: bool
    skip_planner: bool
    planner_enabled: bool
    planner_complexity_threshold: int

    # PR creation parameters (optional)
    create_pr: bool
    branch_name: str
    pr_title: str
    pr_body: str

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
    complexity_score: int
    used_planner: bool
    planner_reasoning: str
    planner_error: str
    execution_plan: Dict[str, Any]
    approved_execution_plan: Dict[str, Any]
    plan_approved: bool
    plan_only_waiting_approval: bool
    user_feedback: str
    dag_execution_order: List[Any]

    # Agent execution results
    agent_outputs: Dict[str, Any]
    current_agent_index: int  # Track which agent we're executing

    # PR creation results (optional)
    pr_details: Dict[str, Any]

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
        plan_only=False,
        skip_planner=False,
        planner_enabled=True,
        planner_complexity_threshold=4,
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
        complexity_score=0,
        used_planner=False,
        planner_reasoning="",
        planner_error="",
        execution_plan={},
        approved_execution_plan={},
        plan_approved=False,
        plan_only_waiting_approval=False,
        user_feedback="accept",
        dag_execution_order=[],
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
    legacy_state = {
        "user_intent": state.get("user_intent", state.get("routing_reasoning", "")),
        "target_agents": state.get("target_agents", []),
        "guardrail_status": "approved" if state.get("guardrails_passed") else "blocked",
        "repo_context": state.get("repo_context", {}),
        "agent_outputs": state.get("agent_outputs", {}),
        "errors": state.get("errors", []),
    }

    # Add PR details if available
    if state.get("pr_details"):
        legacy_state["pr_details"] = state.get("pr_details")

    result = {
        "status": state.get("status", "pending"),
        "state": legacy_state,
    }

    result["used_planner"] = state.get("used_planner", False)
    result["complexity_score"] = state.get("complexity_score", 0)
    result["plan_only"] = state.get("plan_only", False)

    if state.get("execution_plan"):
        result["execution_plan"] = state.get("execution_plan")
    if state.get("planner_reasoning"):
        result["planner_reasoning"] = state.get("planner_reasoning")
    if state.get("planner_error"):
        result["planner_error"] = state.get("planner_error")

    return result
