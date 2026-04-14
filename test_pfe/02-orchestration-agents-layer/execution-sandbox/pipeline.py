"""
Execution Agent - CI/CD Workflow Execution
Validates generated CI/CD workflows by running them via Act.
"""

import subprocess
import tempfile
import time
import shutil
import threading
import queue
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import logging

logger = logging.getLogger(__name__)


class ExecutionPipeline:
    """
    Executes generated CI/CD artifacts for validation.
    Runs Act workflows in isolated temporary workspaces.
    """
    
    def __init__(self):
        self.logger = logger

    def _is_missing_runner_image_error(self, act_result: Dict[str, Any]) -> bool:
        """Detect common Act runner image pull/create failures."""
        logs = act_result.get("logs", []) if isinstance(act_result, dict) else []
        if not isinstance(logs, list):
            return False

        for entry in logs:
            if not isinstance(entry, dict):
                continue
            line = str(entry.get("line", "")).lower()
            if "no such image" in line and "catthehacker/ubuntu:act-latest" in line:
                return True
            if "failed to create container" in line and "no such image" in line:
                return True
        return False

    def _is_transient_network_error(self, act_result: Dict[str, Any]) -> bool:
        """Detect transient network/TLS failures from act logs."""
        logs = act_result.get("logs", []) if isinstance(act_result, dict) else []
        if not isinstance(logs, list):
            return False

        network_markers = (
            "tls handshake timeout",
            "client network socket disconnected before secure tls connection was established",
            "i/o timeout",
            "connection reset by peer",
            "temporary failure in name resolution",
        )

        for entry in logs:
            if not isinstance(entry, dict):
                continue
            line = str(entry.get("line", "")).lower()
            if any(marker in line for marker in network_markers):
                return True
        return False

    def _run_act_with_network_retries(
        self,
        command: List[str],
        workspace_path: Path,
        act_timeout: int,
        step_name_prefix: str,
        max_retries: int = 2,
    ) -> Dict[str, Any]:
        """Run act command and retry on transient network/TLS failures."""
        latest_result: Dict[str, Any] = {}
        retries_used = 0

        for attempt in range(max_retries + 1):
            latest_result = self._run_command_with_timeout(
                command=command,
                cwd=str(workspace_path),
                timeout_seconds=act_timeout,
                step_name=f"{step_name_prefix}-try-{attempt + 1}",
            )

            if latest_result.get("success"):
                latest_result["network_retry_attempts"] = attempt
                return latest_result

            if not self._is_transient_network_error(latest_result):
                latest_result["network_retry_attempts"] = attempt
                return latest_result

            retries_used = attempt + 1
            if attempt < max_retries:
                self.logger.warning(
                    f"Transient network error detected during act execution, retrying ({attempt + 1}/{max_retries})"
                )

        latest_result["network_retry_attempts"] = retries_used
        return latest_result

    def _run_act_with_fallback_images(self, workspace_path: Path, act_timeout: int) -> Dict[str, Any]:
        """Run act and retry with fallback runner images if the default image is missing."""
        base_command = ["act", "-W", ".github/workflows/ci.yml"]
        attempt_summaries: List[Dict[str, Any]] = []

        primary_result = self._run_act_with_network_retries(
            command=base_command,
            workspace_path=workspace_path,
            act_timeout=act_timeout,
            step_name_prefix="act-run",
            max_retries=2,
        )
        attempt_summaries.append({"command": base_command, "result": primary_result})

        if primary_result.get("success") or not self._is_missing_runner_image_error(primary_result):
            primary_result["runner_image_attempts"] = attempt_summaries
            return primary_result

        fallback_images = [
            "catthehacker/ubuntu:full-latest",
            "catthehacker/ubuntu:act-22.04",
            "nektos/act-environments-ubuntu:22.04",
        ]

        latest_result = primary_result
        for image in fallback_images:
            fallback_cmd = [
                "act",
                "-W",
                ".github/workflows/ci.yml",
                "-P",
                f"ubuntu-latest={image}",
            ]
            self.logger.warning(f"Retrying act with fallback runner image: {image}")
            retry_result = self._run_act_with_network_retries(
                command=fallback_cmd,
                workspace_path=workspace_path,
                act_timeout=act_timeout,
                step_name_prefix=f"act-run-fallback-{image}",
                max_retries=2,
            )
            attempt_summaries.append({"command": fallback_cmd, "result": retry_result})
            latest_result = retry_result
            if retry_result.get("success"):
                retry_result["runner_image_attempts"] = attempt_summaries
                retry_result["selected_runner_image"] = image
                return retry_result

        latest_result["runner_image_attempts"] = attempt_summaries
        return latest_result
    
    def execute(
        self,
        dockerfile_content: str,
        cicd_workflow_content: str,
        repository_path: str,
        github_url: str = "",
        docker_timeout: int = 600,
        act_timeout: int = 1800
    ) -> Dict[str, Any]:
        """
        Execute generated CI/CD workflow in a temporary workspace.
        
        Args:
            dockerfile_content: Kept for backward compatibility (ignored)
            cicd_workflow_content: Content of the generated CI/CD workflow (GitHub Actions YAML)
            repository_path: Path to the source repository
            github_url: Optional GitHub URL if cloning from remote
            docker_timeout: Kept for backward compatibility (unused)
            act_timeout: Timeout in seconds for Act execution (default: 600 = 10 minutes)
        
        Returns:
            Dictionary with execution results including:
            - status: "success" or "error"
            - message: Summary message
            - workspace: Path to temporary workspace
            - docker_build: Marked as skipped (backward compatibility)
            - act: Act execution results (exit_code, logs, success)
            - should_self_repair: Boolean indicating if retry is recommended
        """
        self.logger.info("Starting execution pipeline")
        
        # Validate inputs
        if not cicd_workflow_content or not cicd_workflow_content.strip():
            return self._error_result("CI/CD workflow content is empty or missing")
        
        # Create temporary workspace
        temp_workspace = tempfile.mkdtemp(prefix="exec-agent-")
        workspace_path = Path(temp_workspace)
        self.logger.info(f"Created temporary workspace: {workspace_path}")
        
        try:
            # Copy repository source to workspace
            copy_result = self._copy_repo_source(repository_path, workspace_path, github_url)
            self.logger.info(f"Repository copy result: {copy_result}")
            
            if not copy_result.get("copied"):
                return {
                    "status": "error",
                    "message": f"Failed to prepare workspace: {copy_result.get('reason', 'unknown')}",
                    "workspace": str(workspace_path),
                    "repo_copy": copy_result,
                    "docker_build": {
                        "step": "docker-build",
                        "command": [],
                        "cwd": str(workspace_path),
                        "exit_code": 0,
                        "timed_out": False,
                        "logs": [{"stream": "stdout", "line": "Skipped: execution agent runs only act."}],
                        "success": True,
                        "skipped": True,
                    },
                    "act": {"exit_code": -1, "timed_out": False, "logs": []},
                    "should_self_repair": True,
                }
            
            # Write workflow artifact to workspace
            workflow_path = workspace_path / ".github" / "workflows" / "ci.yml"
            workflow_path.parent.mkdir(parents=True, exist_ok=True)
            
            workflow_path.write_text(cicd_workflow_content, encoding="utf-8")
            self.logger.info("Workflow written to workspace")

            docker_build_result = {
                "step": "docker-build",
                "command": [],
                "cwd": str(workspace_path),
                "exit_code": 0,
                "timed_out": False,
                "logs": [{"stream": "stdout", "line": "Skipped: execution agent runs only act."}],
                "success": True,
                "skipped": True,
            }
            
            # Execute Act workflow
            self.logger.info("Starting Act workflow execution")
            act_result = self._run_act_with_fallback_images(
                workspace_path=workspace_path,
                act_timeout=act_timeout,
            )
            
            # Determine overall success
            pipeline_success = act_result.get("success")
            should_self_repair = not pipeline_success
            
            result = {
                "status": "success" if pipeline_success else "error",
                "message": "Act execution completed successfully" if pipeline_success else "Act execution failed",
                "workspace": str(workspace_path),
                "repo_copy": copy_result,
                "docker_build": docker_build_result,
                "act": act_result,
                "should_self_repair": should_self_repair,
            }
            
            self.logger.info(f"Execution pipeline completed with status: {result['status']}")
            return result
            
        except Exception as e:
            self.logger.error(f"Execution pipeline failed with exception: {e}")
            return {
                "status": "error",
                "message": f"Execution failed with exception: {str(e)}",
                "workspace": str(workspace_path),
                "docker_build": {
                    "step": "docker-build",
                    "command": [],
                    "cwd": str(workspace_path),
                    "exit_code": 0,
                    "timed_out": False,
                    "logs": [{"stream": "stdout", "line": "Skipped: execution agent runs only act."}],
                    "success": True,
                    "skipped": True,
                },
                "act": {"exit_code": -1, "timed_out": False, "logs": []},
                "should_self_repair": True,
                "error": str(e)
            }
    
    def _error_result(self, message: str) -> Dict[str, Any]:
        """Helper to create error result"""
        return {
            "status": "error",
            "message": message,
            "workspace": None,
            "docker_build": {
                "step": "docker-build",
                "command": [],
                "cwd": "",
                "exit_code": 0,
                "timed_out": False,
                "logs": [{"stream": "stdout", "line": "Skipped: execution agent runs only act."}],
                "success": True,
                "skipped": True,
            },
            "act": {"exit_code": -1, "timed_out": False, "logs": []},
            "should_self_repair": True,
        }
    
    def _copy_repo_source(
        self,
        repository_path: str,
        workspace_path: Path,
        github_url: str = ""
    ) -> Dict[str, Any]:
        """
        Copy repository source to workspace.
        Supports both local paths and GitHub URLs.
        """
        # Check if repository_path is actually a URL
        if not github_url and isinstance(repository_path, str):
            repo_path_candidate = repository_path.strip()
            if repo_path_candidate.startswith("http://") or repo_path_candidate.startswith("https://"):
                github_url = repo_path_candidate
        
        # Try GitHub clone if URL provided
        if github_url:
            self.logger.info(f"Cloning repository from GitHub: {github_url}")
            clone = subprocess.run(
                ["git", "clone", "--depth", "1", github_url, str(workspace_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if clone.returncode == 0:
                copied_entries = len(list(workspace_path.iterdir()))
                return {
                    "copied": True,
                    "source": github_url,
                    "destination": str(workspace_path),
                    "copied_entries": copied_entries,
                    "mode": "git-clone",
                }
            
            clone_error = (clone.stderr or clone.stdout or "git clone failed").strip()
            return {
                "copied": False,
                "reason": f"Failed to clone GitHub repository: {clone_error}",
                "source": github_url,
                "destination": str(workspace_path),
                "mode": "git-clone",
            }
        
        # Local copy
        if not repository_path:
            return {"copied": False, "reason": "No repository path provided"}
        
        source_path = Path(repository_path)
        if not source_path.exists() or not source_path.is_dir():
            return {
                "copied": False,
                "reason": f"Repository path not found or not a directory: {repository_path}",
            }
        
        self.logger.info(f"Copying repository from local path: {source_path}")
        
        # Directories to ignore during copy
        ignore_dirs = {
            ".git", ".hg", ".svn",
            "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
            ".venv", "venv", "node_modules",
        }
        
        copied_entries = 0
        for child in source_path.iterdir():
            if child.name in ignore_dirs:
                continue
            
            target = workspace_path / child.name
            if child.is_dir():
                shutil.copytree(child, target, dirs_exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(child, target)
            copied_entries += 1
        
        return {
            "copied": True,
            "source": str(source_path),
            "destination": str(workspace_path),
            "copied_entries": copied_entries,
            "mode": "local-copy",
        }
    
    def _run_command_with_timeout(
        self,
        command: List[str],
        cwd: str,
        timeout_seconds: int,
        step_name: str
    ) -> Dict[str, Any]:
        """
        Run a command with real-time output streaming and hard timeout.
        
        Args:
            command: Command to run as list of strings
            cwd: Working directory
            timeout_seconds: Maximum time to allow command to run
            step_name: Name for logging (e.g., "docker-build", "act-run")
        
        Returns:
            Dictionary with:
            - step: Step name
            - command: Command that was run
            - cwd: Working directory
            - exit_code: Process exit code
            - timed_out: Boolean indicating if timeout occurred
            - logs: List of log entries with stream and line
            - success: Boolean (not timed_out and exit_code == 0)
        """
        self.logger.info(f"[{step_name}] Running: {' '.join(command)}")
        
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        
        output_queue: queue.Queue[Tuple[str, str]] = queue.Queue()
        collected_logs: List[Dict[str, str]] = []
        
        def _reader(pipe, stream_name: str) -> None:
            """Thread function to read from pipe and queue output"""
            if pipe is None:
                return
            try:
                for line in iter(pipe.readline, ""):
                    if line:
                        output_queue.put((stream_name, line.rstrip("\n")))
            except Exception as exc:
                output_queue.put(("stderr", f"[{step_name}] log reader error ({stream_name}): {exc}"))
            finally:
                try:
                    pipe.close()
                except Exception:
                    pass
        
        # Start reader threads
        stdout_thread = threading.Thread(target=_reader, args=(process.stdout, "stdout"), daemon=True)
        stderr_thread = threading.Thread(target=_reader, args=(process.stderr, "stderr"), daemon=True)
        stdout_thread.start()
        stderr_thread.start()
        
        start_time = time.monotonic()
        timed_out = False
        
        # Monitor process and collect output
        while True:
            elapsed = time.monotonic() - start_time
            if elapsed > timeout_seconds:
                self.logger.warning(f"[{step_name}] Timeout after {timeout_seconds}s")
                timed_out = True
                process.kill()
                break
            
            # Collect output from queue
            try:
                stream_name, line = output_queue.get(timeout=0.1)
                self.logger.debug(f"[{step_name}][{stream_name}] {line}")
                # Limit log collection to prevent memory issues
                if len(collected_logs) < 2000:
                    collected_logs.append({"stream": stream_name, "line": line})
            except queue.Empty:
                pass
            
            # Check if process finished
            if (process.poll() is not None and 
                output_queue.empty() and 
                not stdout_thread.is_alive() and 
                not stderr_thread.is_alive()):
                break
        
        # Drain any residual buffered lines
        while True:
            try:
                stream_name, line = output_queue.get_nowait()
                self.logger.debug(f"[{step_name}][{stream_name}] {line}")
                if len(collected_logs) < 2000:
                    collected_logs.append({"stream": stream_name, "line": line})
            except queue.Empty:
                break
        
        exit_code = process.wait()
        success = not timed_out and exit_code == 0
        
        result = {
            "step": step_name,
            "command": command,
            "cwd": cwd,
            "exit_code": exit_code,
            "timed_out": timed_out,
            "logs": collected_logs,
            "success": success,
        }
        
        self.logger.info(f"[{step_name}] Completed: exit_code={exit_code}, timed_out={timed_out}, success={success}")
        return result


def run_execution(
    dockerfile_content: str,
    cicd_workflow_content: str,
    repository_path: str,
    github_url: str = "",
    docker_timeout: int = 600,
    act_timeout: int = 1800
) -> Dict[str, Any]:
    """
    Convenience function to run execution pipeline.
    
    Args:
        dockerfile_content: Kept for backward compatibility (ignored)
        cicd_workflow_content: Generated CI/CD workflow content
        repository_path: Path to source repository
        github_url: Optional GitHub URL
        docker_timeout: Kept for backward compatibility (unused)
        act_timeout: Act execution timeout in seconds
    
    Returns:
        Execution results dictionary
    """
    pipeline = ExecutionPipeline()
    return pipeline.execute(
        dockerfile_content=dockerfile_content,
        cicd_workflow_content=cicd_workflow_content,
        repository_path=repository_path,
        github_url=github_url,
        docker_timeout=docker_timeout,
        act_timeout=act_timeout
    )


if __name__ == "__main__":
    # Example usage
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    if len(sys.argv) < 4:
        print("Usage: python pipeline.py <dockerfile_path> <workflow_path> <repo_path> [github_url]")
        print("Example: python pipeline.py Dockerfile .github/workflows/ci.yml /path/to/repo")
        sys.exit(1)
    
    dockerfile_path = sys.argv[1]
    workflow_path = sys.argv[2]
    repo_path = sys.argv[3]
    github_url = sys.argv[4] if len(sys.argv) > 4 else ""
    
    # Read artifacts
    with open(dockerfile_path, 'r', encoding='utf-8') as f:
        dockerfile = f.read()
    
    with open(workflow_path, 'r', encoding='utf-8') as f:
        workflow = f.read()
    
    # Execute
    result = run_execution(
        dockerfile_content=dockerfile,
        cicd_workflow_content=workflow,
        repository_path=repo_path,
        github_url=github_url
    )
    
    # Print result
    import json
    print(json.dumps(result, indent=2, default=str))
