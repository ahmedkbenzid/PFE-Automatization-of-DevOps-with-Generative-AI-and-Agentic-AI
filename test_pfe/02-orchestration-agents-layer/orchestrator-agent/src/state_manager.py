from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class ConversationState(BaseModel):
    user_intent: str = ""
    target_agents: List[str] = Field(default_factory=list)
    guardrail_status: str = "pending" # pending, approved, blocked
    agent_outputs: Dict[str, Any] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)
    
class StateManager:
    def __init__(self):
        self.state = ConversationState()

    def update_intent(self, intent: str, target_agents: List[str]):
        self.state.user_intent = intent
        self.state.target_agents = target_agents

    def update_guardrail_status(self, status: str):
        self.state.guardrail_status = status

    def store_agent_output(self, agent_name: str, output: Any):
        self.state.agent_outputs[agent_name] = output

    def add_error(self, error: str):
        self.state.errors.append(error)

    def get_state(self):
        return self.state
