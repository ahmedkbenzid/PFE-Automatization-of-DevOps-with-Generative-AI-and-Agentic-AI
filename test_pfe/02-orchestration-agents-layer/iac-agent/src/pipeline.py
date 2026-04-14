"""Main IaC Agent pipeline for Terraform generation."""

from __future__ import annotations

import os
import sys
import time
from typing import Optional

if __package__ is None or __package__ == "":
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

from src.components.analyze_project import AnalyzeProject
from src.components.generate_file import GenerateFile
from src.components.prompt_intent_resolver import PromptIntentResolver
from src.components.rag_kb import RAGKnowledgeBase
from src.components.validate import Validate
from src.components.write_files import WriteFiles
from src.components.benchmark import run_generation_benchmark, serialize_benchmark
from src.config import DATA_DIR, IAC_CONFIG
from src.models.types import PipelineResult, UserRequest


class IACPipeline:
    """Implements an IaC generation pipeline compatible with orchestrator contract."""

    def __init__(self):
        self.analyze_project = AnalyzeProject()
        self.prompt_intent_resolver = PromptIntentResolver()
        self.generate_file = GenerateFile()
        self.validate = Validate()
        self.write_files = WriteFiles()
        self.rag_kb = RAGKnowledgeBase(str(DATA_DIR))

    def process_request(
        self,
        request: UserRequest,
        repository_path: str,
        repo_context: Optional[dict] = None,
        write_output_files: bool = False,
    ) -> PipelineResult:
        start = time.time()

        context, analysis = self.analyze_project.analyze(repository_path)

        if repo_context:
            self._apply_orchestrator_context(context, analysis, repo_context)

        prompt_provider, prompt_confidence, provider_scores, resource_hints = self.prompt_intent_resolver.resolve(
            request.text
        )

        effective_provider = (
            prompt_provider
            or context.detected_cloud_provider
            or analysis.cloud_provider
            or IAC_CONFIG.get("default_provider", "aws")
        )

        rag_context = self.rag_kb.query(
            f"{request.text} terraform {effective_provider} {' '.join(resource_hints)}",
            top_k=3,
        )

        # Quick benchmark to compare template and llm generation quality/latency.
        benchmark_results = run_generation_benchmark(
            generator=self.generate_file,
            validator=self.validate,
            request=request,
            context=context,
            provider=effective_provider,
            resource_hints=resource_hints,
            rag_context=rag_context,
        )

        max_repair_attempts = max(0, int(IAC_CONFIG.get("max_repair_attempts", 2)))
        attempt = 0
        current_prompt = request.text
        validation = None
        terraform_config = None

        while True:
            terraform_config = self.generate_file.generate(
                request=UserRequest(text=current_prompt, repository_path=request.repository_path),
                context=context,
                provider=effective_provider,
                resource_hints=resource_hints,
                rag_context=rag_context,
                mode="auto",
            )
            validation = self.validate.run(terraform_config)
            terraform_config.is_valid = validation.is_valid
            terraform_config.generation_attempts = attempt + 1

            if validation.is_valid or attempt >= max_repair_attempts:
                break

            repair_context = self._build_repair_prompt(validation)
            current_prompt = (
                f"{request.text}\n\n"
                f"Repair attempt {attempt + 1}: fix Terraform syntax and validation issues.\n"
                f"Validation feedback:\n{repair_context}"
            )
            attempt += 1

        terraform_config.metadata["detected_provider"] = context.detected_cloud_provider
        terraform_config.metadata["analysis_provider"] = analysis.cloud_provider
        terraform_config.metadata["prompt_provider"] = prompt_provider
        terraform_config.metadata["prompt_provider_confidence"] = prompt_confidence
        terraform_config.metadata["prompt_provider_scores"] = provider_scores
        terraform_config.metadata["effective_provider"] = effective_provider
        terraform_config.metadata["benchmark"] = serialize_benchmark(benchmark_results)

        # validation already computed in loop

        written_files = self.write_files.run(
            terraform_config=terraform_config,
            repository_path=repository_path,
            write=write_output_files and terraform_config.is_valid,
        )
        terraform_config.metadata["written_files"] = written_files

        elapsed_ms = int((time.time() - start) * 1000)

        return PipelineResult(
            success=terraform_config.is_valid,
            request=request,
            terraform_config=terraform_config,
            context=context,
            validation=validation,
            error_message=None if terraform_config.is_valid else "Terraform validation failed.",
            processing_time_ms=elapsed_ms,
        )

    def _build_repair_prompt(self, validation) -> str:
        lines = []
        if validation.errors:
            lines.append("Errors:")
            for err in validation.errors:
                lines.append(f"- {err}")
        if validation.warnings:
            lines.append("Warnings:")
            for warn in validation.warnings:
                lines.append(f"- {warn}")
        if validation.suggestions:
            lines.append("Suggestions:")
            for suggestion in validation.suggestions:
                lines.append(f"- {suggestion}")
        return "\n".join(lines) if lines else "No details. Ensure terraform syntax correctness."

    def _apply_orchestrator_context(self, context, analysis, repo_context: dict) -> None:
        provider = self._detect_provider_from_repo_context(repo_context)
        if provider:
            context.detected_cloud_provider = provider
            analysis.cloud_provider = provider
            analysis.confidence = max(analysis.confidence, 0.95)

        if repo_context.get("languages"):
            context.project_languages = list(repo_context.get("languages", []))

        if repo_context.get("frameworks"):
            context.frameworks = list(repo_context.get("frameworks", []))

        if repo_context.get("package_managers"):
            context.package_managers = list(repo_context.get("package_managers", []))

        if repo_context.get("build_system"):
            context.build_system = repo_context.get("build_system")

        for field_name in [
            "python_version",
            "java_version",
            "node_version",
            "go_version",
            "django_version",
            "fastapi_version",
            "flask_version",
            "spring_boot_version",
            "express_version",
        ]:
            value = repo_context.get(field_name)
            if value:
                setattr(context, field_name, str(value))

        if repo_context.get("dependency_warnings"):
            context.dependency_warnings = list(repo_context.get("dependency_warnings", []))

        if repo_context.get("dependency_recommendations"):
            context.dependency_recommendations = list(repo_context.get("dependency_recommendations", []))

        context.has_version_conflicts = bool(repo_context.get("has_version_conflicts", False))

        if repo_context.get("has_terraform"):
            context.existing_terraform_files = list(repo_context.get("terraform_files", []))

    def _detect_provider_from_repo_context(self, repo_context: dict) -> Optional[str]:
        cloud_provider = str(repo_context.get("cloud_provider", "")).lower()
        if cloud_provider in {"aws", "azure", "gcp"}:
            return cloud_provider

        haystack_parts = []
        for key in ["frameworks", "package_managers", "languages"]:
            value = repo_context.get(key)
            if isinstance(value, list):
                haystack_parts.extend(str(item).lower() for item in value)
            elif isinstance(value, str):
                haystack_parts.append(value.lower())

        haystack = " ".join(haystack_parts)
        if any(token in haystack for token in ["aws", "ec2", "s3", "eks", "ecr"]):
            return "aws"
        if any(token in haystack for token in ["azure", "azurerm", "aks", "acr"]):
            return "azure"
        if any(token in haystack for token in ["gcp", "google", "gke", "cloud run"]):
            return "gcp"
        return None


def run_pipeline(
    request_text: str,
    repository_path: str,
    repo_context: Optional[dict] = None,
    write_output_files: bool = False,
) -> PipelineResult:
    """Run the IaC pipeline.

    Signature order intentionally matches orchestrator invocation:
    run_pipeline(user_prompt, repo_path, repo_ctx, False)
    """
    request = UserRequest(text=request_text, repository_path=repository_path)
    pipeline = IACPipeline()
    return pipeline.process_request(
        request=request,
        repository_path=repository_path,
        repo_context=repo_context,
        write_output_files=write_output_files,
    )
