import os
import json
from pathlib import Path

# Load environment variables from .env if exists (for subprocess execution)
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=True)
        print(f"[Docker Agent Config] Loaded .env from {env_file}")
except ImportError:
    pass  # dotenv not required

# Paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "src" / "datasets" / "knowledge_base"

# LLM Configuration
LLM_CONFIG = {
    "provider": os.getenv("LLM_PROVIDER", "ollama"),  # ollama or groq
    "model": os.getenv("OLLAMA_MODEL", "glm-5:cloud"),  # Ollama GLM-5 cloud model
    "groq_model": os.getenv("GROQ_MODEL", "llama3-70b-8192"),  # Groq fallback
    "fallback_model": os.getenv("GROQ_FALLBACK_MODEL", "mixtral-8x7b-32768"),
    "temperature": 0.2,  # Low temperature for more deterministic code generation
    "max_tokens": 4096,
    "enabled": os.getenv("USE_LLM", "false").lower() == "true",  # Enable/disable LLM generation
}

# Debug: Print loaded configuration
print(f"[Docker Agent Config] LLM Configuration loaded:")
print(f"  - USE_LLM env var: {os.getenv('USE_LLM', 'NOT SET')}")
print(f"  - enabled: {LLM_CONFIG['enabled']}")
print(f"  - provider: {LLM_CONFIG['provider']}")
print(f"  - GROQ_API_KEY: {'SET' if os.getenv('GROQ_API_KEY') else 'NOT SET'}")

# Pipeline Configuration
PIPELINE_CONFIG = {
    "max_retries": 3,
    "retry_delay": 2, # seconds
    "strict_validation": True,
    "strict_security": True,
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
