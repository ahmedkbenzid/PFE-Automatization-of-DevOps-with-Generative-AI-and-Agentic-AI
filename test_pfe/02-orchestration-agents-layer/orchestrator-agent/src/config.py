# Orchestrator Configuration
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class OrchestratorConfig:
    # LLM Configuration
    LLM_API_KEY = os.getenv("GROQ_API_KEY", "")
    MODEL_NAME = "llama-3.1-8b-instant"
    MAX_RETRIES = 3
    DEFAULT_REPOSITORY_PATH = os.getenv("TARGET_REPOSITORY_PATH", os.getcwd())

    # GitHub Integration (MCP)
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
    GITHUB_MCP_ENABLED = os.getenv("MCP_GITHUB_ENABLED", "true").lower() == "true"

    # Artifact Storage
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    ARTIFACT_DB_PATH = os.getenv(
        "ARTIFACT_DB_PATH",
        str(PROJECT_ROOT / "data" / "orchestrator_artifacts.db")
    )

    # Webhook Configuration
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
    WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "5000"))
    WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "0.0.0.0")
