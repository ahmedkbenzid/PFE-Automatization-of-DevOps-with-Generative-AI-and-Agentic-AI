"""CI/CD Docker Build Routes for FastAPI backend."""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List
from uuid import uuid4

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Body
from pydantic import BaseModel, Field

from backend.secrets_manager import SecretsManager

def _get_main_state():
    from backend.main import run_manager, post_run_execution_results, post_run_execution_lock, SIGNAL_DIR
    return run_manager, post_run_execution_results, post_run_execution_lock, SIGNAL_DIR

class BuildRequest(BaseModel):
    """CI/CD build request."""
    pipeline_config: Dict[str, Any] = Field(
        ..., description="Pipeline configuration with stages and scripts"
    )
    secrets: Dict[str, str] = Field(
        default_factory=dict, description="Environment secrets/credentials"
    )
    work_dir: Optional[str] = Field(
        default=None, description="Working directory for execution"
    )

class BuildStatusResponse(BaseModel):
    """Build execution status."""
    execution_id: str
    started_at: float
    completed_at: Optional[float] = None
    returncode: Optional[int] = None
    total_lines: int
    stages: Dict[str, Any]

router = APIRouter(prefix="/cicd", tags=["cicd"])

def _parse_stages_from_logs(execution_id: str) -> Tuple[Dict[str, Any], List[str]]:
    """Parse act logs to dynamically reconstruct stages."""
    run_manager, post_run_execution_results, post_run_execution_lock, SIGNAL_DIR = _get_main_state()
    stages = {}
    logs = []
    
    # Try to read from JSONL logs first
    logs_file = Path(SIGNAL_DIR) / f"{execution_id}.execution.logs.jsonl"
    if logs_file.exists():
        try:
            with open(logs_file, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        log_entry = json.loads(line)
                        line_text = (
                            log_entry.get("line", "")
                            or log_entry.get("message", "")
                            or log_entry.get("stream", "")
                        )
                        if line_text:
                            logs.append(str(line_text))
                    except json.JSONDecodeError:
                        logs.append(line.strip())
        except Exception as e:
            print(f"[CICD] Error reading logs file: {e}", file=sys.stderr)
            
    # If JSONL is empty/missing, try to get from completed result
    if not logs:
        with post_run_execution_lock:
            execution_result = post_run_execution_results.get(execution_id)
        if execution_result and isinstance(execution_result.get("act"), dict):
            act_logs = execution_result["act"].get("logs", [])
            for entry in act_logs:
                if isinstance(entry, dict):
                    line_text = entry.get("line", "") or entry.get("message", "") or entry.get("stream", "")
                    if line_text:
                        logs.append(str(line_text))
                else:
                    logs.append(str(entry))
                    
    # Parse logs for stages (looking for act format: [Job Name] ...)
    for line in logs:
        if line.startswith("[") and "]" in line:
            stage_full = line.split("]", 1)[0][1:]
            # e.g., "Python CI/CD/test" -> "test"
            stage_name = stage_full.split("/")[-1] if "/" in stage_full else stage_full
            
            if stage_name not in stages:
                stages[stage_name] = {
                    "name": stage_name,
                    "status": "running",
                    "start_time": 0,
                    "end_time": None,
                    "duration": 0,
                    "log_count": 0,
                    "error": None
                }
            stages[stage_name]["log_count"] += 1
            
            if "⭐ Run Main" in line:
                pass
            elif "✅  Success" in line:
                stages[stage_name]["status"] = "completed"
            elif "❌  Failure" in line:
                stages[stage_name]["status"] = "failed"
                
    # If we have logs but no parseable act stage markers, expose a generic stage
    # so frontend still shows execution progress.
    if logs and not stages:
        stages["execution"] = {
            "name": "execution",
            "status": "running",
            "start_time": 0,
            "end_time": None,
            "duration": 0,
            "log_count": len(logs),
            "error": None,
        }

    return stages, logs

@router.post("/build", response_model=dict)
async def start_build(request: BuildRequest = Body(...)) -> Dict[str, str]:
    """Start a manual CI/CD build (Deprecated, orchestration layer handles it automatically)."""
    return {"execution_id": str(uuid4())}

@router.get("/build/{execution_id}/status", response_model=BuildStatusResponse)
async def get_build_status(execution_id: str) -> BuildStatusResponse:
    """Get CI/CD build execution status mapped from execution-sandbox."""
    run_manager, post_run_execution_results, post_run_execution_lock, SIGNAL_DIR = _get_main_state()
    run_state = run_manager.get_run(execution_id)

    with post_run_execution_lock:
        execution_result = post_run_execution_results.get(execution_id)

    stages, logs = _parse_stages_from_logs(execution_id)

    status = "running"
    completed_at = None
    returncode = None
    
    if execution_result:
        status = execution_result.get("status", "running")
        if status != "running":
            completed_at = 0
            if isinstance(execution_result.get("act"), dict):
                returncode = execution_result["act"].get("exit_code", 0)
            elif status == "error":
                returncode = 1
            else:
                returncode = 0
    elif not run_state and logs:
        # Reconstructed from logs after server restart
        status = "completed"
        returncode = 1 if any(s.get("status") == "failed" for s in stages.values()) else 0

    if not run_state and not logs:
        # Really not found, no logs on disk
        return BuildStatusResponse(
            execution_id=execution_id,
            started_at=0,
            completed_at=None,
            returncode=None,
            total_lines=0,
            stages={}
        )

    # If execution finished but we didn't catch ✅ Success marks, force them to completed/failed based on returncode
    if status != "running":
        for s_name, s_data in stages.items():
            if s_data["status"] == "running":
                s_data["status"] = "completed" if returncode == 0 else "failed"

    return BuildStatusResponse(
        execution_id=execution_id,
        started_at=run_state.started_at if run_state and hasattr(run_state, "started_at") else 0,
        completed_at=completed_at,
        returncode=returncode,
        total_lines=len(logs),
        stages=stages
    )

@router.get("/build/{execution_id}/logs")
async def get_build_logs(
    execution_id: str,
    start_line: int = 0,
    limit: int = 100,
) -> Dict[str, Any]:
    """Get CI/CD build logs."""
    _, logs = _parse_stages_from_logs(execution_id)
    
    return {
        "execution_id": execution_id,
        "start_line": start_line,
        "limit": limit,
        "logs": logs[start_line : start_line + limit],
        "total_available": len(logs),
    }

@router.post("/build/{execution_id}/stop")
async def stop_build(execution_id: str) -> Dict[str, bool]:
    """Stop a running CI/CD build."""
    return {"stopped": True}

@router.websocket("/build/{execution_id}/ws")
async def websocket_build_logs(websocket: WebSocket, execution_id: str) -> None:
    """WebSocket endpoint for streaming CI/CD build logs."""
    await websocket.accept()

    line_index = 0
    try:
        while True:
            _, logs = _parse_stages_from_logs(execution_id)
            
            if line_index < len(logs):
                for line in logs[line_index:]:
                    level = "info"
                    if "ERROR" in line or "error" in line:
                        level = "error"
                    elif "WARN" in line or "warn" in line:
                        level = "warn"

                    current_stage = None
                    stage_status = None
                    if line.startswith("[") and "]" in line:
                        stage_full = line.split("]", 1)[0][1:]
                        current_stage = stage_full.split("/")[-1] if "/" in stage_full else stage_full
                        if "⭐ Run Main" in line:
                            stage_status = "running"
                        elif "✅  Success" in line:
                            stage_status = "completed"
                        elif "❌  Failure" in line:
                            stage_status = "failed"

                    await websocket.send_json(
                        {
                            "type": "log",
                            "execution_id": execution_id,
                            "line": line,
                            "level": level,
                            "stage": current_stage,
                            "stage_status": stage_status,
                            "line_index": line_index,
                        }
                    )
                    line_index += 1

            run_manager, post_run_execution_results, post_run_execution_lock, SIGNAL_DIR = _get_main_state()
            run_state = run_manager.get_run(execution_id)
            if run_state:
                with post_run_execution_lock:
                    execution_result = post_run_execution_results.get(execution_id)
                if execution_result and execution_result.get("status") != "running":
                    stages, _ = _parse_stages_from_logs(execution_id)
                    returncode = 0
                    if isinstance(execution_result.get("act"), dict):
                        returncode = execution_result["act"].get("exit_code", 0)
                    elif execution_result.get("status") == "error":
                        returncode = 1
                        
                    await websocket.send_json(
                        {
                            "type": "complete",
                            "execution_id": execution_id,
                            "returncode": returncode,
                            "stages": stages,
                            "total_lines": len(logs),
                        }
                    )
                    break

            await asyncio.sleep(0.5)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[CICD] WebSocket error: {str(e)}", file=sys.stderr)
        try:
            await websocket.send_json({"type": "error", "message": f"WebSocket error: {str(e)}"})
        except Exception:
            pass

@router.post("/build/{execution_id}/cleanup")
async def cleanup_build(execution_id: str) -> Dict[str, bool]:
    """Clean up a CI/CD build execution."""
    return {"cleaned_up": True}

@router.get("/build/{execution_id}/artifacts")
async def get_build_artifacts(execution_id: str) -> Dict[str, Any]:
    """Get artifacts from a completed build."""
    run_manager, post_run_execution_results, post_run_execution_lock, SIGNAL_DIR = _get_main_state()
    run_state = run_manager.get_run(execution_id)

    with post_run_execution_lock:
        execution_result = post_run_execution_results.get(execution_id)

    stages, logs = _parse_stages_from_logs(execution_id)

    if not run_state and not logs:
        raise HTTPException(status_code=404, detail="Execution not found")

    if run_state and execution_result and execution_result.get("status") == "running":
        raise HTTPException(status_code=400, detail="Build is still running")

    returncode = 0
    if execution_result:
        if isinstance(execution_result.get("act"), dict):
            returncode = execution_result["act"].get("exit_code", 0)
        elif execution_result.get("status") == "error":
            returncode = 1
    elif not run_state and logs:
        returncode = 1 if any(s.get("status") == "failed" for s in stages.values()) else 0

    return {
        "execution_id": execution_id,
        "returncode": returncode,
        "success": returncode == 0,
        "stages_completed": sum(1 for s in stages.values() if s.get("status") == "completed"),
        "total_stages": len(stages),
        "logs": logs[-100:],
    }
