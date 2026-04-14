# IaC Agent (Terraform)

This agent generates Terraform artifacts for cloud infrastructure requests.

## Features

- Terraform generation for AWS, Azure, and GCP.
- Prompt intent parsing for cloud provider and resource hints.
- Repository-aware generation using local context and orchestrator context.
- Retrieval-augmented hints from a local PageIndex knowledge base.
- Compatibility with orchestrator output contract:
  - `terraform_config.providers_tf`
  - `terraform_config.variables_tf`
  - `terraform_config.main_tf`
  - `terraform_config.outputs_tf`
  - `terraform_config.provider`
  - `terraform_config.resources`
  - `terraform_config.is_valid`

## Dataset Source

The knowledge base includes metadata and examples grounded on:

- TerraDS (Zenodo): https://zenodo.org/records/14217386
- DOI: 10.5281/zenodo.14217386

## Quick Usage

```python
from src.pipeline import run_pipeline

result = run_pipeline(
    request_text="Create Terraform for AWS ECS deployment with VPC and ECR",
    repository_path="/path/to/repo",
    repo_context=None,
    write_output_files=False,
)

print(result.success)
print(result.terraform_config.main_tf)
```

## Output Files (when write enabled)

Terraform files are written to:

- `terraform/providers.tf`
- `terraform/variables.tf`
- `terraform/main.tf`
- `terraform/outputs.tf`
