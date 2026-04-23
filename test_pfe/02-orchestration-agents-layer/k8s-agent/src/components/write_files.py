"""Write generated Kubernetes manifests to repository when enabled."""

from __future__ import annotations

from pathlib import Path
from typing import List

from ..config import K8S_CONFIG
from ..models.types import KubernetesManifests


class WriteFiles:
    def run(self, manifests: KubernetesManifests, repository_path: str, write: bool = False) -> List[str]:
        if not write:
            return []

        if repository_path.startswith("http://") or repository_path.startswith("https://"):
            return []

        output_dir = K8S_CONFIG.get("output_directory", "kubernetes")
        repo = Path(repository_path)
        k8s_dir = repo / output_dir
        k8s_dir.mkdir(parents=True, exist_ok=True)

        written_files = []
        for filename, content in manifests.files.items():
            path = k8s_dir / filename
            path.write_text(content, encoding="utf-8")
            written_files.append(str(path))

        return written_files
