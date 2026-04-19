"""Validation Layer: runtime Docker build gate."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List


class DockerBuildValidator:
    """Verify Dockerfile buildability by running a real docker build command."""

    def run(
        self,
        dockerfile_content: str,
        repository_path: str,
        timeout_seconds: int = 300,
        pull: bool = False,
    ) -> Dict[str, Any]:
        if not dockerfile_content or not dockerfile_content.strip():
            return {
                "passed": False,
                "timed_out": False,
                "exit_code": -1,
                "error": "Dockerfile content is empty; build validation cannot run.",
                "logs": [],
            }

        with tempfile.TemporaryDirectory(prefix="docker-agent-build-") as temp_dir:
            context_path = Path(temp_dir)
            prep = self._prepare_build_context(repository_path, context_path)
            if not prep.get("prepared", False):
                return {
                    "passed": False,
                    "timed_out": False,
                    "exit_code": -1,
                    "error": prep.get("reason", "Failed to prepare build context."),
                    "logs": prep.get("logs", []),
                    "mode": prep.get("mode"),
                }

            dockerfile_path = context_path / "Dockerfile"
            dockerfile_path.write_text(dockerfile_content, encoding="utf-8")

            image_tag = f"docker-agent-validate-{uuid.uuid4().hex[:12]}"
            command = ["docker", "build", "-t", image_tag]
            if pull:
                command.append("--pull")
            command.append(".")

            try:
                completed = subprocess.run(
                    command,
                    cwd=str(context_path),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout_seconds,
                    check=False,
                )
            except FileNotFoundError:
                return {
                    "passed": False,
                    "timed_out": False,
                    "exit_code": -1,
                    "error": "Docker CLI is not installed or not available in PATH.",
                    "logs": [],
                    "mode": prep.get("mode"),
                }
            except subprocess.TimeoutExpired as exc:
                return {
                    "passed": False,
                    "timed_out": True,
                    "exit_code": -1,
                    "error": f"Docker build timed out after {timeout_seconds}s.",
                    "logs": self._collect_logs(exc.stdout, exc.stderr),
                    "mode": prep.get("mode"),
                }

            logs = self._collect_logs(completed.stdout, completed.stderr)
            passed = completed.returncode == 0

            if passed:
                self._cleanup_built_image(image_tag)

            return {
                "passed": passed,
                "timed_out": False,
                "exit_code": completed.returncode,
                "error": None if passed else f"Docker build failed with exit code {completed.returncode}.",
                "logs": logs,
                "image_tag": image_tag,
                "mode": prep.get("mode"),
            }

    def _prepare_build_context(self, repository_path: str, context_path: Path) -> Dict[str, Any]:
        repo_input = (repository_path or "").strip()
        if not repo_input:
            return {"prepared": False, "reason": "No repository path or URL provided."}

        if repo_input.startswith("http://") or repo_input.startswith("https://"):
            try:
                clone = subprocess.run(
                    ["git", "clone", "--depth", "1", repo_input, str(context_path)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                    timeout=180,
                )
            except FileNotFoundError:
                return {
                    "prepared": False,
                    "reason": "Git CLI is not installed or not available in PATH.",
                    "mode": "git-clone",
                }
            except subprocess.TimeoutExpired:
                return {
                    "prepared": False,
                    "reason": "Timed out while cloning repository for build validation.",
                    "mode": "git-clone",
                }

            if clone.returncode != 0:
                clone_error = (clone.stderr or clone.stdout or "git clone failed").strip()
                return {
                    "prepared": False,
                    "reason": f"Failed to clone repository: {clone_error}",
                    "logs": self._collect_logs(clone.stdout, clone.stderr),
                    "mode": "git-clone",
                }

            return {"prepared": True, "mode": "git-clone"}

        source_path = Path(repo_input)
        if not source_path.exists() or not source_path.is_dir():
            return {
                "prepared": False,
                "reason": f"Repository path not found or not a directory: {repo_input}",
                "mode": "local-copy",
            }

        ignore_dirs = {
            ".git",
            ".hg",
            ".svn",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            ".venv",
            "venv",
            "node_modules",
        }

        copied_entries = 0
        for child in source_path.iterdir():
            if child.name in ignore_dirs:
                continue

            target = context_path / child.name
            try:
                if child.is_dir():
                    shutil.copytree(child, target, dirs_exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(child, target)
                copied_entries += 1
            except OSError as exc:
                return {
                    "prepared": False,
                    "reason": f"Failed to copy build context: {exc}",
                    "mode": "local-copy",
                }

        if copied_entries == 0:
            return {
                "prepared": False,
                "reason": "Repository is empty after filtering ignored directories.",
                "mode": "local-copy",
            }

        return {"prepared": True, "mode": "local-copy"}

    def _cleanup_built_image(self, image_tag: str) -> None:
        try:
            subprocess.run(
                ["docker", "image", "rm", "-f", image_tag],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=30,
            )
        except Exception:
            return

    def _collect_logs(self, stdout: str | None, stderr: str | None, max_lines: int = 250) -> List[str]:
        logs: List[str] = []

        if stdout:
            for line in stdout.splitlines():
                if len(logs) >= max_lines:
                    break
                logs.append(f"[stdout] {line}")

        if stderr and len(logs) < max_lines:
            for line in stderr.splitlines():
                if len(logs) >= max_lines:
                    break
                logs.append(f"[stderr] {line}")

        return logs
