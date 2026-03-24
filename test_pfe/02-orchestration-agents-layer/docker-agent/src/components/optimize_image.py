"""Tools Layer: optimize_image component."""

from __future__ import annotations

from src.models.types import GeneratedConfiguration


class OptimizeImage:
    """Apply deterministic, safe optimizations to generated Dockerfiles."""

    def run(self, configuration: GeneratedConfiguration) -> GeneratedConfiguration:
        dockerfile = configuration.dockerfile_content or ""
        lines = dockerfile.splitlines()

        optimized_lines = []
        for line in lines:
            # Normalize common whitespace drift from template composition.
            optimized_lines.append(line.rstrip())

        optimized = "\n".join(optimized_lines).strip() + "\n"
        configuration.dockerfile_content = optimized
        configuration.metadata["optimized"] = True
        return configuration
