from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RepoContextState(BaseModel):
    """Repository context stored in conversation state"""
    is_available: bool = False
    source: str = "none"  # "local", "github", "none"
    path: str = ""
    languages: List[str] = Field(default_factory=list)
    build_system: Optional[str] = None
    package_managers: List[str] = Field(default_factory=list)
    frameworks: List[str] = Field(default_factory=list)
    has_dockerfile: bool = False
    has_docker_compose: bool = False
    has_ci_workflows: bool = False
    existing_workflows: List[str] = Field(default_factory=list)
    config_files: Dict[str, bool] = Field(default_factory=dict)


class ConversationState(BaseModel):
    user_intent: str = ""
    target_agents: List[str] = Field(default_factory=list)
    guardrail_status: str = "pending"  # pending, approved, blocked
    repo_context: RepoContextState = Field(default_factory=RepoContextState)
    agent_outputs: Dict[str, Any] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)


class StateManager:
    def __init__(self):
        self.state = ConversationState()

    def reset(self):
        """Reset state for a new request"""
        self.state = ConversationState()

    def update_intent(self, intent: str, target_agents: List[str]):
        self.state.user_intent = intent
        self.state.target_agents = target_agents

    def update_guardrail_status(self, status: str):
        self.state.guardrail_status = status

    def update_repo_context(self, repo_context: Dict[str, Any]):
        """Update repository context from RepoAnalyzer results"""
        self.state.repo_context = RepoContextState(
            is_available=repo_context.get("is_available", False),
            source=repo_context.get("source", "none"),
            path=repo_context.get("path", ""),
            languages=repo_context.get("languages", []),
            build_system=repo_context.get("build_system"),
            package_managers=repo_context.get("package_managers", []),
            frameworks=repo_context.get("frameworks", []),
            has_dockerfile=repo_context.get("has_dockerfile", False),
            has_docker_compose=repo_context.get("has_docker_compose", False),
            has_ci_workflows=repo_context.get("has_ci_workflows", False),
            existing_workflows=repo_context.get("existing_workflows", []),
            config_files=repo_context.get("config_files", {}),
        )

    def get_repo_context(self) -> RepoContextState:
        """Get the current repository context"""
        return self.state.repo_context

    def store_agent_output(self, agent_name: str, output: Any):
        self.state.agent_outputs[agent_name] = output

    def add_error(self, error: str):
        self.state.errors.append(error)

    def get_state(self):
        return self.state
