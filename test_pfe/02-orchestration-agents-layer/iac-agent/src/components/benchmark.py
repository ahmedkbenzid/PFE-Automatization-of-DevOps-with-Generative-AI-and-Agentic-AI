"""Benchmark helpers for comparing Terraform generation modes."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, Sequence

from ..models.types import RepositoryContext, TerraformConfiguration, UserRequest


def _score_generation(terraform_config: TerraformConfiguration, is_valid: bool) -> float:
    """Compute a simple quality score to compare generation outputs."""
    score = 0.0
    if is_valid:
        score += 70.0

    score += min(20.0, float(len(terraform_config.resources)) * 2.5)

    has_providers = bool((terraform_config.providers_tf or "").strip())
    has_variables = bool((terraform_config.variables_tf or "").strip())
    has_main = bool((terraform_config.main_tf or "").strip())
    has_outputs = bool((terraform_config.outputs_tf or "").strip())

    if has_providers:
        score += 3.0
    if has_variables:
        score += 3.0
    if has_main:
        score += 3.0
    if has_outputs:
        score += 1.0

    return round(score, 2)


def run_generation_benchmark(
    generator,
    validator,
    request: UserRequest,
    context: RepositoryContext,
    provider: str,
    resource_hints: Sequence[str],
    rag_context: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Run a lightweight benchmark comparing template and llm modes."""
    benchmark_runs = []

    for mode in ["template", "llm"]:
        started = time.perf_counter()
        terraform_config = generator.generate(
            request=request,
            context=context,
            provider=provider,
            resource_hints=resource_hints,
            rag_context=rag_context,
            mode=mode,
        )
        validation = validator.run(terraform_config)
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        benchmark_runs.append(
            {
                "mode": mode,
                "elapsed_ms": elapsed_ms,
                "is_valid": validation.is_valid,
                "error_count": len(validation.errors),
                "warning_count": len(validation.warnings),
                "resource_count": len(terraform_config.resources),
                "generator": terraform_config.metadata.get("generator", "unknown"),
                "quality_score": _score_generation(terraform_config, validation.is_valid),
            }
        )

    winner = max(
        benchmark_runs,
        key=lambda run: (run["quality_score"], -run["elapsed_ms"]),
    )

    return {
        "completed_at": datetime.utcnow().isoformat() + "Z",
        "winner_mode": winner["mode"],
        "winner_generator": winner["generator"],
        "runs": benchmark_runs,
    }


def serialize_benchmark(benchmark_results: Dict[str, Any]) -> Dict[str, Any]:
    """Return a compact benchmark payload suitable for response metadata."""
    runs = benchmark_results.get("runs", [])
    compact_runs = []

    for run in runs:
        compact_runs.append(
            {
                "mode": run.get("mode"),
                "generator": run.get("generator"),
                "elapsed_ms": run.get("elapsed_ms"),
                "is_valid": run.get("is_valid"),
                "quality_score": run.get("quality_score"),
            }
        )

    return {
        "completed_at": benchmark_results.get("completed_at"),
        "winner_mode": benchmark_results.get("winner_mode"),
        "winner_generator": benchmark_results.get("winner_generator"),
        "runs": compact_runs,
    }
