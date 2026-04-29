"""Realtime Execution Agent API.

Provides HTTP + WebSocket endpoints to run sandbox execution and stream act
output in real-time for frontend visualization panels.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Awaitable, Callable, Deque, Dict, Literal, Optional, Set, Tuple

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from pipeline import ExecutionPipeline

logger = logging.getLogger(__name__)

StageName = Literal["checkout", "build", "test", "docker push"]
StageStatus = Literal["pending", "running", "done", "failed"]
LogLevel = Literal["info", "warn", "error"]

STAGE_ORDER: Tuple[StageName, ...] = ("checkout", "build", "test", "docker push")


class ExecutionRunRequest(BaseModel):
    """Request payload to start a sandbox execution run."""

    cicd_workflow_content: str = Field(..., min_length=1)
    repository_path: str = Field(..., min_length=1)
    dockerfile_content: str = ""
    github_url: str = ""
    act_timeout: int = 1800
    secrets: Dict[str, str] = Field(default_factory=dict)
    prebuilt_image_name: str = ""


class RunStreamHub:
    """Tracks WebSocket clients and broadcasts run events."""

    def __init__(self) -> None:
        self._clients: Dict[str, Set[WebSocket]] = defaultdict(set)
        self._history: Dict[str, Deque[Dict[str, Any]]] = defaultdict(lambda: deque(maxlen=500))
        self._lock = asyncio.Lock()

    async def connect(self, run_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._clients[run_id].add(websocket)
            replay_events = list(self._history.get(run_id, deque()))

        for event in replay_events:
            try:
                await websocket.send_json(event)
            except Exception:
                break

    async def disconnect(self, run_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            run_clients = self._clients.get(run_id)
            if run_clients and websocket in run_clients:
                run_clients.remove(websocket)
            if run_clients is not None and not run_clients:
                self._clients.pop(run_id, None)

    async def broadcast(self, run_id: str, payload: Dict[str, Any]) -> None:
        async with self._lock:
            self._history[run_id].append(payload)
            sockets = list(self._clients.get(run_id, set()))

        dead_sockets: list[WebSocket] = []
        for socket in sockets:
            try:
                await socket.send_json(payload)
            except Exception:
                dead_sockets.append(socket)

        if dead_sockets:
            async with self._lock:
                active = self._clients.get(run_id, set())
                for socket in dead_sockets:
                    active.discard(socket)
                if not active and run_id in self._clients:
                    self._clients.pop(run_id, None)


class ExecutionRealtimeRunner:
    """Runs execution pipeline and emits realtime events."""

    def __init__(self, hub: RunStreamHub) -> None:
        self.hub = hub
        self.pipeline = ExecutionPipeline()

    async def run(self, run_id: str, request: ExecutionRunRequest) -> bool:
        start_ts = time.monotonic()
        stage_states: Dict[StageName, StageStatus] = {stage: "pending" for stage in STAGE_ORDER}
        current_stage: Optional[StageName] = None

        def elapsed_ms() -> int:
            return int((time.monotonic() - start_ts) * 1000)

        async def emit_stage_update(
            stage: StageName,
            status: StageStatus,
            line: str,
            level: LogLevel = "info",
        ) -> None:
            stage_states[stage] = status
            await self.hub.broadcast(
                run_id,
                {
                    "type": "stage_update",
                    "run_id": run_id,
                    "stage": stage,
                    "line": line,
                    "level": level,
                    "elapsed_ms": elapsed_ms(),
                    "stage_status": status,
                },
            )

        async def emit_log(
            stage: StageName,
            line: str,
            level: LogLevel,
        ) -> None:
            await self.hub.broadcast(
                run_id,
                {
                    "run_id": run_id,
                    "stage": stage,
                    "line": line,
                    "level": level,
                    "elapsed_ms": elapsed_ms(),
                    "stage_status": stage_states.get(stage, "pending"),
                },
            )

        async def transition_to(new_stage: StageName) -> None:
            nonlocal current_stage
            if current_stage and stage_states[current_stage] == "running":
                await emit_stage_update(current_stage, "done", f"Stage {current_stage} completed")

            if stage_states[new_stage] not in {"done", "failed", "running"}:
                await emit_stage_update(new_stage, "running", f"Stage {new_stage} started")

            current_stage = new_stage

        # Publish initial stage state for clients that join immediately.
        for stage in STAGE_ORDER:
            await emit_stage_update(stage, "pending", f"Stage {stage} pending")

        temp_workspace = Path(tempfile.mkdtemp(prefix="exec-agent-realtime-"))
        logger.info("Realtime execution %s using workspace %s", run_id, temp_workspace)

        try:
            await emit_stage_update("checkout", "running", "Preparing sandbox workspace")
            current_stage = "checkout"

            copy_result = await asyncio.to_thread(
                self.pipeline._copy_repo_source,
                request.repository_path,
                temp_workspace,
                request.github_url,
            )
            if not copy_result.get("copied"):
                await emit_stage_update(
                    "checkout",
                    "failed",
                    f"Checkout failed: {copy_result.get('reason', 'unknown error')}",
                    level="error",
                )
                await self.hub.broadcast(
                    run_id,
                    {
                        "type": "stage_update",
                        "run_id": run_id,
                        "stage": "checkout",
                        "line": "Sandbox execution failed during checkout",
                        "level": "error",
                        "elapsed_ms": elapsed_ms(),
                        "stage_status": "failed",
                        "result": "failed",
                    },
                )
                return False

            workflow_path = temp_workspace / ".github" / "workflows" / "ci.yml"
            workflow_path.parent.mkdir(parents=True, exist_ok=True)
            workflow_path.write_text(request.cicd_workflow_content, encoding="utf-8")

            if request.dockerfile_content.strip():
                dockerfile_path = temp_workspace / "Dockerfile"
                dockerfile_path.write_text(request.dockerfile_content, encoding="utf-8")

            await emit_stage_update("checkout", "done", "Sandbox workspace ready")
            current_stage = None

            act_temp_dir = temp_workspace / ".act-temp"
            act_temp_dir.mkdir(parents=True, exist_ok=True)

            act_env = os.environ.copy()
            act_env["TEMP"] = str(act_temp_dir)
            act_env["TMP"] = str(act_temp_dir)
            act_env["TMPDIR"] = str(act_temp_dir)
            act_env["RUNNER_TEMP"] = str(act_temp_dir)

            common_args = self.pipeline._build_act_common_args()
            secret_args = self.pipeline._build_act_secret_args(request.secrets)
            extra_args: list[str] = []

            prebuilt_image = request.prebuilt_image_name.strip()
            if prebuilt_image:
                act_env["EXECUTION_DOCKER_IMAGE"] = prebuilt_image
                extra_args.extend(["--env", f"EXECUTION_DOCKER_IMAGE={prebuilt_image}"])

            act_command = [
                "act",
                "-W",
                ".github/workflows/ci.yml",
                *common_args,
                *secret_args,
                *extra_args,
            ]

            await emit_log("build", f"Running: {' '.join(act_command)}", "info")

            async def handle_line(stream: str, raw_line: str) -> None:
                nonlocal current_stage
                candidate_stage = _detect_stage(raw_line, current_stage)
                if candidate_stage and candidate_stage != current_stage:
                    await transition_to(candidate_stage)
                elif candidate_stage and stage_states[candidate_stage] == "pending":
                    await emit_stage_update(candidate_stage, "running", f"Stage {candidate_stage} started")
                    current_stage = candidate_stage

                active_stage = candidate_stage or current_stage or "build"
                if stage_states[active_stage] == "pending":
                    await emit_stage_update(active_stage, "running", f"Stage {active_stage} started")
                    current_stage = active_stage

                level = _detect_level(stream, raw_line)
                await emit_log(active_stage, raw_line, level)

            exit_code, timed_out = await _run_subprocess_with_streaming(
                command=act_command,
                cwd=str(temp_workspace),
                timeout_seconds=max(1, int(request.act_timeout)),
                env=act_env,
                on_line=handle_line,
            )

            if timed_out:
                failed_stage = current_stage or "build"
                await emit_stage_update(failed_stage, "failed", "Act execution timed out", level="error")
                await self.hub.broadcast(
                    run_id,
                    {
                        "type": "stage_update",
                        "run_id": run_id,
                        "stage": failed_stage,
                        "line": "Sandbox execution timed out",
                        "level": "error",
                        "elapsed_ms": elapsed_ms(),
                        "stage_status": "failed",
                        "result": "failed",
                    },
                )
                return False

            if exit_code == 0:
                if current_stage and stage_states[current_stage] == "running":
                    await emit_stage_update(current_stage, "done", f"Stage {current_stage} completed")

                # Complete unobserved stages so progress reaches 100% in the panel.
                for stage in STAGE_ORDER:
                    if stage_states[stage] == "pending":
                        await emit_stage_update(stage, "done", f"Stage {stage} completed")

                await self.hub.broadcast(
                    run_id,
                    {
                        "type": "stage_update",
                        "run_id": run_id,
                        "stage": "docker push",
                        "line": "Sandbox execution completed successfully",
                        "level": "info",
                        "elapsed_ms": elapsed_ms(),
                        "stage_status": "done",
                        "result": "done",
                    },
                )
                return True
            else:
                failed_stage = current_stage or "build"
                if stage_states[failed_stage] != "failed":
                    await emit_stage_update(
                        failed_stage,
                        "failed",
                        f"Stage {failed_stage} failed (exit code {exit_code})",
                        level="error",
                    )

                await self.hub.broadcast(
                    run_id,
                    {
                        "type": "stage_update",
                        "run_id": run_id,
                        "stage": failed_stage,
                        "line": f"Sandbox execution failed with exit code {exit_code}",
                        "level": "error",
                        "elapsed_ms": elapsed_ms(),
                        "stage_status": "failed",
                        "result": "failed",
                        "exit_code": exit_code,
                    },
                )
                return False
        except Exception as exc:
            logger.exception("Realtime execution failed: %s", exc)
            failed_stage = current_stage or "build"
            await self.hub.broadcast(
                run_id,
                {
                    "type": "stage_update",
                    "run_id": run_id,
                    "stage": failed_stage,
                    "line": f"Execution error: {exc}",
                    "level": "error",
                    "elapsed_ms": elapsed_ms(),
                    "stage_status": "failed",
                    "result": "failed",
                },
            )
            return False
        finally:
            # Ephemeral sandbox cleanup to keep observability read-only and isolated.
            shutil.rmtree(temp_workspace, ignore_errors=True)


async def _run_subprocess_with_streaming(
    command: list[str],
    cwd: str,
    timeout_seconds: int,
    env: Optional[Dict[str, str]],
    on_line: Callable[[str, str], Awaitable[None]],
) -> Tuple[int, bool]:
    """Run a subprocess and stream stdout/stderr line-by-line asynchronously."""

    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    async def read_stream(stream: asyncio.StreamReader, stream_name: str) -> None:
        while True:
            raw = await stream.readline()
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").rstrip("\n")
            await on_line(stream_name, line)

    stdout_task = asyncio.create_task(read_stream(process.stdout, "stdout"))
    stderr_task = asyncio.create_task(read_stream(process.stderr, "stderr"))

    timed_out = False
    try:
        exit_code = await asyncio.wait_for(process.wait(), timeout=max(1, timeout_seconds))
    except asyncio.TimeoutError:
        timed_out = True
        process.kill()
        exit_code = await process.wait()

    await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
    return exit_code, timed_out


def _detect_level(stream_name: str, line: str) -> LogLevel:
    lowered = line.lower()
    if stream_name == "stderr":
        if any(token in lowered for token in ("warn", "warning")):
            return "warn"
        return "error"

    if any(token in lowered for token in ("error", "failed", "exception", "traceback")):
        return "error"
    if any(token in lowered for token in ("warn", "warning", "deprecated")):
        return "warn"
    return "info"


def _detect_stage(line: str, current_stage: Optional[StageName]) -> Optional[StageName]:
    lowered = line.lower()

    if any(token in lowered for token in ("actions/checkout", "checkout", "cloning into")):
        return "checkout"
    if any(
        token in lowered
        for token in (
            "build",
            "compile",
            "packaging",
            "mvn -b",
            "gradle build",
            "npm run build",
            "docker build",
        )
    ):
        return "build"
    if any(
        token in lowered
        for token in (
            "test",
            "pytest",
            "junit",
            "surefire",
            "npm test",
            "mvn test",
            "gradle test",
        )
    ):
        return "test"
    if any(
        token in lowered
        for token in (
            "docker push",
            "pushing",
            "buildx",
            "publish",
            "login-action",
            "docker/login-action",
        )
    ):
        return "docker push"

    return current_stage


app = FastAPI(title="Execution Agent Realtime API", version="1.0.0")
_hub = RunStreamHub()
_runner = ExecutionRealtimeRunner(_hub)
_run_tasks: Dict[str, asyncio.Task[None]] = {}
_run_status: Dict[str, str] = {}


@app.post("/api/execution/runs")
async def start_run(request: ExecutionRunRequest) -> Dict[str, str]:
    run_id = uuid.uuid4().hex
    _run_status[run_id] = "running"

    async def _run_wrapper() -> None:
        try:
            succeeded = await _runner.run(run_id, request)
            _run_status[run_id] = "done" if succeeded else "failed"
        except Exception:
            _run_status[run_id] = "failed"
            raise

    task = asyncio.create_task(_run_wrapper())
    _run_tasks[run_id] = task

    def _on_done(done_task: asyncio.Task[None]) -> None:
        if done_task.cancelled():
            _run_status[run_id] = "failed"
        elif done_task.exception() is not None:
            _run_status[run_id] = "failed"
        elif _run_status.get(run_id) == "running":
            _run_status[run_id] = "done"

    task.add_done_callback(_on_done)

    return {
        "run_id": run_id,
        "status": "started",
        "ws_path": f"/ws/execution/{run_id}",
    }


@app.get("/api/execution/runs/{run_id}")
async def get_run_status(run_id: str) -> Dict[str, str]:
    if run_id not in _run_status:
        raise HTTPException(status_code=404, detail="run_id not found")
    return {"run_id": run_id, "status": _run_status[run_id]}


@app.websocket("/ws/execution/{run_id}")
async def execution_stream(websocket: WebSocket, run_id: str) -> None:
    await _hub.connect(run_id, websocket)
    try:
        while True:
            # Keep socket open and detect disconnect cleanly.
            await websocket.receive_text()
    except WebSocketDisconnect:
        await _hub.disconnect(run_id, websocket)
    except Exception:
        await _hub.disconnect(run_id, websocket)
