# Orchestrator Configuration
import os
from dotenv import load_dotenv

load_dotenv()

class OrchestratorConfig:
    # LLM Configuration
    LLM_API_KEY = os.getenv("GROQ_API_KEY", "")
    MODEL_NAME = "llama-3.1-8b-instant"
    MAX_RETRIES = 3
    DEFAULT_REPOSITORY_PATH = os.getenv("TARGET_REPOSITORY_PATH", os.getcwd())

    # GitHub Integration (MCP)
    GITHUB_TOKEN = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN", os.getenv("GITHUB_TOKEN", ""))
    GITHUB_HOST = os.getenv("GITHUB_HOST", "https://github.com")
    GITHUB_MCP_ENABLED = os.getenv("MCP_GITHUB_ENABLED", "true").lower() == "true"
    MCP_GITHUB_SERVER_COMMAND = os.getenv("MCP_GITHUB_SERVER_COMMAND", "docker")
    MCP_GITHUB_SERVER_ARGS = os.getenv(
        "MCP_GITHUB_SERVER_ARGS",
        "run -i --rm -e GITHUB_PERSONAL_ACCESS_TOKEN -e GITHUB_HOST ghcr.io/github/github-mcp-server",
    )
    MCP_GITHUB_CALL_TIMEOUT = int(os.getenv("MCP_GITHUB_CALL_TIMEOUT", "30"))
    MCP_GITHUB_STRICT = os.getenv("MCP_GITHUB_STRICT", "false").lower() == "true"

    # Repository Analysis
    # Set to True for deep recursive analysis (slower, more thorough)
    # Default False uses fast GitHub tree API (single API call)
    DEEP_REPO_ANALYSIS = os.getenv("DEEP_REPO_ANALYSIS", "false").lower() == "true"

    # Webhook Configuration
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
    WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "5000"))
    WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "0.0.0.0")
