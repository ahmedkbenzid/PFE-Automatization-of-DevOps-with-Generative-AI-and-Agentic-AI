"""Validate generated Kubernetes manifests with YAML checks and kubeconform schema validation."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

from ..config import K8S_CONFIG
from ..models.types import KubernetesManifests, ValidationResult


class Validate:
    _CLUSTER_UNAVAILABLE_MARKERS = (
        "couldn't get current server api group list",
        "unable to recognize",
        "connectex",
        "connection refused",
        "dial tcp",
        "no connection could be made",
        "the server could not find the requested resource",
    )

    def run(self, manifests: KubernetesManifests) -> ValidationResult:
        errors = []
        warnings = []

        for name, content in manifests.files.items():
            if not content.strip():
                errors.append(f"{name} is empty")
                continue
            try:
                docs = list(yaml.safe_load_all(content))
            except yaml.YAMLError as exc:
                errors.append(f"{name} yaml parse error: {exc}")
                continue

            if not docs:
                errors.append(f"{name} does not contain a YAML document")
                continue

            for idx, doc in enumerate(docs, 1):
                if not isinstance(doc, dict):
                    errors.append(f"{name} document {idx} is not a mapping")
                    continue
                if "apiVersion" not in doc:
                    errors.append(f"{name} document {idx} missing apiVersion")
                if "kind" not in doc:
                    errors.append(f"{name} document {idx} missing kind")
                metadata = doc.get("metadata") or {}
                if not isinstance(metadata, dict) or not metadata.get("name"):
                    errors.append(f"{name} document {idx} missing metadata.name")

        kubeconform_errors, kubeconform_warnings = self._run_kubeconform(manifests)
        errors.extend(kubeconform_errors)
        warnings.extend(kubeconform_warnings)

        kubelinter_errors, kubelinter_warnings = self._run_kubelinter(manifests)
        errors.extend(kubelinter_errors)
        warnings.extend(kubelinter_warnings)

        kubectl_errors, kubectl_warnings = self._run_kubectl_dry_run(manifests)
        errors.extend(kubectl_errors)
        warnings.extend(kubectl_warnings)

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)

    def _run_kubeconform(self, manifests: KubernetesManifests) -> tuple[list[str], list[str]]:
        errors = []
        warnings = []

        kubeconform_binary = K8S_CONFIG.get("kubeconform_binary", "kubeconform")
        kubeconform_path = shutil.which(kubeconform_binary)
        if not kubeconform_path:
            message = "kubeconform binary not found in PATH; schema validation skipped"
            if K8S_CONFIG.get("kubeconform_skip_if_missing", True):
                warnings.append(message)
                return errors, warnings
            errors.append(message)
            return errors, warnings

        with tempfile.TemporaryDirectory(prefix="k8s-agent-") as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_files = []
            for file_name, content in manifests.files.items():
                out_path = tmp_path / file_name
                out_path.write_text(content, encoding="utf-8")
                input_files.append(str(out_path))

            command = [kubeconform_path, "-summary"]
            if K8S_CONFIG.get("kubeconform_strict", True):
                command.append("-strict")
            command.extend(input_files)

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
            if result.returncode != 0:
                payload = stderr or stdout or "kubeconform failed"
                errors.append(f"kubeconform validation failed: {payload}")
            elif stdout:
                warnings.append(f"kubeconform: {stdout}")

        return errors, warnings

    def _run_kubelinter(self, manifests: KubernetesManifests) -> tuple[list[str], list[str]]:
        errors = []
        warnings = []

        kubelinter_binary = K8S_CONFIG.get("kubelinter_binary", "kube-linter")
        kubelinter_path = shutil.which(kubelinter_binary)
        if not kubelinter_path:
            message = "kube-linter binary not found in PATH; lint validation skipped"
            if K8S_CONFIG.get("kubelinter_skip_if_missing", True):
                warnings.append(message)
                return errors, warnings
            errors.append(message)
            return errors, warnings

        with tempfile.TemporaryDirectory(prefix="k8s-agent-linter-") as tmp_dir:
            tmp_path = Path(tmp_dir)
            for file_name, content in manifests.files.items():
                (tmp_path / file_name).write_text(content, encoding="utf-8")

            command = [kubelinter_path, "lint", str(tmp_path)]
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
            if result.returncode != 0:
                payload = stderr or stdout or "kube-linter failed"
                errors.append(f"kube-linter validation failed: {payload}")
            elif stdout:
                warnings.append(f"kube-linter: {stdout}")

        return errors, warnings

    def _run_kubectl_dry_run(self, manifests: KubernetesManifests) -> tuple[list[str], list[str]]:
        errors = []
        warnings = []

        kubectl_binary = K8S_CONFIG.get("kubectl_binary", "kubectl")
        kubectl_path = shutil.which(kubectl_binary)
        if not kubectl_path:
            message = "kubectl binary not found in PATH; dry-run validation skipped"
            if K8S_CONFIG.get("kubectl_dry_run_skip_if_missing", True):
                warnings.append(message)
                return errors, warnings
            errors.append(message)
            return errors, warnings

        with tempfile.TemporaryDirectory(prefix="k8s-agent-kubectl-") as tmp_dir:
            tmp_path = Path(tmp_dir)
            for file_name, content in manifests.files.items():
                out_path = tmp_path / file_name
                out_path.write_text(content, encoding="utf-8")

            command = [kubectl_path, "apply", "--dry-run=client", "--validate=false", "-f", str(tmp_path)]
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
            if result.returncode != 0:
                payload = stderr or stdout or "kubectl dry-run failed"
                cluster_unreachable = self._is_cluster_unavailable(payload)
                if cluster_unreachable and K8S_CONFIG.get("kubectl_dry_run_skip_if_missing", True):
                    warnings.append("kubectl dry-run skipped: no reachable Kubernetes cluster/context configured")
                else:
                    errors.append(f"kubectl dry-run validation failed: {self._summarize_error(payload)}")
            elif stdout:
                warnings.append(f"kubectl dry-run: {stdout}")

        return errors, warnings

    def _is_cluster_unavailable(self, payload: str) -> bool:
        lowered = (payload or "").lower()
        return any(marker in lowered for marker in self._CLUSTER_UNAVAILABLE_MARKERS)

    def _summarize_error(self, payload: str, max_lines: int = 3) -> str:
        lines = [line.strip() for line in (payload or "").splitlines() if line.strip()]
        if not lines:
            return "unknown error"
        summary = " | ".join(lines[:max_lines])
        if len(lines) > max_lines:
            summary += " | ..."
        return summary
