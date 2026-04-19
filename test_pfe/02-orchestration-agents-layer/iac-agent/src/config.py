import json
import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=True)
except ImportError:
    pass

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "src" / "datasets" / "knowledge_base"

IAC_CONFIG = {
    "default_provider": os.getenv("IAC_DEFAULT_PROVIDER", "aws").lower(),
    "strict_validation": os.getenv("IAC_STRICT_VALIDATION", "true").lower() == "true",
    "supported_providers": ["aws", "azure", "gcp"],
    "write_terraform_dir": os.getenv("IAC_TERRAFORM_DIR", "terraform"),
    "use_llm": os.getenv("IAC_USE_LLM", "true").lower() == "true",
    "enable_benchmark": os.getenv("IAC_ENABLE_BENCHMARK", "false").lower() == "true",
    "llm_provider": os.getenv("IAC_LLM_PROVIDER", os.getenv("LLM_PROVIDER", "groq")).lower(),
    "groq_model": os.getenv("IAC_GROQ_MODEL", "llama-3.1-8b-instant"),
    "ollama_model": os.getenv("IAC_OLLAMA_MODEL", os.getenv("OLLAMA_MODEL", "llama3.1")),
    "llm_temperature": float(os.getenv("IAC_LLM_TEMPERATURE", "0.1")),
    "llm_max_tokens": int(os.getenv("IAC_LLM_MAX_TOKENS", "4096")),
    "max_llm_attempts": int(os.getenv("IAC_MAX_LLM_ATTEMPTS", "1")),
    "max_repair_attempts": int(os.getenv("IAC_MAX_REPAIR_ATTEMPTS", "2")),
}


def validate() -> None:
    """Validate configuration and ensure knowledge-base directory exists."""
    os.makedirs(DATA_DIR / "pages", exist_ok=True)

    page_index_path = DATA_DIR / "page_index.json"
    if not page_index_path.exists():
        with open(page_index_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "doc_name": "iac-agent-knowledge-base",
                    "doc_description": "Empty IaC knowledge base",
                    "structure": [],
                },
                f,
                indent=2,
            )
