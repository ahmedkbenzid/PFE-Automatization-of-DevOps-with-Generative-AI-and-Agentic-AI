"""Docker-in-Docker sandbox manager for secure CI/CD pipeline execution."""

import asyncio
import json
import subprocess
import sys
import threading
import time
import uuid
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class SandboxStage:
    """Represents a CI/CD pipeline stage."""
    name: str
    status: str = "pending"  # pending, running, completed, failed
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    logs: List[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class SandboxExecution:
    """Represents a docker sandbox execution."""
    execution_id: str
    container_id: Optional[str] = None
    stages: Dict[str, SandboxStage] = field(default_factory=dict)
    output_lines: List[str] = field(default_factory=list)
    process: Optional[subprocess.Popen] = None
    reader_thread: Optional[threading.Thread] = None
    started_at: float = field(default_factory=time.time)
    returncode: Optional[int] = None
    completed_at: Optional[float] = None


class DockerSandbox:
    """Manages Docker-in-Docker sandbox for CI/CD pipeline execution."""

    def __init__(self, image: str = "docker:24-dind", max_capture_lines: int = 5000):
        """
        Initialize Docker sandbox manager.

        Args:
            image: Docker image to use for dind sandbox
            max_capture_lines: Max lines to buffer in memory
        """
        self.image = image
        self.max_capture_lines = max_capture_lines
        self.executions: Dict[str, SandboxExecution] = {}
        self._lock = threading.Lock()

    def start_execution(
        self,
        pipeline_config: Dict[str, Any],
        secrets: Optional[Dict[str, str]] = None,
        work_dir: Optional[str] = None,
    ) -> str:
        """
        Start a CI/CD pipeline execution in a Docker sandbox.

        Args:
            pipeline_config: Pipeline configuration (stages, scripts, etc.)
            secrets: Environment secrets/credentials
            work_dir: Working directory for execution

        Returns:
            execution_id: Unique identifier for this execution
        """
        execution_id = str(uuid.uuid4())

        # Initialize stages from pipeline config
        stages = {}
        if "stages" in pipeline_config:
            for stage_name in pipeline_config["stages"]:
                stages[stage_name] = SandboxStage(name=stage_name)

        execution = SandboxExecution(
            execution_id=execution_id,
            stages=stages,
        )

        with self._lock:
            self.executions[execution_id] = execution

        execution_work_dir = self._resolve_work_dir(work_dir, execution_id)

        # Start the execution in background
        cmd = self._build_docker_command(pipeline_config, secrets, str(execution_work_dir))
        self._start_process(execution_id, cmd, str(execution_work_dir))

        return execution_id

    def _resolve_work_dir(self, work_dir: Optional[str], execution_id: str) -> Path:
        """Resolve a host working directory that is valid on the current machine."""
        if work_dir:
            candidate = Path(work_dir).expanduser()
            if candidate.exists():
                candidate.mkdir(parents=True, exist_ok=True)
                return candidate

        fallback = Path(tempfile.gettempdir()) / "cicd-build" / execution_id
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

    def _build_docker_command(
        self,
        pipeline_config: Dict[str, Any],
        secrets: Optional[Dict[str, str]],
        work_dir: Optional[str],
    ) -> List[str]:
        """Build Docker command to execute pipeline."""
        cmd = ["docker", "run", "--rm", "-i"]

        # Mount docker socket for dind
        cmd.extend(["-v", "/var/run/docker.sock:/var/run/docker.sock"])

        # Add secrets as environment variables
        if secrets:
            for key, value in secrets.items():
                # Sanitize key
                if key.replace("_", "").replace("-", "").isalnum():
                    cmd.extend(["-e", f"{key}={value}"])

        # Mount working directory
        if work_dir:
            cmd.extend(["-v", f"{work_dir}:/workspace"])
            cmd.extend(["-w", "/workspace"])

        # Add the dind image
        cmd.append(self.image)

        # Add pipeline execution script
        cmd.extend(["/bin/sh", "-c", self._generate_pipeline_script(pipeline_config)])

        return cmd

    def _generate_pipeline_script(self, pipeline_config: Dict[str, Any]) -> str:
        """Generate shell script to execute the pipeline."""
        script_lines = ["#!/bin/sh", "set -e"]

        stages = pipeline_config.get("stages", [])
        for stage_name in stages:
            script_lines.append(f"\necho '=== Starting stage: {stage_name} ==='")
            
            # Get stage scripts
            stage_scripts = pipeline_config.get(stage_name, {})
            if isinstance(stage_scripts, list):
                for cmd in stage_scripts:
                    script_lines.append(f"echo 'Running: {cmd}'")
                    script_lines.append(cmd)
            elif isinstance(stage_scripts, str):
                script_lines.append(f"echo 'Running: {stage_scripts}'")
                script_lines.append(stage_scripts)
            
            script_lines.append(f"echo '=== Completed stage: {stage_name} ==='")

        return "\n".join(script_lines)

    def _start_process(self, execution_id: str, cmd: List[str], cwd: str) -> None:
        """Start the Docker process."""
        execution = self.executions[execution_id]

        try:
            process = subprocess.Popen(
                cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            execution.process = process

            # Start reader thread
            reader_thread = threading.Thread(
                target=self._read_output_worker,
                args=(execution_id,),
                daemon=True,
            )
            execution.reader_thread = reader_thread
            reader_thread.start()

        except Exception as e:
            execution.returncode = 1
            execution.output_lines.append(f"Error starting process: {str(e)}")

    def _read_output_worker(self, execution_id: str) -> None:
        """Background worker to read process output."""
        execution = self.executions[execution_id]
        if not execution.process:
            return

        current_stage = None

        try:
            for line in execution.process.stdout:
                line = line.rstrip("\n")
                execution.output_lines.append(line)

                # Manage buffer size
                if len(execution.output_lines) > self.max_capture_lines:
                    del execution.output_lines[:1000]

                # Track stage transitions
                if "=== Starting stage:" in line:
                    stage_name = line.split("=== Starting stage: ")[1].rstrip(" ===")
                    if stage_name in execution.stages:
                        current_stage = stage_name
                        execution.stages[stage_name].status = "running"
                        execution.stages[stage_name].start_time = time.time()

                elif "=== Completed stage:" in line:
                    stage_name = line.split("=== Completed stage: ")[1].rstrip(" ===")
                    if stage_name in execution.stages:
                        execution.stages[stage_name].status = "completed"
                        execution.stages[stage_name].end_time = time.time()

                # Add to current stage logs
                if current_stage and current_stage in execution.stages:
                    execution.stages[current_stage].logs.append(line)

            execution.returncode = execution.process.returncode or 0
            execution.completed_at = time.time()

        except Exception as e:
            execution.returncode = 1
            execution.output_lines.append(f"Error reading output: {str(e)}")
            execution.completed_at = time.time()

    def get_execution(self, execution_id: str) -> Optional[SandboxExecution]:
        """Get execution details."""
        with self._lock:
            return self.executions.get(execution_id)

    def get_execution_status(self, execution_id: str) -> Dict[str, Any]:
        """Get execution status as dictionary."""
        execution = self.get_execution(execution_id)
        if not execution:
            return {"error": "Execution not found"}

        return {
            "execution_id": execution_id,
            "started_at": execution.started_at,
            "completed_at": execution.completed_at,
            "returncode": execution.returncode,
            "total_lines": len(execution.output_lines),
            "stages": {
                name: {
                    "name": stage.name,
                    "status": stage.status,
                    "start_time": stage.start_time,
                    "end_time": stage.end_time,
                    "duration": (
                        (stage.end_time or time.time()) - stage.start_time
                        if stage.start_time
                        else None
                    ),
                    "log_count": len(stage.logs),
                    "error": stage.error,
                }
                for name, stage in execution.stages.items()
            },
        }

    def get_execution_logs(
        self, execution_id: str, start_line: int = 0, limit: int = 100
    ) -> List[str]:
        """Get execution logs."""
        execution = self.get_execution(execution_id)
        if not execution:
            return []

        return execution.output_lines[start_line : start_line + limit]

    def stop_execution(self, execution_id: str) -> bool:
        """Stop a running execution."""
        execution = self.get_execution(execution_id)
        if not execution or not execution.process:
            return False

        try:
            execution.process.terminate()
            execution.process.wait(timeout=10)
            return True
        except subprocess.TimeoutExpired:
            execution.process.kill()
            return True
        except Exception:
            return False

    def cleanup_execution(self, execution_id: str) -> None:
        """Clean up execution resources."""
        execution = self.get_execution(execution_id)
        if execution:
            self.stop_execution(execution_id)

        with self._lock:
            if execution_id in self.executions:
                del self.executions[execution_id]
