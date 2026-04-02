"""Main CI/CD Agent Pipeline"""
import os
import sys
import time
import re
from typing import Optional, Dict, Any, List

if __package__ is None or __package__ == "":
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

from src.config import Config
from src.models.types import (
    UserRequest, PipelineResult, RequestType, GeneratedWorkflow
)
from src.components.llm_client import LLMClient
from src.components.intent_layer import IntentLayer
from src.components.prompt_intent_resolver import PromptIntentResolver
from src.components.context_collector import ContextCollector
from src.components.template_manager import TemplateManager
from src.components.yaml_generator import YAMLGenerator
from src.components.schema_validator import SchemaValidator
from src.components.security_guardrails import SecurityGuardrails
from src.components.workflow_compiler import WorkflowCompiler
from src.components.github_integration import GitHubIntegration
from src.datasets.dataset_manager import DatasetManager

class CICDPipeline:
    """Main CI/CD Agent Pipeline"""
    
    def __init__(self, strict_security: bool = False):
        self.llm_client = LLMClient()
        self.intent_layer = IntentLayer(self.llm_client)
        self.prompt_intent_resolver = PromptIntentResolver()
        self.context_collector = ContextCollector()
        self.template_manager = TemplateManager()
        self.yaml_generator = YAMLGenerator(self.llm_client)
        self.schema_validator = SchemaValidator()
        self.security_guardrails = SecurityGuardrails(strict_mode=strict_security)
        self.workflow_compiler = WorkflowCompiler()
        self.github_integration = GitHubIntegration()
        self.dataset_manager = DatasetManager()
        
        self.metrics = {
            'total_requests': 0,
            'successful_workflows': 0,
            'failed_workflows': 0,
            'total_attempts': 0,
            'avg_generation_latency_ms': 0.0,
        }
    
    def process_request(self, request: UserRequest, repo_path: Optional[str] = None,
                       max_retries: Optional[int] = None,
                       repo_context: Optional[Dict[str, Any]] = None) -> PipelineResult:
        """Main pipeline: process user request to generated workflow

        Args:
            request: User request object
            repo_path: Optional path to local repository
            max_retries: Maximum number of retries for generation
            repo_context: Optional pre-analyzed repository context from orchestrator
                         (if provided, skips local context collection)
        """
        
        max_retries = max_retries or Config.MAX_RETRIES
        start_time = time.time()
        attempt = 0
        errors = []
        
        self.metrics['total_requests'] += 1
        
        print(f"\n{'='*80}")
        print(f"Processing request: {request.text[:100]}...")
        print(f"{'='*80}\n")
        
        # Step 1: Intent extraction and metadata
        print("[STEP 1] Extracting intent and metadata...")
        try:
            intent_metadata, markdown_metadata = self.intent_layer.process_request(request)
            print(f"✓ Intent: {intent_metadata.intent}")
            print(f"✓ Type: {intent_metadata.request_type.value}")
            print(f"✓ Confidence: {intent_metadata.confidence:.2%}\n")
        except Exception as e:
            errors.append(f"Intent extraction failed: {str(e)}")
            return self._create_failed_result(errors, 0, time.time() - start_time)
        
        # Step 2: Context collection (use pre-analyzed context if provided)
        print("[STEP 2] Collecting repository context...")
        try:
            if repo_context:
                # Use pre-analyzed context from orchestrator
                print("  (Using pre-analyzed context from orchestrator)")
                # Convert orchestrator format to local format if needed
                local_repo_context = {
                    'languages': repo_context.get('languages', []),
                    'build_system': repo_context.get('build_system'),
                    'package_managers': repo_context.get('package_managers', []),
                    'frameworks': repo_context.get('frameworks', []),
                    'has_dockerfile': repo_context.get('has_dockerfile', False),
                    'has_ci_workflows': repo_context.get('has_ci_workflows', False),
                    'existing_workflows': repo_context.get('existing_workflows', []),
                }
            elif repo_path:
                local_repo_context = self.context_collector.collect_from_local_repo(repo_path)
            else:
                local_repo_context = {}
            print(f"✓ Languages detected: {', '.join(local_repo_context.get('languages', []))}")
            print(f"✓ Build system: {local_repo_context.get('build_system', 'None')}\n")
        except Exception as e:
            errors.append(f"Context collection failed: {str(e)}")
            local_repo_context = {}
        
        # Step 3: Find relevant examples from datasets
        print("[STEP 3] Finding relevant examples from datasets...")
        try:
            relevant_examples = []
            preferred_languages = self._infer_preferred_languages(
                request.text,
                intent_metadata.keywords,
                local_repo_context,
            )

            for lang in local_repo_context.get('languages', []):
                examples = self.dataset_manager.find_similar_examples(lang)
                relevant_examples.extend(examples)

            if not relevant_examples:
                query_examples = self.dataset_manager.get_examples_by_pattern(request.text)
                relevant_examples.extend(query_examples)

            if not relevant_examples:
                relevant_examples.extend(list(self.dataset_manager.examples.values()))

            deduplicated = {}
            for example in relevant_examples:
                deduplicated[getattr(example, "id", getattr(example, "name", str(example)))] = example
            relevant_examples = list(deduplicated.values())
            relevant_examples = self._rank_examples_by_relevance(
                relevant_examples,
                request.text,
                preferred_languages,
            )

            retrieval_query_parts = [request.text, intent_metadata.intent, " ".join(intent_metadata.keywords)]
            if local_repo_context.get("languages"):
                retrieval_query_parts.append(" ".join(local_repo_context.get("languages", [])))
            if preferred_languages:
                retrieval_query_parts.append(" ".join(preferred_languages))
            # Retrieve relevant knowledge using enhanced semantic chunking
            # This uses the new enhanced chunking system that breaks workflows into
            # metadata, job, and step chunks for better matching
            retrieved_knowledge = self.dataset_manager.retrieve_knowledge(knowledge_query, top_k=3)

            print(f"✓ Found {len(relevant_examples)} relevant examples")
            if preferred_languages:
                print(f"✓ Preferred stack: {', '.join(preferred_languages)}")
            print(f"✓ Retrieved {len(retrieved_knowledge)} knowledge pages\n")
        except Exception as e:
            print(f"Note: Could not fetch examples: {str(e)}\n")
            relevant_examples = []
            retrieved_knowledge = []
        
        # Step 4-6: Generation with retries
        workflow = None
        validation_result = None
        security_audit = None
        for attempt in range(1, max_retries + 1):
            print(f"[STEP 4] Generating workflow (Attempt {attempt}/{max_retries})...")
            
            try:
                # Build detailed prompt
                prompt = self.intent_layer.build_context_prompt(
                    user_request=request,
                    intent=intent_metadata,
                    repo_context=local_repo_context,
                    knowledge_pages=retrieved_knowledge,
                    reference_examples=relevant_examples[:2],
                )
                
                # Generate YAML
                workflow = self.yaml_generator.generate_from_prompt(prompt)
                print(f"✓ Generated YAML ({len(workflow.yaml_content)} chars)\n")
                
                # Step 5: Schema validation
                print("[STEP 5] Validating workflow schema...")
                parsed_yaml = self.yaml_generator.parse_yaml(workflow.yaml_content)
                
                if not parsed_yaml:
                    is_valid, syntax_error = self.yaml_generator.validate_yaml_syntax(workflow.yaml_content)
                    if not is_valid:
                        workflow.validation_errors.append(f"YAML syntax error: {syntax_error}")
                        print(f"✗ YAML syntax error\n")
                        continue

                    parsed_yaml = self.yaml_generator.parse_yaml(workflow.yaml_content)
                    if not parsed_yaml:
                        workflow.validation_errors.append("Could not parse YAML after syntax normalization")
                        print("✗ Could not parse YAML after normalization\n")
                        continue
                
                validation_result = self.schema_validator.validate_workflow(parsed_yaml, self.yaml_generator)
                workflow.validation_errors.extend(validation_result.errors)
                
                if validation_result.is_valid:
                    print(f"✓ Schema validation passed")
                    print(f"  Warnings: {len(validation_result.warnings)}")
                    print(f"  Suggestions: {len(validation_result.suggestions)}\n")
                    workflow.is_valid = True
                else:
                    print(f"✗ Schema validation failed ({len(validation_result.errors)} errors)")
                    for error in validation_result.errors[:3]:
                        print(f"  - {error}")
                    
                    # Try to auto-fix
                    if attempt < max_retries:
                        print("\n[AUTO-FIX] Attempting to fix common issues...")
                        workflow.yaml_content = self.yaml_generator.auto_fix_common_issues(workflow.yaml_content)
                        print("Retrying validation...\n")
                        continue
                
                # Step 6: Security audit
                print("[STEP 6] Performing security audit...")
                security_audit = self.security_guardrails.audit_workflow(parsed_yaml, workflow.yaml_content)
                
                if security_audit.is_safe:
                    print(f"✓ Security audit passed")
                else:
                    print(f"⚠ Security audit found {len(security_audit.risks)} risks:")
                    for risk in security_audit.risks[:3]:
                        print(f"  - [{risk.get('severity', 'unknown').upper()}] {risk.get('description', 'Unknown risk')}")
                
                print()
                
                # Success - break out of retry loop
                if workflow.is_valid:
                    break
                
            except Exception as e:
                errors.append(f"Error on attempt {attempt}: {str(e)}")
                print(f"✗ Generation error: {str(e)}\n")
                if attempt == max_retries:
                    return self._create_failed_result(errors, attempt, time.time() - start_time)
        
        if not workflow or not workflow.is_valid:
            errors.append("Failed to generate valid workflow after all attempts")
            return self._create_failed_result(errors, attempt, time.time() - start_time)
        
        # Step 7: Compile and generate lock file
        print("[STEP 7] Compiling workflow and generating lock file...")
        try:
            compiled_yaml, lock_file = self.workflow_compiler.compile_workflow(
                workflow.yaml_content,
                workflow_name=f"{request.request_type.value}-workflow",
                metadata={
                    'intent': intent_metadata.intent,
                    'repo_context': local_repo_context,
                }
            )
            checksum_preview = lock_file.checksum[:12] if lock_file and lock_file.checksum else "n/a"
            print(f"✓ Workflow compiled with checksum: {checksum_preview}...")
            print(f"✓ Generated lock file\n")
        except Exception as e:
            errors.append(f"Compilation failed: {str(e)}")
            compiled_yaml = workflow.yaml_content
            lock_file = None
        
        # Calculate metrics
        latency_ms = (time.time() - start_time) * 1000
        self.metrics['total_attempts'] += attempt
        self.metrics['avg_generation_latency_ms'] = (
            (self.metrics['avg_generation_latency_ms'] * (self.metrics['successful_workflows']) + latency_ms) /
            (self.metrics['successful_workflows'] + 1)
        )
        self.metrics['successful_workflows'] += 1
        
        # Print summary
        print(f"{'='*80}")
        print(f"PIPELINE COMPLETED SUCCESSFULLY")
        print(f"Duration: {latency_ms:.0f}ms | Attempts: {attempt}")
        print(f"{'='*80}\n")
        
        return PipelineResult(
            success=True,
            workflow_yaml=compiled_yaml,
            lock_file=lock_file,
            validation_result=validation_result,
            security_audit=security_audit,
            generation_latency_ms=latency_ms,
            attempts=attempt,
            errors=errors,
        )
    
    def _create_failed_result(self, errors: list, attempts: int, elapsed_seconds: float) -> PipelineResult:
        """Create a failed pipeline result

        Args:
            errors: List of error messages
            attempts: Number of attempts made
            elapsed_seconds: Time elapsed in seconds (will be converted to ms)
        """
        self.metrics['failed_workflows'] += 1

        return PipelineResult(
            success=False,
            workflow_yaml="",
            lock_file=None,
            validation_result=None,
            security_audit=None,
            generation_latency_ms=elapsed_seconds * 1000,
            attempts=attempts,
            errors=errors,
        )

    def _infer_preferred_languages(
        self,
        request_text: str,
        intent_keywords: List[str],
        repo_context: Dict[str, Any],
    ) -> List[str]:
        return self.prompt_intent_resolver.infer_preferred_languages(
            request_text=request_text,
            intent_keywords=intent_keywords,
            repo_languages=repo_context.get("languages", []),
        )

    def _rank_examples_by_relevance(self, examples: List[Any], request_text: str, preferred_languages: List[str]) -> List[Any]:
        if not examples:
            return examples

        request_lower = request_text.lower()
        query_tokens = set(re.findall(r"[a-zA-Z0-9_\-.]+", request_lower))

        def score(example: Any) -> float:
            language = getattr(example, "language", "")
            name = getattr(example, "name", "")
            trigger = getattr(example, "trigger", "")
            yaml_content = getattr(example, "yaml_content", "")
            success_rate = float(getattr(example, "success_rate", 0) or 0)

            searchable = f"{name} {language} {trigger} {yaml_content}".lower()
            example_tokens = set(re.findall(r"[a-zA-Z0-9_\-.]+", searchable))
            overlap = len(query_tokens.intersection(example_tokens))

            total_score = overlap + success_rate

            if preferred_languages:
                if language in preferred_languages:
                    total_score += 8
                else:
                    total_score -= 2

            if "sonar" in request_lower and "sonar" in searchable:
                total_score += 8
            if "spring" in request_lower and "spring" in searchable:
                total_score += 6
            if "maven" in request_lower and "mvn" in searchable:
                total_score += 4

            return total_score

        return sorted(examples, key=score, reverse=True)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get pipeline metrics"""
        return {
            **self.metrics,
            'success_rate': (
                self.metrics['successful_workflows'] / self.metrics['total_requests']
                if self.metrics['total_requests'] > 0 else 0
            ),
        }


def main() -> None:
    """Script entrypoint for direct execution."""
    print("CICDPipeline module loaded successfully.")
    print("Use test_pipeline.py for full test flow or instantiate CICDPipeline in your code.")


if __name__ == "__main__":
    main()
