"""Configuration management for CI/CD Agent"""
import os
from typing import Optional

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(*args, **kwargs):
        return False

try:
    load_dotenv(encoding="utf-8")
except UnicodeDecodeError:
    print("Warning: .env is not UTF-8 encoded; skipping .env load")

class Config:
    """Application configuration"""

    # LLM Provider Configuration (ollama or groq)
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama")

    # Ollama Cloud Configuration (primary)
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "minimax-m2.7:cloud")

    # Groq LLM Configuration (fallback)
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    GROQ_FALLBACK_MODELS: list[str] = [
        model.strip()
        for model in os.getenv("GROQ_FALLBACK_MODELS", "llama-3.3-70b-versatile,llama3-70b-8192").split(",")
        if model.strip()
    ]

    # Common LLM Settings
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "2048"))
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.3"))

    # Legacy aliases
    GROQ_MAX_TOKENS: int = LLM_MAX_TOKENS
    GROQ_TEMPERATURE: float = LLM_TEMPERATURE
    
    # GitHub Configuration
    GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
    GITHUB_REPO_OWNER: str = os.getenv("GITHUB_REPO_OWNER", "")
    GITHUB_REPO_NAME: str = os.getenv("GITHUB_REPO_NAME", "")
    
    # Agent Configuration
    MAX_RETRIES: int = 3
    RETRY_DELAY: int = 2
    
    # Validation Configuration
    ENABLE_SCHEMA_VALIDATION: bool = True
    ENABLE_SECURITY_CHECK: bool = True
    
    # Dataset paths
    DATASET_DIR: str = os.path.join(os.path.dirname(__file__), "datasets")
    
    @classmethod
    def validate(cls) -> bool:
        """Validate required configuration"""
        if cls.LLM_PROVIDER == "ollama":
            # Ollama cloud models use ollama CLI login, no API key needed here
            return True
        else:
            if not cls.GROQ_API_KEY:
                print("Warning: GROQ_API_KEY not set")
                return False
        return True
