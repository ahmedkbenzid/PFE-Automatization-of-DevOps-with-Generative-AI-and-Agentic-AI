import os
import json
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Load environment variables from .env if exists (for subprocess execution)
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=True)
        logger.info(f"Loaded .env from {env_file}")
except ImportError:
    pass  # dotenv not required

# Paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "src" / "datasets" / "knowledge_base"

# LLM Configuration
LLM_CONFIG = {
    "provider": os.getenv("LLM_PROVIDER", "ollama"),  # ollama or groq
    "model": os.getenv("OLLAMA_MODEL", "gpt-oss:20b:cloud"),  # Ollama gpt-oss:20b cloud model
    "groq_model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),  # Groq fallback
    "fallback_model": os.getenv("GROQ_FALLBACK_MODEL", "llama-3.3-70b-versatile"),
    "temperature": 0.2,  # Low temperature for more deterministic code generation
    "max_tokens": 4096,
    "enabled": os.getenv("USE_LLM", "false").lower() == "true",  # Enable/disable LLM generation
    "timeout": int(os.getenv("LLM_TIMEOUT", "120")),
}

logger.info(f"LLM Configuration: enabled={LLM_CONFIG['enabled']}, provider={LLM_CONFIG.get('provider')}")

# Pipeline Configuration
PIPELINE_CONFIG = {
    "max_retries": 3,
    "retry_delay": 2, # seconds
    "strict_validation": True,
    "strict_security": True,
    "build_validation_timeout_sec": int(os.getenv("DOCKER_BUILD_VALIDATION_TIMEOUT_SEC", "300")),
    "build_validation_pull": os.getenv("DOCKER_BUILD_VALIDATION_PULL", "false").lower() == "true",
}

def validate() -> None:
    """Validate required configuration and environment variables."""
    provider = LLM_CONFIG.get("provider", "ollama")
    
    if provider == "groq":
        required_envs = ["GROQ_API_KEY"]
        missing = [env for env in required_envs if not os.getenv(env)]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
    # Ollama cloud models use ollama CLI login, no API key needed here
    
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
