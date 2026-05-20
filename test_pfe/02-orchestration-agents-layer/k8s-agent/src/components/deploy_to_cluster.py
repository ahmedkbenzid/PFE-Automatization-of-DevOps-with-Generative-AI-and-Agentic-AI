"""Apply Kubernetes manifests to the local Minikube cluster."""

from __future__ import annotations

import shutil
import subprocess
from typing import Any, Dict, List

from ..config import K8S_CONFIG


class DeployToCluster:
    def __init__(self) -> None:
        self.kubectl_binary = K8S_CONFIG.get("kubectl_binary", "kubectl")
        self.minikube_binary = "minikube"

    def run(self, written_files: List[str], app_name: str) -> Dict[str, Any]:
        if not written_files:
            return {
                "context": {},
                "nodes": {},
                "apply_results": [],
                "rollout_status": {},
                "service_url": "",
                "error": "No manifest files were written; deploy skipped.",
            }

        if not shutil.which(self.kubectl_binary):
            return {
                "context": {},
                "nodes": {},
                "apply_results": [],
                "rollout_status": {},
                "service_url": "",
                "error": f"kubectl not found in PATH: {self.kubectl_binary}",
            }

        if not shutil.which(self.minikube_binary):
            return {
                "context": {},
                "nodes": {},
                "apply_results": [],
                "rollout_status": {},
                "service_url": "",
                "error": "minikube not found in PATH",
            }

        context_result = self._run_command([
            self.kubectl_binary,
            "config",
            "use-context",
            "minikube",
        ])
        nodes_result = self._run_command([self.kubectl_binary, "get", "nodes"])

        apply_results: List[Dict[str, Any]] = []
        for file_path in written_files:
            apply_result = self._run_command([
                self.kubectl_binary,
                "apply",
                "-f",
                file_path,
            ])
            apply_result["file"] = file_path
            apply_results.append(apply_result)

        rollout_result = self._run_command([
            self.kubectl_binary,
            "rollout",
            "status",
            f"deployment/{app_name}",
            "--timeout=120s",
        ])

        service_result = self._run_command([
            self.minikube_binary,
            "service",
            f"{app_name}-service",
            "--url",
        ])
        service_url = self._first_line(service_result.get("stdout", ""))

        return {
            "context": context_result,
            "nodes": nodes_result,
            "apply_results": apply_results,
            "rollout_status": rollout_result,
            "service_url": service_url,
        }

    def _run_command(self, command: List[str]) -> Dict[str, Any]:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        return {
            "command": command,
            "returncode": result.returncode,
            "stdout": (result.stdout or "").strip(),
            "stderr": (result.stderr or "").strip(),
            "success": result.returncode == 0,
        }

    def _first_line(self, text: str) -> str:
        for line in (text or "").splitlines():
            if line.strip():
                return line.strip()
        return ""
