import os
import json
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "src" / "datasets" / "knowledge_base"

# LLM Configuration
LLM_CONFIG = {
    "provider": "groq",
    "model": os.getenv("GROQ_MODEL", "llama3-70b-8192"), # Default to large model for code gen
    "fallback_model": os.getenv("GROQ_FALLBACK_MODEL", "mixtral-8x7b-32768"),
    "temperature": 0.2, # Low temperature for more deterministic code generation
    "max_tokens": 4096,
}

# Pipeline Configuration
PIPELINE_CONFIG = {
    "max_retries": 3,
    "retry_delay": 2, # seconds
    "strict_validation": True,
    "strict_security": True,
}

def validate() -> None:
    """Validate required configuration and environment variables."""
    required_envs = ["GROQ_API_KEY"]
    missing = [env for env in required_envs if not os.getenv(env)]
    
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
    
    if not DATA_DIR.exists():
        os.makedirs(DATA_DIR / "pages", exist_ok=True)
        # Create an empty page_index if it doesn't exist
        index_path = DATA_DIR / "page_index.json"
        if not index_path.exists():
            with open(index_path, "w") as f:
                json.dump(
                    {
                        "doc_name": "docker-agent-knowledge-base",
                        "doc_description": "Empty knowledge base",
                        "structure": [],
                    },
                    f,
                )
