"""Tools Layer: analyze_project component."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from src.models.types import RepositoryContext


@dataclass
class AnalysisResult:
    stack_type: str
    confidence: float


class AnalyzeProject:
    """Detect repository stack and core containerization signals."""

    def analyze(self, repository_path: str) -> tuple[RepositoryContext, AnalysisResult]:
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
