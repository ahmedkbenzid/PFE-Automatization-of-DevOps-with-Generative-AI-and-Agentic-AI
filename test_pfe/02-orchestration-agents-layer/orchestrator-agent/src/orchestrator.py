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
    
    def _invoke_planner(self, user_prompt: str, repo_context: Dict[str, Any], max_retries: int = 2) -> Dict[str, Any]:
        """
        Invoke planner agent to create execution plan with retry logic.
        
        Args:
            user_prompt: User request
            repo_context: Repository analysis context
            max_retries: Number of retry attempts on timeout/failure
            
        Returns:
            Planner response with execution plan
        """
        print("[Orchestrator] 🧠 Complex request detected - Invoking Planner Agent...")
        
        # Path to planner pipeline
        planner_root = Path(__file__).parent.parent.parent / "planner-agent"
        planner_path = planner_root / "src" / "pipeline.py"
        
        if not planner_path.exists():
            print(f"[Orchestrator] ⚠️  Planner not found at {planner_path}, using direct execution")
            return {"status": "error", "message": "Planner not available"}
        
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                current_timeout = 60 * (attempt + 1)  # 60s, 120s, 180s
                
                if attempt > 0:
                    print(f"[Orchestrator] Retrying planner (attempt {attempt + 1}/{max_retries + 1}, timeout: {current_timeout}s)...")
                
                # Set up environment with PYTHONPATH and ensure GROQ_API_KEY is passed
                import os
                env = os.environ.copy()
                env["PYTHONPATH"] = str(planner_root) + os.pathsep + env.get("PYTHONPATH", "")
                env["PYTHONIOENCODING"] = "utf-8"
                env["LLM_PROVIDER"] = "groq"  # Force Groq for planner
                
                # Execute planner as subprocess with increasing timeout
                result = subprocess.run(
                    [sys.executable, str(planner_path), user_prompt, json.dumps(repo_context or {})],
                    capture_output=True,
                    text=True,
                    timeout=current_timeout,
                    cwd=str(planner_root),
                    env=env
                )
                
                if result.returncode != 0:
                    error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                    if attempt == max_retries:
                        print(f"[Orchestrator] Planner failed: {error_msg}")
                        return {"status": "error", "message": "Planner execution failed"}
                    print(f"[Orchestrator] Planner failed: {error_msg[:100]}... (will retry)")
                    last_error = error_msg
                    continue
                
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
                if attempt == max_retries:
                    print(f"[Orchestrator] Planner timeout after {current_timeout}s (all retries exhausted)")
                    return {"status": "error", "message": "Planner timeout"}
                print(f"[Orchestrator] Planner timeout at {current_timeout}s (will retry)")
                last_error = f"Timeout at {current_timeout}s"
                continue
            except json.JSONDecodeError as e:
                if attempt == max_retries:
                    print(f"[Orchestrator] Failed to parse planner output: {e}")
                    return {"status": "error", "message": "Invalid planner response"}
                print(f"[Orchestrator] JSON parse error (will retry)")
                last_error = str(e)
                continue
            except Exception as e:
                if attempt == max_retries:
                    print(f"[Orchestrator] Planner invocation error: {e}")
                    return {"status": "error", "message": str(e)}
                print(f"[Orchestrator] Planner error: {str(e)[:100]}... (will retry)")
                last_error = str(e)
                continue
        
        # Should never reach here
        return {"status": "error", "message": f"Planner failed after {max_retries + 1} attempts. Last error: {last_error}"}

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
        execution_plan: Optional[Dict[str, Any]] = None,
        user_feedback: str = "accept",
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
            execution_plan: Pre-approved execution plan to follow (from plan approval)
            user_feedback: Post-execution feedback ("accept" or "not") used by graph PR decision
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
        # Run orchestration fully through LangGraph (including planner/man-in-the-loop path)
        result = run_orchestrator(
            user_prompt=user_prompt,
            repository_path=repository_path,
            github_url=github_url,
            create_pr=create_pr if not plan_only else False,  # No PR in plan-only mode
            branch_name=branch_name,
            pr_title=pr_title,
            pr_body=pr_body,
            execution_plan=execution_plan,
            plan_only=plan_only,
            skip_planner=skip_planner,
            planner_enabled=self.enable_planner,
            planner_complexity_threshold=self.planner_complexity_threshold,
            user_feedback=user_feedback,
        )

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
