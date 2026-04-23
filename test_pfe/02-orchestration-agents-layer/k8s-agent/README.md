# K8s Agent (Raw Manifests v1)

This agent generates Kubernetes manifests in one run with local-cluster defaults.

## Generated Resources

The agent always generates all files below inside `kubernetes/`:

- `namespace.yaml`
- `configmap.yaml`
- `secret.yaml`
- `deployment.yaml`
- `service.yaml`
- `ingress.yaml`
- `hpa.yaml`

## Defaults

- Namespace: app-named namespace (auto-created)
- Replicas: 1
- Resources:
  - requests: cpu `100m`, memory `128Mi`
  - limits: cpu `500m`, memory `512Mi`
- Ingress class: `traefik`
- Cloud profile: generic Kubernetes (no provider-specific annotations)

## Security Model

- Non-sensitive env vars are placed in ConfigMap.
- Sensitive env vars are placed in Secret.
- Deployment uses only `configMapKeyRef` and `secretKeyRef` for env injection.

## Validation

- YAML parse/lint checks for every manifest
- Kubernetes schema checks through `kubeconform` when available

## Quick Usage

```python
from src.pipeline import run_pipeline

result = run_pipeline(
    request_text="Generate Kubernetes manifests for my API",
    repository_path="/path/to/repo",
    write_output_files=True,
)

print(result.success)
print(result.k8s_manifests.files.keys())
```
