"""YAML workflow generation from LLM output"""
import yaml
from typing import Dict, Any, Optional, List
from src.models.types import GeneratedWorkflow
from src.components.llm_client import LLMClient
from src.components.rag_kb import RAGKnowledgeBase
from pathlib import Path
import os


class YAMLGenerator:
    """Generate and manage YAML workflows with RAG support"""

    def __init__(self, llm_client: LLMClient, kb_path: Optional[str] = None):
        self.llm_client = llm_client

        # --- RAG KB path resolution (explicit > env var > convention-based) ---
        if kb_path:
            resolved_kb_path = Path(kb_path)
        elif os.environ.get("CICD_KB_PATH"):
            resolved_kb_path = Path(os.environ["CICD_KB_PATH"])
        else:
            # Convention: datasets/knowledge_base/ relative to the backend root
            # Walk up from this file's location to find the backend root
            # yaml_generator.py lives at: backend/agents/cicd_agent/yaml_generator.py
            # So parent.parent.parent = backend/
            resolved_kb_path = Path(__file__).parent.parent.parent / "datasets" / "knowledge_base"

        if resolved_kb_path.exists():
            # Validate the KB has the expected page_index.json before initializing
            page_index = resolved_kb_path / "page_index.json"
            if page_index.exists():
                self.rag_kb = RAGKnowledgeBase(str(resolved_kb_path))
                print(f"[YAML Generator] RAG knowledge base initialized: {resolved_kb_path}")
            else:
                self.rag_kb = None
                print(
                    f"[YAML Generator] WARNING: KB directory exists but page_index.json is missing at "
                    f"{page_index}. RAG disabled."
                )
        else:
            self.rag_kb = None
            print(
                f"[YAML Generator] WARNING: Knowledge base directory not found at {resolved_kb_path}. "
                f"RAG disabled. Set CICD_KB_PATH env var or pass kb_path= to override."
            )

    def generate_from_prompt(self, prompt: str) -> GeneratedWorkflow:
        """Generate YAML from a detailed prompt, enhanced with RAG examples"""

        # --- RAG retrieval ---
        rag_context: List[Dict[str, Any]] = []
        if self.rag_kb:
            try:
                rag_context = self.rag_kb.query(prompt, top_k=3)
                print(f"[YAML Generator] Retrieved {len(rag_context)} workflow examples from RAG")
                if not rag_context:
                    print(
                        "[YAML Generator] WARNING: RAG returned 0 results. "
                        "Check that page_index.json structure is correct and pages exist on disk."
                    )
            except Exception as e:
                print(f"[YAML Generator] RAG retrieval failed (continuing without context): {e}")
        else:
            print("[YAML Generator] RAG not available — generating without knowledge base context")

        # --- Build enriched prompt with RAG context injected ---
        enriched_prompt = self._build_enriched_prompt(prompt, rag_context)

        # --- LLM call ---
        yaml_content = self.llm_client.generate_workflow_yaml(enriched_prompt, rag_context=rag_context)
        yaml_content = self._sanitize_llm_yaml(yaml_content)

        workflow = GeneratedWorkflow(
            yaml_content=yaml_content,
            metadata={
                "generation_method": "llm+rag" if rag_context else "llm",
                "rag_examples_used": len(rag_context),
                "rag_sources": [r.get("title") for r in rag_context] if rag_context else [],
                "rag_pages": [r.get("page_id") or r.get("title") for r in rag_context] if rag_context else [],
            },
            is_valid=False,
            attempts=1,
        )

        return workflow

    def _build_enriched_prompt(self, original_prompt: str, rag_context: List[Dict[str, Any]]) -> str:
        """
        Inject RAG-retrieved examples directly into the prompt so that even if
        llm_client.generate_workflow_yaml() ignores the rag_context= parameter,
        the context is still present in the prompt text itself.
        """
        if not rag_context:
            return original_prompt

        context_blocks = []
        for i, result in enumerate(rag_context, start=1):
            title = result.get("title", f"Example {i}")
            content = result.get("content", "")
            if content:
                context_blocks.append(
                    f"### Reference Example {i}: {title}\n```yaml\n{content}\n```"
                )

        if not context_blocks:
            return original_prompt

        context_section = "\n\n".join(context_blocks)

        enriched = (
            f"{original_prompt}\n\n"
            f"---\n"
            f"## Relevant CI/CD Knowledge Base Examples\n"
            f"Use the following verified examples as references for best practices, "
            f"correct action versions, Maven usage, Docker caching, and platform-specific patterns. "
            f"Do NOT copy them verbatim — adapt them to the task above.\n\n"
            f"{context_section}\n"
            f"---\n"
        )

        return enriched

    def _sanitize_llm_yaml(self, raw_output: str) -> str:
        """Strip markdown wrappers and normalize raw LLM YAML output."""
        if not raw_output:
            return raw_output

        cleaned = raw_output.strip()

        # Remove all ``` fences (```yaml, ```yml, ``` alone)
        lines = [line for line in cleaned.splitlines() if not line.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()

        # Strip leading language hint if present (e.g. "yaml\n...")
        if cleaned.lower().startswith("yaml\n"):
            cleaned = cleaned[5:]
        elif cleaned.lower().startswith("yml\n"):
            cleaned = cleaned[4:]

        # Find the first real YAML key and strip everything before it
        yaml_start_keys = ("name:", "on:", "jobs:", "permissions:", "env:")
        cleaned_lines = cleaned.splitlines()
        start_index = 0
        for index, line in enumerate(cleaned_lines):
            if line.strip().lower().startswith(yaml_start_keys):
                start_index = index
                break
        candidate_lines = cleaned_lines[start_index:]

        # Trim trailing non-YAML prose
        trimmed_lines = []
        for line in candidate_lines:
            stripped = line.strip()
            if stripped and not line.startswith((" ", "\t", "-", "#")) and ":" not in line:
                break
            trimmed_lines.append(line)

        return "\n".join(trimmed_lines).strip()

    def parse_yaml(self, yaml_content: str) -> Optional[Dict[str, Any]]:
        """Parse YAML content, handling the boolean True key issue for 'on:'"""
        yaml_content = self._sanitize_llm_yaml(yaml_content)
        try:
            parsed = yaml.safe_load(yaml_content)
            if isinstance(parsed, dict) and True in parsed and "on" not in parsed:
                parsed["on"] = parsed.pop(True)
            return parsed
        except yaml.YAMLError as e:
            print(f"YAML parsing error: {e}")
            return None

    def validate_yaml_syntax(self, yaml_content: str) -> tuple[bool, Optional[str]]:
        """Validate YAML syntax"""
        yaml_content = self._sanitize_llm_yaml(yaml_content)
        try:
            yaml.safe_load(yaml_content)
            return True, None
        except yaml.YAMLError as e:
            return False, str(e)

    def format_yaml(self, data: Dict[str, Any], width: int = 120) -> str:
        """Format dictionary as pretty YAML with consistent indentation"""
        return yaml.dump(
            data,
            default_flow_style=False,
            sort_keys=False,
            width=width,
            allow_unicode=True,
            default_style=None,
            indent=2,
        )

    def merge_yaml_configs(self, base_yaml: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
        """Deep-merge two YAML configurations (overrides win on conflict)"""
        merged = base_yaml.copy()
        for key, value in overrides.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = self.merge_yaml_configs(merged[key], value)
            else:
                merged[key] = value
        return merged

    def add_metadata(self, yaml_content: str, metadata: Dict[str, Any]) -> str:
        """Prepend metadata comments to YAML"""
        header = [
            "# GitHub Actions Workflow",
            "# Auto-generated by CI/CD Agent",
            "#",
            f"# Generated: {metadata.get('generated_at', 'Unknown')}",
        ]
        if metadata.get("description"):
            header.append(f"# Description: {metadata['description']}")
        header.append("#\n")
        return "\n".join(header) + "\n" + yaml_content

    def extract_jobs(self, parsed_yaml: Dict[str, Any]) -> Dict[str, Any]:
        """Extract jobs from parsed YAML"""
        return parsed_yaml.get("jobs", {})

    def validate_required_fields(self, parsed_yaml: Dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate required top-level YAML fields and job structure"""
        errors = []

        # Normalize boolean True key produced by yaml.safe_load for 'on:'
        if isinstance(parsed_yaml, dict) and True in parsed_yaml and "on" not in parsed_yaml:
            parsed_yaml["on"] = parsed_yaml.pop(True)

        for field in ("name", "on", "jobs"):
            if field not in parsed_yaml:
                errors.append(f"Missing required field: '{field}'")

        jobs = parsed_yaml.get("jobs", {})
        if not jobs:
            errors.append("At least one job is required")

        for job_name, job_config in jobs.items():
            if not isinstance(job_config, dict):
                errors.append(f"Job '{job_name}' must be an object")
                continue
            if "runs-on" not in job_config:
                errors.append(f"Job '{job_name}' missing 'runs-on'")
            if "steps" not in job_config:
                errors.append(f"Job '{job_name}' missing 'steps'")

        return len(errors) == 0, errors

    def auto_fix_common_issues(self, yaml_content: str) -> str:
        """Attempt to auto-fix common YAML structure issues"""
        parsed = self.parse_yaml(yaml_content)
        if not parsed:
            return yaml_content

        # Normalize 'on:' boolean key
        if True in parsed and "on" not in parsed:
            parsed["on"] = parsed.pop(True)

        # Ensure 'on' is not a bare string
        if isinstance(parsed.get("on"), str):
            parsed["on"] = [parsed["on"]]

        # Patch jobs missing 'runs-on' or unnamed steps
        for job_name, job_config in parsed.get("jobs", {}).items():
            if not isinstance(job_config, dict):
                continue
            if "runs-on" not in job_config:
                job_config["runs-on"] = "ubuntu-latest"
            for i, step in enumerate(job_config.get("steps", [])):
                if isinstance(step, dict) and "name" not in step and "uses" in step:
                    step["name"] = f"Step {i + 1}"

        return self.format_yaml(parsed)