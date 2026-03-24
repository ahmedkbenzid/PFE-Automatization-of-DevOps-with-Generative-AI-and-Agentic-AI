if __package__:
    from .config import OrchestratorConfig
    from .state_manager import StateManager
    from .guardrails import Guardrails
    from .intent_router import IntentRouter
else:
    from config import OrchestratorConfig
    from state_manager import StateManager
    from guardrails import Guardrails
    from intent_router import IntentRouter

import json
import os
import subprocess
import sys
from typing import Any, Dict, List

class Orchestrator:
    def __init__(self):
        self.config = OrchestratorConfig()
        
        # In a real environment, you'd handle API keys robustly
        api_key = self.config.LLM_API_KEY
        if not api_key:
            raise ValueError("GROQ_API_KEY is missing from environment. Cannot initialize orchestrator.")
            
        self.state_manager = StateManager()
        self.guardrails = Guardrails(api_key=api_key, model_name=self.config.MODEL_NAME)
        self.router = IntentRouter(api_key=api_key, model_name=self.config.MODEL_NAME)

    def _resolve_agent_path(self, agent_folder_name: str) -> str:
        return os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", agent_folder_name)
        )

    def _invoke_python_agent(
        self,
        *,
        agent_name: str,
        agent_folder_name: str,
        run_code: str,
        args: List[str],
        result_prefix: str,
    ) -> Dict[str, Any]:
        agent_path = self._resolve_agent_path(agent_folder_name)
        if not os.path.exists(agent_path):
            raise FileNotFoundError(f"Could not find {agent_name} at: {agent_path}")

        completed = subprocess.run(
            [sys.executable, "-c", run_code, *args],
            cwd=agent_path,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            check=False,
        )

        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or f"Unknown {agent_name} error").strip())

        for line in (completed.stdout or "").splitlines():
            if line.startswith(result_prefix):
                return json.loads(line[len(result_prefix):])

        raise RuntimeError(f"{agent_name} returned no structured result")

    def process_request(self, user_prompt: str, repository_path: str | None = None) -> dict:
        """
        Main entry point for handling a user request through the layer 2 architecture.
        """
        # --- 1. GUARDRAILS ---
        print("[Orchestrator] 🛡️ Running Guardrails Check...")
        guard_result = self.guardrails.validate_input(user_prompt)
        
        if not guard_result.get("is_allowed", False):
            print(f"[Orchestrator] ⛔ Blocked by Guardrails: {guard_result.get('reason')}")
            self.state_manager.update_guardrail_status("blocked")
            self.state_manager.add_error(guard_result.get("reason", "Violated input policies."))
            
            return {
                "status": "blocked",
                "state": self.state_manager.get_state().dict()
            }
        
        self.state_manager.update_guardrail_status("approved")
        print("[Orchestrator] ✅ Guardrails Passed.")

        # --- 2. INTENT ROUTING ---
        print("[Orchestrator] 🧭 Analyzing User Intent & Routing...")
        route_result = self.router.route(user_prompt)
        
        # Update State
        primary_agent = route_result.get("primary_agent")
        secondary_agents = route_result.get("secondary_agents", [])
        
        target_agents = []
        if primary_agent and primary_agent != "error":
            target_agents.append(primary_agent)
        target_agents.extend(secondary_agents)
        
        self.state_manager.update_intent(
            intent=route_result.get("reasoning", "Routing execution"), 
            target_agents=target_agents
        )
        self.state_manager.store_agent_output("intent_router", route_result)
        
        print(f"[Orchestrator] 🔀 Assigned to: Primary -> {primary_agent} | Secondary -> {secondary_agents}")
        print(f"[Orchestrator] 💡 Reasoning: {route_result.get('reasoning')}")

        effective_repo_path = repository_path or self.config.DEFAULT_REPOSITORY_PATH

        # --- 3. EXECUTION DISPATCHER ---
        print("[Orchestrator] 🚀 Dispatching to Target Agents...")
        for agent in target_agents:
            if agent == "cicd-agent":
                print(f"[Orchestrator] -> Invoking {agent} locally")
                try:
                    run_code = (
                        "import json,sys; "
                        "from dataclasses import asdict; "
                        "from src.pipeline import CICDPipeline; "
                        "from src.models.types import UserRequest; "
                        "req=UserRequest(text=sys.argv[1]); "
                        "result=CICDPipeline().process_request(req, repo_path=sys.argv[2]); "
                        "print('CICD_RESULT_JSON=' + json.dumps(asdict(result), default=str))"
                    )
                    cicd_result = self._invoke_python_agent(
                        agent_name="cicd-agent",
                        agent_folder_name="cicd-agent",
                        run_code=run_code,
                        args=[user_prompt, effective_repo_path],
                        result_prefix="CICD_RESULT_JSON=",
                    )
                    
                    print(f"[Orchestrator] <- Result received from {agent}")
                    self.state_manager.store_agent_output(agent, {"status": "success", "data": cicd_result})
                    
                except Exception as e:
                    print(f"[Orchestrator] ❌ Error executing {agent}: {str(e)}")
                    
                    self.state_manager.store_agent_output(agent, {"status": "error", "message": str(e)})
                    self.state_manager.add_error(f"{agent} failed: {str(e)}")
            elif agent == "docker-agent":
                print(f"[Orchestrator] -> Invoking {agent} locally")
                try:
                    run_code = (
                        "import json,sys; "
                        "from dataclasses import asdict; "
                        "from src.pipeline import run_pipeline; "
                        "result=run_pipeline(sys.argv[1], sys.argv[2], False); "
                        "print('DOCKER_RESULT_JSON=' + json.dumps(asdict(result), default=str))"
                    )
                    docker_result = self._invoke_python_agent(
                        agent_name="docker-agent",
                        agent_folder_name="docker-agent",
                        run_code=run_code,
                        args=[user_prompt, effective_repo_path],
                        result_prefix="DOCKER_RESULT_JSON=",
                    )

                    print(f"[Orchestrator] <- Result received from {agent}")
                    self.state_manager.store_agent_output(agent, {"status": "success", "data": docker_result})

                except Exception as e:
                    print(f"[Orchestrator] ❌ Error executing {agent}: {str(e)}")
                    self.state_manager.store_agent_output(agent, {"status": "error", "message": str(e)})
                    self.state_manager.add_error(f"{agent} failed: {str(e)}")
            else:
                print(f"[Orchestrator] ⚠️ Agent '{agent}' is not yet integrated. Skipping execution.")
                self.state_manager.store_agent_output(agent, {"status": "skipped", "message": "Not integrated"})
        
        return {
            "status": "completed",
            "state": self.state_manager.get_state().model_dump() # model_dump() replaces dict() in newer pydantic
        }

if __name__ == "__main__":
    import pprint
    
    # Let's test the Orchestrator with the complex Spring Boot prompt you used recently!
    test_prompt = (
        "if i push in github spring boot micro-service analyse the code with sonarqube "
        "then build with maven then do continuous delivery with ansible to deploy with "
        "kubernetes by pulling a dockerhub image then do monitoring with grafana and prometheus"
    )
    
    try:
        print(f"=== Testing Orchestrator ===")
        print(f"Prompt: '{test_prompt}'\n")
        
        orchestrator = Orchestrator()
        result = orchestrator.process_request(test_prompt)
        
        print("\n=== Final Conversation State ===")
        pprint.pprint(result)
        
    except ValueError as e:
        print(f"\nConfiguration Error: {e}")
        print("Please ensure you have a .env file with GROQ_API_KEY in the orchestrator-agent folder.")
