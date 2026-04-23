"""Analyze repository signals relevant to Kubernetes manifest generation."""

from __future__ import annotations

from pathlib import Path

from ..models.types import RepositoryContext


class AnalyzeProject:
    def analyze(self, repository_path: str) -> tuple[RepositoryContext, dict]:
        if repository_path.startswith("http://") or repository_path.startswith("https://"):
            context = RepositoryContext(repository_path=repository_path)
            return context, {"confidence": 0.0, "image_name": None}

        repo = Path(repository_path)
        project_languages = self._detect_languages(repo)
        frameworks = self._detect_frameworks(repo)
        package_managers = self._detect_package_managers(repo)
        build_system = self._detect_build_system(repo)

        service_port = 80
        container_port = 8000

        context = RepositoryContext(
            repository_path=str(repo),
            project_languages=project_languages,
            frameworks=frameworks,
            package_managers=package_managers,
            build_system=build_system,
            has_dockerfile=(repo / "Dockerfile").exists(),
            has_k8s_manifests=self._has_k8s_manifests(repo),
            image_name=self._infer_image_name(repo),
            service_port=service_port,
            container_port=container_port,
        )
        return context, {"confidence": 0.85, "image_name": context.image_name}

    def _infer_image_name(self, repo: Path) -> str:
        normalized = "".join(ch if (ch.isalnum() or ch in {"-", "_"}) else "-" for ch in repo.name.lower())
        normalized = normalized.strip("-") or "app"
        return f"{normalized}:latest"

    def _detect_languages(self, repo: Path) -> list[str]:
        languages = []
        if (repo / "requirements.txt").exists() or (repo / "pyproject.toml").exists():
            languages.append("Python")
        if (repo / "package.json").exists():
            languages.append("JavaScript")
        if (repo / "pom.xml").exists() or (repo / "build.gradle").exists() or (repo / "build.gradle.kts").exists():
            languages.append("Java")
        if (repo / "go.mod").exists():
            languages.append("Go")
        return languages

    def _detect_frameworks(self, repo: Path) -> list[str]:
        frameworks = []

        requirements = repo / "requirements.txt"
        if requirements.exists():
            text = requirements.read_text(encoding="utf-8", errors="ignore").lower()
            if "fastapi" in text:
                frameworks.append("fastapi")
            if "flask" in text:
                frameworks.append("flask")
            if "django" in text:
                frameworks.append("django")

        package_json = repo / "package.json"
        if package_json.exists():
            text = package_json.read_text(encoding="utf-8", errors="ignore").lower()
            if "express" in text:
                frameworks.append("express")
            if "next" in text:
                frameworks.append("nextjs")

        if (repo / "pom.xml").exists():
            frameworks.append("spring")

        return frameworks

    def _detect_package_managers(self, repo: Path) -> list[str]:
        managers = []
        if (repo / "requirements.txt").exists():
            managers.append("pip")
        if (repo / "poetry.lock").exists():
            managers.append("poetry")
        if (repo / "package-lock.json").exists():
            managers.append("npm")
        if (repo / "yarn.lock").exists():
            managers.append("yarn")
        if (repo / "pom.xml").exists():
            managers.append("maven")
        return managers

    def _detect_build_system(self, repo: Path) -> str | None:
        if (repo / "pom.xml").exists():
            return "maven"
        if (repo / "build.gradle").exists() or (repo / "build.gradle.kts").exists():
            return "gradle"
        if (repo / "package.json").exists():
            return "npm"
        if (repo / "requirements.txt").exists() or (repo / "pyproject.toml").exists():
            return "pip"
        return None

    def _has_k8s_manifests(self, repo: Path) -> bool:
        candidates = list(repo.rglob("*.yaml"))[:250] + list(repo.rglob("*.yml"))[:250]
        for path in candidates:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore").lower()
            except OSError:
                continue
            if "apiversion:" in text and "kind:" in text:
                return True
        return False
