"""Validation component for generated Terraform artifacts."""

from __future__ import annotations

import re

from ..models.types import TerraformConfiguration, ValidationResult


class Validate:
    """Apply lightweight structural validation to Terraform files."""

    def run(self, terraform_config: TerraformConfiguration) -> ValidationResult:
        errors = []
        warnings = []
        suggestions = []

        providers_tf = terraform_config.providers_tf or ""
        variables_tf = terraform_config.variables_tf or ""
        main_tf = terraform_config.main_tf or ""
        outputs_tf = terraform_config.outputs_tf or ""

        if not providers_tf.strip():
            errors.append("providers.tf content is missing.")
        if not variables_tf.strip():
            errors.append("variables.tf content is missing.")
        if not main_tf.strip():
            errors.append("main.tf content is missing.")

        if "terraform {" not in providers_tf:
            errors.append("providers.tf should include a terraform block.")
        if "required_providers" not in providers_tf:
            errors.append("providers.tf should include required_providers.")

        resources = re.findall(r"^\s*resource\s+\"([^\"]+)\"\s+\"[^\"]+\"", main_tf, flags=re.MULTILINE)
        if not resources:
            errors.append("main.tf should define at least one Terraform resource.")

        provider = (terraform_config.provider or "").lower()
        if provider == "aws" and resources and not any(resource.startswith("aws_") for resource in resources):
            warnings.append("Selected provider is aws but no aws_* resources were found.")
        if provider == "azure" and resources and not any(resource.startswith("azurerm_") for resource in resources):
            warnings.append("Selected provider is azure but no azurerm_* resources were found.")
        if provider == "gcp" and resources and not any(resource.startswith("google_") for resource in resources):
            warnings.append("Selected provider is gcp but no google_* resources were found.")

        if not outputs_tf.strip():
            suggestions.append("Add outputs.tf values to simplify downstream integrations.")

        if "default     = \"ChangeMe123!\"" in variables_tf:
            warnings.append("Default demo passwords are present; replace them for production use.")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            suggestions=suggestions,
        )
