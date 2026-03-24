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
    
    # Groq LLM Configuration
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "GROQ_API_KEY_REMOVED")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    GROQ_FALLBACK_MODELS: list[str] = [
        model.strip()
        for model in os.getenv("GROQ_FALLBACK_MODELS", "llama-3.3-70b-versatile,llama3-70b-8192").split(",")
        if model.strip()
    ]
    GROQ_MAX_TOKENS: int = 2048
    GROQ_TEMPERATURE: float = 0.3
    
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
        if not cls.GROQ_API_KEY:
            print("Warning: GROQ_API_KEY not set")
            return False
        return True
