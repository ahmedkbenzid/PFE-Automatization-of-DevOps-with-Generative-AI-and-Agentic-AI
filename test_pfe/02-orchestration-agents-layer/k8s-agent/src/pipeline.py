"""Main Kubernetes agent pipeline."""

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
from src.config import DATA_DIR
from src.models.types import PipelineResult, UserRequest


class K8sPipeline:
    def __init__(self):
        self.analyze_project = AnalyzeProject()
        self.prompt_intent_resolver = PromptIntentResolver()
        self.rag_kb = RAGKnowledgeBase(str(DATA_DIR))
        self.generate_file = GenerateFile()
        self.validate = Validate()
        self.write_files = WriteFiles()

    def process_request(
        self,
        request: UserRequest,
        repository_path: str,
        write_output_files: bool = False,
        repo_context: Optional[dict] = None,
    ) -> PipelineResult:
        start = time.time()

        context, analysis = self.analyze_project.analyze(repository_path)

        if repo_context:
            self._apply_orchestrator_context(context, repo_context)

        intent = self.prompt_intent_resolver.resolve(request.text)

        if not intent.get("app_name"):
            intent["app_name"] = self._derive_app_name_from_context(context)

        if not intent.get("image"):
            intent["image"] = self._infer_image(repo_context, context)

        rag_pages = self.rag_kb.query(
            query_text=f"{request.text} kubernetes deployment service ingress configmap secret rbac networkpolicy",
            top_k=3,
        )
        rag_hints = self._derive_rag_hints(request.text, rag_pages)

        manifests = self.generate_file.generate(request, context, intent, rag_hints=rag_hints)
        manifests.metadata["analysis"] = analysis
        manifests.metadata["intent"] = intent
        manifests.metadata["rag_pages"] = [page.get("page_id") or page.get("title") for page in rag_pages]

        validation = self.validate.run(manifests)
        manifests.is_valid = validation.is_valid

        written_files = self.write_files.run(
            manifests=manifests,
            repository_path=repository_path,
            write=write_output_files and manifests.is_valid,
        )
        manifests.metadata["written_files"] = written_files

        elapsed_ms = int((time.time() - start) * 1000)

        return PipelineResult(
            success=manifests.is_valid,
            request=request,
            k8s_manifests=manifests,
            context=context,
            validation=validation,
            error_message=None if manifests.is_valid else "Kubernetes manifest validation failed.",
            processing_time_ms=elapsed_ms,
        )

    def _apply_orchestrator_context(self, context, repo_context: dict) -> None:
        if repo_context.get("languages"):
            context.project_languages = list(repo_context.get("languages", []))
        if repo_context.get("frameworks"):
            context.frameworks = list(repo_context.get("frameworks", []))
        if repo_context.get("package_managers"):
            context.package_managers = list(repo_context.get("package_managers", []))
        if repo_context.get("build_system"):
            context.build_system = str(repo_context.get("build_system"))
        if isinstance(repo_context.get("has_dockerfile"), bool):
            context.has_dockerfile = repo_context.get("has_dockerfile")

        docker_output = (repo_context.get("docker_output") or {}) if isinstance(repo_context, dict) else {}
        if not isinstance(docker_output, dict):
            docker_output = {}

        image_hint = docker_output.get("image_name") or repo_context.get("docker_image")
        if image_hint:
            context.image_name = str(image_hint)

    def _derive_app_name_from_context(self, context) -> str:
        repository_path = context.repository_path or "app"
        return repository_path.rstrip("/\\").split("/")[-1].split("\\")[-1] or "app"

    def _infer_image(self, repo_context: Optional[dict], context) -> str:
        if isinstance(repo_context, dict):
            docker_data = ((repo_context.get("docker-agent") or {}).get("data") or {})
            config = docker_data.get("configuration") if isinstance(docker_data, dict) else {}
            if isinstance(config, dict):
                generated_name = config.get("image_name") or config.get("repository")
                if generated_name:
                    return str(generated_name)

            docker_image = repo_context.get("docker_image")
            if docker_image:
                return str(docker_image)

        return context.image_name or "app:latest"

    def _derive_rag_hints(self, request_text: str, pages: list[dict]) -> dict:
        request_lower = (request_text or "").lower()
        tags = " ".join(
            " ".join(page.get("tags", [])) for page in pages if isinstance(page.get("tags"), list)
        ).lower()

        service_type = "ClusterIP"
        if "loadbalancer" in request_lower or "external" in request_lower:
            service_type = "LoadBalancer"
        elif "nodeport" in request_lower:
            service_type = "NodePort"
        elif "loadbalancer" in tags:
            service_type = "LoadBalancer"
        elif "nodeport" in tags:
            service_type = "NodePort"

        return {
            "service_type": service_type,
            "security_recommended": any(token in tags for token in ["rbac", "networkpolicy", "security"]),
            "source_pages": [page.get("page_id") for page in pages],
        }


def run_pipeline(
    request_text: str,
    repository_path: str,
    write_output_files: bool = False,
    repo_context: Optional[dict] = None,
) -> PipelineResult:
    request = UserRequest(text=request_text, repository_path=repository_path)
    pipeline = K8sPipeline()
    return pipeline.process_request(
        request=request,
        repository_path=repository_path,
        write_output_files=write_output_files,
        repo_context=repo_context,
    )
