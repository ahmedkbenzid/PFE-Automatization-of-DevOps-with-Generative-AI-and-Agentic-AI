"""
Orchestrator - LangGraph-based Multi-Agent Coordination.

This module provides the main Orchestrator class that coordinates
requests through guardrails, routing, and agent execution using LangGraph.

The orchestrator:
1. Validates requests through security guardrails
2. Analyzes repositories (local or GitHub)
3. Routes requests to appropriate agents (with optional planner for complex requests)
4. Executes agents and collects results
5. Returns structured output

Architecture:
- Uses LangGraph for state management and flow control
- Supports cicd-agent, docker-agent, and iac-agent
- Optional planner-agent for complex multi-step requests
- Provides backward-compatible interface
"""

from typing import Any, Dict, Optional
import sys
import json
import subprocess
from pathlib import Path

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
        
        # Planner configuration
        self.enable_planner = True  # Set to False to disable planner
        self.planner_complexity_threshold = 4

    def _calculate_complexity(self, user_prompt: str, repo_context: Dict[str, Any] = None) -> int:
        """
        Calculate complexity score for request to determine if planner is needed.
        
        Scoring factors:
        - Multiple artifacts requested: +2 each
        - Deployment keywords: +3
        - Microservices mentioned: +2
        - Cloud provider mentioned: +2
        - Multiple repos/services: +3
        - Conditional logic: +2
        
        Threshold: >= 4 triggers planner
        """
        score = 0
        prompt_lower = user_prompt.lower()
        
        # Factor 1: Multiple artifacts requested
        artifact_keywords = {
            'docker': ['docker', 'dockerfile', 'container'],
            'cicd': ['ci/cd', 'cicd', 'pipeline', 'github actions', 'workflow'],
            'iac': ['infrastructure', 'terraform', 'cloudformation'],
            'k8s': ['kubernetes', 'k8s', 'kubectl', 'helm']
        }
        
        artifacts_count = 0
        for artifact_type, keywords in artifact_keywords.items():
            if any(kw in prompt_lower for kw in keywords):
                artifacts_count += 1
        
        if artifacts_count > 1:
            score += artifacts_count * 2
        
        # Factor 2: Deployment/infrastructure keywords
        deployment_keywords = ['deploy', 'production', 'infrastructure', 'setup', 
                              'complete', 'full stack', 'end-to-end']
        if any(kw in prompt_lower for kw in deployment_keywords):
            score += 3
        
        # Factor 3: Microservices
        if 'microservice' in prompt_lower or 'multi-service' in prompt_lower:
            score += 2
        
        # Factor 4: Cloud provider setup
        cloud_keywords = ['aws', 'azure', 'gcp', 'ecs', 'eks', 'aks', 'gke']
        if any(kw in prompt_lower for kw in cloud_keywords):
            score += 2
        
        # Factor 5: Conditional/complex logic
        conditional_keywords = ['if', 'when', 'based on', 'depending on']
        if any(kw in prompt_lower for kw in conditional_keywords):
            score += 2
        
        # Factor 6: Multiple repos (from context)
        if repo_context and repo_context.get('multiple_repos', False):
            score += 3
        
        return score
    
    def _should_use_planner(self, user_prompt: str, repo_context: Dict[str, Any] = None) -> bool:
        """
        Determine if planner should be used for this request.
        
        Returns True if:
        - Planner is enabled AND
        - Complexity score >= threshold
        """
        if not self.enable_planner:
            return False
        
        # Check for force keywords (always use planner)
        prompt_lower = user_prompt.lower()
        force_keywords = ['production setup', 'complete deployment', 'end-to-end', 
                         'full stack setup', 'microservices', 'complete ci/cd']
        if any(kw in prompt_lower for kw in force_keywords):
            return True
        
        # Check for skip keywords (never use planner)
        skip_keywords = ['just', 'only', 'simple', 'single']
        if any(kw in prompt_lower for kw in skip_keywords):
            return False
        
        # Calculate complexity and compare to threshold
        complexity = self._calculate_complexity(user_prompt, repo_context)
        return complexity >= self.planner_complexity_threshold
    
    def _invoke_planner(self, user_prompt: str, repo_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Invoke planner agent to create execution plan.
        
        Args:
            user_prompt: User request
            repo_context: Repository analysis context
            
        Returns:
            Planner response with execution plan
        """
        print("[Orchestrator] 🧠 Complex request detected - Invoking Planner Agent...")
        
        try:
            # Path to planner pipeline
            planner_root = Path(__file__).parent.parent.parent / "planner-agent"
            planner_path = planner_root / "src" / "pipeline.py"
            
            if not planner_path.exists():
                print(f"[Orchestrator] ⚠️  Planner not found at {planner_path}, using direct execution")
                return {"status": "error", "message": "Planner not available"}
            
            # Set up environment with PYTHONPATH and ensure GROQ_API_KEY is passed
            import os
            env = os.environ.copy()
            env["PYTHONPATH"] = str(planner_root) + os.pathsep + env.get("PYTHONPATH", "")
            env["PYTHONIOENCODING"] = "utf-8"
            env["LLM_PROVIDER"] = "groq"  # Force Groq for planner
            
            # Execute planner as subprocess with longer timeout
            result = subprocess.run(
                [sys.executable, str(planner_path), user_prompt, json.dumps(repo_context or {})],
                capture_output=True,
                text=True,
                timeout=60,  # Increased timeout for LLM calls
                cwd=str(planner_root),
                env=env
            )
            
            if result.returncode != 0:
                print(f"[Orchestrator] Planner failed: {result.stderr}")
                return {"status": "error", "message": "Planner execution failed"}
            
            # Parse planner output
            output = result.stdout
            
            # Look for JSON output marker
            if "=== PLANNER OUTPUT ===" in output:
                json_part = output.split("=== PLANNER OUTPUT ===")[1].strip()
                return json.loads(json_part)
            else:
                # Try to parse entire output as JSON
                return json.loads(output)
                
        except subprocess.TimeoutExpired:
            print("[Orchestrator] Planner timeout")
            return {"status": "error", "message": "Planner timeout"}
        except json.JSONDecodeError as e:
            print(f"[Orchestrator] Failed to parse planner output: {e}")
            return {"status": "error", "message": "Invalid planner response"}
        except Exception as e:
            print(f"[Orchestrator] Planner invocation error: {e}")
            return {"status": "error", "message": str(e)}

    def process_request(
        self,
        user_prompt: str,
        repository_path: Optional[str] = None,
        github_url: Optional[str] = None,
        create_pr: bool = False,
        branch_name: str = "",
        pr_title: str = "Auto-generated changes from Orchestrator",
        pr_body: str = "Generated by Orchestrator Agent with AI-powered DevOps automation",
        plan_only: bool = False,
        skip_planner: bool = False,
    ) -> Dict[str, Any]:
        """
        Process a user request through the orchestration pipeline.

        This is the main entry point for handling requests. The request
        flows through:
        1. Guardrails - Security validation
        2. Repository Analysis - Extract context from repos
        3. Complexity Check - Determine if planner is needed
        4. Planner (optional) - Create strategic execution plan for complex requests
        5. Intent Routing - Determine target agents
        6. Agent Execution - Run specialized agents (skipped if plan_only=True)
        7. PR Creation (optional) - Create pull request with generated artifacts
        8. Cleanup - Remove temporary resources

        Args:
            user_prompt: The user's natural language request
            repository_path: Optional local path to a repository
            github_url: Optional GitHub URL to clone and analyze
            create_pr: Whether to create a pull request with generated artifacts
            branch_name: Branch name for the pull request (required if create_pr=True)
            plan_only: If True, only generate plan without executing agents (for human approval)
            skip_planner: If True, skip planner and execute agents directly
            pr_title: Title for the pull request
            pr_body: Description/body for the pull request

        Returns:
            Dictionary containing:
                - status: "completed", "blocked", or "error"
                - used_planner: bool (True if planner was used)
                - complexity_score: int (request complexity)
                - execution_plan: Dict (if planner was used)
                - state: {
                    user_intent: str,
                    target_agents: List[str],
                    guardrail_status: str,
                    repo_context: Dict,
                    agent_outputs: Dict,
                    pr_details: Dict (if PR creation requested),
                    errors: List[str]
                }

        Example:
            >>> orchestrator = Orchestrator()
            >>> result = orchestrator.process_request(
            ...     "Create Terraform for S3",
            ...     github_url="https://github.com/user/repo",
            ...     create_pr=True,
            ...     branch_name="feature/terraform-s3"
            ... )
            >>> print(result["status"])
            "completed"
            >>> if result["used_planner"]:
            ...     print("Complex request - planner was used")
        """
        # Override planner if user requested to skip it
        if skip_planner:
            self.enable_planner = False
        
        # First, run the standard orchestration to get repo context
        result = run_orchestrator(
            user_prompt=user_prompt,
            repository_path=repository_path,
            github_url=github_url,
            create_pr=create_pr if not plan_only else False,  # No PR in plan-only mode
            branch_name=branch_name,
            pr_title=pr_title,
            pr_body=pr_body,
        )
        
        # Get repo context from result
        repo_context = result.get("state", {}).get("repo_context", {})
        
        # Check if planner should be used
        complexity_score = self._calculate_complexity(user_prompt, repo_context)
        should_use_planner = self._should_use_planner(user_prompt, repo_context) and not skip_planner
        
        # Add planner metadata to result
        result["used_planner"] = should_use_planner
        result["complexity_score"] = complexity_score
        result["plan_only"] = plan_only
        
        if should_use_planner:
            print(f"[Orchestrator] Complexity score: {complexity_score} (threshold: {self.planner_complexity_threshold})")
            
            # Invoke planner
            planner_result = self._invoke_planner(user_prompt, repo_context)
            
            if planner_result.get("status") == "success":
                result["execution_plan"] = planner_result.get("plan", {})
                result["planner_reasoning"] = planner_result.get("reasoning", "")
                print("[Orchestrator] ✅ Execution plan received from Planner")
                
                # If plan_only mode, stop here and return the plan for approval
                if plan_only:
                    result["status"] = "plan_ready"
                    print("[Orchestrator] 🛑 Plan-only mode: Awaiting user approval")
                    return result
                
            else:
                print(f"[Orchestrator] ⚠️  Planner failed: {planner_result.get('message')}")
                result["planner_error"] = planner_result.get("message")
        else:
            print(f"[Orchestrator] ⚡ Direct execution (complexity: {complexity_score})")
        
        # If plan_only and no planner, still return for approval
        if plan_only:
            result["status"] = "plan_ready"
            print("[Orchestrator] 🛑 Plan-only mode: Awaiting user approval")
        
        return result

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
