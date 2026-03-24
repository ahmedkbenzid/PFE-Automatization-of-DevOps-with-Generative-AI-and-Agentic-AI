"""Tools Layer: write_files component."""

from __future__ import annotations

from pathlib import Path

from src.models.types import GeneratedConfiguration


class WriteFiles:
    """Persist generated Docker artifacts to the target repository."""

    def run(self, configuration: GeneratedConfiguration, repository_path: str, write: bool = False) -> list[str]:
        if not write:
            return []

        written = []
        repo = Path(repository_path)
        dockerfile_path = repo / "Dockerfile"
        dockerfile_path.write_text(configuration.dockerfile_content or "", encoding="utf-8")
        written.append(str(dockerfile_path))

        if configuration.compose_content:
            compose_path = repo / "docker-compose.yml"
            compose_path.write_text(configuration.compose_content, encoding="utf-8")
            written.append(str(compose_path))

        return written
