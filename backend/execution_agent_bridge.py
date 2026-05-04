from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Callable


@lru_cache(maxsize=1)
def _load_pipeline_module():
    module_path = (
        Path(__file__).resolve().parent.parent
        / "test_pfe"
        / "02-orchestration-agents-layer"
        / "execution-sandbox"
        / "pipeline.py"
    )
    spec = importlib.util.spec_from_file_location("execution_sandbox_pipeline", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load execution pipeline from {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_generated_cicd_workflow(
    *,
    dockerfile_content: str,
    cicd_workflow_content: str,
    repository_path: str,
    github_url: str = "",
    act_timeout: int = 1800,
    secrets: Optional[Dict[str, str]] = None,
    prebuilt_image_name: str = "",
    log_callback: Optional[Callable[[Dict[str, str]], None]] = None,
) -> Dict[str, Any]:
    module = _load_pipeline_module()
    return module.run_execution(
        dockerfile_content=dockerfile_content,
        cicd_workflow_content=cicd_workflow_content,
        repository_path=repository_path,
        github_url=github_url,
        act_timeout=act_timeout,
        secrets=secrets,
        prebuilt_image_name=prebuilt_image_name,
        log_callback=log_callback,
    )