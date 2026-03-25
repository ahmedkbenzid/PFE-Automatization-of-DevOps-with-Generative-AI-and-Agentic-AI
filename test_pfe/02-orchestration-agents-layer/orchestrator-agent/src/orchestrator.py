"""
Orchestrator - LangGraph-based Multi-Agent Coordination.

This module provides the main Orchestrator class that coordinates
requests through guardrails, routing, and agent execution using LangGraph.

The orchestrator:
1. Validates requests through security guardrails
2. Analyzes repositories (local or GitHub)
3. Routes requests to appropriate agents
4. Executes agents and collects results
5. Returns structured output

Architecture:
- Uses LangGraph for state management and flow control
- Supports cicd-agent, docker-agent, and iac-agent
- Provides backward-compatible interface
"""

from typing import Any, Dict, Optional

# Import the LangGraph-based orchestrator
if __package__:
    from .orchestrator_graph import run_orchestrator, get_compiled_graph, visualize_graph
    from .graph_state import OrchestratorState, create_initial_state, state_to_legacy_format
    from .config import OrchestratorConfig
else:
    from orchestrator_graph import run_orchestrator, get_compiled_graph, visualize_graph
    from graph_state import OrchestratorState, create_initial_state, state_to_legacy_format
    from config import OrchestratorConfig


class Orchestrator:
    """
    LangGraph-based orchestrator for DevOps multi-agent coordination.

    This class provides a backward-compatible interface to the LangGraph
    orchestration system. It handles:
    - Security guardrails validation
    - Repository analysis (local paths and GitHub URLs)
    - Intent-based routing to specialized agents
    - Agent execution and result collection

    Usage:
        orchestrator = Orchestrator()
        result = orchestrator.process_request(
            "Create a CI/CD pipeline for my Python project",
            repository_path="/path/to/repo"
        )

    The result contains:
        - status: "completed", "blocked", or "error"
        - state: Dictionary with agent outputs, errors, etc.
    """

    def __init__(self):
        """
        Initialize the orchestrator.

        This validates that required configuration (API keys) is present
        and prepares the LangGraph for execution.
        """
        self.config = OrchestratorConfig()

        # Validate API key
        if not self.config.LLM_API_KEY:
            raise ValueError("GROQ_API_KEY is missing from environment. Cannot initialize orchestrator.")

        # Get the compiled graph (this also initializes components)
        self._graph = get_compiled_graph()

    def process_request(
        self,
        user_prompt: str,
        repository_path: Optional[str] = None,
        github_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process a user request through the orchestration pipeline.

        This is the main entry point for handling requests. The request
        flows through:
        1. Guardrails - Security validation
        2. Repository Analysis - Extract context from repos
        3. Intent Routing - Determine target agents
        4. Agent Execution - Run specialized agents
        5. Cleanup - Remove temporary resources

        Args:
            user_prompt: The user's natural language request
            repository_path: Optional local path to a repository
            github_url: Optional GitHub URL to clone and analyze

        Returns:
            Dictionary containing:
                - status: "completed", "blocked", or "error"
                - state: {
                    user_intent: str,
                    target_agents: List[str],
                    guardrail_status: str,
                    repo_context: Dict,
                    agent_outputs: Dict,
                    errors: List[str]
                }

        Example:
            >>> orchestrator = Orchestrator()
            >>> result = orchestrator.process_request("Create Terraform for S3")
            >>> print(result["status"])
            "completed"
            >>> print(result["state"]["agent_outputs"]["iac-agent"])
            {"status": "success", "data": {...}}
        """
        return run_orchestrator(
            user_prompt=user_prompt,
            repository_path=repository_path,
            github_url=github_url,
        )

    def get_graph_visualization(self) -> str:
        """
        Get a Mermaid diagram of the orchestration graph.

        This can be rendered at https://mermaid.live for visualization.

        Returns:
            Mermaid diagram string
        """
        return visualize_graph()


# =============================================================================
# DIRECT EXECUTION (for testing)
# =============================================================================

if __name__ == "__main__":
    import pprint

    # Test prompt
    test_prompt = (
        "if i push in github spring boot micro-service analyse the code with sonarqube "
        "then build with maven then do continuous delivery with ansible to deploy with "
        "kubernetes by pulling a dockerhub image then do monitoring with grafana and prometheus"
    )

    try:
        print("=== Testing LangGraph Orchestrator ===")
        print(f"Prompt: '{test_prompt}'\n")

        orchestrator = Orchestrator()

        # Show graph structure
        print("=== Graph Structure (Mermaid) ===")
        print(orchestrator.get_graph_visualization())
        print()

        # Test 1: Prompt-only mode (no repo)
        print("\n--- Mode 1: Prompt-only (no repository) ---")
        result = orchestrator.process_request(test_prompt)

        print("\n=== Final Conversation State ===")
        pprint.pprint(result)

        # Test 2: With local repo path (uncomment to test)
        # print("\n--- Mode 2: With local repository ---")
        # result = orchestrator.process_request(
        #     test_prompt,
        #     repository_path="/path/to/your/repo"
        # )

        # Test 3: With GitHub URL (uncomment to test)
        # print("\n--- Mode 3: With GitHub URL ---")
        # result = orchestrator.process_request(
        #     test_prompt,
        #     github_url="https://github.com/user/repo"
        # )

    except ValueError as e:
        print(f"\nConfiguration Error: {e}")
        print("Please ensure you have a .env file with GROQ_API_KEY in the orchestrator-agent folder.")
