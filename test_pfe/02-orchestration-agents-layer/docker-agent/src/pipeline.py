"""Main Docker Agent pipeline aligned with architecture diagram."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Optional

if __package__ is None or __package__ == "":
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

from src.components.analyze_project import AnalyzeProject
from src.components.generate_file import GenerateFile
from src.components.optimize_image import OptimizeImage
from src.components.prompt_intent_resolver import PromptIntentResolver
from src.components.rag_kb import RAGKnowledgeBase
from src.components.scout_scan import ScoutScan
from src.components.validate import Validate
from src.components.write_files import WriteFiles
from src.config import DATA_DIR
from src.models.types import DockerLockFile, PipelineResult, UserRequest
from src.validation.hadolint_validator import HadolintValidator
from src.validation.policy_gates import PolicyGates
from src.validation.trivy_validator import TrivyValidator


class DockerPipeline:
    """Implements the Docker Agent structure shown in architecture."""

    def __init__(self):
        # Tools Layer
        self.analyze_project = AnalyzeProject()
        self.prompt_intent_resolver = PromptIntentResolver()
        self.generate_file = GenerateFile()
        self.validate = Validate()
        self.rag_kb = RAGKnowledgeBase(str(DATA_DIR / "knowledge_base"))
        self.scout_scan = ScoutScan()
        self.optimize_image = OptimizeImage()
        self.write_files = WriteFiles()

        # Validation Layer
        self.hadolint = HadolintValidator()
        self.trivy = TrivyValidator()
        self.policy_gates = PolicyGates()

    def process_request(
        self,
        request: UserRequest,
        repository_path: str,
        write_output_files: bool = False,
    ) -> PipelineResult:
        start = time.time()

        # Input from orchestrator: user intent + project context
        context, analysis = self.analyze_project.analyze(repository_path)
        prompt_stack, prompt_stack_confidence, prompt_stack_scores = self.prompt_intent_resolver.resolve_stack(
            request.text
        )
        effective_stack = prompt_stack or analysis.stack_type

        # Tools Layer
        rag_context = self.rag_kb.query(
            f"{request.text} {effective_stack} Dockerfile best practices",
            top_k=3,
        )

        configuration = self.generate_file.generate(request, context, effective_stack)
        configuration.metadata["rag_pages"] = [
            page.get("page_id") or page.get("title") for page in rag_context
        ]
        configuration.metadata["detected_stack"] = analysis.stack_type
        configuration.metadata["prompt_stack"] = prompt_stack
        configuration.metadata["prompt_stack_confidence"] = prompt_stack_confidence
        configuration.metadata["prompt_stack_scores"] = prompt_stack_scores
        configuration.metadata["effective_stack"] = effective_stack

        configuration = self.optimize_image.run(configuration)
        validation_result = self.validate.run(configuration)
        security_result = self.scout_scan.run(configuration)

        # Validation Layer gates: hadolint, trivy, policy gates
        hadolint_result = self.hadolint.run(configuration.dockerfile_content or "")
        trivy_result = self.trivy.run(configuration.dockerfile_content or "")
        policy_result = self.policy_gates.run(configuration.dockerfile_content or "")

        gate_errors = []
        if not hadolint_result["passed"]:
            gate_errors.extend([f"hadolint: {issue}" for issue in hadolint_result["issues"]])
        if not trivy_result["passed"]:
            gate_errors.extend([f"trivy: {issue}" for issue in trivy_result["findings"]])
        if not policy_result["passed"]:
            gate_errors.extend([f"policy: {issue}" for issue in policy_result["violations"]])

        validation_result.errors.extend(gate_errors)
        validation_result.is_valid = validation_result.is_valid and len(gate_errors) == 0

        # Validation decision
        configuration.is_valid = validation_result.is_valid and security_result.is_safe

        written_files = self.write_files.run(
            configuration=configuration,
            repository_path=repository_path,
            write=write_output_files and configuration.is_valid,
        )
        configuration.metadata["written_files"] = written_files

        lock_file = DockerLockFile(
            base_images=self._extract_base_images(configuration.dockerfile_content or ""),
            dependencies={},
        )

        elapsed_ms = int((time.time() - start) * 1000)

        return PipelineResult(
            success=configuration.is_valid,
            request=request,
            configuration=configuration,
            intent=None,
            context=context,
            validation=validation_result,
            security=security_result,
            lock_file=lock_file,
            error_message=None if configuration.is_valid else "Validation failed in one or more gates.",
            processing_time_ms=elapsed_ms,
        )

    def _extract_base_images(self, dockerfile_content: str) -> dict[str, str]:
        images: dict[str, str] = {}
        for line in dockerfile_content.splitlines():
            line = line.strip()
            if line.startswith("FROM "):
                image = line.replace("FROM ", "").split(" AS ")[0].strip()
                images[image] = image
        return images


def run_pipeline(request_text: str, repository_path: str, write_output_files: bool = False) -> PipelineResult:
    request = UserRequest(text=request_text, repository_path=repository_path)
    pipeline = DockerPipeline()
    return pipeline.process_request(
        request=request,
        repository_path=repository_path,
        write_output_files=write_output_files,
    )
