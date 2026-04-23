import sys
from pathlib import Path


AGENT_ROOT = Path(__file__).parent
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from src.pipeline import run_pipeline


def test_k8s_pipeline_generates_all_resources() -> None:
    result = run_pipeline(
        request_text="Generate Kubernetes manifests for my app",
        repository_path=str(AGENT_ROOT),
        write_output_files=False,
        repo_context=None,
    )

    assert result.k8s_manifests.namespace_yaml
    assert result.k8s_manifests.configmap_yaml
    assert result.k8s_manifests.secret_yaml
    assert result.k8s_manifests.deployment_yaml
    assert result.k8s_manifests.service_yaml
    assert result.k8s_manifests.ingress_yaml
    assert result.k8s_manifests.hpa_yaml

    files = result.k8s_manifests.files
    expected = {
        "namespace.yaml",
        "configmap.yaml",
        "secret.yaml",
        "deployment.yaml",
        "service.yaml",
        "ingress.yaml",
        "hpa.yaml",
    }
    assert expected.issubset(files.keys())


def test_deployment_uses_value_from_refs() -> None:
    result = run_pipeline(
        request_text="Generate Kubernetes manifests with API_KEY=mykey and APP_ENV=dev",
        repository_path=str(AGENT_ROOT),
        write_output_files=False,
        repo_context=None,
    )

    deployment = result.k8s_manifests.deployment_yaml
    assert "valueFrom:" in deployment
    assert "configMapKeyRef:" in deployment
    assert "secretKeyRef:" in deployment
