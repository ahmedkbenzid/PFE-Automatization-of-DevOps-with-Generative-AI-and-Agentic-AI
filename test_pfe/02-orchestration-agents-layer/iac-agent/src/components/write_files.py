"""Write generated Terraform files to repository when enabled."""

from __future__ import annotations

from pathlib import Path
from typing import List

from ..config import IAC_CONFIG
from ..models.types import TerraformConfiguration


class WriteFiles:
    """Persist Terraform artifacts to the target repository."""

    def run(self, terraform_config: TerraformConfiguration, repository_path: str, write: bool = False) -> List[str]:
        if not write:
            return []

        if repository_path.startswith("http://") or repository_path.startswith("https://"):
            return []

        terraform_dir_name = IAC_CONFIG.get("write_terraform_dir", "terraform")
        repo = Path(repository_path)
        tf_dir = repo / terraform_dir_name
        tf_dir.mkdir(parents=True, exist_ok=True)

        file_mapping = {
            "providers.tf": terraform_config.providers_tf,
            "variables.tf": terraform_config.variables_tf,
            "main.tf": terraform_config.main_tf,
            "outputs.tf": terraform_config.outputs_tf,
        }

        written_files: List[str] = []
        for filename, content in file_mapping.items():
            if not content or not str(content).strip():
                continue
            path = tf_dir / filename
            path.write_text(str(content), encoding="utf-8")
            written_files.append(str(path))

        return written_files
