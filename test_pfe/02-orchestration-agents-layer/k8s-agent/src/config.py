"""Configuration for Kubernetes manifest generator agent."""

import os
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=True)
        logger.info(f"Loaded .env from {env_file}")
except ImportError:
    pass

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "src" / "datasets" / "knowledge_base"

LLM_CONFIG = {
    "provider": os.getenv("K8S_LLM_PROVIDER", "ollama"),
    "model": os.getenv("K8S_OLLAMA_MODEL", "glm-5:cloud"),
    "groq_model": os.getenv("K8S_GROQ_MODEL", "mixtral-8x7b-32768"),
    "temperature": 0.2,
    "max_tokens": 2048,
    "timeout": int(os.getenv("K8S_LLM_TIMEOUT", "120")),
    "enabled": os.getenv("USE_LLM", "false").lower() == "true",
}

logger.info(f"K8s LLM config: enabled={LLM_CONFIG['enabled']}, provider={LLM_CONFIG['provider']}")

K8S_CONFIG = {
    "llm_api_key_env": "GROQ_API_KEY",
    "llm_model_name": LLM_CONFIG.get("model"),
    "llm_temperature": LLM_CONFIG.get("temperature"),
    "default_namespace_prefix": "",
    "default_replicas": 1,
    "default_service_port": 80,
    "default_container_port": 8000,
    "default_ingress_class": "traefik",
    "default_host_suffix": ".local",
    "output_directory": "kubernetes",
    "resource_defaults": {
        "requests": {"cpu": "100m", "memory": "128Mi"},
        "limits": {"cpu": "500m", "memory": "512Mi"},
    },
    "hpa": {
        "min_replicas": 1,
        "max_replicas": 3,
        "target_cpu_utilization": 70,
        "target_memory_utilization": 75,
    },
    "kubeconform_binary": "kubeconform",
    "kubeconform_strict": True,
    "kubeconform_skip_if_missing": True,
    "kubelinter_binary": "kube-linter",
    "kubelinter_skip_if_missing": True,
    "kubectl_binary": "kubectl",
    "kubectl_dry_run_skip_if_missing": True,
}