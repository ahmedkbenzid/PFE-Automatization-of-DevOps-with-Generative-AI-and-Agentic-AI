"""Tools Layer: analyze_project component."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from src.models.types import RepositoryContext
from src.components.dependency_analyzer import DependencyAnalyzer


@dataclass
class AnalysisResult:
    stack_type: str = "unknown"
    confidence: float = 0.0


class AnalyzeProject:
    """Detect repository stack and core containerization signals."""

    def analyze(self, repository_path: str) -> tuple[RepositoryContext, AnalysisResult]:
        # FIXED: Check if repository_path is a URL (GitHub) instead of local path
        # If it's a URL, we'll rely on repo_context passed from orchestrator
        if repository_path.startswith("http://") or repository_path.startswith("https://"):
            print(f"[Docker Agent] Repository is GitHub URL, skipping local file detection: {repository_path}")
            # Return empty context - will be filled by orchestrator's repo_context
            return RepositoryContext(
                repository_path=repository_path,
                project_languages=[],
                package_managers=[],
                frameworks=[],
                build_tools=[],
            ), AnalysisResult()
        
        repo = Path(repository_path)
        languages: List[str] = []
        package_managers: List[str] = []
        frameworks: List[str] = []
        build_tools: List[str] = []

        # Detect Node.js/JavaScript
        if (repo / "package.json").exists():
            languages.append("JavaScript")
            package_managers.append("npm")
            frameworks.append("node")

        # Detect Python
        if (repo / "requirements.txt").exists() or (repo / "pyproject.toml").exists():
            languages.append("Python")
            package_managers.append("pip")
            frameworks.append("python")

        # Detect Java/Maven
        if (repo / "pom.xml").exists():
            languages.append("Java")
            package_managers.append("maven")
            build_tools.append("maven")
            frameworks.append("spring")

        # Detect Java/Gradle
        if (repo / "build.gradle").exists() or (repo / "build.gradle.kts").exists():
            if "Java" not in languages:
                languages.append("Java")
            package_managers.append("gradle")
            build_tools.append("gradle")
            if "spring" not in frameworks:
                frameworks.append("spring")

        # Detect Go
        if (repo / "go.mod").exists():
            languages.append("Go")
            frameworks.append("go")

        # Detect Rust
        if (repo / "Cargo.toml").exists():
            languages.append("Rust")
            frameworks.append("rust")

        existing_dockerfiles = [str(path) for path in repo.rglob("Dockerfile*")]
        existing_compose_files = [str(path) for path in repo.rglob("docker-compose*.yml")]
        existing_compose_files += [str(path) for path in repo.rglob("docker-compose*.yaml")]

        detected_ports = self._detect_ports(repo)
        env_vars = self._detect_env_vars(repo)
        
        # NEW: Analyze dependencies to extract version information
        print("[Docker Agent] Analyzing project dependencies...")
        try:
            dep_analyzer = DependencyAnalyzer(str(repo))
            dep_info = dep_analyzer.analyze()
            
            # Log findings
            if dep_info.python_version:
                print(f"  ✓ Detected Python {dep_info.python_version}")
            if dep_info.java_version:
                print(f"  ✓ Detected Java {dep_info.java_version}")
            if dep_info.node_version:
                print(f"  ✓ Detected Node.js {dep_info.node_version}")
            if dep_info.django_version:
                print(f"  ✓ Detected Django {dep_info.django_version}")
            if dep_info.spring_boot_version:
                print(f"  ✓ Detected Spring Boot {dep_info.spring_boot_version}")
            
            # Log warnings
            if dep_info.warnings:
                print(f"  ⚠ {len(dep_info.warnings)} compatibility warning(s)")
                for warning in dep_info.warnings:
                    print(f"    - {warning}")
            
            # Log recommendations
            if dep_info.recommendations:
                print(f"  ℹ {len(dep_info.recommendations)} recommendation(s)")
                for rec in dep_info.recommendations[:3]:  # Show first 3
                    print(f"    - {rec}")
        
        except Exception as e:
            print(f"  ⚠ Dependency analysis failed: {str(e)}")
            # Create empty dep_info to avoid errors
            class EmptyDepInfo:
                python_version = None
                java_version = None
                node_version = None
                go_version = None
                django_version = None
                fastapi_version = None
                flask_version = None
                spring_boot_version = None
                express_version = None
                warnings = []
                recommendations = []
                has_version_conflicts = False
            dep_info = EmptyDepInfo()

        # Determine stack type - use None if not clearly detected
        stack_type = None
        confidence = 0.0
        if frameworks:
            stack_type = frameworks[0]
            confidence = 0.9
        elif languages:
            # Fallback: use language name as stack
            lang_map = {
                "JavaScript": "node",
                "Python": "python",
                "Java": "java",
                "Go": "go",
                "Rust": "rust",
                "Ruby": "ruby",
            }
            stack_type = lang_map.get(languages[0])
            confidence = 0.6

        context = RepositoryContext(
            repository_path=str(repo),
            project_languages=languages,
            package_managers=package_managers,
            frameworks=frameworks,
            build_tools=build_tools,
            existing_dockerfiles=existing_dockerfiles,
            existing_compose_files=existing_compose_files,
            detected_ports=detected_ports,
            environment_variables=env_vars,
            # NEW: Add dependency version information
            python_version=dep_info.python_version,
            java_version=dep_info.java_version,
            node_version=dep_info.node_version,
            go_version=dep_info.go_version,
            django_version=dep_info.django_version,
            fastapi_version=dep_info.fastapi_version,
            flask_version=dep_info.flask_version,
            spring_boot_version=dep_info.spring_boot_version,
            express_version=dep_info.express_version,
            dependency_warnings=dep_info.warnings,
            dependency_recommendations=dep_info.recommendations,
            has_version_conflicts=dep_info.has_version_conflicts,
        )
        return context, AnalysisResult(stack_type=stack_type, confidence=confidence)

    def _detect_ports(self, repo: Path) -> List[int]:
        ports: set[int] = set()
        for pattern in ["*.py", "*.js", "*.ts", "*.java", "*.yml", "*.yaml", "*.env"]:
            for file_path in repo.rglob(pattern):
                try:
                    text = file_path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                for candidate in [3000, 5000, 8000, 8080, 80]:
                    if str(candidate) in text:
                        ports.add(candidate)
        return sorted(list(ports))

    def _detect_env_vars(self, repo: Path) -> List[str]:
        env_vars: set[str] = set()
        env_file = repo / ".env"
        if env_file.exists():
            content = env_file.read_text(encoding="utf-8", errors="ignore")
            for line in content.splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    env_vars.add(line.split("=", 1)[0].strip())
        return sorted(list(env_vars))
