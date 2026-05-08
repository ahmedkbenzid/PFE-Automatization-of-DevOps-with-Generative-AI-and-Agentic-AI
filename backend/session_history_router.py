"""
Session History API Router
Stores and retrieves DevOps automation session history with artifacts and execution logs.
Add to your FastAPI app with: app.include_router(history_router, prefix="/api")
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
import json
from pathlib import Path

history_router = APIRouter(prefix="/history", tags=["history"])

# ---------------------------------------------------------------------------
# Storage (file-based JSON — swap for DB if needed)
# ---------------------------------------------------------------------------
HISTORY_FILE = Path(__file__).parent / "data" / "session_history.json"
HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load() -> List[Dict[str, Any]]:
    if not HISTORY_FILE.exists():
        return []
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(sessions: List[Dict[str, Any]]) -> None:
    HISTORY_FILE.write_text(json.dumps(sessions, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ArtifactModel(BaseModel):
    type: str                          # "cicd" | "dockerfile" | "kubernetes" | "terraform"
    filename: str
    content: str
    validation_status: str = "unknown" # "passed" | "failed" | "skipped" | "unknown"
    validation_errors: List[str] = []


class RepairAttempt(BaseModel):
    attempt_number: int
    error_detected: str
    fix_applied: str
    success: bool


class ExecutionLog(BaseModel):
    timestamp: str
    level: str   # "info" | "warning" | "error" | "success"
    message: str
    agent: Optional[str] = None


class CreateSessionRequest(BaseModel):
    prompt: str
    artifacts: List[ArtifactModel] = []
    execution_logs: List[ExecutionLog] = []
    repair_attempts: List[RepairAttempt] = []
    status: str = "running"            # "running" | "completed" | "failed"
    rag_sources: List[str] = []
    agents_used: List[str] = []
    duration_seconds: Optional[float] = None


class UpdateSessionRequest(BaseModel):
    artifacts: Optional[List[ArtifactModel]] = None
    execution_logs: Optional[List[ExecutionLog]] = None
    repair_attempts: Optional[List[RepairAttempt]] = None
    status: Optional[str] = None
    duration_seconds: Optional[float] = None


class SessionResponse(BaseModel):
    session_id: str
    prompt: str
    created_at: str
    updated_at: str
    status: str
    artifacts: List[ArtifactModel]
    execution_logs: List[ExecutionLog]
    repair_attempts: List[RepairAttempt]
    rag_sources: List[str]
    agents_used: List[str]
    duration_seconds: Optional[float]
    artifact_count: int
    log_count: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@history_router.post("/sessions", response_model=SessionResponse, status_code=201)
def create_session(req: CreateSessionRequest):
    """Create a new session entry when a user submits a prompt."""
    sessions = _load()
    now = datetime.utcnow().isoformat() + "Z"
    session = {
        "session_id": str(uuid.uuid4()),
        "prompt": req.prompt,
        "created_at": now,
        "updated_at": now,
        "status": req.status,
        "artifacts": [a.dict() for a in req.artifacts],
        "execution_logs": [l.dict() for l in req.execution_logs],
        "repair_attempts": [r.dict() for r in req.repair_attempts],
        "rag_sources": req.rag_sources,
        "agents_used": req.agents_used,
        "duration_seconds": req.duration_seconds,
        "artifact_count": len(req.artifacts),
        "log_count": len(req.execution_logs),
    }
    sessions.insert(0, session)  # newest first
    _save(sessions)
    return session


@history_router.patch("/sessions/{session_id}", response_model=SessionResponse)
def update_session(session_id: str, req: UpdateSessionRequest):
    """Append artifacts and logs as agents complete their work."""
    sessions = _load()
    for s in sessions:
        if s["session_id"] == session_id:
            now = datetime.utcnow().isoformat() + "Z"
            s["updated_at"] = now
            if req.artifacts is not None:
                s["artifacts"].extend([a.dict() for a in req.artifacts])
                s["artifact_count"] = len(s["artifacts"])
            if req.execution_logs is not None:
                s["execution_logs"].extend([l.dict() for l in req.execution_logs])
                s["log_count"] = len(s["execution_logs"])
            if req.repair_attempts is not None:
                s["repair_attempts"].extend([r.dict() for r in req.repair_attempts])
            if req.status is not None:
                s["status"] = req.status
            if req.duration_seconds is not None:
                s["duration_seconds"] = req.duration_seconds
            _save(sessions)
            return s
    raise HTTPException(status_code=404, detail=f"Session {session_id} not found")


@history_router.get("/sessions", response_model=List[SessionResponse])
def list_sessions(limit: int = 50, status: Optional[str] = None):
    """List all sessions, newest first. Optionally filter by status."""
    sessions = _load()
    if status:
        sessions = [s for s in sessions if s.get("status") == status]
    return sessions[:limit]


@history_router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(session_id: str):
    """Get full detail for a single session."""
    sessions = _load()
    for s in sessions:
        if s["session_id"] == session_id:
            return s
    raise HTTPException(status_code=404, detail=f"Session {session_id} not found")


@history_router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str):
    """Delete a session by ID."""
    sessions = _load()
    updated = [s for s in sessions if s["session_id"] != session_id]
    if len(updated) == len(sessions):
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    _save(updated)


@history_router.get("/stats")
def get_stats():
    """Aggregate stats for the dashboard header cards."""
    sessions = _load()
    if not sessions:
        return {"total": 0, "completed": 0, "failed": 0, "running": 0,
                "total_artifacts": 0, "avg_duration": None, "repair_rate": 0}

    completed = [s for s in sessions if s.get("status") == "completed"]
    failed = [s for s in sessions if s.get("status") == "failed"]
    running = [s for s in sessions if s.get("status") == "running"]
    total_artifacts = sum(s.get("artifact_count", 0) for s in sessions)
    durations = [s["duration_seconds"] for s in completed if s.get("duration_seconds")]
    avg_duration = round(sum(durations) / len(durations), 1) if durations else None
    sessions_with_repairs = sum(1 for s in sessions if s.get("repair_attempts"))
    repair_rate = round(sessions_with_repairs / len(sessions) * 100) if sessions else 0

    return {
        "total": len(sessions),
        "completed": len(completed),
        "failed": len(failed),
        "running": len(running),
        "total_artifacts": total_artifacts,
        "avg_duration": avg_duration,
        "repair_rate": repair_rate,
    }