"""
Planner Agent - Main Pipeline

Strategic planning agent that decomposes complex DevOps requests into executable task plans.
Invoked by Orchestrator when request complexity exceeds threshold.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple
from collections import defaultdict, deque

# Add planner-agent root to path for imports
_planner_root = Path(__file__).parent.parent
sys.path.insert(0, str(_planner_root))

from src.config import PlannerConfig
from src.components.llm_client import PlannerLLMClient


class PlannerPipeline:
    """
    Main planner pipeline - receives requests from Orchestrator, creates execution plans
    """
    
    def __init__(self):
        self.config = PlannerConfig()
        self.llm_client = PlannerLLMClient()
        self.agent_registry = self._load_agent_registry()
    
    def _load_agent_registry(self) -> Dict[str, Any]:
        """Load agent registry from JSON file"""
        registry_path = self.config.AGENT_REGISTRY_PATH
        if not registry_path.exists():
            print(f"[Planner] Warning: Agent registry not found at {registry_path}")
            return {}
        
        with open(registry_path, 'r') as f:
            return json.load(f)
    
    def process_request(self, user_request: str, repo_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main entry point - create execution plan for complex request
        
        Args:
            user_request: User's DevOps request
            repo_context: Repository analysis context
            
        Returns:
            Execution plan with tasks, dependencies, and ordering
        """
        print("[Planner] 📥 Request received from Orchestrator")
        print(f"[Planner] Analyzing: {user_request[:100]}...")
        
        try:
            # Step 1: Analyze intent and extract requirements
            intent_analysis = self._analyze_intent(user_request, repo_context)
            
            # Step 2: Select required agents
            selected_agents = self._select_agents(intent_analysis)
            
            if not selected_agents:
                return {
                    "status": "no_agents_needed",
                    "message": "No agents required for this request"
                }
            
            # Step 3: Build dependency graph
            dependency_graph = self._build_dependency_graph(selected_agents, intent_analysis)
            
            # Step 4: Determine execution order (topological sort)
            execution_order = self._topological_sort(dependency_graph)
            
            # Step 5: Identify parallel execution groups
            parallel_groups = self._identify_parallel_groups(execution_order, dependency_graph)
            
            # Step 6: Create task list with inputs
            tasks = self._create_task_list(selected_agents, intent_analysis, repo_context)
            
            # Step 7: Estimate execution time
            estimated_time = self._estimate_execution_time(tasks)
            
            # Build complete plan
            plan = {
                "tasks": tasks,
                "execution_order": parallel_groups,
                "dependencies": dependency_graph,
                "tasks_by_id": {task["id"]: task for task in tasks},
                "estimated_time_sec": estimated_time,
                "agent_count": len(selected_agents),
                "parallel_opportunities": len([g for g in parallel_groups if isinstance(g, list) and len(g) > 1])
            }
            
            print("[Planner] ✅ Plan created successfully")
            print(f"[Planner] 📋 Summary: {len(tasks)} tasks, {len(parallel_groups)} steps")
            print(f"[Planner] 📤 Returning plan to Orchestrator")
            
            return {
                "status": "success",
                "plan": plan,
                "intent_analysis": intent_analysis,
                "reasoning": self._generate_reasoning(plan, intent_analysis)
            }
            
        except Exception as e:
            print(f"[Planner] ❌ Planning failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                "status": "error",
                "message": f"Planning failed: {str(e)}"
            }
    
    def _analyze_intent(self, user_request: str, repo_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Use LLM to analyze user intent and extract requirements
        """
        print("[Planner] 🤔 Analyzing intent with LLM...")
        
        prompt = f"""
Analyze this DevOps request and extract the requirements:

User Request: "{user_request}"

Repository Context:
- Languages: {repo_context.get('languages', [])}
- Build System: {repo_context.get('build_system', 'unknown')}
- Frameworks: {repo_context.get('frameworks', [])}
- Has Dockerfile: {repo_context.get('has_dockerfile', False)}
- Has CI/CD: {repo_context.get('has_github_actions', False)}

Extract and return JSON with:
1. "primary_goal": What is the main objective?
2. "requires_docker": Does this need Dockerfile generation? (true/false)
3. "requires_cicd": Does this need CI/CD pipeline? (true/false)
4. "requires_infrastructure": Does this need cloud infrastructure? (true/false)
5. "requires_k8s": Does this need Kubernetes manifests? (true/false)
6. "cloud_provider": Which cloud provider if any? (aws/azure/gcp/none)
7. "deployment_type": Type of deployment (container/serverless/vm/k8s/none)
8. "complexity_factors": List of complexity factors

Return ONLY valid JSON, no markdown.
"""
        
        response = self.llm_client.generate(prompt)
        
        try:
            # Try to parse JSON response
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                response = response.split("```")[1].split("```")[0].strip()
            
            analysis = json.loads(response)
            print(f"[Planner] Intent analysis complete: {analysis.get('primary_goal', 'unknown')}")
            return analysis
        except json.JSONDecodeError:
            # Fallback to keyword-based analysis
            print("[Planner] LLM response not JSON, using fallback analysis")
            return self._fallback_intent_analysis(user_request, repo_context)
    
    def _fallback_intent_analysis(self, request: str, context: Dict) -> Dict[str, Any]:
        """Fallback intent analysis using keywords"""
        request_lower = request.lower()
        
        return {
            "primary_goal": "devops automation",
            "requires_docker": any(k in request_lower for k in ['docker', 'container', 'containerize']),
            "requires_cicd": any(k in request_lower for k in ['ci/cd', 'cicd', 'pipeline', 'github actions', 'workflow']),
            "requires_infrastructure": any(k in request_lower for k in ['infrastructure', 'terraform', 'cloud', 'aws', 'azure', 'gcp', 'deploy']),
            "requires_k8s": any(k in request_lower for k in ['kubernetes', 'k8s', 'kubectl', 'helm']),
            "cloud_provider": self._extract_cloud_provider(request_lower),
            "deployment_type": self._extract_deployment_type(request_lower),
            "complexity_factors": []
        }
    
    def _extract_cloud_provider(self, request: str) -> str:
        """Extract cloud provider from request"""
        if 'aws' in request or 'ecs' in request or 'ec2' in request:
            return 'aws'
        elif 'azure' in request or 'aks' in request:
            return 'azure'
        elif 'gcp' in request or 'gke' in request:
            return 'gcp'
        return 'none'
    
    def _extract_deployment_type(self, request: str) -> str:
        """Extract deployment type from request"""
        if 'kubernetes' in request or 'k8s' in request:
            return 'k8s'
        elif 'container' in request or 'docker' in request:
            return 'container'
        elif 'serverless' in request or 'lambda' in request:
            return 'serverless'
        return 'none'
    
    def _select_agents(self, intent: Dict[str, Any]) -> List[str]:
        """
        Select which agents to use based on intent analysis
        """
        selected = []
        
        if intent.get('requires_docker'):
            selected.append('docker-agent')
        
        if intent.get('requires_cicd'):
            selected.append('cicd-agent')
        
        if intent.get('requires_infrastructure'):
            selected.append('iac-agent')
        
        if intent.get('requires_k8s'):
            selected.append('k8s-agent')
        
        print(f"[Planner] Selected agents: {selected}")
        return selected
    
    def _build_dependency_graph(self, agents: List[str], intent: Dict) -> Dict[str, List[str]]:
        """
        Build dependency graph using agent registry metadata
        """
        graph = {}
        
        for agent_id in agents:
            dependencies = []
            agent_info = self.agent_registry.get(agent_id, {})
            
            # Get dependencies from agent registry
            requires_before = agent_info.get('dependencies', {}).get('requires_before', [])
            for required_agent in requires_before:
                if required_agent in agents:
                    dependencies.append(required_agent)
            
            # Smart dependency detection
            # CI/CD should run after Docker if both selected
            if agent_id == 'cicd-agent' and 'docker-agent' in agents:
                if 'docker-agent' not in dependencies:
                    dependencies.append('docker-agent')
            
            # IaC should run after Docker if both selected
            if agent_id == 'iac-agent' and 'docker-agent' in agents:
                if 'docker-agent' not in dependencies:
                    dependencies.append('docker-agent')
            
            # K8s should run after Docker if both selected
            if agent_id == 'k8s-agent' and 'docker-agent' in agents:
                if 'docker-agent' not in dependencies:
                    dependencies.append('docker-agent')
            
            graph[agent_id] = dependencies
        
        print(f"[Planner] Dependency graph: {graph}")
        return graph
    
    def _topological_sort(self, graph: Dict[str, List[str]]) -> List[str]:
        """
        Topological sort to determine execution order
        """
        # Calculate in-degrees
        in_degree = {node: 0 for node in graph}
        for node in graph:
            for neighbor in graph[node]:
                in_degree[node] += 1
        
        # Queue of nodes with no dependencies
        queue = deque([node for node in graph if in_degree[node] == 0])
        result = []
        
        while queue:
            node = queue.popleft()
            result.append(node)
            
            # Reduce in-degree for dependents
            for other_node in graph:
                if node in graph[other_node]:
                    in_degree[other_node] -= 1
                    if in_degree[other_node] == 0:
                        queue.append(other_node)
        
        return result
    
    def _identify_parallel_groups(self, order: List[str], graph: Dict[str, List[str]]) -> List[Any]:
        """
        Group tasks that can run in parallel
        """
        groups = []
        processed = set()
        
        for node in order:
            if node in processed:
                continue
            
            # Find all nodes that can run in parallel with this one
            parallel_group = [node]
            
            for other_node in order:
                if other_node == node or other_node in processed:
                    continue
                
                # Check if they can run in parallel
                # (no dependencies between them and same dependencies)
                if (node not in graph[other_node] and 
                    other_node not in graph[node] and
                    graph[node] == graph[other_node]):
                    
                    # Check agent registry for explicit parallel compatibility
                    agent_info = self.agent_registry.get(node, {})
                    can_parallel_with = agent_info.get('can_run_parallel_with', [])
                    
                    if other_node in can_parallel_with or not can_parallel_with:
                        parallel_group.append(other_node)
            
            # Add group (as list if multiple, otherwise single string)
            if len(parallel_group) > 1:
                groups.append(parallel_group)
                processed.update(parallel_group)
            else:
                groups.append(node)
                processed.add(node)
        
        return groups
    
    def _create_task_list(self, agents: List[str], intent: Dict, context: Dict) -> List[Dict]:
        """
        Create detailed task list with inputs for each agent
        """
        tasks = []
        
        for agent_id in agents:
            agent_info = self.agent_registry.get(agent_id, {})
            
            task = {
                "id": agent_id,
                "agent": agent_id,
                "name": agent_info.get('name', agent_id),
                "description": agent_info.get('description', ''),
                "priority": agent_info.get('priority', 99),
                "inputs": {
                    "user_prompt": self._generate_agent_prompt(agent_id, intent, context),
                    "repo_context": context
                },
                "expected_output": agent_info.get('outputs', {}).get('primary', 'artifact')
            }
            
            tasks.append(task)
        
        # Sort by priority
        tasks.sort(key=lambda x: x['priority'])
        
        return tasks
    
    def _generate_agent_prompt(self, agent_id: str, intent: Dict, context: Dict) -> str:
        """
        Generate optimized prompt for specific agent
        """
        agent_info = self.agent_registry.get(agent_id, {})
        goal = intent.get('primary_goal', 'devops automation')
        
        prompts = {
            'docker-agent': f"Create an optimized Dockerfile for {context.get('primary_language', 'this')} application. Goal: {goal}",
            'cicd-agent': f"Generate a GitHub Actions CI/CD workflow for {context.get('primary_language', 'this')} project. Goal: {goal}",
            'iac-agent': f"Create Terraform infrastructure for {intent.get('cloud_provider', 'cloud')} deployment. Goal: {goal}",
            'k8s-agent': f"Generate Kubernetes deployment manifests for this application. Goal: {goal}"
        }
        
        return prompts.get(agent_id, f"Generate {agent_info.get('name', agent_id)} for this project")
    
    def _estimate_execution_time(self, tasks: List[Dict]) -> int:
        """
        Estimate total execution time in seconds
        """
        total = 0
        for task in tasks:
            agent_info = self.agent_registry.get(task['agent'], {})
            exec_time = agent_info.get('constraints', {}).get('execution_time_sec', 60)
            total += exec_time
        
        # Account for parallelization (rough estimate: 60% efficiency)
        return int(total * 0.6)
    
    def _generate_reasoning(self, plan: Dict, intent: Dict) -> str:
        """
        Generate human-readable reasoning for the plan
        """
        tasks = plan['tasks']
        order = plan['execution_order']
        
        reasoning = f"Plan created for: {intent.get('primary_goal', 'devops automation')}\n\n"
        reasoning += f"Selected {len(tasks)} agents based on requirements:\n"
        
        for task in tasks:
            reasoning += f"  - {task['name']}: {task['description']}\n"
        
        reasoning += f"\nExecution will proceed in {len(order)} steps:\n"
        for i, step in enumerate(order, 1):
            if isinstance(step, list):
                reasoning += f"  Step {i}: Parallel execution of {', '.join(step)}\n"
            else:
                reasoning += f"  Step {i}: {step}\n"
        
        reasoning += f"\nEstimated completion time: {plan['estimated_time_sec']}s"
        
        return reasoning


def main():
    """
    CLI entry point for planner agent
    """
    if len(sys.argv) < 2:
        print("Usage: python pipeline.py '<request>' [<context_json>]")
        sys.exit(1)
    
    request = sys.argv[1]
    context = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    
    planner = PlannerPipeline()
    result = planner.process_request(request, context)
    
    # Output as JSON for orchestrator to parse
    print("\n=== PLANNER OUTPUT ===")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
