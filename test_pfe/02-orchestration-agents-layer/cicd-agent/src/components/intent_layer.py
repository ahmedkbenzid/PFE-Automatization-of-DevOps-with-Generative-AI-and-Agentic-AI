"""Intent layer for understanding user requests"""
from typing import Dict, Any, List
from src.models.types import UserRequest, IntentMetadata, RequestType
from src.components.llm_client import GroqLLMClient

class IntentLayer:
    """Extract and understand user intent with markdown metadata"""
    
    def __init__(self, llm_client: GroqLLMClient):
        self.llm_client = llm_client
        
    def process_request(self, user_request: UserRequest) -> tuple[IntentMetadata, Dict[str, Any]]:
        """Process user request and extract intent with metadata"""
        
        # Extract intent using LLM
        intent_metadata = self.llm_client.extract_intent(user_request.text)
        
        # Build markdown metadata
        markdown_metadata = self._build_markdown_metadata(user_request, intent_metadata)
        
        return intent_metadata, markdown_metadata
    
    def _build_markdown_metadata(self, request: UserRequest, intent: IntentMetadata) -> Dict[str, Any]:
        """Build markdown-formatted metadata"""
        metadata = {
            "user_request": request.text,
            "intent_summary": f"## Intent: {intent.intent}",
            "request_type": f"**Type:** {intent.request_type.value}",
            "keywords": f"**Keywords:** {', '.join(intent.keywords)}",
            "tools_needed": f"**Tools:** {', '.join(intent.required_tools)}",
            "confidence": f"**Confidence:** {intent.confidence:.2%}",
            "context": request.context,
            "repo_info": request.repo_path,
        }
        return metadata
    
    def build_context_prompt(
        self,
        user_request: UserRequest,
        intent: IntentMetadata,
        repo_context: Dict[str, Any],
        knowledge_pages: List[Dict[str, Any]] | None = None,
        reference_examples: List[Any] | None = None,
    ) -> str:
        """Build a dynamic prompt tailored to user goal, context, and retrieved knowledge."""
        languages = repo_context.get('languages') or []
        workflows = repo_context.get('workflows') or []
        build_system = repo_context.get('build_system', 'None detected')
        
        # Version information from dependency analysis
        python_version = repo_context.get('python_version')
        java_version = repo_context.get('java_version')
        node_version = repo_context.get('node_version')
        go_version = repo_context.get('go_version')
        spring_boot_version = repo_context.get('spring_boot_version')
        django_version = repo_context.get('django_version')
        
        # Docker-specific context (for Docker agent integration)
        has_dockerfile = repo_context.get('has_dockerfile', False)
        dockerfile_being_generated = repo_context.get('dockerfile_being_generated', False)
        dockerfile_path = repo_context.get('dockerfile_path', 'Dockerfile')
        docker_context_path = repo_context.get('docker_context_path', '.')

        dynamic_goals = [
            f"Primary goal: {intent.intent}",
            f"Original request: {user_request.text}",
            f"Request type: {intent.request_type.value}",
            f"Detected keywords: {', '.join(intent.keywords) if intent.keywords else 'None'}",
            f"Confidence: {intent.confidence:.2f}",
        ]

        requirement_lines = [
            "Return valid GitHub Actions YAML only (no markdown code fences, no explanations).",
            "Ensure top-level keys include: name, on, jobs.",
            "Use secure defaults and minimal permissions.",
            "Pin action versions and prefer stable action releases.",
        ]

        keywords_blob = " ".join(intent.keywords).lower()
        request_blob = user_request.text.lower()
        combined = f"{keywords_blob} {request_blob}"

        requests_java = any(token in combined for token in ["java", "spring", "spring boot", "springboot", "maven", "gradle"])
        requests_python = any(token in combined for token in ["python", "pytest", "pip"])
        requests_node = any(token in combined for token in ["node", "npm", "yarn", "javascript", "typescript"])
        requests_sonar = any(token in combined for token in ["sonarqube", "sonar", "quality gate"])
        requests_maven = any(token in combined for token in ["maven", "mvn", "pom.xml"])
        requests_dockerhub = any(token in combined for token in ["dockerhub", "docker hub", "docker"])
        requests_ansible = any(token in combined for token in ["ansible", "playbook"])
        requests_k8s = any(token in combined for token in ["kubernetes", "k8s", "kubectl", "helm"])
        requests_monitoring = any(token in combined for token in ["prometheus", "grafana", "monitoring", "observability"])

        if any(token in combined for token in ["python", "pytest", "pip"]):
            if python_version:
                requirement_lines.append(f"Include Python setup with version {python_version} (detected from dependencies) and test execution steps.")
            else:
                requirement_lines.append("Include Python setup and test execution steps.")
        if any(token in combined for token in ["node", "npm", "yarn", "javascript", "typescript"]):
            if node_version:
                requirement_lines.append(f"Include Node.js setup with version {node_version} (detected from package.json) and package install/test steps.")
            else:
                requirement_lines.append("Include Node.js setup and package install/test steps.")
        if requests_java:
            if java_version:
                requirement_lines.append(f"Use Java {java_version} (detected from pom.xml/build.gradle) with actions/setup-java. Use Maven or Gradle for build/test steps.")
            else:
                requirement_lines.append("Use Java build/test steps with Maven or Gradle and configure JDK with actions/setup-java.")
        if requests_maven:
            requirement_lines.append("Build and test using Maven commands (for example mvn -B clean verify) and Maven cache.")
        if requests_sonar:
            requirement_lines.append("Include SonarQube analysis steps using secrets for SONAR_TOKEN and SONAR_HOST_URL.")
        if any(token in combined for token in ["docker", "image", "registry", "buildx"]):
            if dockerfile_being_generated or has_dockerfile:
                # Dockerfile exists or is being generated - provide explicit path
                requirement_lines.append(
                    f"Include Docker build workflow steps. "
                    f"Use context: '{docker_context_path}' and file: './{dockerfile_path}' for docker/build-push-action."
                )
            else:
                # No Dockerfile detected - use generic guidance
                requirement_lines.append("Include Docker build workflow steps with safe defaults.")
        if requests_dockerhub:
            requirement_lines.append("Login to Docker Hub with docker/login-action and push image with docker/build-push-action.")
        if requests_ansible:
            requirement_lines.append("Install Ansible via pip and run ansible-playbook for delivery steps.")
        if requests_k8s:
            requirement_lines.append("Deploy to Kubernetes by referencing the Docker Hub image tag in manifests or Ansible variables.")
        if requests_monitoring:
            requirement_lines.append("Provision monitoring with Prometheus and Grafana using Kubernetes-native tooling (Helm/kubectl).")
        if any(token in combined for token in ["deploy", "production", "release"]):
            requirement_lines.append("Separate build/test and deploy phases with gating conditions.")

        if requests_java and not requests_python:
            requirement_lines.append("Do not include Python-specific steps (setup-python, pip, pytest) unless explicitly requested.")
        if requests_java and not requests_node:
            requirement_lines.append("Do not include Node.js-specific steps (setup-node, npm, yarn) unless explicitly requested.")

        if requests_ansible or requests_monitoring or requests_k8s:
            requirement_lines.append("Do not invent unofficial marketplace actions for Ansible, Grafana, Prometheus, or generic Kubernetes deploy; prefer shell commands and official setup actions.")

        if intent.request_type == RequestType.MIGRATE_WORKFLOW:
            requirement_lines.append("Preserve behavior while mapping old CI stages into GitHub Actions jobs.")
        if intent.request_type == RequestType.OPTIMIZE_WORKFLOW:
            requirement_lines.append("Optimize execution with caching and parallel matrix where relevant.")
        if intent.request_type == RequestType.VALIDATE_WORKFLOW:
            requirement_lines.append("Prioritize correctness and compatibility over feature breadth.")

        repo_context_block = [
            f"Languages: {', '.join(languages) if languages else 'Unknown'}",
            f"Build system: {build_system}",
            f"Existing workflows: {', '.join(workflows) if workflows else 'None'}",
        ]
        
        # Add version information if available
        version_info = []
        if python_version:
            version_info.append(f"Python {python_version}")
        if java_version:
            version_info.append(f"Java {java_version}")
        if node_version:
            version_info.append(f"Node.js {node_version}")
        if go_version:
            version_info.append(f"Go {go_version}")
        if spring_boot_version:
            version_info.append(f"Spring Boot {spring_boot_version}")
        if django_version:
            version_info.append(f"Django {django_version}")
        
        if version_info:
            repo_context_block.append(f"Detected versions: {', '.join(version_info)}")
        
        # Add Docker context information if relevant
        if dockerfile_being_generated:
            repo_context_block.append(f"Dockerfile: Being generated by Docker agent at '{dockerfile_path}'")
        elif has_dockerfile:
            repo_context_block.append(f"Dockerfile: Exists at '{dockerfile_path}'")
        
        if dockerfile_being_generated or has_dockerfile:
            repo_context_block.append(f"Docker build context: '{docker_context_path}'")

        knowledge_block = []
        for index, page in enumerate(knowledge_pages or [], start=1):
            knowledge_block.append(
                f"[{index}] {page.get('title', 'Untitled')} | source={page.get('source', 'unknown')} | tags={', '.join(page.get('tags', []))}\n"
                f"{page.get('content', '')[:450]}"
            )

        examples_block = []
        for index, example in enumerate(reference_examples or [], start=1):
            examples_block.append(
                f"Example {index}: {getattr(example, 'name', 'workflow')} | language={getattr(example, 'language', 'unknown')} | success_rate={getattr(example, 'success_rate', 'n/a')}\n"
                f"{getattr(example, 'yaml_content', '')[:500]}"
            )

        prompt = (
            "You are a CI/CD generation agent. Build one GitHub Actions workflow matching the exact user goal.\n\n"
            "## Dynamic Goal\n"
            + "\n".join(f"- {line}" for line in dynamic_goals)
            + "\n\n## Repository Context\n"
            + "\n".join(f"- {line}" for line in repo_context_block)
            + "\n\n## Requirements\n"
            + "\n".join(f"- {line}" for line in requirement_lines)
        )

        if knowledge_block:
            prompt += "\n\n## Retrieved Knowledge Base Pages\n" + "\n\n".join(knowledge_block)

        if examples_block:
            prompt += "\n\n## Reference Workflow Examples\n" + "\n\n".join(examples_block)

        prompt += (
            "\n\n## Output Rules\n"
            "- Output ONLY the GitHub Actions workflow YAML text.\n"
            "- Do NOT include Dockerfile, Docker Compose, or any other artifacts.\n"
            "- Do NOT generate bonus artifacts beyond what was requested.\n"
            "- Do not wrap output in markdown fences.\n"
            "- Ensure a valid 'on' trigger block is included.\n"
            "- Include at least one job with steps.\n"
        )

        return prompt
