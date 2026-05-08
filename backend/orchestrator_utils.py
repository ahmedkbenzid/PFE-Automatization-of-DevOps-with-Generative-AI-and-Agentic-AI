from __future__ import annotations

import json
import re
import threading
from typing import Any, Dict, List, Optional


class _StreamlitShim:
    def __init__(self) -> None:
        self.session_state: Dict[str, Any] = {}


st = _StreamlitShim()
_runtime_secrets_lock = threading.Lock()


def set_runtime_secrets(runtime_secrets: Optional[Dict[str, str]]) -> None:
    st.session_state["runtime_secrets"] = runtime_secrets or {}


def build_launch_env(base_env: Dict[str, str], runtime_secrets: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Build launch environment using the Streamlit-compatible env override logic."""
    with _runtime_secrets_lock:
        previous = st.session_state.get("runtime_secrets")
        st.session_state["runtime_secrets"] = runtime_secrets or {}
        try:
            return _apply_runtime_env_overrides(base_env)
        finally:
            if previous is None:
                st.session_state.pop("runtime_secrets", None)
            else:
                st.session_state["runtime_secrets"] = previous


def _collect_runtime_secrets() -> Dict[str, str]:
    """Return sanitized session runtime secrets with common Docker Hub aliases."""
    raw_secrets = st.session_state.get("runtime_secrets", {})
    if not isinstance(raw_secrets, dict):
        return {}

    key_pattern = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    cleaned: Dict[str, str] = {}
    for raw_key, raw_value in raw_secrets.items():
        key = str(raw_key).strip()
        value = str(raw_value)
        if not key or value == "":
            continue
        if not key_pattern.match(key):
            continue
        cleaned[key] = value

    if cleaned.get("DOCKERHUB_USERNAME") and not cleaned.get("DOCKER_USERNAME"):
        cleaned["DOCKER_USERNAME"] = cleaned["DOCKERHUB_USERNAME"]

    dockerhub_token = cleaned.get("DOCKERHUB_TOKEN") or cleaned.get("DOCKERHUB_PASSWORD")
    if dockerhub_token:
        cleaned.setdefault("DOCKERHUB_TOKEN", dockerhub_token)
        cleaned.setdefault("DOCKERHUB_PASSWORD", dockerhub_token)
        cleaned.setdefault("DOCKER_PASSWORD", dockerhub_token)

    return cleaned


def _apply_runtime_env_overrides(base_env: Dict[str, str]) -> Dict[str, str]:
    """Apply session runtime secrets and compatibility env aliases before process launch."""
    launch_env = dict(base_env)
    launch_env["PYTHONIOENCODING"] = "utf-8"

    runtime_secrets = _collect_runtime_secrets()
    for key, value in runtime_secrets.items():
        launch_env[key] = value
        launch_env.setdefault(f"ACT_SECRET_{key}", value)

    # Backward-compat env alias used by previous configs.
    fallback_single = str(launch_env.get("GROQ_FALLBACK_MODEL", "") or "").strip()
    if fallback_single and not str(launch_env.get("GROQ_FALLBACK_MODELS", "") or "").strip():
        launch_env["GROQ_FALLBACK_MODELS"] = fallback_single

    return launch_env


def extract_artifacts(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract artifacts from orchestrator result.
    Handles both JSON response format and console output parsing.
    """
    artifacts = {
        "yaml": None,
        "dockerfile": None,
        "terraform": None,
        "kubernetes": None,
        "metadata": {}
    }

    if not result or not isinstance(result, dict):
        return artifacts

    # Case 1: JSON response with state.agent_outputs
    state = result.get("state", {})
    agent_outputs = state.get("agent_outputs", {})

    def _first_base_image_from_dockerfile(dockerfile_content: Optional[str]) -> Optional[str]:
        if not dockerfile_content:
            return None
        normalized = _unwrap_fenced_text(dockerfile_content, expected_language="dockerfile")
        for line in normalized.splitlines():            
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            match = re.match(r"^FROM\s+([^\s]+)", stripped, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def _infer_stack_type(raw_stack: Optional[str], base_image: Optional[str]) -> str:
        stack = (raw_stack or "").strip()
        if stack:
            return stack

        image = (base_image or "").lower()
        if "node" in image:
            return "node"
        if "python" in image:
            return "python"
        if any(x in image for x in ["openjdk", "eclipse-temurin", "adoptopenjdk", "maven", "gradle", "java"]):
            return "java"
        if any(x in image for x in ["golang", "go:"]):
            return "go"
        if "dotnet" in image:
            return "dotnet"

        return "Unknown"

    if agent_outputs:
        # Extract CI/CD workflow
        cicd_output = agent_outputs.get("cicd-agent", {})
        if cicd_output.get("status") == "success":
            cicd_data = cicd_output.get("data", {})
            # Extract workflow if data is present (success flag may not always be present)
            workflow_yaml = cicd_data.get("workflow_yaml")
            if workflow_yaml or cicd_data.get("success"):
                # Convert generation_latency_ms to seconds
                generation_latency_ms = cicd_data.get("generation_latency_ms", 0)
                latency_s = generation_latency_ms / 1000 if generation_latency_ms else 0

                artifacts["yaml"] = workflow_yaml
                artifacts["metadata"]["cicd"] = {
                    "attempts": cicd_data.get("attempts", 1),
                    "latency_s": latency_s,
                    "validation": cicd_data.get("validation_result", {})
                }

        # Extract Dockerfile
        docker_output = agent_outputs.get("docker-agent", {})
        if docker_output.get("status") == "success":
            docker_data = docker_output.get("data", {})
            # Extract dockerfile if data is present (success flag may not always be present)
            configuration = docker_data.get("configuration")
            if configuration or docker_data.get("success"):
                configuration = docker_data.get("configuration", {})
                config_metadata = configuration.get("metadata", {})
                dockerfile_content = configuration.get("dockerfile_content")
                lock_file = docker_data.get("lock_file", {})

                # Convert processing_time_ms to seconds
                processing_time_ms = docker_data.get("processing_time_ms", 0)
                build_time_s = processing_time_ms / 1000 if processing_time_ms else 0

                # Resolve base image with fallbacks: explicit field -> metadata -> lock file -> parsed FROM
                lock_base_images = lock_file.get("base_images", {}) if isinstance(lock_file, dict) else {}
                lock_first_image = next(iter(lock_base_images.keys()), None) if isinstance(lock_base_images, dict) else None
                base_image = (
                    configuration.get("base_image")
                    or config_metadata.get("base_image")
                    or lock_first_image
                    or _first_base_image_from_dockerfile(dockerfile_content)
                    or "Unknown"
                )

                # Resolve stack type with fallbacks and inference from base image
                raw_stack = (
                    config_metadata.get("effective_stack")
                    or config_metadata.get("detected_stack")
                    or config_metadata.get("stack_type")
                    or config_metadata.get("original_stack_input")
                )
                stack = _infer_stack_type(raw_stack, base_image)

                artifacts["dockerfile"] = _unwrap_fenced_text(dockerfile_content, expected_language="dockerfile")
                artifacts["metadata"]["docker"] = {
                    "build_time_s": build_time_s,
                    "stack": stack,
                    "base_image": base_image,
                    "validation": docker_data.get("validation", {})
                }

        # Extract Terraform
        iac_output = agent_outputs.get("iac-agent", {})
        if iac_output.get("status") == "success":
            iac_data = iac_output.get("data", {})
            # Extract terraform if data is present (success flag may not always be present)
            terraform_config = iac_data.get("terraform_config")
            if terraform_config or iac_data.get("success"):
                terraform_config = terraform_config or {}
                artifacts["terraform"] = {
                    "main_tf": terraform_config.get("main_tf"),
                    "variables_tf": terraform_config.get("variables_tf"),
                    "outputs_tf": terraform_config.get("outputs_tf"),
                    "providers_tf": terraform_config.get("providers_tf"),
                }
                artifacts["metadata"]["terraform"] = {
                    "provider": terraform_config.get("provider"),
                    "resources": terraform_config.get("resources", []),
                    "is_valid": terraform_config.get("is_valid", False)
                }

        # Extract Kubernetes manifests
        k8s_output = agent_outputs.get("k8s-agent", {})
        if k8s_output.get("status") == "success":
            k8s_data = k8s_output.get("data", {})
            k8s_manifests = k8s_data.get("k8s_manifests")
            if k8s_manifests or k8s_data.get("success"):
                k8s_manifests = k8s_manifests or {}
                if isinstance(k8s_manifests, dict):
                    artifacts["kubernetes"] = {
                        "namespace_yaml": k8s_manifests.get("namespace_yaml"),
                        "configmap_yaml": k8s_manifests.get("configmap_yaml"),
                        "secret_yaml": k8s_manifests.get("secret_yaml"),
                        "deployment_yaml": k8s_manifests.get("deployment_yaml"),
                        "service_yaml": k8s_manifests.get("service_yaml"),
                        "ingress_yaml": k8s_manifests.get("ingress_yaml"),
                        "hpa_yaml": k8s_manifests.get("hpa_yaml"),
                    }
                    k8s_validation = k8s_data.get("validation", {})
                    artifacts["metadata"]["kubernetes"] = {
                        "namespace": k8s_manifests.get("namespace"),
                        "app_name": k8s_manifests.get("app_name"),
                        "image": k8s_manifests.get("image"),
                        "is_valid": k8s_validation.get("is_valid", k8s_manifests.get("is_valid", False)),
                        "warnings": k8s_validation.get("warnings", []),
                    }

    # Case 2: Parse console output for artifacts (from subprocess)
    elif "stdout" in result or "raw_output" in result:
        output = result.get("stdout") or result.get("raw_output", "")

        # Extract GitHub Actions Workflow
        yaml_match = output.find("--- GitHub Actions Workflow (.yaml) ---")
        if yaml_match != -1:
            yaml_start = yaml_match + len("--- GitHub Actions Workflow (.yaml) ---\n")
            # Find the next artifact or end
            yaml_end = output.find("\n---", yaml_start)
            if yaml_end == -1:
                yaml_end = output.find("\n===", yaml_start)
            if yaml_end == -1:
                yaml_end = len(output)

            yaml_content = output[yaml_start:yaml_end].strip()
            # Remove error messages
            if yaml_content and not yaml_content.startswith("No workflow") and not yaml_content.startswith("cicd-agent did not"):
                artifacts["yaml"] = yaml_content
                artifacts["metadata"]["cicd"] = {"source": "console"}

        # Extract Dockerfile
        docker_match = output.find("--- Dockerfile (.txt) ---")
        if docker_match != -1:
            docker_start = docker_match + len("--- Dockerfile (.txt) ---\n")
            docker_end = output.find("\n---", docker_start)
            if docker_end == -1:
                docker_end = output.find("\n===", docker_start)
            if docker_end == -1:
                docker_end = len(output)

            dockerfile_content = output[docker_start:docker_end].strip()
            if dockerfile_content and not dockerfile_content.startswith("No Dockerfile") and not dockerfile_content.startswith("docker-agent did not"):
                artifacts["dockerfile"] = _unwrap_fenced_text(dockerfile_content, expected_language="dockerfile")
                artifacts["metadata"]["docker"] = {"source": "console"}

        # Extract Terraform
        terraform_match = output.find("--- Terraform HCL Scripts ---")
        if terraform_match != -1:
            terraform_start = terraform_match + len("--- Terraform HCL Scripts ---\n")
            terraform_end = output.find("\n--- Terraform Metadata ---", terraform_start)
            if terraform_end == -1:
                terraform_end = output.find("\n===", terraform_start)
            if terraform_end == -1:
                terraform_end = len(output)

            terraform_content = output[terraform_start:terraform_end].strip()
            if terraform_content and not terraform_content.startswith("No terraform") and not terraform_content.startswith("iac-agent did not"):
                # Parse individual terraform files
                artifacts["terraform"] = {}

                # Extract providers.tf
                if "# providers.tf" in terraform_content:
                    providers_start = terraform_content.find("# providers.tf\n") + len("# providers.tf\n")
                    providers_end = terraform_content.find("\n# ", providers_start)
                    if providers_end == -1:
                        providers_end = len(terraform_content)
                    artifacts["terraform"]["providers_tf"] = terraform_content[providers_start:providers_end].strip()

                # Extract variables.tf
                if "# variables.tf" in terraform_content:
                    vars_start = terraform_content.find("# variables.tf\n") + len("# variables.tf\n")
                    vars_end = terraform_content.find("\n# ", vars_start)
                    if vars_end == -1:
                        vars_end = len(terraform_content)
                    artifacts["terraform"]["variables_tf"] = terraform_content[vars_start:vars_end].strip()

                # Extract main.tf
                if "# main.tf" in terraform_content:
                    main_start = terraform_content.find("# main.tf\n") + len("# main.tf\n")
                    main_end = terraform_content.find("\n# ", main_start)
                    if main_end == -1:
                        main_end = len(terraform_content)
                    artifacts["terraform"]["main_tf"] = terraform_content[main_start:main_end].strip()

                # Extract outputs.tf
                if "# outputs.tf" in terraform_content:
                    outputs_start = terraform_content.find("# outputs.tf\n") + len("# outputs.tf\n")
                    outputs_end = terraform_content.find("\n# ", outputs_start)
                    if outputs_end == -1:
                        outputs_end = len(terraform_content)
                    artifacts["terraform"]["outputs_tf"] = terraform_content[outputs_start:outputs_end].strip()

                artifacts["metadata"]["terraform"] = {"source": "console"}

        # Extract Kubernetes manifests
        k8s_match = output.find("--- Kubernetes Manifests (.yaml) ---")
        if k8s_match != -1:
            k8s_start = k8s_match + len("--- Kubernetes Manifests (.yaml) ---\n")
            k8s_end = output.find("\n===", k8s_start)
            if k8s_end == -1:
                k8s_end = len(output)

            k8s_content = output[k8s_start:k8s_end].strip()
            if k8s_content and not k8s_content.startswith("No Kubernetes") and not k8s_content.startswith("k8s-agent did not"):
                parsed_k8s: Dict[str, str] = {}
                blocks = re.split(r"\n#\s+", "\n" + k8s_content)
                key_map = {
                    "namespace.yaml": "namespace_yaml",
                    "configmap.yaml": "configmap_yaml",
                    "secret.yaml": "secret_yaml",
                    "deployment.yaml": "deployment_yaml",
                    "service.yaml": "service_yaml",
                    "ingress.yaml": "ingress_yaml",
                    "hpa.yaml": "hpa_yaml",
                }

                for block in blocks:
                    block = block.strip()
                    if not block:
                        continue
                    lines = block.splitlines()
                    title = lines[0].strip()
                    body = "\n".join(lines[1:]).strip()
                    mapped_key = key_map.get(title)
                    if mapped_key and body:
                        parsed_k8s[mapped_key] = body

                if parsed_k8s:
                    artifacts["kubernetes"] = parsed_k8s
                    artifacts["metadata"]["kubernetes"] = {"source": "console"}

    return artifacts
def _unwrap_fenced_text(text: Optional[str], expected_language: Optional[str] = None) -> str:
    """Remove markdown code fences (```lang ... ```) from generated artifact text."""
    if text is None:
        return ""
    cleaned = str(text).strip()
    if not cleaned:
        return ""

    for fence in ("```", "'''"):
        lines = cleaned.splitlines()
        if len(lines) < 2:
            continue
        first = lines[0].strip()
        last = lines[-1].strip()
        if not first.startswith(fence) or last != fence:
            continue

        header = first[len(fence):].strip().lower()
        if expected_language and header and expected_language not in header:
            continue
        return "\n".join(lines[1:-1]).strip()

    return cleaned

_ORCHESTRATOR_PREFIX_RE = re.compile(r"^\[Orchestrator\]\s*")


def _strip_orchestrator_prefix(line: str) -> str:
    """Remove the [Orchestrator] prefix that run_orchestrator.py adds to every stdout line."""
    return _ORCHESTRATOR_PREFIX_RE.sub("", line)


def _parse_orchestrator_stdout(stdout_text: str, stderr_text: str = "") -> Dict[str, Any]:
    """Parse orchestrator stdout into a structured result payload.

    Priority order:
    1. Explicit ``=== JSON OUTPUT === … === END JSON OUTPUT ===`` block (the final result).
    2. Per-line scan for a bare JSON object (fallback for simpler runs).

    The explicit block is checked *first* because intermediate signals (e.g. ``plan_ready``)
    are also emitted as bare JSON lines earlier in the stream — scanning lines first would
    incorrectly pick those up instead of the final ``completed`` result.
    """
    output_lines = stdout_text.strip().split("\n") if stdout_text else []
    result_data = {
        "status": "completed",
        "stdout": stdout_text,
        "stderr": stderr_text,
        "artifacts": [],
        "raw_output": stdout_text,
    }

    # Strip [Orchestrator] prefix from every line before searching.
    clean_lines = [_strip_orchestrator_prefix(l) for l in output_lines]
    clean_text = "\n".join(clean_lines)

    json_found = False

    # Pass 1 – explicit marker block (highest priority; this is the final orchestrator output).
    # Use rindex to find the LAST occurrence — the orchestrator emits the block twice:
    # once for plan_ready (intermediate) and once for completed (final). We always want the last.
    if "=== JSON OUTPUT ===" in clean_text:
        try:
            marker_start = "=== JSON OUTPUT ==="
            marker_end = "=== END JSON OUTPUT ==="
            json_start = clean_text.rindex(marker_start) + len(marker_start)
            json_end = clean_text.rindex(marker_end)
            if json_end > json_start:
                json_str = clean_text[json_start:json_end].strip()
                json_data = json.loads(json_str)
                result_data.update(json_data)
                json_found = True
        except (ValueError, json.JSONDecodeError):
            pass

    # Pass 2 – per-line scan (fallback for simpler runs without the marker block).
    if not json_found:
        for clean_line in clean_lines:
            clean_line = clean_line.strip()
            if clean_line.startswith("{"):
                try:
                    json_data = json.loads(clean_line)
                    # Only accept a "completed" payload, not intermediate signals like plan_ready.
                    if json_data.get("status") == "completed" or "state" in json_data:
                        result_data.update(json_data)
                        json_found = True  # noqa: F841
                        break
                except json.JSONDecodeError:
                    continue

    return result_data
