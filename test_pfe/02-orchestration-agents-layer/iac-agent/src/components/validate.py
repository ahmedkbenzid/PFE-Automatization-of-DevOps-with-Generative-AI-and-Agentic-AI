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

        syntax_errors = []
        syntax_errors.extend(self._check_hcl_syntax("providers.tf", providers_tf))
        syntax_errors.extend(self._check_hcl_syntax("variables.tf", variables_tf))
        syntax_errors.extend(self._check_hcl_syntax("main.tf", main_tf))
        syntax_errors.extend(self._check_hcl_syntax("outputs.tf", outputs_tf))
        errors.extend(syntax_errors)

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

    def _check_hcl_syntax(self, file_name: str, content: str) -> list[str]:
        """Perform lightweight HCL syntax checks usable in repair prompts."""
        if not content.strip():
            return []

        issues = []

        brace_balance = 0
        in_double_quote = False
        escape = False
        line_number = 1

        for ch in content:
            if ch == "\n":
                line_number += 1

            if in_double_quote:
                if escape:
                    escape = False
                    continue
                if ch == "\\":
                    escape = True
                    continue
                if ch == '"':
                    in_double_quote = False
                continue

            if ch == '"':
                in_double_quote = True
            elif ch == "{":
                brace_balance += 1
            elif ch == "}":
                brace_balance -= 1
                if brace_balance < 0:
                    issues.append(f"{file_name}: unmatched closing brace near line {line_number}.")
                    brace_balance = 0

        if in_double_quote:
            issues.append(f"{file_name}: unterminated double-quoted string literal.")
        if brace_balance != 0:
            issues.append(f"{file_name}: unbalanced braces detected ({brace_balance} unmatched opening brace(s)).")

        # Basic block header checks.
        block_header = re.compile(r"^\s*(resource|variable|provider|output|locals|terraform)\b")
        for idx, raw_line in enumerate(content.splitlines(), 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if block_header.search(line) and "{" not in line:
                issues.append(f"{file_name}: block declaration missing '{{' near line {idx}.")

        return issues
