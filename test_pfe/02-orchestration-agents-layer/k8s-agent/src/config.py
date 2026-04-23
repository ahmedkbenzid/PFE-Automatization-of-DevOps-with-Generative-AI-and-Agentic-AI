"""Configuration for Kubernetes manifest generator agent."""

from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "src" / "datasets" / "knowledge_base"

K8S_CONFIG = {
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
