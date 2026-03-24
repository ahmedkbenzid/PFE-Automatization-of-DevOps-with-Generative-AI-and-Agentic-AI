"""Tools Layer: validate component for Dockerfile syntax and policy checks."""

from __future__ import annotations

from src.models.types import GeneratedConfiguration, ValidationResult


class Validate:
    """Lightweight structural validator before the dedicated validation layer."""

    def run(self, configuration: GeneratedConfiguration) -> ValidationResult:
        errors = []
        warnings = []
        suggestions = []

        dockerfile = configuration.dockerfile_content or ""
        lines = [line.strip() for line in dockerfile.splitlines() if line.strip()]

        if not any(line.startswith("FROM ") for line in lines):
            errors.append("Dockerfile must include at least one FROM instruction.")

        if not any(line.startswith("CMD ") or line.startswith("ENTRYPOINT ") for line in lines):
            warnings.append("No CMD or ENTRYPOINT found; container may not start a process.")

        if any("latest" in line for line in lines if line.startswith("FROM ")):
            suggestions.append("Pin base image tags to avoid non-deterministic builds.")

        if not any(line.startswith("USER ") for line in lines):
            warnings.append("No USER instruction found; container may run as root.")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            suggestions=suggestions,
        )
