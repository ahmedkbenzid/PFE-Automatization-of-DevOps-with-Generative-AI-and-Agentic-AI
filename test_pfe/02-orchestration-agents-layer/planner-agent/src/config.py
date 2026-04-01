"""
Planner Agent Configuration

Strategic planning agent settings for task decomposition and execution planning.
"""

import os
from pathlib import Path
from typing import Optional

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
PLANNER_ROOT = Path(__file__).parent.parent


class PlannerConfig:
    """Configuration for Planner Agent"""
    
    # LLM Configuration - Default to Groq since it's faster and already configured
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "groq")
    OLLAMA_MODEL: str = os.getenv("PLANNER_OLLAMA_MODEL", "glm-5:cloud")
    GROQ_MODEL: str = os.getenv("PLANNER_GROQ_MODEL", "llama-3.1-8b-instant")
    GROQ_API_KEY: Optional[str] = os.getenv("GROQ_API_KEY")
    
    # Planning parameters
    TEMPERATURE: float = 0.1  # Low temperature for consistent planning
    MAX_TOKENS: int = 4000
    
    # Complexity detection thresholds
    COMPLEXITY_THRESHOLD: int = int(os.getenv("PLANNER_COMPLEXITY_THRESHOLD", "4"))
    
    # Agent registry path
    AGENT_REGISTRY_PATH: Path = PLANNER_ROOT / "src" / "agent_registry.json"
    
    # Planning constraints
    MAX_PARALLEL_TASKS: int = 4  # Maximum tasks to run in parallel
    MAX_PLAN_DEPTH: int = 10  # Maximum dependency depth
    PLANNING_TIMEOUT_SEC: int = 30  # Timeout for plan generation
    
    # Force planner keywords (always use planner if these appear)
    FORCE_PLANNER_KEYWORDS = [
        "production setup",
        "complete deployment",
        "end-to-end",
        "full stack setup",
        "microservices",
        "complete ci/cd"
    ]
    
    # Skip planner keywords (never use planner)
    SKIP_PLANNER_KEYWORDS = [
        "just",
        "only",
        "simple",
        "single"
    ]
    
    @classmethod
    def get_llm_config(cls) -> dict:
        """Get LLM configuration based on provider"""
        if cls.LLM_PROVIDER == "groq":
            return {
                "provider": "groq",
                "model": cls.GROQ_MODEL,
                "api_key": cls.GROQ_API_KEY,
                "temperature": cls.TEMPERATURE,
                "max_tokens": cls.MAX_TOKENS
            }
        else:  # ollama
            return {
                "provider": "ollama",
                "model": cls.OLLAMA_MODEL,
                "temperature": cls.TEMPERATURE,
                "max_tokens": cls.MAX_TOKENS
            }
