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
from src.config import DATA_DIR, LLM_CONFIG
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
        self.generate_file = GenerateFile(use_llm=LLM_CONFIG.get("enabled", False))
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
        repo_context: Optional[dict] = None,
    ) -> PipelineResult:
        """Process request to generate Docker configuration.

        Args:
            request: User request object
            repository_path: Path to the repository
            write_output_files: Whether to write output files
            repo_context: Optional pre-analyzed repository context from orchestrator
                         (if provided, supplements local analysis)
        """
        start = time.time()

        # Input from orchestrator: user intent + project context
        context, analysis = self.analyze_project.analyze(repository_path)

        # If orchestrator provided repo context, use it to override/supplement local analysis
        if repo_context:
            try:
                # Orchestrator context takes priority for language and framework detection
                orchestrator_stack = None
                
                # Extract stack from orchestrator's framework info (most reliable)
                if repo_context.get('frameworks'):
                    frameworks = repo_context.get('frameworks', [])
                    for fw in frameworks:
                        fw_lower = fw.lower()
                        if 'spring' in fw_lower or 'java' in fw_lower or 'maven' in fw_lower:
                            orchestrator_stack = 'spring'
                            break
                        elif 'node' in fw_lower or 'express' in fw_lower or 'next' in fw_lower:
                            orchestrator_stack = 'node'
                            break
                        elif 'python' in fw_lower or 'django' in fw_lower or 'flask' in fw_lower or 'fastapi' in fw_lower:
                            orchestrator_stack = 'python'
                            break
                        elif 'go' in fw_lower:
                            orchestrator_stack = 'go'
                            break
                        elif 'rust' in fw_lower:
                            orchestrator_stack = 'rust'
                            break
                
                # If no framework match, use build system
                if not orchestrator_stack and repo_context.get('build_system'):
                    build_sys = repo_context.get('build_system', '').lower()
                    if build_sys == 'maven' or build_sys == 'gradle':
                        orchestrator_stack = 'spring'
                    elif build_sys == 'npm' or build_sys == 'yarn':
                        orchestrator_stack = 'node'
                    elif build_sys == 'pip' or build_sys == 'poetry':
                        orchestrator_stack = 'python'
                
                # If still no match, use primary language
                if not orchestrator_stack and repo_context.get('languages'):
                    langs = repo_context.get('languages', [])
                    if langs:
                        primary_lang = langs[0]
                        lang_map = {
                            'Python': 'python',
                            'Java': 'spring',
                            'JavaScript': 'node',
                            'TypeScript': 'node',
                            'Go': 'go',
                            'Rust': 'rust',
                            'Ruby': 'ruby',
                        }
                        orchestrator_stack = lang_map.get(primary_lang)
                
                # Override local analysis with orchestrator's detection
                if orchestrator_stack:
                    analysis.stack_type = orchestrator_stack
                    analysis.confidence = 0.95  # High confidence from orchestrator
                    
            except (KeyError, AttributeError, TypeError) as e:
                # If repo_context is malformed, continue with local analysis
                print(f"[Docker Agent] Warning: Error processing repo_context: {e}")
                pass

        prompt_stack, prompt_stack_confidence, prompt_stack_scores = self.prompt_intent_resolver.resolve_stack(
            request.text
        )
        effective_stack = prompt_stack or analysis.stack_type
        
        # Debug logging
        print(f"[Docker Agent] Stack Detection Summary:")
        print(f"  - Local analysis: {analysis.stack_type} (confidence: {analysis.confidence})")
        print(f"  - Prompt analysis: {prompt_stack} (confidence: {prompt_stack_confidence})")
        print(f"  - Orchestrator context: {repo_context.get('frameworks') if repo_context else 'None'}")
        print(f"  - Effective stack: {effective_stack}")

        # Tools Layer - Retrieve relevant Docker examples using enhanced semantic chunking
        # This uses the new enhanced chunking system that breaks Dockerfiles into
        # metadata, stage, and instruction-group chunks for better matching
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


def run_pipeline(
    request_text: str,
    repository_path: str,
    write_output_files: bool = False,
    repo_context: Optional[dict] = None,
) -> PipelineResult:
    """Run the Docker pipeline.

    Args:
        request_text: User request text
        repository_path: Path to the repository
        write_output_files: Whether to write output files
        repo_context: Optional pre-analyzed repository context from orchestrator
    """
    request = UserRequest(text=request_text, repository_path=repository_path)
    pipeline = DockerPipeline()
    return pipeline.process_request(
        request=request,
        repository_path=repository_path,
        write_output_files=write_output_files,
        repo_context=repo_context,
    )
