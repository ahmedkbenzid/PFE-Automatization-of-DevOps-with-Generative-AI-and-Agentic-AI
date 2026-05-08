"""
LLM-as-a-Judge for Orchestrator Logs
=====================================
Preprocesses raw orchestrator output (strips ANSI, timestamps, log-levels,
deduplicates, filters by importance, truncates to a token budget) then sends
the cleaned payload to an LLM for a structured verdict.

The verdict includes: overall status, root-cause analysis, agent-level
summaries, warnings/errors found, and actionable recommendations.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx


# ─── Regex patterns for log cleaning ────────────────────────────────────────

# ANSI escape codes  (e.g. \x1b[31m ... \x1b[0m)
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mGKHJ]")

# Timestamps in common formats:  10:05:22 | 2026-05-08 11:05:12,125 | [2026-05-08T10:15:22]
_TIMESTAMP_LINE_RE = re.compile(r"^\d{2}:\d{2}:\d{2}\s*$")
_INLINE_TIMESTAMP_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}[,.]?\d*\s*"
)

# Log-level tags that appear as standalone lines OR inline prefixes
_LOGLEVEL_SOLO_RE = re.compile(r"^\s*(INFO|ERROR|WARNING|SUCCESS|DEBUG)\s*$")
_LOGLEVEL_PREFIX_RE = re.compile(
    r"^\s*\[?(INFO|ERROR|WARNING|WARN|SUCCESS|DEBUG)\]?\s*[-:]?\s*"
)

# Python logger prefixes: "src.components.llm_client - INFO -"
_PYTHON_LOGGER_RE = re.compile(
    r"\s*-\s+\S+\s+-\s+(INFO|ERROR|WARNING|DEBUG)\s+-\s+"
)

# httpx / HTTP request noise
_HTTPX_RE = re.compile(r"httpx\s+-\s+INFO\s+-\s+HTTP Request:")

# Orchestrator prefix:  [Orchestrator]
_ORCH_PREFIX_RE = re.compile(r"^\[Orchestrator\]\s*")

# Duplicate agent prefix inside orchestrator lines: [cicd-agent]
_AGENT_PREFIX_RE = re.compile(r"^\[[\w-]+\]\s*")


# ─── Importance keywords ────────────────────────────────────────────────────

_IMPORTANT_KEYWORDS = (
    "error", "warning", "warn", "failed", "failure", "exception",
    "traceback", "success", "completed", "passed", "guardrails",
    "routing", "dispatching", "generated", "validation", "security",
    "schema", "pipeline", "duration", "attempt", "timeout",
    "fallback", "detected", "analyzing", "invoking",
    "rag", "knowledge", "intent", "audit", "compiled",
    "checksum", "lock file", "result received",
)

_NOISE_PATTERNS = (
    "httpx - INFO",
    "HTTP Request: POST",
    "HTTP/1.1 200 OK",
    "================",
    "---",
    "===",
)


# ─── Dataclasses for the structured verdict ─────────────────────────────────

@dataclass
class AgentVerdict:
    """Per-agent summary produced by the judge."""
    agent_name: str
    status: str                        # "success" | "failed" | "skipped"
    summary: str = ""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class JudgeVerdict:
    """Full structured output of the LLM judge."""
    overall_status: str                # "success" | "partial_success" | "failed"
    confidence: float = 0.0            # 0-100
    summary: str = ""
    root_cause: Optional[str] = None
    agents: List[AgentVerdict] = field(default_factory=list)
    errors_found: List[str] = field(default_factory=list)
    warnings_found: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    token_usage: Dict[str, int] = field(default_factory=dict)
    cleaned_log_length: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ─── Log preprocessing pipeline ────────────────────────────────────────────

def _strip_ansi(text: str) -> str:
    """Remove ANSI terminal colour / cursor codes."""
    return _ANSI_RE.sub("", text)


def _clean_line(line: str) -> str:
    """
    Clean a single log line:
    1. Strip ANSI codes
    2. Remove inline timestamps
    3. Remove python logger prefixes
    4. Remove [Orchestrator] prefix
    5. Strip leading whitespace
    """
    line = _strip_ansi(line)
    line = _INLINE_TIMESTAMP_RE.sub("", line)
    line = _PYTHON_LOGGER_RE.sub("", line)
    line = _ORCH_PREFIX_RE.sub("", line)
    # Remove the agent sub-prefix only if it's redundant
    line = _AGENT_PREFIX_RE.sub("", line)
    line = _LOGLEVEL_PREFIX_RE.sub("", line)
    return line.strip()


def _is_noise(line: str) -> bool:
    """Return True if the line is purely visual noise (separators, HTTP logs)."""
    if not line:
        return True
    for pattern in _NOISE_PATTERNS:
        if pattern in line:
            return True
    return False


def _is_important(line: str) -> bool:
    """Heuristic: does this line carry meaningful information?"""
    lowered = line.lower()
    return any(kw in lowered for kw in _IMPORTANT_KEYWORDS)


def _is_timestamp_only_line(line: str) -> bool:
    """Detect standalone timestamp lines like '10:05:22'."""
    return bool(_TIMESTAMP_LINE_RE.match(line.strip()))


def _is_loglevel_only_line(line: str) -> bool:
    """Detect standalone log-level lines like 'INFO'."""
    return bool(_LOGLEVEL_SOLO_RE.match(line.strip()))


def _deduplicate(lines: List[str]) -> List[str]:
    """Collapse consecutive identical lines into one."""
    if not lines:
        return []
    deduped = [lines[0]]
    for line in lines[1:]:
        if line != deduped[-1]:
            deduped.append(line)
    return deduped


def preprocess_log(
    raw_log: str,
    *,
    max_chars: int = 6000,
    keep_head: int = 20,
    keep_tail: int = 80,
) -> str:
    """
    Turn raw orchestrator log output into a clean, token-efficient string.

    Pipeline:
    1. Split into lines
    2. Drop standalone timestamp / log-level lines
    3. Clean each remaining line (strip ANSI, timestamps, prefixes)
    4. Drop noise lines (separators, httpx chatter)
    5. Keep only "important" lines (errors, milestones, key events)
    6. Deduplicate consecutive identical lines
    7. Truncate to budget using head + tail strategy

    Parameters
    ----------
    raw_log : str
        Full multiline log text.
    max_chars : int
        Approximate character budget for the cleaned output.
        Default 6000 chars ≈ 1500 tokens.
    keep_head : int
        Lines to always keep from the beginning (setup context).
    keep_tail : int
        Lines to always keep from the end (final events / errors).

    Returns
    -------
    str   Cleaned log ready for LLM ingestion.
    """
    raw_lines = raw_log.splitlines()

    # Step 1+2: filter out timestamp-only and loglevel-only lines
    filtered = [
        l for l in raw_lines
        if not _is_timestamp_only_line(l) and not _is_loglevel_only_line(l)
    ]

    # Step 3: clean each line
    cleaned = [_clean_line(l) for l in filtered]

    # Step 4: drop noise
    cleaned = [l for l in cleaned if not _is_noise(l)]

    # Step 5: keep only important lines
    important = [l for l in cleaned if l and _is_important(l)]

    # If importance filter was too aggressive, fall back to all non-empty
    if len(important) < 5:
        important = [l for l in cleaned if l]

    # Step 6: deduplicate
    important = _deduplicate(important)

    # Step 7: truncate if over budget
    joined = "\n".join(important)
    if len(joined) > max_chars:
        half = max_chars // 2
        skipped_chars = len(joined) - max_chars
        return joined[:half] + f"\n... ({skipped_chars} characters truncated) ...\n" + joined[-half:]

    return joined


# ─── Groq API key loader (mirrors main.py pattern) ─────────────────────────

def _load_groq_credentials() -> tuple[str, str]:
    """
    Load GROQ_API_KEY and model name.
    Checks env vars first, then falls back to the orchestrator .env file.
    Returns (api_key, model_name).
    Raises RuntimeError if no key is found.
    """
    groq_key = os.environ.get("GROQ_API_KEY", "")
    model_name = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

    if not groq_key:
        # Try loading from orchestrator .env
        project_root = Path(__file__).resolve().parent.parent
        env_path = (
            project_root
            / "test_pfe"
            / "02-orchestration-agents-layer"
            / "orchestrator-agent"
            / ".env"
        )
        if env_path.exists():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("GROQ_API_KEY="):
                        groq_key = line.split("=", 1)[1].strip().strip("\"'")
                    elif line.startswith("GROQ_MODEL="):
                        model_name = line.split("=", 1)[1].strip().strip("\"'")
            except Exception:
                pass

    if not groq_key:
        raise RuntimeError(
            "GROQ_API_KEY is not configured. "
            "Set it in the environment or in the orchestrator .env file."
        )

    return groq_key, model_name


# ─── LLM Judge prompt ──────────────────────────────────────────────────────

_JUDGE_SYSTEM_PROMPT = """\
You are an expert DevOps pipeline judge. Your job is to analyze orchestrator
execution logs and produce a structured JSON verdict.

You will receive cleaned orchestrator logs. Analyze them carefully and respond
with ONLY a valid JSON object in this exact shape:

{
  "overall_status": "success" | "partial_success" | "failed",
  "confidence": <0-100>,
  "summary": "<1-3 sentence high-level summary of what happened>",
  "root_cause": "<if failed: the root cause of the failure, else null>",
  "agents": [
    {
      "agent_name": "<name of the agent, e.g. cicd-agent>",
      "status": "success" | "failed" | "skipped",
      "summary": "<what this agent did>",
      "errors": ["<any errors from this agent>"],
      "warnings": ["<any warnings from this agent>"]
    }
  ],
  "errors_found": ["<all error messages found in the logs>"],
  "warnings_found": ["<all warning messages found in the logs>"],
  "recommendations": ["<actionable suggestions to improve the pipeline>"]
}

Rules:
- Respond with ONLY the JSON object, no markdown fences, no explanation.
- Be precise about error messages — quote them from the logs.
- If the pipeline succeeded but had warnings, use "partial_success".
- Focus on actionable insights, not just repeating the log.
- If an agent had a fallback (e.g. Ollama failed → Groq fallback), note it.
"""


# ─── Core judge function ───────────────────────────────────────────────────

async def judge_orchestrator_logs(
    raw_log: str,
    *,
    max_chars: int = 6000,
    timeout: float = 30.0,
) -> JudgeVerdict:
    """
    Preprocess raw orchestrator logs and send them to the LLM for evaluation.

    Parameters
    ----------
    raw_log : str
        The full raw log output from the orchestrator run.
    max_chars : int
        Character budget for the cleaned log payload.
    timeout : float
        HTTP timeout for the Groq API call.

    Returns
    -------
    JudgeVerdict
        Structured verdict with status, summary, errors, recommendations, etc.
    """
    # 1. Preprocess
    cleaned = preprocess_log(raw_log, max_chars=max_chars)

    # 2. Load credentials
    try:
        groq_key, model_name = _load_groq_credentials()
    except RuntimeError as exc:
        return JudgeVerdict(
            overall_status="error",
            summary=str(exc),
            cleaned_log_length=len(cleaned),
        )

    # 3. Build the prompt
    user_prompt = f"Orchestrator execution logs:\n\n{cleaned}"

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
        "max_tokens": 2048,
    }
    headers = {
        "Authorization": f"Bearer {groq_key}",
        "Content-Type": "application/json",
    }

    # 4. Call the LLM
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
            )

        if resp.status_code != 200:
            error_detail = resp.text[:500]
            print(
                f"[LLM Judge] Groq API error {resp.status_code}: {error_detail}",
                file=sys.stderr,
            )
            return JudgeVerdict(
                overall_status="error",
                summary=f"LLM API returned status {resp.status_code}: {error_detail}",
                cleaned_log_length=len(cleaned),
            )

        data = resp.json()
        raw_text = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "{}")
        )

        # Extract token usage
        usage = data.get("usage", {})
        token_usage = {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        }

    except httpx.TimeoutException:
        return JudgeVerdict(
            overall_status="error",
            summary="LLM request timed out.",
            cleaned_log_length=len(cleaned),
        )
    except Exception as exc:
        return JudgeVerdict(
            overall_status="error",
            summary=f"LLM request failed: {exc}",
            cleaned_log_length=len(cleaned),
        )

    # 5. Parse the LLM response
    content = raw_text.strip()
    # Strip markdown fences if the model added them
    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return JudgeVerdict(
            overall_status="error",
            summary=f"LLM returned invalid JSON. Raw response: {raw_text[:300]}",
            cleaned_log_length=len(cleaned),
            token_usage=token_usage,
        )

    # 6. Build the verdict
    agents = []
    for agent_data in parsed.get("agents", []):
        agents.append(
            AgentVerdict(
                agent_name=agent_data.get("agent_name", "unknown"),
                status=agent_data.get("status", "unknown"),
                summary=agent_data.get("summary", ""),
                errors=agent_data.get("errors", []),
                warnings=agent_data.get("warnings", []),
            )
        )

    return JudgeVerdict(
        overall_status=parsed.get("overall_status", "unknown"),
        confidence=float(parsed.get("confidence", 0)),
        summary=parsed.get("summary", ""),
        root_cause=parsed.get("root_cause"),
        agents=agents,
        errors_found=parsed.get("errors_found", []),
        warnings_found=parsed.get("warnings_found", []),
        recommendations=parsed.get("recommendations", []),
        token_usage=token_usage,
        cleaned_log_length=len(cleaned),
    )
