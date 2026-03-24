# Orchestrator Configuration
import os
from dotenv import load_dotenv

load_dotenv()

class OrchestratorConfig:
    LLM_API_KEY = os.getenv("GROQ_API_KEY", "")
    MODEL_NAME = "llama-3.1-8b-instant"
    MAX_RETRIES = 3
    DEFAULT_REPOSITORY_PATH = os.getenv("TARGET_REPOSITORY_PATH", os.getcwd())
