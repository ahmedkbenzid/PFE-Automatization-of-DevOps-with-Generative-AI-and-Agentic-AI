"""
API routes for the LLM-as-a-Judge log analysis feature.

Endpoints:
  POST /api/judge/{run_id}          — Judge the logs of a completed run
  POST /api/judge/raw               — Judge arbitrary raw log text
  GET  /api/judge/{run_id}/preview  — Preview the cleaned log (no LLM call)
"""

from __future__ import annotations

import sys
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.llm_judge import judge_orchestrator_logs, preprocess_log

router = APIRouter(prefix="/judge", tags=["llm-judge"])


# ─── Request / Response models ──────────────────────────────────────────────

class RawJudgeRequest(BaseModel):
    """Request body for judging arbitrary raw log text."""
    raw_log: str
    max_chars: int = Field(default=6000, ge=500, le=20000)


class JudgeResponse(BaseModel):
    """Structured verdict returned by the LLM judge."""
    run_id: Optional[str] = None
    overall_status: str
    confidence: float = 0.0
    summary: str = ""
    root_cause: Optional[str] = None
    agents: list = Field(default_factory=list)
    errors_found: list = Field(default_factory=list)
    warnings_found: list = Field(default_factory=list)
    recommendations: list = Field(default_factory=list)
    token_usage: Dict[str, int] = Field(default_factory=dict)
    cleaned_log_length: int = 0
    cached: bool = False


class PreviewResponse(BaseModel):
    """Cleaned log preview (no LLM call)."""
    run_id: str
    cleaned_log: str
    original_line_count: int
    cleaned_line_count: int
    cleaned_char_count: int


# ─── Helpers ────────────────────────────────────────────────────────────────

def _get_run_manager():
    """
    Lazily import the run_manager from main to avoid circular imports.
    """
    from backend.main import run_manager
    return run_manager


def _get_raw_log_for_run(run_id: str):
    """
    Fetch the raw log lines for a run and return (run_state, raw_log).
    Raises HTTPException(404) if the run doesn't exist.
    """
    rm = _get_run_manager()
    run_state = rm.get_run(run_id)
    if run_state is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    raw_log = "\n".join(run_state.output_lines)
    return run_state, raw_log


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.post("/{run_id}", response_model=JudgeResponse)
async def judge_run(run_id: str, force: bool = False) -> JudgeResponse:
    """
    Analyse the orchestrator logs for a given run using the LLM judge.

    The run must exist (started via POST /api/runs).  The endpoint reads
    all captured output lines, preprocesses them (strips noise, deduplicates,
    truncates) and sends the cleaned payload to the LLM for a structured
    verdict.

    If a cached verdict exists and ``force`` is not set, returns it directly.
    """
    run_state, raw_log = _get_raw_log_for_run(run_id)

    # Return cached verdict if available (and not forced refresh)
    if not force and run_state.judge_verdict is not None:
        print(f"[LLM Judge] Returning cached verdict for run {run_id}", file=sys.stderr)
        return JudgeResponse(
            run_id=run_id,
            cached=True,
            **run_state.judge_verdict,
        )

    if not raw_log.strip():
        raise HTTPException(
            status_code=400,
            detail="Run has no log output yet. Wait for the orchestrator to finish.",
        )

    print(f"[LLM Judge] Judging run {run_id} ({len(raw_log)} chars raw)", file=sys.stderr)

    verdict = await judge_orchestrator_logs(raw_log)
    verdict_dict = verdict.to_dict()

    # Cache the verdict on the run state
    run_state.judge_verdict = verdict_dict

    print(
        f"[LLM Judge] Verdict for {run_id}: {verdict.overall_status} "
        f"(confidence={verdict.confidence}%, tokens={verdict.token_usage})",
        file=sys.stderr,
    )

    return JudgeResponse(
        run_id=run_id,
        **verdict_dict,
    )


@router.post("/raw", response_model=JudgeResponse)
async def judge_raw_log(request: RawJudgeRequest) -> JudgeResponse:
    """
    Judge arbitrary raw log text (not tied to a specific run).

    Useful for testing or analysing logs from external sources.
    """
    if not request.raw_log.strip():
        raise HTTPException(status_code=400, detail="raw_log is required")

    print(
        f"[LLM Judge] Judging raw log ({len(request.raw_log)} chars, "
        f"budget={request.max_chars})",
        file=sys.stderr,
    )

    verdict = await judge_orchestrator_logs(
        request.raw_log, max_chars=request.max_chars
    )

    return JudgeResponse(**verdict.to_dict())


@router.get("/{run_id}/preview", response_model=PreviewResponse)
async def preview_cleaned_log(run_id: str) -> PreviewResponse:
    """
    Preview what the log looks like after preprocessing (no LLM call).

    Useful for debugging the cleaning pipeline and understanding how
    many tokens will actually be sent to the LLM.
    """
    _, raw_log = _get_raw_log_for_run(run_id)
    cleaned = preprocess_log(raw_log)
    original_lines = len(raw_log.splitlines())
    cleaned_lines = len(cleaned.splitlines())

    return PreviewResponse(
        run_id=run_id,
        cleaned_log=cleaned,
        original_line_count=original_lines,
        cleaned_line_count=cleaned_lines,
        cleaned_char_count=len(cleaned),
    )
