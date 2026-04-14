"""Analyze repository signals relevant to Terraform generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ..models.types import RepositoryContext


@dataclass
class AnalysisResult:
    cloud_provider: str = "aws"
    confidence: float = 0.0
    resources: List[str] = field(default_factory=list)


class AnalyzeProject:
    """Detect local repository characteristics for IaC generation."""

    def analyze(self, repository_path: str) -> tuple[RepositoryContext, AnalysisResult]:
        if repository_path.startswith("http://") or repository_path.startswith("https://"):
            return (
                RepositoryContext(repository_path=repository_path),
                AnalysisResult(),
            )

        repo = Path(repository_path)

        languages = self._detect_languages(repo)
        frameworks = self._detect_frameworks(repo)
        tf_files = [str(path) for path in repo.rglob("*.tf")]
        has_dockerfile = (repo / "Dockerfile").exists()
        has_k8s = self._has_k8s_manifests(repo)

        provider, confidence, resources = self._scan_infra_signals(repo, tf_files)

        context = RepositoryContext(
            repository_path=str(repo),
            project_languages=languages,
            frameworks=frameworks,
            existing_terraform_files=tf_files,
            detected_cloud_provider=provider,
            detected_resources=resources,
            has_dockerfile=has_dockerfile,
            has_k8s_manifests=has_k8s,
        )

        return (
            context,
            AnalysisResult(
                cloud_provider=provider or "aws",
                confidence=confidence,
                resources=resources,
            ),
        )

    def _scan_infra_signals(self, repo: Path, tf_files: List[str]) -> tuple[Optional[str], float, List[str]]:
        provider_scores = {"aws": 0, "azure": 0, "gcp": 0}
        resources: set[str] = set()

        files_to_scan: List[Path] = [Path(path) for path in tf_files]
        if not files_to_scan:
            files_to_scan.extend(repo.rglob("*.yaml"))
            files_to_scan.extend(repo.rglob("*.yml"))

        for file_path in files_to_scan[:300]:
            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore").lower()
            except OSError:
                continue

            if "provider \"aws\"" in text or "aws_" in text:
                provider_scores["aws"] += 3
            if "provider \"azurerm\"" in text or "azurerm_" in text:
                provider_scores["azure"] += 3
            if "provider \"google\"" in text or "google_" in text:
                provider_scores["gcp"] += 3

            if "aws_vpc" in text or "azurerm_virtual_network" in text or "google_compute_network" in text:
                resources.add("network")
            if "aws_ec2" in text or "aws_instance" in text or "azurerm_linux_virtual_machine" in text or "google_compute_instance" in text:
                resources.add("compute")
            if "ecs" in text or "container" in text or "cloud run" in text or "kubernetes" in text or "gke" in text or "aks" in text or "eks" in text:
                resources.add("container")
            if "rds" in text or "sql" in text or "postgres" in text or "mysql" in text:
                resources.add("database")
            if "s3" in text or "storage" in text or "bucket" in text or "blob" in text:
                resources.add("storage")

        winner = max(provider_scores, key=provider_scores.get)
        best_score = provider_scores[winner]
        if best_score <= 0:
            return None, 0.0, sorted(resources)

        confidence = min(0.95, best_score / 10.0)
        return winner, confidence, sorted(resources)

    def _detect_languages(self, repo: Path) -> List[str]:
        languages: List[str] = []

        if (repo / "package.json").exists():
            languages.append("JavaScript")
        if (repo / "requirements.txt").exists() or (repo / "pyproject.toml").exists():
            languages.append("Python")
        if (repo / "pom.xml").exists() or (repo / "build.gradle").exists() or (repo / "build.gradle.kts").exists():
            languages.append("Java")
        if (repo / "go.mod").exists():
            languages.append("Go")

        return languages

    def _detect_frameworks(self, repo: Path) -> List[str]:
        frameworks: List[str] = []

        package_json = repo / "package.json"
        if package_json.exists():
            try:
                content = package_json.read_text(encoding="utf-8", errors="ignore").lower()
                if "next" in content:
                    frameworks.append("nextjs")
                if "express" in content:
                    frameworks.append("express")
            except OSError:
                pass

        requirements = repo / "requirements.txt"
        if requirements.exists():
            try:
                content = requirements.read_text(encoding="utf-8", errors="ignore").lower()
                if "django" in content:
                    frameworks.append("django")
                if "fastapi" in content:
                    frameworks.append("fastapi")
                if "flask" in content:
                    frameworks.append("flask")
            except OSError:
                pass

        if (repo / "pom.xml").exists():
            frameworks.append("spring")

        return frameworks

    def _has_k8s_manifests(self, repo: Path) -> bool:
        for file_path in list(repo.rglob("*.yaml"))[:300] + list(repo.rglob("*.yml"))[:300]:
            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            lower = text.lower()
            if "apiversion:" in lower and "kind:" in lower:
                return True

        return False
