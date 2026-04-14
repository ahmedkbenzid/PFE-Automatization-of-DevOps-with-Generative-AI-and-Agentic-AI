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
