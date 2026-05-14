from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from uuid import uuid4

from dotenv import load_dotenv
load_dotenv()

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.orchestrator_utils import (
    _parse_orchestrator_stdout,
    build_launch_env,
    extract_artifacts,
)
from backend.execution_agent_bridge import run_generated_cicd_workflow
from backend.session_history_router import (
    history_router,
    _load as _history_load,
    _save as _history_save,
)
from backend.websocket_manager import RunManager, RunState
from backend.routes.artifacts import router as artifacts_router
from backend.routes.cicd_build import router as cicd_router
from backend.routes.log_judge import router as judge_router


class RunRequest(BaseModel):
    prompt: str
    repo_path: Optional[str] = None
    github_url: Optional[str] = None
    require_plan_approval: bool = False
    create_pr: bool = False
    branch_name: Optional[str] = None
    pr_title: Optional[str] = None
    pr_body: Optional[str] = None
    output_scope: Literal["asked", "all"] = "asked"
    runtime_secrets: Dict[str, str] = Field(default_factory=dict)
    build_in_docker: bool = True


class ApproveRequest(BaseModel):
    approved: bool
    edited_execution_order: List[Any] = Field(default_factory=list)

class StartExecutionRequest(BaseModel):
    force: bool = False
    artifacts: Optional[Dict[str, Any]] = None


def _strip_json_fences(text: str) -> str:
    content = text.strip()
    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()


def _parse_chat_artifacts_response(raw_text: str) -> Dict[str, Any]:
    content = _strip_json_fences(raw_text)

    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise json.JSONDecodeError("Expected a JSON object", content, 0)

    for _ in range(3):
        explanation = parsed.get("explanation")
        artifacts = parsed.get("artifacts")

        if not isinstance(explanation, str):
            break

        inner_content = _strip_json_fences(explanation)
        if not inner_content.startswith("{"):
            break

        try:
            inner_parsed = json.loads(inner_content)
        except json.JSONDecodeError:
            break

        if not isinstance(inner_parsed, dict):
            break

        parsed = inner_parsed
        if artifacts is not None:
            break

    return {
        "explanation": parsed.get("explanation", "Done."),
        "artifacts": parsed.get("artifacts"),
    }


def _merge_artifacts(
    original: Dict[str, Any],
    updates: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge LLM-returned artifacts with the originals so partial responses
    don't wipe out unchanged fields (e.g. terraform sub-files)."""
    merged = dict(original)
    for key in ("yaml", "dockerfile", "metadata"):
        if key in updates:
            merged[key] = updates[key]

    for group_key in ("terraform", "kubernetes"):
        if group_key in updates and isinstance(updates[group_key], dict):
            base = dict(merged.get(group_key) or {})
            base.update(updates[group_key])
            merged[group_key] = base
        elif group_key in updates:
            merged[group_key] = updates[group_key]

    return merged

app = FastAPI(title="Orchestrator Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://localhost:4201"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include artifact routes
app.include_router(artifacts_router, prefix="/api")

# Include CI/CD routes
app.include_router(cicd_router, prefix="/api")

# Include LLM-as-a-Judge routes
app.include_router(judge_router, prefix="/api")

# Include session history routes
app.include_router(history_router, prefix="/api")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ORCHESTRATOR_SCRIPT = PROJECT_ROOT / "test_pfe" / "02-orchestration-agents-layer" / "orchestrator-agent" / "run_orchestrator.py"
ORCHESTRATOR_CWD = ORCHESTRATOR_SCRIPT.parent
SIGNAL_DIR = ORCHESTRATOR_CWD  # Directory for approval/repair signal files

run_manager = RunManager()
runs: Dict[str, RunState] = run_manager.runs
post_run_execution_results: Dict[str, Dict[str, Any]] = {}
post_run_execution_lock = threading.Lock()
edited_artifacts_overrides: Dict[str, Dict[str, Any]] = {}
edited_artifacts_lock = threading.Lock()
history_lock = threading.Lock()


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _to_history_artifacts(artifacts: Dict[str, Any]) -> List[Dict[str, Any]]:
    history_artifacts: List[Dict[str, Any]] = []

    yaml_content = artifacts.get("yaml")
    if isinstance(yaml_content, str) and yaml_content.strip():
        history_artifacts.append(
            {
                "type": "cicd",
                "filename": ".github/workflows/ci.yml",
                "content": yaml_content,
                "validation_status": "unknown",
                "validation_errors": [],
            }
        )

    dockerfile = artifacts.get("dockerfile")
    if isinstance(dockerfile, str) and dockerfile.strip():
        history_artifacts.append(
            {
                "type": "dockerfile",
                "filename": "Dockerfile",
                "content": dockerfile,
                "validation_status": "unknown",
                "validation_errors": [],
            }
        )

    terraform = artifacts.get("terraform")
    if isinstance(terraform, dict):
        for name, content in terraform.items():
            if isinstance(content, str) and content.strip():
                history_artifacts.append(
                    {
                        "type": "terraform",
                        "filename": str(name),
                        "content": content,
                        "validation_status": "unknown",
                        "validation_errors": [],
                    }
                )

    kubernetes = artifacts.get("kubernetes")
    if isinstance(kubernetes, dict):
        for name, content in kubernetes.items():
            if isinstance(content, str) and content.strip():
                history_artifacts.append(
                    {
                        "type": "kubernetes",
                        "filename": str(name),
                        "content": content,
                        "validation_status": "unknown",
                        "validation_errors": [],
                    }
                )

    return history_artifacts


def _to_history_logs(lines: List[str], max_lines: int = 200) -> List[Dict[str, Any]]:
    recent_lines = lines[-max_lines:]
    logs: List[Dict[str, Any]] = []
    now = _utc_now_iso()

    for line in recent_lines:
        level = "info"
        lowered = str(line).lower()
        if "error" in lowered or "traceback" in lowered or "failed" in lowered:
            level = "error"
        elif "warn" in lowered:
            level = "warning"
        elif "success" in lowered or "completed" in lowered:
            level = "success"

        logs.append(
            {
                "timestamp": now,
                "level": level,
                "message": str(line),
                "agent": None,
            }
        )

    return logs


def _create_history_session_for_run(run_id: str, request: RunRequest) -> Optional[str]:
    try:
        now = _utc_now_iso()
        session_id = str(uuid4())
        entry: Dict[str, Any] = {
            "session_id": session_id,
            "run_id": run_id,
            "prompt": request.prompt,
            "created_at": now,
            "updated_at": now,
            "status": "running",
            "artifacts": [],
            "execution_logs": [],
            "repair_attempts": [],
            "rag_sources": [],
            "agents_used": [],
            "duration_seconds": None,
            "artifact_count": 0,
            "log_count": 0,
        }
        with history_lock:
            sessions = _history_load()
            sessions.insert(0, entry)
            _history_save(sessions)
        return session_id
    except Exception as exc:
        print(f"[Backend] Failed to create history session for run {run_id}: {exc}", file=sys.stderr)
        return None


def _finalize_history_session_for_run(run_id: str, run_state: RunState) -> None:
    if run_state.history_finalized:
        return
    if not run_state.history_session_id:
        return

    try:
        if run_state.parsed_result is None:
            stdout_text = "\n".join(run_state.output_lines)
            run_state.parsed_result = _parse_orchestrator_stdout(stdout_text, "")

        artifacts = _get_effective_artifacts(run_id, run_state, refresh_parse=False)
        history_artifacts = _to_history_artifacts(artifacts)
        history_logs = _to_history_logs(run_state.output_lines)

        status = "completed"
        if (run_state.process.poll() or 0) != 0:
            status = "failed"
        parsed_status = str((run_state.parsed_result or {}).get("status") or "").lower()
        if parsed_status in {"error", "failed"}:
            status = "failed"

        repo_context = (run_state.parsed_result or {}).get("state", {}).get("repo_context", {})
        agents_used = (run_state.parsed_result or {}).get("state", {}).get("execution_order")
        if not isinstance(agents_used, list):
            agents_used = []
        rag_sources: List[str] = []
        if isinstance(repo_context, dict):
            github_url = repo_context.get("github_url")
            repo_path = repo_context.get("path")
            if isinstance(github_url, str) and github_url.strip():
                rag_sources.append(github_url)
            if isinstance(repo_path, str) and repo_path.strip():
                rag_sources.append(repo_path)

        now = _utc_now_iso()
        duration = max(0.0, time.time() - run_state.started_at)

        with history_lock:
            sessions = _history_load()
            for session in sessions:
                if session.get("session_id") == run_state.history_session_id:
                    session["updated_at"] = now
                    session["status"] = status
                    session["artifacts"] = history_artifacts
                    session["artifact_count"] = len(history_artifacts)
                    session["execution_logs"] = history_logs
                    session["log_count"] = len(history_logs)
                    session["duration_seconds"] = round(duration, 1)
                    session["agents_used"] = [str(a) for a in agents_used]
                    session["rag_sources"] = rag_sources
                    break
            _history_save(sessions)

        run_state.history_finalized = True
    except Exception as exc:
        print(f"[Backend] Failed to finalize history for run {run_id}: {exc}", file=sys.stderr)


def _to_safe_jsonable(value: Any, seen: Optional[set[int]] = None) -> Any:
    if seen is None:
        seen = set()

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    obj_id = id(value)
    if obj_id in seen:
        return "<circular-reference>"

    seen.add(obj_id)
    try:
        if isinstance(value, dict):
            return {str(k): _to_safe_jsonable(v, seen) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_to_safe_jsonable(item, seen) for item in value]
        return str(value)
    finally:
        seen.discard(obj_id)


def _build_orchestrator_command(payload: RunRequest, run_id: str) -> List[str]:
    print(f"[Backend] DEBUG: require_plan_approval = {payload.require_plan_approval}", file=sys.stderr)
    cmd = [sys.executable, "-u", str(ORCHESTRATOR_SCRIPT)]
    cmd.extend(["--prompt", payload.prompt])
    cmd.extend(["--run-id", run_id])

    # Pass run_id via environment variable as backup
    # (command-line arg should work, but this is a safety net)

    if payload.require_plan_approval:
        print(f"[Backend] Adding --plan-only flag", file=sys.stderr)
        cmd.append("--plan-only")
    else:
        print(f"[Backend] NOT adding --plan-only flag", file=sys.stderr)

    if payload.repo_path:
        cmd.extend(["--repo-path", payload.repo_path])

    if payload.github_url:
        cmd.extend(["--github-url", payload.github_url])

    cmd.extend(["--output-scope", payload.output_scope])

    user_feedback = "accept" if payload.create_pr else "not"
    cmd.extend(["--user-feedback", user_feedback])

    if payload.create_pr:
        branch_name = str(payload.branch_name or "").strip() or "devops/auto-generated"
        pr_title = str(payload.pr_title or "").strip() or "Auto-generated DevOps configurations"
        pr_body = str(payload.pr_body or "").strip() or "Generated by Multi-Agent DevOps Orchestrator"
        cmd.append("--create-pr")
        cmd.extend(["--branch-name", branch_name])
        cmd.extend(["--pr-title", pr_title])
        cmd.extend(["--pr-body", pr_body])

    return cmd


def _ensure_run_exists(run_id: str) -> RunState:
    run_state = run_manager.get_run(run_id)
    if run_state is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return run_state

def _get_effective_artifacts(run_id: str, run_state: RunState, refresh_parse: bool = False) -> Dict[str, Any]:
    if refresh_parse or run_state.parsed_result is None:
        stdout_text = "\n".join(run_state.output_lines)
        run_state.parsed_result = _parse_orchestrator_stdout(stdout_text, "")

    artifacts = extract_artifacts(run_state.parsed_result or {})
    with edited_artifacts_lock:
        override = edited_artifacts_overrides.get(run_id)

    if isinstance(override, dict):
        for key in ("yaml", "dockerfile", "terraform", "kubernetes", "metadata"):
            if key in override:
                artifacts[key] = override.get(key)

    return artifacts


def _normalize_edited_artifacts_payload(artifacts: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(artifacts)
    dockerfile = normalized.get("dockerfile")
    if isinstance(dockerfile, str):
        content = dockerfile.strip()
        for fence in ("```", "'''"):
            lines = content.splitlines()
            if len(lines) >= 2 and lines[0].strip().startswith(fence) and lines[-1].strip() == fence:
                content = "\n".join(lines[1:-1]).strip()
                break
        normalized["dockerfile"] = content
    return normalized

def _run_execution_agent_after_artifacts(run_id: str, request: RunRequest) -> None:
    print(f"[Backend] Execution watcher started for run {run_id}", file=sys.stderr)
    while run_manager.is_running(run_id):
        time.sleep(1)

    run_state = run_manager.get_run(run_id)
    if run_state is None or not request.build_in_docker:
        print(f"[Backend] Execution watcher exiting early for run {run_id}: run_state missing or build_in_docker disabled", file=sys.stderr)
        return

    artifacts = _get_effective_artifacts(run_id, run_state, refresh_parse=True)

    workflow_yaml = artifacts.get("yaml") or ""
    if not workflow_yaml.strip():
        with post_run_execution_lock:
            post_run_execution_results[run_id] = {
                "status": "error",
                "message": "No CI/CD workflow was generated by cicd-agent.",
                "started": False,
            }
        print(f"[Backend] Execution watcher found no workflow artifact for run {run_id}", file=sys.stderr)
        return

    repo_context = (run_state.parsed_result or {}).get("state", {}).get("repo_context", {})
    repository_path = (
        str(request.repo_path).strip()
        if request.repo_path and str(request.repo_path).strip()
        else str(repo_context.get("path") or PROJECT_ROOT)
    )
    github_url = str(request.github_url or repo_context.get("github_url") or "").strip()

    pending_result = {
        "status": "running",
        "started": True,
        "message": "Execution agent is validating the generated CI/CD workflow.",
    }
    run_state.execution_result = pending_result
    with post_run_execution_lock:
        post_run_execution_results[run_id] = pending_result

    try:
        print(f"[Backend] Launching execution agent for run {run_id} using repository_path={repository_path}", file=sys.stderr)
        
        logs_file = Path(SIGNAL_DIR) / f"{run_id}.execution.logs.jsonl"
        logs_file.parent.mkdir(parents=True, exist_ok=True)
        if logs_file.exists():
            logs_file.unlink()
            
        def append_log(log_entry: Dict[str, str]):
            with open(logs_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")

        execution_result = run_generated_cicd_workflow(
            dockerfile_content=artifacts.get("dockerfile") or "",
            cicd_workflow_content=workflow_yaml,
            repository_path=repository_path,
            github_url=github_url,
            act_timeout=1800,
            secrets=request.runtime_secrets,
            log_callback=append_log,
        )
        execution_result = _to_safe_jsonable(execution_result)
        
        print(f"[Backend] Execution agent completed for run {run_id} with status={execution_result.get('status')}", file=sys.stderr)
        run_state.execution_result = execution_result
        with post_run_execution_lock:
            post_run_execution_results[run_id] = execution_result
    except Exception as exc:
        error_result = {
            "status": "error",
            "started": True,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        print(f"[Backend] Execution agent failed for run {run_id}: {exc}", file=sys.stderr)
        run_state.execution_result = error_result
        with post_run_execution_lock:
            post_run_execution_results[run_id] = error_result


def _start_execution_agent_for_run(run_id: str, force_restart: bool = False) -> Dict[str, Any]:
    run_state = _ensure_run_exists(run_id)

    with post_run_execution_lock:
        existing = post_run_execution_results.get(run_id)
        if isinstance(existing, dict) and existing.get("started"):
            existing_status = str(existing.get("status") or "").lower()
            if existing_status in {"running", "pending"}:
                return {
                    "run_id": run_id,
                    "started": True,
                    "already_started": True,
                    "status": existing.get("status", "running"),
                    "message": existing.get("message", "Execution agent already running."),
                }
            if not force_restart:
                return {
                    "run_id": run_id,
                    "started": True,
                    "already_started": True,
                    "status": existing.get("status", "running"),
                    "message": existing.get("message", "Execution agent already started."),
                }

    preserved_secrets = None
    if isinstance(run_state.execution_result, dict):
        preserved_secrets = run_state.execution_result.get("secrets")
    if preserved_secrets is None and isinstance(existing, dict):
        preserved_secrets = existing.get("secrets")

    artifacts = _get_effective_artifacts(run_id, run_state, refresh_parse=(run_state.parsed_result is None))
    workflow_yaml = artifacts.get("yaml") or ""
    if not workflow_yaml.strip():
        with post_run_execution_lock:
            post_run_execution_results[run_id] = {
                "status": "error",
                "started": False,
                "message": "No CI/CD workflow artifact is available for execution.",
            }
        return {
            "run_id": run_id,
            "started": False,
            "status": "error",
            "message": "No CI/CD workflow artifact is available for execution.",
        }

    repo_context = (run_state.parsed_result or {}).get("state", {}).get("repo_context", {})
    repository_path = str(repo_context.get("path") or PROJECT_ROOT)
    github_url = str(repo_context.get("github_url") or "").strip()

    pending_result = {
        "status": "running",
        "started": True,
        "message": "Execution-sandbox agent is validating the generated CI/CD workflow.",
    }
    if isinstance(preserved_secrets, dict):
        pending_result["secrets"] = preserved_secrets
    run_state.execution_result = pending_result
    with post_run_execution_lock:
        post_run_execution_results[run_id] = pending_result

    def _direct_execution_worker() -> None:
        try:
            print(f"[Backend] Launching execution-sandbox for run {run_id} using repository_path={repository_path}", file=sys.stderr)
            
            # Create a logs file for streaming output
            logs_file = Path(SIGNAL_DIR) / f"{run_id}.execution.logs.jsonl"
            logs_file.parent.mkdir(parents=True, exist_ok=True)
            if logs_file.exists():
                logs_file.unlink()
                
            def append_log(log_entry: Dict[str, str]):
                with open(logs_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_entry) + "\n")
            
            execution_result = run_generated_cicd_workflow(
                dockerfile_content=artifacts.get("dockerfile") or "",
                cicd_workflow_content=workflow_yaml,
                repository_path=repository_path,
                github_url=github_url,
                act_timeout=1800,
                secrets=preserved_secrets if isinstance(preserved_secrets, dict) else None,
                log_callback=append_log,
            )
            execution_result = _to_safe_jsonable(execution_result)
            
            print(f"[Backend] Execution-sandbox completed for run {run_id} with status={execution_result.get('status')}", file=sys.stderr)
            run_state.execution_result = execution_result
            with post_run_execution_lock:
                post_run_execution_results[run_id] = execution_result
        except Exception as exc:
            error_result = {
                "status": "error",
                "started": True,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
            print(f"[Backend] Execution-sandbox failed for run {run_id}: {exc}", file=sys.stderr)
            run_state.execution_result = error_result
            with post_run_execution_lock:
                post_run_execution_results[run_id] = error_result

    worker = threading.Thread(target=_direct_execution_worker, daemon=True)
    worker.start()

    return {
        "run_id": run_id,
        "started": True,
        "already_started": False,
        "status": "running",
        "message": "Execution-sandbox agent started for this run.",
    }


@app.post("/api/runs")
async def start_run(request: RunRequest) -> Dict[str, str]:
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt is required")

    if not ORCHESTRATOR_SCRIPT.exists():
        raise HTTPException(status_code=500, detail=f"Orchestrator script not found: {ORCHESTRATOR_SCRIPT}")

    run_id = str(uuid4())
    cmd = _build_orchestrator_command(request, run_id)
    run_env = build_launch_env(os.environ.copy(), request.runtime_secrets)
    run_env.setdefault("PYTHONUNBUFFERED", "1")
    run_env.setdefault("PYTHONIOENCODING", "utf-8")
    # Pass run_id via environment variable as backup
    run_env["ORCHESTRATOR_RUN_ID"] = run_id
    run_manager.start_run(
        run_id=run_id,
        cmd=cmd,
        cwd=str(ORCHESTRATOR_CWD),
        env=run_env,
    )

    run_state = run_manager.get_run(run_id)
    if run_state is not None:
        run_state.build_in_docker = request.build_in_docker
        run_state.history_session_id = _create_history_session_for_run(run_id, request)

    if request.build_in_docker:
        watcher = threading.Thread(
            target=_run_execution_agent_after_artifacts,
            args=(run_id, request),
            daemon=True,
        )
        watcher.start()

    return {"run_id": run_id}


@app.websocket("/ws/runs/{run_id}")
async def stream_run_logs(websocket: WebSocket, run_id: str) -> None:
    await websocket.accept()

    run_state = run_manager.get_run(run_id)
    if run_state is None:
        await websocket.send_json({"type": "error", "message": f"Run not found: {run_id}"})
        await websocket.close(code=1008)
        return

    line_index = 0
    try:
        while True:
            new_lines = run_manager.get_new_lines(run_id, line_index)
            if new_lines:
                for line in new_lines:
                    await websocket.send_json({"type": "log", "line": line})
                line_index += len(new_lines)

            if not run_manager.is_running(run_id):
                run_state = _ensure_run_exists(run_id)
                if run_state.parsed_result is None:
                    stdout_text = "\n".join(run_state.output_lines)
                    run_state.parsed_result = _parse_orchestrator_stdout(stdout_text, "")

                run_state.returncode = (
                    run_state.process.returncode
                    if run_state.process.returncode is not None
                    else run_state.process.poll()
                )

                _finalize_history_session_for_run(run_id, run_state)

                await websocket.send_json({"type": "complete", "result": run_state.parsed_result})
                await websocket.close()
                return

            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        return


@app.get("/api/runs/{run_id}/status")
async def get_run_status(run_id: str) -> Dict[str, Any]:
    run_state = _ensure_run_exists(run_id)
    running = run_manager.is_running(run_id)
    returncode = run_state.process.returncode if run_state.process.returncode is not None else run_state.process.poll()
    run_state.returncode = returncode

    if not running:
        _finalize_history_session_for_run(run_id, run_state)

    with post_run_execution_lock:
        execution_result = post_run_execution_results.get(run_id)
    execution_result = _to_safe_jsonable(execution_result)

    return {
        "run_id": run_id,
        "running": running,
        "returncode": returncode,
        "line_count": len(run_state.output_lines),
        "build_in_docker": run_state.build_in_docker,
        "execution_result": execution_result,
        "judge_verdict": _to_safe_jsonable(run_state.judge_verdict),
    }


@app.get("/api/runs/{run_id}/execution")
async def get_post_run_execution(run_id: str) -> Dict[str, Any]:
    _ensure_run_exists(run_id)
    with post_run_execution_lock:
        execution_result = post_run_execution_results.get(run_id)
    execution_result = _to_safe_jsonable(execution_result)

    if execution_result is None:
        return {"run_id": run_id, "status": "pending", "started": False}

    return {"run_id": run_id, **execution_result}


@app.get("/api/runs/{run_id}/execution/logs")
async def get_execution_logs(run_id: str) -> Dict[str, Any]:
    """Get execution logs from the streaming logs file."""
    _ensure_run_exists(run_id)
    
    logs_file = Path(SIGNAL_DIR) / f"{run_id}.execution.logs.jsonl"
    logs = []
    
    if logs_file.exists():
        try:
            with open(logs_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            log_entry = json.loads(line)
                            logs.append(log_entry)
                        except json.JSONDecodeError:
                            pass
        except Exception as e:
            print(f"Error reading logs file: {e}", file=sys.stderr)
    
    # Also try to get logs from the completed result
    with post_run_execution_lock:
        execution_result = post_run_execution_results.get(run_id)
    
    if execution_result and isinstance(execution_result.get("act"), dict):
        act_logs = execution_result.get("act", {}).get("logs", [])
        # Merge with file logs, preferring act logs if available
        if act_logs and not logs:
            logs = act_logs
    
    return {
        "run_id": run_id,
        "logs": logs,
        "count": len(logs),
    }

@app.post("/api/runs/{run_id}/artifacts/edited")
async def save_edited_artifacts(run_id: str, payload: Dict[str, Any] = Body(default_factory=dict)) -> Dict[str, Any]:
    _ensure_run_exists(run_id)

    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        raise HTTPException(status_code=400, detail="artifacts payload must be an object")

    safe_artifacts = _to_safe_jsonable(artifacts)
    with edited_artifacts_lock:
        edited_artifacts_overrides[run_id] = safe_artifacts

    return {"ok": True, "run_id": run_id}

@app.post("/api/runs/{run_id}/execution/start")
async def start_post_run_execution(run_id: str, request: StartExecutionRequest = Body(default_factory=StartExecutionRequest)) -> Dict[str, Any]:
    _ensure_run_exists(run_id)
    if isinstance(request.artifacts, dict):
        safe_artifacts = _to_safe_jsonable(request.artifacts)
        with edited_artifacts_lock:
            edited_artifacts_overrides[run_id] = safe_artifacts
    return _start_execution_agent_for_run(run_id, force_restart=request.force)


@app.post("/api/runs/{run_id}/approve")
async def approve_run(run_id: str, request: ApproveRequest) -> Dict[str, Any]:
    _ensure_run_exists(run_id)
    
    # Ensure signal directory exists
    SIGNAL_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[Backend] Signal directory: {SIGNAL_DIR.resolve()}", file=sys.stderr)
    print(f"[Backend] Signal directory exists: {SIGNAL_DIR.exists()}", file=sys.stderr)
    
    approval_file = SIGNAL_DIR / f"{run_id}.approval.json"
    payload = {
        "run_id": run_id,
        "approved": request.approved,
        "edited_execution_order": request.edited_execution_order,
        "timestamp": time.time(),
    }
    
    try:
        approval_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"[Backend] ✅ Approval signal written to: {approval_file.resolve()}", file=sys.stderr)
        print(f"[Backend] File exists: {approval_file.exists()}", file=sys.stderr)
        print(f"[Backend] Signal content: {json.dumps(payload, indent=2)}", file=sys.stderr)
        sys.stderr.flush()
    except Exception as e:
        print(f"[Backend] ❌ ERROR writing approval signal: {e}", file=sys.stderr)
        sys.stderr.flush()
        raise
    
    return {"ok": True, "file": str(approval_file)}


@app.post("/api/runs/{run_id}/repair")
async def request_repair(run_id: str, payload: Dict[str, Any] = Body(default_factory=dict)) -> Dict[str, Any]:
    _ensure_run_exists(run_id)
    repair_file = ORCHESTRATOR_CWD / f"{run_id}.repair.json"
    repair_payload = {
        "run_id": run_id,
        "timestamp": time.time(),
        **(payload or {}),
    }
    repair_file.write_text(json.dumps(repair_payload, indent=2), encoding="utf-8")
    return {"ok": True, "file": str(repair_file)}


@app.get("/api/runs/{run_id}/debug")
async def debug_run(run_id: str) -> Dict[str, Any]:
    """Debug endpoint: shows raw stored lines and what the parser sees."""
    run_state = _ensure_run_exists(run_id)
    total_lines = len(run_state.output_lines)
    # Show last 30 lines so we can see the JSON block
    tail = run_state.output_lines[max(0, total_lines - 30):]
    stdout_text = "\n".join(run_state.output_lines)
    parsed = _parse_orchestrator_stdout(stdout_text, "")
    return {
        "run_id": run_id,
        "total_lines": total_lines,
        "tail_lines": tail,
        "parsed_status": parsed.get("status"),
        "has_state": "state" in parsed,
        "has_agent_outputs": bool(parsed.get("state", {}).get("agent_outputs")),
        "parsed_result_cached": run_state.parsed_result is not None,
    }


@app.get("/api/runs/{run_id}/artifacts")
async def get_artifacts(run_id: str) -> Dict[str, Any]:
    run_state = _ensure_run_exists(run_id)

    artifacts = _get_effective_artifacts(run_id, run_state, refresh_parse=True)
    print(f"[Backend] artifacts: total_lines={len(run_state.output_lines)}, has_state={bool(run_state.parsed_result and 'state' in run_state.parsed_result)}, has_agent_outputs={bool((run_state.parsed_result or {}).get('state', {}).get('agent_outputs'))}", file=sys.stderr)
    sys.stderr.flush()

    return artifacts


@app.get("/api/runs/{run_id}/plan")
async def get_execution_plan(run_id: str) -> Dict[str, Any]:
    run_state = _ensure_run_exists(run_id)

    if run_state.parsed_result is None:
        stdout_text = "\n".join(run_state.output_lines)
        run_state.parsed_result = _parse_orchestrator_stdout(stdout_text, "")

    result = run_state.parsed_result or {}
    plan = result.get("execution_plan", {})
    
    return {
        "run_id": run_id,
        "plan": plan,
        "complexity_score": result.get("complexity_score", 0),
        "planner_reasoning": result.get("planner_reasoning", ""),
        "status": result.get("status", "unknown"),
        "plan_only": result.get("plan_only", False),
    }


@app.get("/api/runs/{run_id}/logs")
async def get_logs(
    run_id: str,
    offset: int = 0,
    limit: int = 100,
) -> Dict[str, Any]:
    run_state = _ensure_run_exists(run_id)
    
    all_lines = run_state.output_lines
    total = len(all_lines)
    lines = all_lines[offset : offset + limit] if offset < total else []
    
    return {
        "run_id": run_id,
        "lines": lines,
        "offset": offset,
        "limit": limit,
        "total": total,
        "has_more": offset + limit < total,
    }


class ArtifactChatRequest(BaseModel):
    """Request body for the artifact chat endpoint."""
    message: str
    artifacts: Dict[str, Any]
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)


@app.post("/api/chat/artifacts")
async def chat_modify_artifacts(request: ArtifactChatRequest) -> Dict[str, Any]:
    """
    LLM-powered endpoint that understands user prompts in the context of
    correcting / modifying DevOps artifacts (CI/CD YAML, Dockerfile,
    Terraform HCL, Kubernetes manifests).

    Uses the Groq LLM already configured for the orchestrator so no
    extra API keys are needed and nothing is exposed on the frontend.
    """
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="message is required")

    # ── Load Groq config from orchestrator ──────────────────────────
    orchestrator_env = ORCHESTRATOR_CWD / ".env"
    groq_key = os.environ.get("GROQ_API_KEY", "")
    model_name = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")

    # Try loading from orchestrator .env if not already in environment
    if not groq_key and orchestrator_env.exists():
        try:
            for line in orchestrator_env.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("GROQ_API_KEY="):
                    groq_key = line.split("=", 1)[1].strip().strip("\"'")
                    break
        except Exception:
            pass

    if not groq_key:
        raise HTTPException(
            status_code=500,
            detail="GROQ_API_KEY is not configured. Set it in the orchestrator .env file.",
        )

    # ── Build the prompt for the LLM ────────────────────────────────
    system_prompt = (
        "You are a DevOps assistant that modifies CI/CD, Dockerfile, Terraform, "
        "and Kubernetes artifacts based on user requests.\n\n"
        "You will receive the current artifacts as JSON and a user instruction.\n"
        "You MUST respond with ONLY a valid JSON object in this exact shape:\n"
        "{\n"
        '  "explanation": "brief human-readable summary of what you changed",\n'
        '  "artifacts": { ...the full updated artifacts object... }\n'
        "}\n\n"
        "Return the actual JSON object itself, not a JSON string containing JSON.\n"
        "Do not wrap the response in markdown fences. Do not put JSON inside the explanation field.\n"
        "The artifacts object has these fields:\n"
        '- "yaml": string or null — GitHub Actions CI/CD workflow YAML content\n'
        '- "dockerfile": string or null — Dockerfile content\n'
        '- "terraform": object with keys "main_tf", "variables_tf", "outputs_tf", "providers_tf"\n'
        '- "kubernetes": object with keys "namespace_yaml", "configmap_yaml", "secret_yaml", '
        '"deployment_yaml", "service_yaml", "ingress_yaml", "hpa_yaml"\n'
        '- "metadata": any additional metadata\n\n'
        "Rules:\n"
        "- Always return the COMPLETE artifacts object, not just the changed fields.\n"
        "- If a field is unchanged, keep it exactly as-is.\n"
        '- If the user\'s request does not require any artifact change, set "artifacts" to null '
        "and explain why.\n"
        "- Never add markdown fences or any text outside the JSON object.\n"
        "- Focus ONLY on artifact corrections. Do not re-generate artifacts from scratch unless "
        "explicitly asked."
    )

    user_content = (
        f"Current artifacts:\n"
        f"{json.dumps(request.artifacts, separators=(',', ':'))}\n\n"
        f"User request: {request.message}"
    )

    # Build messages array including conversation history for context
    messages = []
    for hist_msg in request.conversation_history[-10:]:  # Keep last 10 messages for context
        role = hist_msg.get("role", "user")
        content = hist_msg.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_content})

    # ── Call Groq API ───────────────────────────────────────────────
    import httpx

    groq_url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {groq_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            *messages,
        ],
        "temperature": 0,
        "max_tokens": 8192,
        "response_format": {"type": "json_object"},
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(groq_url, headers=headers, json=payload)

        if resp.status_code != 200:
            error_detail = resp.text[:500]
            print(f"[Backend] Groq API error {resp.status_code}: {error_detail}", file=sys.stderr)
            raise HTTPException(
                status_code=502,
                detail=f"LLM API returned status {resp.status_code}",
            )

        data = resp.json()
        raw_text = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "{}")
        )

        try:
            result = _parse_chat_artifacts_response(raw_text)
            # Merge returned artifacts with originals so partial responses
            # don't wipe unchanged fields
            if isinstance(result.get("artifacts"), dict):
                result["artifacts"] = _merge_artifacts(
                    request.artifacts, result["artifacts"]
                )
            return result
        except json.JSONDecodeError:
            # If the LLM didn't return valid JSON, return the raw text as explanation
            print(f"[Backend] Chat artifacts: LLM returned non-JSON: {raw_text[:200]}", file=sys.stderr)
            return {
                "explanation": raw_text[:500],
                "artifacts": None,
            }

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="LLM request timed out")
    except HTTPException:
        raise
    except Exception as exc:
        print(f"[Backend] Chat artifacts error: {exc}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/runs/{run_id}/cancel")
async def cancel_run(run_id: str) -> Dict[str, Any]:
    run_state = _ensure_run_exists(run_id)
    
    if run_state.process and run_state.process.poll() is None:
        run_state.process.terminate()
        try:
            run_state.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            run_state.process.kill()
    
    return {"ok": True, "run_id": run_id}
