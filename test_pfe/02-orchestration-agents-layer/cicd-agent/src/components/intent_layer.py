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
        fastapi_version = repo_context.get('fastapi_version')
        flask_version = repo_context.get('flask_version')
        maven_version = repo_context.get('maven_version')
        gradle_version = repo_context.get('gradle_version')
        
        # Docker-specific context (for Docker agent integration)
        has_dockerfile = repo_context.get('has_dockerfile', False)
        dockerfile_being_generated = repo_context.get('dockerfile_being_generated', False)
        dockerfile_path = repo_context.get('dockerfile_path', 'Dockerfile')
        docker_context_path = repo_context.get('docker_context_path', '.')
        dockerfile_built_successfully = repo_context.get('dockerfile_built_successfully', False)  # NEW: Docker agent succeeded flag
        iac_output_available = bool(repo_context.get('iac_output_available', False))

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
            "CI-only workflow: include exactly one job named 'build-image' and no additional jobs.",
            "Do not include deploy jobs or kubectl/helm/k3s steps in this workflow.",
        ]

        keywords_blob = " ".join(intent.keywords).lower()
        request_blob = user_request.text.lower()
        combined = f"{keywords_blob} {request_blob}"

        explicit_java_requested = any(token in combined for token in ["java", "spring", "spring boot", "springboot", "maven", "gradle"])
        explicit_python_requested = any(token in combined for token in ["python", "pytest", "pip", "poetry", "tox"])
        explicit_node_requested = any(token in combined for token in ["node", "npm", "yarn", "javascript", "typescript", "angular"])
        requests_java = explicit_java_requested
        requests_python = explicit_python_requested
        requests_node = explicit_node_requested
        requests_sonar = any(token in combined for token in ["sonarqube", "sonar", "quality gate"])
        requests_maven = any(token in combined for token in ["maven", "mvn", "pom.xml"])
        requests_dockerhub = any(token in combined for token in ["dockerhub", "docker hub", "docker"])
        requests_ansible = any(token in combined for token in ["ansible", "playbook"])
        requests_k8s = any(token in combined for token in ["kubernetes", "k8s", "kubectl", "helm"])
        requests_monitoring = any(token in combined for token in ["prometheus", "grafana", "monitoring", "observability"])

        # Monorepo layout paths detected by context collector / dependency analyzer
        frontend_dir = repo_context.get('frontend_dir') or repo_context.get('angular_dir') or ''
        backend_dir  = repo_context.get('backend_dir') or ''
        requirements_path = repo_context.get('python_requirements_path') or (
            f"{backend_dir}/requirements.txt" if backend_dir else 'requirements.txt'
        )
        nodejs_package_path = repo_context.get('nodejs_package_path') or (
            f"{frontend_dir}/package.json" if frontend_dir else 'package.json'
        )
        is_monorepo = bool(repo_context.get('is_monorepo')) or bool(frontend_dir and backend_dir)
        angular_version = repo_context.get('angular_version') or repo_context.get('node_version')

        # Also detect based on detected frameworks and build systems
        frameworks_str = " ".join(repo_context.get('frameworks') or []).lower()
        build_system_str = (repo_context.get('build_system') or "").lower()
        detected_python = "python" in frameworks_str or "python" in build_system_str or python_version
        detected_java = "java" in frameworks_str or "maven" in build_system_str or "gradle" in build_system_str or java_version
        detected_nodejs = "node.js" in frameworks_str or "angular" in frameworks_str or "npm" in build_system_str or node_version
        detected_angular = "angular" in frameworks_str or bool(repo_context.get('angular_version'))
        detected_django = django_version is not None or "django" in frameworks_str
        detected_fastapi = fastapi_version is not None or "fastapi" in frameworks_str
        detected_flask = flask_version is not None or "flask" in frameworks_str
        detected_spring_boot = spring_boot_version is not None or "spring" in frameworks_str.lower()

        is_java_primary = bool(
            build_system_str in {"maven", "gradle"}
            or "java" in frameworks_str
            or "spring" in frameworks_str
            or java_version
        )
        python_allowed_by_context = bool(explicit_python_requested or (detected_python and not is_java_primary and not explicit_java_requested))
        node_allowed_by_context = bool(explicit_node_requested or (detected_nodejs and not is_java_primary and not explicit_java_requested))
        java_allowed_by_context = bool(explicit_java_requested or detected_java)

        if python_allowed_by_context and detected_python:  # Only if Python is actually in the project
            req_path_hint = f" Use 'pip install -r {requirements_path}'" if requirements_path != 'requirements.txt' else ""
            if python_version:
                requirement_lines.append(
                    f"Include Python setup with version {python_version} (detected from dependencies) and test execution steps.{req_path_hint}"
                )
                # Add framework-specific guidance ONLY if framework is detected
                if detected_django:
                    requirement_lines.append(f"Project uses Django {django_version or 'detected'}. Include Django migrations and test runner (e.g., python manage.py test).")
                elif detected_fastapi:
                    requirement_lines.append(
                        f"Project uses FastAPI {fastapi_version or 'detected'}. "
                        f"Install dependencies with: pip install -r {requirements_path}. "
                        f"Run tests with: pytest {backend_dir or '.'} -q || echo 'No tests found'."
                    )
                elif detected_flask:
                    requirement_lines.append(f"Project uses Flask {flask_version or 'detected'}. Include Flask test runner and WSGI compatibility checks.")
            else:
                requirement_lines.append(f"Include Python setup and test execution steps.{req_path_hint}")

        # Angular-specific requirements
        if detected_angular and node_allowed_by_context:
            node_ver = node_version or "20"
            pkg_dir = frontend_dir if frontend_dir else "."
            lock_path = f"{pkg_dir}/package-lock.json" if frontend_dir else "package-lock.json"
            requirement_lines.append(
                f"CRITICAL: This project uses Angular {angular_version or 'detected'}. "
                f"Use actions/setup-node@v4 with node-version: '{node_ver}'. "
                f"Install with: npm ci --prefix {pkg_dir}. "
                f"Build with: npm run build --prefix {pkg_dir} (this runs 'ng build'). "
                f"Use cache: 'npm' with cache-dependency-path: {lock_path}."
            )
            if is_monorepo:
                requirement_lines.append(
                    f"IMPORTANT: This is a monorepo. Angular frontend is in '{frontend_dir}/', "
                    f"Python backend is in '{backend_dir}/'. "
                    "Create SEPARATE jobs: one 'build-frontend' job for Angular and one 'test-backend' job for Python. "
                    "Do NOT mix Node.js and Python steps in the same job."
                )
        elif node_allowed_by_context and detected_nodejs:  # Generic Node.js (non-Angular)
            if node_version:
                requirement_lines.append(f"Include Node.js setup with version {node_version} (detected from package.json) and package install/test steps.")
            else:
                requirement_lines.append("Include Node.js setup and package install/test steps.")
        
        if java_allowed_by_context and detected_java:  # Only if Java is actually in the project
            if java_version:
                requirement_lines.append(f"Use Java {java_version} (detected from pom.xml/build.gradle) with actions/setup-java. Use Maven or Gradle for build/test steps.")
                if detected_spring_boot:
                    requirement_lines.append(f"Project uses Spring Boot {spring_boot_version or 'detected'}. Include Spring Boot test commands (mvn spring-boot:test or gradle bootTest).")
            else:
                requirement_lines.append("Use Java build/test steps with Maven or Gradle and configure JDK with actions/setup-java.")
        
        if requests_maven or build_system_str == "maven":
            if java_version:
                requirement_lines.append(
                    f"Use Maven with Java {java_version}. Build command: mvn -B -DskipTests clean package. Test command: mvn -B test."
                )
                requirement_lines.append(
                    "CRITICAL: actions/setup-java does NOT install Maven. "
                    "If mvnw exists, use ./mvnw. Otherwise, install Maven in each job before mvn: "
                    "run: sudo apt-get update && sudo apt-get install -y maven"
                )
            else:
                requirement_lines.append(
                    "Build and test using Maven commands (for example mvn -B clean verify). "
                    "If mvnw exists, use ./mvnw. Otherwise, install Maven before mvn commands."
                )
        
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
        
        # NEW: If Dockerfile is being generated, create a workflow that builds and uses it
        if dockerfile_built_successfully or dockerfile_being_generated:
            requirement_lines.append(
                "CRITICAL: The workflow MUST include a single 'build-image' job. "
                "Start with actions/checkout@v4, then add stack-specific build steps based on detected repo context. "
                "Do not hardcode Java/Maven steps unless Java is detected. "
                "If a Dockerfile exists or is being generated, build and push the image within this job."
            )
        
        if requests_dockerhub:
            requirement_lines.append(
                "Login to Docker Hub with docker/login-action (conditionally: if secrets.DOCKERHUB_USERNAME != '') "
                "and push image with docker/build-push-action only when secrets are available. "
                "Skip or comment out Docker Hub push steps if they will fail due to missing credentials."
            )
        
        if requests_ansible:
            requirement_lines.append("Do not run Ansible in this workflow; keep CI build-only.")
        
        if requests_k8s or requests_monitoring or any(token in combined for token in ["deploy", "production", "release"]):
            requirement_lines.append("Do not add deploy phases or Kubernetes commands; CI pipeline must stay build-only.")

        if iac_output_available:
            requirement_lines.append(
                "IaC agent already produced Terraform artifacts. Do NOT run terraform init/plan/apply/fmt/validate in this workflow unless the user explicitly asks for Terraform execution."
            )

        if is_java_primary and not explicit_python_requested:
            requirement_lines.append(
                "CRITICAL: This is a Java-primary project. Use actions/setup-java for toolchain setup and do NOT use actions/setup-python@v5 (or any setup-python) or Python package/test commands unless explicitly requested."
            )

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
        
        # Add dependency conflict warnings if present
        if repo_context.get('has_version_conflicts'):
            dep_warnings = repo_context.get('dependency_warnings', [])
            if dep_warnings:
                warning_str = "; ".join(dep_warnings[:3])  # First 3 warnings
                requirement_lines.append(f"⚠️ Dependency conflicts detected: {warning_str}. Include version compatibility checks in workflow.")
        
        repo_context_block = [
            f"Languages: {', '.join(languages) if languages else 'Unknown'}",
            f"Build system: {build_system}",
            f"Frameworks: {frameworks_str or 'None detected'}",
            f"Existing workflows: {', '.join(workflows) if workflows else 'None'}",
        ]

        # Monorepo structure hints
        if is_monorepo:
            repo_context_block.append(f"Monorepo layout: frontend in '{frontend_dir}/', backend in '{backend_dir}/'")
        if requirements_path:
            repo_context_block.append(f"Python requirements file: {requirements_path}")
        if nodejs_package_path:
            repo_context_block.append(f"Node.js package file: {nodejs_package_path}")
        if frontend_dir:
            lock_file = f"{frontend_dir}/package-lock.json"
            repo_context_block.append(f"npm lock file: {lock_file} (use as cache-dependency-path)")
        
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
        
        # NEW: Add Docker image build guidance (workflow should build and push from Dockerfile)
        if dockerfile_built_successfully or dockerfile_being_generated:
            repo_context_block.append(f"Docker workflow strategy: Build image during workflow execution and push to Docker Hub")
            repo_context_block.append(f"Build command: docker build -f Dockerfile -t build-image:latest .")

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
