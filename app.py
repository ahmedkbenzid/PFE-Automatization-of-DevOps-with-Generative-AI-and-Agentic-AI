"""
Multi-Agent DevOps Orchestration System - Streamlit Interface

This application provides an interactive web interface for the multi-agent
orchestration system that generates CI/CD pipelines, Dockerfiles, and IaC configurations.
"""

import streamlit as st
import sys
import os
from pathlib import Path
import json
import time
import re
import html
from collections import defaultdict, deque
from typing import Dict, Any, Optional, List, Set
import tempfile
import shutil
import subprocess
import threading

try:
    import yaml
except ModuleNotFoundError:
    yaml = None

# Load environment variables from .env file
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent
orchestrator_agent_path = project_root / "test_pfe" / "02-orchestration-agents-layer" / "orchestrator-agent"
cicd_agent_path = project_root / "test_pfe" / "02-orchestration-agents-layer" / "cicd-agent"
docker_agent_path = project_root / "test_pfe" / "02-orchestration-agents-layer" / "docker-agent"
iac_agent_path = project_root / "test_pfe" / "02-orchestration-agents-layer" / "iac-agent"


def _ensure_sys_path(path: Path) -> None:
    """Add a path to sys.path only once to avoid path bloat on reruns."""
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

# Load .env file from project root
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)
    # Also load from orchestrator directory if exists
    orchestrator_env = project_root / "test_pfe" / "02-orchestration-agents-layer" / "orchestrator-agent" / ".env"
    if orchestrator_env.exists():
        load_dotenv(orchestrator_env, override=False)
    # Load docker-agent .env
    docker_env = project_root / "test_pfe" / "02-orchestration-agents-layer" / "docker-agent" / ".env"
    if docker_env.exists():
        load_dotenv(docker_env, override=False)
    # Load cicd-agent .env
    cicd_env = project_root / "test_pfe" / "02-orchestration-agents-layer" / "cicd-agent" / ".env"
    if cicd_env.exists():
        load_dotenv(cicd_env, override=False)

_ensure_sys_path(orchestrator_agent_path)
_ensure_sys_path(cicd_agent_path)
_ensure_sys_path(docker_agent_path)

# Page configuration
st.set_page_config(
    page_title="DevOps Multi-Agent Orchestrator",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    :root {
        --ink: #0e1b2a;
        --muted: #5d6b7b;
        --paper: #f4f7fb;
        --card: #ffffff;
        --line: #d8e0ea;
        --accent: #0f6d58;
        --accent-2: #145ea8;
        --ok: #1c7c54;
        --warn: #c06a00;
        --bad: #b00020;
    }
    .stApp {
        background:
            radial-gradient(1500px 560px at -10% -30%, #d6ebff 0%, transparent 70%),
            radial-gradient(1300px 520px at 110% -20%, #d4f4e4 0%, transparent 72%),
            var(--paper);
        color: var(--ink);
        font-family: "Manrope", "Segoe UI", sans-serif;
    }
    .main-header {
        font-size: 2.1rem;
        font-weight: 800;
        color: var(--ink);
        margin: 0;
        letter-spacing: -0.02em;
    }
    .sub-header {
        font-size: 1.02rem;
        color: var(--muted);
        margin: 0.35rem 0 0 0;
    }
    .hero-card {
        border: 1px solid var(--line);
        border-radius: 16px;
        padding: 1.1rem 1.25rem;
        background: linear-gradient(115deg, rgba(255,255,255,0.94) 0%, rgba(240,248,255,0.94) 45%, rgba(236,255,246,0.94) 100%);
        box-shadow: 0 12px 28px rgba(15, 45, 80, 0.08);
        margin-bottom: 1rem;
    }
    .menu-badge {
        display: inline-block;
        border: 1px solid #c9d7e8;
        background: #eef4fb;
        color: #1d3553;
        border-radius: 999px;
        font-size: 0.8rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        padding: 0.2rem 0.65rem;
        margin-bottom: 0.45rem;
    }
    .agent-box {
        padding: 0.9rem;
        border-radius: 0.75rem;
        border: 1px solid var(--line);
        margin: 0.45rem 0;
    }
    .cicd-box {
        border-left: 4px solid var(--ok);
        background-color: #f4fbf7;
    }
    .docker-box {
        border-left: 4px solid var(--accent-2);
        background-color: #eff6ff;
    }
    .iac-box {
        border-left: 4px solid var(--warn);
        background-color: #fff7ed;
    }
    .success-box,
    .error-box,
    .warning-box {
        padding: 0.9rem;
        border-radius: 0.55rem;
        border: 1px solid;
        font-weight: 600;
    }
    .success-box {
        background-color: #ebf8ef;
        border-color: #b9e8c6;
        color: #0f5a35;
    }
    .error-box {
        background-color: #fdeef0;
        border-color: #f3c4cc;
        color: #7f1324;
    }
    .warning-box {
        background-color: #fff6e5;
        border-color: #f7dcaa;
        color: #7f4f00;
    }
    .metric-card {
        background-color: var(--card);
        border: 1px solid var(--line);
        padding: 0.9rem;
        border-radius: 0.75rem;
        box-shadow: 0 10px 20px rgba(10, 28, 52, 0.06);
        text-align: center;
    }
    .pipeline-board {
        border: 1px solid #1f2f44;
        border-radius: 14px;
        background: linear-gradient(180deg, #0f1a2b 0%, #101d31 100%);
        padding: 1rem;
        overflow-x: auto;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
    }
    .pipeline-row {
        display: flex;
        flex-wrap: nowrap;
        gap: 0.6rem;
        align-items: stretch;
        margin: 0.4rem 0;
    }
    .pipeline-step {
        min-width: 220px;
        max-width: 260px;
        padding: 0.72rem 0.75rem;
        border-radius: 10px;
        border: 1px solid #3c4c66;
        background: #142339;
        color: #e6edf7;
    }
    .pipeline-step.pass {
        border-color: #2d9b65;
        background: #123428;
    }
    .pipeline-step.fail {
        border-color: #d05b6f;
        background: #3a1b25;
    }
    .pipeline-step.running {
        border-color: #e0a542;
        background: #3b2b15;
    }
    .pipeline-step-title {
        font-weight: 700;
        font-size: 0.92rem;
        margin-bottom: 0.3rem;
    }
    .pipeline-step-subtitle {
        font-size: 0.8rem;
        color: #c8d5e7;
    }
    .pipeline-arrow {
        font-size: 1.1rem;
        color: #8ea4c2;
        align-self: center;
        padding: 0 0.08rem;
    }
    .logs-note {
        border: 1px dashed #c8d2df;
        border-radius: 10px;
        background: #f8fbff;
        padding: 0.75rem 0.85rem;
        color: #30475f;
        margin-bottom: 0.75rem;
    }
    @media (max-width: 900px) {
        .main-header {
            font-size: 1.7rem;
        }
        .hero-card {
            padding: 0.9rem;
        }
        .pipeline-step {
            min-width: 180px;
        }
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'orchestration_result' not in st.session_state:
    st.session_state.orchestration_result = None
if 'execution_history' not in st.session_state:
    st.session_state.execution_history = []
if 'temp_repo_path' not in st.session_state:
    st.session_state.temp_repo_path = None
if 'pending_plan' not in st.session_state:
    st.session_state.pending_plan = None
if 'plan_approved' not in st.session_state:
    st.session_state.plan_approved = False
if 'feedback_stage' not in st.session_state:
    st.session_state.feedback_stage = False
if 'pending_feedback_result' not in st.session_state:
    st.session_state.pending_feedback_result = None
if 'user_feedback_choice' not in st.session_state:
    st.session_state.user_feedback_choice = "not"
if 'feedback_edits' not in st.session_state:
    st.session_state.feedback_edits = {}
if 'artifacts_applied' not in st.session_state:
    st.session_state.artifacts_applied = False
if 'apply_result' not in st.session_state:
    st.session_state.apply_result = None
if 'current_repo_path' not in st.session_state:
    st.session_state.current_repo_path = None
if 'execution_result' not in st.session_state:
    st.session_state.execution_result = None
if 'plan_editor_text' not in st.session_state:
    st.session_state.plan_editor_text = ""
if 'plan_editor_source' not in st.session_state:
    st.session_state.plan_editor_source = ""
if 'last_user_prompt' not in st.session_state:
    st.session_state.last_user_prompt = ""
if 'ui_menu' not in st.session_state:
    st.session_state.ui_menu = "Workspace"
if 'runtime_logs' not in st.session_state:
    st.session_state.runtime_logs = []
if 'orchestrator_task' not in st.session_state:
    st.session_state.orchestrator_task = None
if 'orchestrator_task_error' not in st.session_state:
    st.session_state.orchestrator_task_error = None
if 'runtime_secrets' not in st.session_state:
    st.session_state.runtime_secrets = {}
if 'runtime_secret_lines' not in st.session_state:
    st.session_state.runtime_secret_lines = ""


@st.cache_data(ttl=45, show_spinner=False)
def _is_ollama_running() -> bool:
    """Quick cached probe for Ollama availability to avoid rerun latency."""
    try:
        import requests

        response = requests.get("http://localhost:11434", timeout=0.6)
        return response.status_code == 200 and "ollama is running" in response.text.lower()
    except Exception:
        return False


@st.cache_data(ttl=45, show_spinner=False)
def _agent_paths_exist() -> Dict[str, bool]:
    """Fast agent health check using expected directories/files."""
    return {
        "Orchestrator": (orchestrator_agent_path / "run_orchestrator.py").exists(),
        "CI/CD Agent": (cicd_agent_path / "src" / "pipeline.py").exists(),
        "Docker Agent": (docker_agent_path / "src" / "pipeline.py").exists(),
        "IaC Agent": (iac_agent_path / "src" / "pipeline.py").exists(),
    }


def check_environment() -> Dict[str, bool]:
    """Check required dependencies with a lightweight cached strategy."""
    checks = {
        "Ollama": _is_ollama_running(),
    }
    checks.update(_agent_paths_exist())
    return checks


def _parse_runtime_secret_lines(raw_lines: str) -> tuple[Dict[str, str], List[str]]:
    """Parse KEY=VALUE lines used for additional runtime secrets."""
    parsed: Dict[str, str] = {}
    errors: List[str] = []
    key_pattern = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

    for line_number, raw_line in enumerate((raw_lines or "").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            errors.append(f"Line {line_number}: missing '=' separator")
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key_pattern.match(key):
            errors.append(f"Line {line_number}: invalid secret key '{key}'")
            continue
        if value == "":
            errors.append(f"Line {line_number}: empty value for '{key}'")
            continue

        parsed[key] = value

    return parsed, errors


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
    
    # Check if result has state directly at top level (like from direct agent invocation)
    if "status" in result and "data" in result:
        # This is direct agent output format (not wrapped in state)
        agent_data = result.get("data", {})
        if agent_data.get("success") and "k8s_manifests" in agent_data:
            k8s_manifests = agent_data.get("k8s_manifests", {})
            artifacts["kubernetes"] = {
                "namespace_yaml": k8s_manifests.get("namespace_yaml"),
                "configmap_yaml": k8s_manifests.get("configmap_yaml"),
                "secret_yaml": k8s_manifests.get("secret_yaml"),
                "deployment_yaml": k8s_manifests.get("deployment_yaml"),
                "service_yaml": k8s_manifests.get("service_yaml"),
                "ingress_yaml": k8s_manifests.get("ingress_yaml"),
                "hpa_yaml": k8s_manifests.get("hpa_yaml"),
            }
            processing_time_ms = agent_data.get("processing_time_ms", 0)
            artifacts["metadata"]["kubernetes"] = {
                "processing_time_s": processing_time_ms / 1000 if processing_time_ms else 0,
                "is_valid": agent_data.get("is_valid", False),
                "validation": agent_data.get("validation", {}),
                "source": "direct"
            }
            return artifacts
    
    # Case 1: JSON response with state.agent_outputs
    state = result.get("state", {})
    agent_outputs = state.get("agent_outputs", {})
    
    if agent_outputs:
        # Extract Kubernetes manifests
        k8s_output = agent_outputs.get("k8s-agent", {})
        if k8s_output.get("status") == "success":
            k8s_data = k8s_output.get("data", {})
            if k8s_data.get("success"):
                k8s_manifests = k8s_data.get("k8s_manifests", {})
                artifacts["kubernetes"] = {
                    "namespace_yaml": k8s_manifests.get("namespace_yaml"),
                    "configmap_yaml": k8s_manifests.get("configmap_yaml"),
                    "secret_yaml": k8s_manifests.get("secret_yaml"),
                    "deployment_yaml": k8s_manifests.get("deployment_yaml"),
                    "service_yaml": k8s_manifests.get("service_yaml"),
                    "ingress_yaml": k8s_manifests.get("ingress_yaml"),
                    "hpa_yaml": k8s_manifests.get("hpa_yaml"),
                }
                processing_time_ms = k8s_data.get("processing_time_ms", 0)
                artifacts["metadata"]["kubernetes"] = {
                    "processing_time_s": processing_time_ms / 1000 if processing_time_ms else 0,
                    "is_valid": k8s_data.get("is_valid", False),
                    "validation": k8s_data.get("validation", {})
                }
    
    def _first_base_image_from_dockerfile(dockerfile_content: Optional[str]) -> Optional[str]:
        if not dockerfile_content:
            return None
        for line in dockerfile_content.splitlines():
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
            # Only extract workflow if generation was successful (check inner success field)
            if cicd_data.get("success"):
                # Convert generation_latency_ms to seconds
                generation_latency_ms = cicd_data.get("generation_latency_ms", 0)
                latency_s = generation_latency_ms / 1000 if generation_latency_ms else 0
                
                artifacts["yaml"] = cicd_data.get("workflow_yaml")
                artifacts["metadata"]["cicd"] = {
                    "attempts": cicd_data.get("attempts", 1),
                    "latency_s": latency_s,
                    "validation": cicd_data.get("validation_result", {})
                }
        
        # Extract Dockerfile
        docker_output = agent_outputs.get("docker-agent", {})
        if docker_output.get("status") == "success":
            docker_data = docker_output.get("data", {})
            # Only extract dockerfile if generation was successful (check inner success field)
            if docker_data.get("success"):
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

                artifacts["dockerfile"] = dockerfile_content
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
            # Only extract terraform if generation was successful (check inner success field)
            if iac_data.get("success"):
                terraform_config = iac_data.get("terraform_config", {})
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
            if k8s_data.get("success"):
                k8s_manifests = k8s_data.get("k8s_manifests", {})
                artifacts["kubernetes"] = {
                    "namespace_yaml": k8s_manifests.get("namespace_yaml"),
                    "configmap_yaml": k8s_manifests.get("configmap_yaml"),
                    "secret_yaml": k8s_manifests.get("secret_yaml"),
                    "deployment_yaml": k8s_manifests.get("deployment_yaml"),
                    "service_yaml": k8s_manifests.get("service_yaml"),
                    "ingress_yaml": k8s_manifests.get("ingress_yaml"),
                    "hpa_yaml": k8s_manifests.get("hpa_yaml"),
                }
                processing_time_ms = k8s_data.get("processing_time_ms", 0)
                artifacts["metadata"]["kubernetes"] = {
                    "processing_time_s": processing_time_ms / 1000 if processing_time_ms else 0,
                    "is_valid": k8s_data.get("is_valid", False),
                    "validation": k8s_data.get("validation", {})
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
                artifacts["dockerfile"] = dockerfile_content
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
    
    return artifacts


def run_orchestrator_command_with_live_logs(
    cmd: list,
    cwd: str,
    env: Dict[str, str],
    panel_title: str,
    show_live_panel: bool = False,
) -> Dict[str, Any]:
    """Run orchestrator command while streaming combined stdout/stderr in the UI."""
    log_panel = st.expander(f"Runtime Logs: {panel_title}", expanded=True) if show_live_panel else None
    live_log = log_panel.empty() if log_panel else None
    output_lines = []
    max_capture_lines = 8000
    ui_render_enabled = bool(live_log)
    last_render_at = 0.0

    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    def _render_logs(force: bool = False) -> None:
        nonlocal ui_render_enabled, last_render_at
        if not ui_render_enabled or live_log is None:
            return

        now = time.monotonic()
        should_render = force or (now - last_render_at) >= 0.2 or (len(output_lines) % 8 == 0)
        if not should_render:
            return

        try:
            live_log.code("\n".join(output_lines[-220:]), language="text")
            last_render_at = now
        except Exception:
            # Client websocket may close during long-running commands; keep collecting logs silently.
            ui_render_enabled = False

    while True:
        line = process.stdout.readline()
        if line == "" and process.poll() is not None:
            break
        if line:
            output_lines.append(line.rstrip("\n"))
            if len(output_lines) > max_capture_lines:
                del output_lines[:2000]
            _render_logs()

    _render_logs(force=True)

    return_code = process.wait()
    stdout_text = "\n".join(output_lines)
    _store_runtime_log(panel_title, output_lines, return_code)

    try:
        if log_panel and return_code == 0:
            log_panel.caption("Command completed successfully.")
        elif log_panel:
            log_panel.caption(f"Command failed with exit code {return_code}.")
    except Exception:
        pass

    return {
        "returncode": return_code,
        "stdout": stdout_text,
        "stderr": "",
    }


def _parse_orchestrator_stdout(stdout_text: str, stderr_text: str = "") -> Dict[str, Any]:
    """Parse orchestrator stdout into a structured result payload."""
    output_lines = stdout_text.strip().split("\n") if stdout_text else []
    result_data = {
        "status": "completed",
        "stdout": stdout_text,
        "stderr": stderr_text,
        "artifacts": [],
        "raw_output": stdout_text,
    }

    json_found = False
    for line in output_lines:
        line = line.strip()
        if line.startswith("{"):
            try:
                json_data = json.loads(line)
                if "status" in json_data or "state" in json_data:
                    result_data.update(json_data)
                    json_found = True
                    break
            except json.JSONDecodeError:
                continue

    if not json_found and "=== JSON OUTPUT ===" in stdout_text:
        try:
            json_start = stdout_text.index("=== JSON OUTPUT ===") + len("=== JSON OUTPUT ===")
            json_end = stdout_text.index("=== END JSON OUTPUT ===")
            json_str = stdout_text[json_start:json_end].strip()
            json_data = json.loads(json_str)
            result_data.update(json_data)
        except (ValueError, json.JSONDecodeError):
            pass

    return result_data


def _stream_subprocess_output(process: subprocess.Popen, output_lines: List[str], max_capture_lines: int = 8000) -> None:
    """Background reader thread for subprocess stdout."""
    while True:
        line = process.stdout.readline()
        if line == "" and process.poll() is not None:
            break
        if line:
            output_lines.append(line.rstrip("\n"))
            if len(output_lines) > max_capture_lines:
                del output_lines[:2000]


def _start_orchestrator_background_task(
    cmd: List[str],
    cwd: str,
    env: Dict[str, str],
    panel_title: str,
    task_type: str,
    payload: Dict[str, Any],
) -> None:
    """Launch orchestrator in background so Streamlit reruns don't restart work."""
    launch_env = dict(env)
    launch_env.setdefault("PYTHONUNBUFFERED", "1")
    launch_env.setdefault("PYTHONIOENCODING", "utf-8")

    launch_cmd = list(cmd)
    if launch_cmd and len(launch_cmd) > 1:
        exe_name = Path(str(launch_cmd[0])).name.lower()
        if exe_name.startswith("python") and launch_cmd[1] != "-u":
            launch_cmd = [launch_cmd[0], "-u", *launch_cmd[1:]]

    process = subprocess.Popen(
        launch_cmd,
        cwd=cwd,
        env=launch_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    output_lines: List[str] = []
    reader_thread = threading.Thread(
        target=_stream_subprocess_output,
        args=(process, output_lines),
        daemon=True,
    )
    reader_thread.start()

    st.session_state.orchestrator_task = {
        "task_type": task_type,
        "payload": payload,
        "panel_title": panel_title,
        "process": process,
        "reader_thread": reader_thread,
        "output_lines": output_lines,
        "started_at": time.time(),
    }
    st.session_state.orchestrator_task_error = None


def _is_orchestrator_task_running(task: Optional[Dict[str, Any]]) -> bool:
    """Return True when a background orchestrator subprocess is still running."""
    if not isinstance(task, dict):
        return False
    process = task.get("process")
    return process is not None and process.poll() is None


def _finalize_orchestrator_task_if_done() -> bool:
    """Finalize background task output into session state when process completes."""
    task = st.session_state.get("orchestrator_task")
    if not isinstance(task, dict):
        return False

    process = task.get("process")
    if process is None or process.poll() is None:
        return False

    reader_thread = task.get("reader_thread")
    if isinstance(reader_thread, threading.Thread):
        reader_thread.join(timeout=0.2)

    output_lines = task.get("output_lines", [])
    stdout_text = "\n".join(output_lines)
    returncode = process.returncode if process.returncode is not None else process.poll()
    returncode = int(returncode) if returncode is not None else -1

    _store_runtime_log(task.get("panel_title", "Orchestrator Runtime Logs"), output_lines, returncode)

    task_type = task.get("task_type", "plan-only")
    payload = task.get("payload", {}) if isinstance(task.get("payload"), dict) else {}

    if returncode == 0:
        result_data = _parse_orchestrator_stdout(stdout_text, "")

        if task_type == "approved-plan":
            plan_data = payload.get("plan_data", {}) if isinstance(payload.get("plan_data"), dict) else {}
            result_data["execution_plan"] = plan_data.get("execution_plan")
            result_data["planner_reasoning"] = plan_data.get("planner_reasoning")
            result_data["used_planner"] = True
            result_data["complexity_score"] = plan_data.get("complexity_score", 0)

            st.session_state.pending_feedback_result = result_data
            st.session_state.feedback_stage = True
            st.session_state.pending_plan = None
            st.session_state.plan_approved = False

        else:
            user_prompt = payload.get("user_prompt", "")
            repo_path = payload.get("repo_path")
            github_url = payload.get("github_url")

            if result_data.get("status") == "plan_ready" and result_data.get("used_planner"):
                st.session_state.pending_plan = {
                    "prompt": user_prompt,
                    "repo_path": repo_path,
                    "github_url": github_url,
                    "execution_plan": result_data.get("execution_plan"),
                    "planner_reasoning": result_data.get("planner_reasoning"),
                    "complexity_score": result_data.get("complexity_score", 0),
                    "create_pr": bool(payload.get("create_pr", False)),
                    "branch_name": str(payload.get("branch_name", "") or "").strip(),
                    "pr_title": str(payload.get("pr_title", "") or "").strip(),
                    "pr_body": str(payload.get("pr_body", "") or "").strip(),
                }
                st.session_state.plan_approved = False
            else:
                st.session_state.pending_feedback_result = result_data
                st.session_state.feedback_stage = True

        st.session_state.orchestrator_task = None
        st.session_state.orchestrator_task_error = None
        return True

    st.session_state.orchestrator_task_error = {
        "exit_code": returncode,
        "stdout": stdout_text,
        "panel_title": task.get("panel_title", "Orchestrator Runtime Logs"),
    }
    st.session_state.orchestrator_task = None
    return True


def display_agent_status(result: Dict[str, Any]):
    """Display status of each agent execution"""
    if not result or not isinstance(result, dict):
        return
    
    state = result.get("state", {})
    agent_outputs = state.get("agent_outputs", {})
    target_agents = state.get("target_agents", [])
    
    st.markdown("### 📊 Agent Execution Status")
    
    cols = st.columns(len(target_agents) if target_agents else 3)
    
    agent_info = {
        "cicd-agent": {"name": "CI/CD Agent", "icon": "🔧", "class": "cicd-box"},
        "docker-agent": {"name": "Docker Agent", "icon": "🐳", "class": "docker-box"},
        "iac-agent": {"name": "IaC Agent", "icon": "☁️", "class": "iac-box"}
    }
    
    for idx, agent_key in enumerate(target_agents):
        info = agent_info.get(agent_key, {"name": agent_key, "icon": "🤖", "class": ""})
        output = agent_outputs.get(agent_key, {})
        status = output.get("status", "not_run")
        
        with cols[idx]:
            if status == "success":
                st.markdown(f'<div class="metric-card" style="border-left: 4px solid #4CAF50;">', unsafe_allow_html=True)
                st.markdown(f"{info['icon']} **{info['name']}**")
                st.markdown("✅ **Success**")
            elif status == "error" or status == "failed":
                st.markdown(f'<div class="metric-card" style="border-left: 4px solid #f44336;">', unsafe_allow_html=True)
                st.markdown(f"{info['icon']} **{info['name']}**")
                st.markdown("❌ **Failed**")
            else:
                st.markdown(f'<div class="metric-card" style="border-left: 4px solid #9E9E9E;">', unsafe_allow_html=True)
                st.markdown(f"{info['icon']} **{info['name']}**")
                st.markdown("⏸️ **Pending**")
            
            st.markdown('</div>', unsafe_allow_html=True)


def display_pipeline_execution(result: Dict[str, Any], show_logs: bool = False):
    """Render docker/act local execution details, retries, and logs."""
    if not result or not isinstance(result, dict):
        return

    state = result.get("state", {})
    agent_outputs = state.get("agent_outputs", {})
    pipeline_execution = agent_outputs.get("pipeline_execution", {}) if isinstance(agent_outputs, dict) else {}

    if not pipeline_execution:
        return

    st.markdown("### 🔬 Local Pipeline Execution")

    status = pipeline_execution.get("status", "unknown")
    if status == "success":
        st.success("Docker build and act completed successfully.")
    elif status == "skipped":
        st.info(pipeline_execution.get("message", "Pipeline execution skipped."))
    else:
        st.error(pipeline_execution.get("message", "Local pipeline execution failed."))

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Retries Used", pipeline_execution.get("repair_retry_count", 0))
    with col2:
        st.metric("Max Retries", pipeline_execution.get("max_self_repair_retries", 0))
    with col3:
        st.metric("Final Status", status)

    workspace = pipeline_execution.get("workspace")
    if workspace:
        st.caption(f"Workspace: {workspace}")

    attempts = pipeline_execution.get("attempts", [])
    if not attempts:
        attempts = [{"attempt_number": 1, "kind": "single", "result": pipeline_execution}]

    for attempt in attempts:
        attempt_number = attempt.get("attempt_number", 1)
        kind = attempt.get("kind", "single")
        attempt_result = attempt.get("result", {})
        attempt_status = attempt_result.get("status", "unknown")

        with st.expander(f"Attempt {attempt_number} ({kind}) - {attempt_status}", expanded=(attempt_status != "success")):
            repo_copy = attempt_result.get("repo_copy", {})
            if isinstance(repo_copy, dict):
                if repo_copy.get("copied"):
                    st.caption(
                        f"Repo copied from {repo_copy.get('source', 'unknown')} to {repo_copy.get('destination', 'unknown')} "
                        f"({repo_copy.get('copied_entries', 0)} entries)."
                    )
                elif repo_copy.get("reason"):
                    st.caption(f"Repo copy skipped: {repo_copy.get('reason')}")

            for step_key, label in (("docker_build", "Docker Build"), ("act", "Act Workflow")):
                step_data = attempt_result.get(step_key, {})
                if not isinstance(step_data, dict):
                    continue

                st.markdown(f"**{label}**")
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("Exit Code", step_data.get("exit_code", "n/a"))
                with c2:
                    st.metric("Timed Out", "Yes" if step_data.get("timed_out") else "No")
                with c3:
                    st.metric("Success", "Yes" if step_data.get("success") else "No")

                logs = step_data.get("logs", [])
                if show_logs and isinstance(logs, list) and logs:
                    rendered_logs = []
                    for log_item in logs[-220:]:
                        if isinstance(log_item, dict):
                            rendered_logs.append(f"[{log_item.get('stream', 'stdout')}] {log_item.get('line', '')}")
                        else:
                            rendered_logs.append(str(log_item))
                    st.code("\n".join(rendered_logs), language="text")


def _parse_act_pipeline_steps(act_logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Parse act logs into ordered pipeline steps with status and duration."""
    start_re = re.compile(r"⭐\s+Run\s+(.+)$")
    success_re = re.compile(r"✅\s+Success\s+-\s+(.+?)(?:\s+\[([^\]]+)\])?$")
    fail_re = re.compile(r"❌\s+Failure\s+-\s+(.+?)(?:\s+\[([^\]]+)\])?$")

    steps: List[Dict[str, Any]] = []
    index_by_name: Dict[str, int] = {}

    def _ensure_step(name: str) -> Dict[str, Any]:
        if name not in index_by_name:
            index_by_name[name] = len(steps)
            steps.append({
                "name": name,
                "status": "running",
                "duration": None,
                "errors": [],
            })
        return steps[index_by_name[name]]

    for entry in act_logs or []:
        if not isinstance(entry, dict):
            continue
        raw_line = str(entry.get("line", ""))
        if not raw_line:
            continue

        m_start = start_re.search(raw_line)
        if m_start:
            _ensure_step(m_start.group(1).strip())
            continue

        m_success = success_re.search(raw_line)
        if m_success:
            name = m_success.group(1).strip()
            step = _ensure_step(name)
            step["status"] = "pass"
            step["duration"] = m_success.group(2)
            continue

        m_fail = fail_re.search(raw_line)
        if m_fail:
            name = m_fail.group(1).strip()
            step = _ensure_step(name)
            step["status"] = "fail"
            step["duration"] = m_fail.group(2)
            continue

        lower = raw_line.lower()
        if "::error::" in raw_line or "job failed" in lower or "exitcode" in lower:
            target = steps[-1] if steps else _ensure_step("act")
            target["status"] = "fail"
            if len(target["errors"]) < 3:
                target["errors"].append(raw_line)

    return steps


def _extract_act_failure_summary(act_logs: List[Dict[str, Any]]) -> str:
    """Extract the most useful failure reason from act logs."""
    plain_lines = [
        str(item.get("line", ""))
        for item in (act_logs or [])
        if isinstance(item, dict) and item.get("line")
    ]
    for line in reversed(plain_lines):
        lower = line.lower()
        if "input required and not supplied: username" in lower or "input required and not supplied: password" in lower:
            return (
                "Required registry secrets are missing for docker/login-action. "
                "Add DOCKERHUB_USERNAME and DOCKERHUB_TOKEN in the app Runtime Secrets panel."
            )
        if ("version 21" in lower or "jdk 21" in lower) and ("not found" in lower or "unable to find" in lower):
            return (
                "Local Act run failed to provision JDK 21. "
                "Preserve Java 21 in the workflow and fix setup-java configuration or runner/network constraints."
            )
        if "No such image: catthehacker/ubuntu:act-latest" in line:
            return "Act default runner image is unavailable on your Docker host. The execution agent now retries with fallback runner images automatically."
        if "TLS handshake timeout" in line:
            return "Network/TLS handshake timed out while Act tried to fetch a GitHub Action dependency."
        if "Client network socket disconnected before secure TLS connection was established" in line:
            return "Network/TLS handshake failed while an action tried to download dependencies (actions/setup-java)."
        if "::error::" in line:
            return line.split("::error::", 1)[1].strip() or line.strip()
    for line in reversed(plain_lines):
        if "Error: Job" in line or "Job failed" in line:
            return line.strip()
    return "Act job failed. Open the logs for the exact failing command."


def _json_safe(value: Any, seen: Optional[Set[int]] = None) -> Any:
    """Convert arbitrary objects to a JSON-serializable structure for debug UI rendering."""
    if seen is None:
        seen = set()
        
    if isinstance(value, (int, float, str, bool, type(None))):
        return value
        
    if id(value) in seen:
        return "<circular reference>"
        
    seen.add(id(value))
    
    if isinstance(value, dict):
        return {str(k): _json_safe(v, seen.copy()) for k, v in value.items()}
    elif isinstance(value, (list, tuple, set)):
        return [_json_safe(v, seen.copy()) for v in value]
        
    return str(value)


def display_act_pipeline(exec_result: Dict[str, Any], expanded: bool = True) -> None:
    """Display act execution as a pipeline timeline instead of logs-only output."""
    if not isinstance(exec_result, dict):
        return

    act_result = exec_result.get("act", {})
    if not isinstance(act_result, dict):
        return

    act_logs = act_result.get("logs", [])
    if not isinstance(act_logs, list) or not act_logs:
        return

    steps = _parse_act_pipeline_steps(act_logs)
    if not steps:
        return

    with st.expander("🧭 Act Pipeline View", expanded=expanded):
        segments: List[str] = []
        for idx, step in enumerate(steps):
            status = step.get("status", "running")
            icon = "✅" if status == "pass" else ("❌" if status == "fail" else "⏳")
            safe_name = html.escape(str(step.get("name", "step")))
            duration = html.escape(str(step.get("duration") or "no duration"))
            subtitle = f"Status: {status} | Duration: {duration}"

            if step.get("errors"):
                subtitle += " | Error captured"

            segments.append(
                """
                <div class=\"pipeline-step {status}\">
                    <div class=\"pipeline-step-title\">{icon} {name}</div>
                    <div class=\"pipeline-step-subtitle\">{subtitle}</div>
                </div>
                """.format(status=status, icon=icon, name=safe_name, subtitle=html.escape(subtitle))
            )
            if idx < len(steps) - 1:
                segments.append('<div class="pipeline-arrow">→</div>')

        st.markdown(f'<div class="pipeline-row">{"".join(segments)}</div>', unsafe_allow_html=True)

        if not act_result.get("success"):
            st.error(_extract_act_failure_summary(act_logs))


def _normalize_pipeline_key(value: str) -> str:
    """Normalize step/job labels for fuzzy status matching."""
    return re.sub(r"[^a-z0-9]+", "", (value or "").strip().lower())


def _prettify_job_name(job_id: str) -> str:
    """Convert workflow job id into a readable label."""
    pretty = re.sub(r"[_\-]+", " ", job_id or "").strip()
    return pretty.title() if pretty else "Pipeline Step"


def _default_pipeline_jobs() -> Dict[str, Dict[str, Any]]:
    """Fallback pipeline resembling a professional CI/CD flow."""
    return {
        "code_quality": {"id": "code_quality", "name": "Code Quality Checks", "needs": [], "order": 0},
        "unit_tests": {"id": "unit_tests", "name": "Unit Tests", "needs": ["code_quality"], "order": 1},
        "build_image": {"id": "build_image", "name": "Build Docker Image", "needs": ["unit_tests"], "order": 2},
        "scan_image": {"id": "scan_image", "name": "Container Image Scan", "needs": ["build_image"], "order": 3},
        "deploy_dev": {"id": "deploy_dev", "name": "Deploy To Development", "needs": ["scan_image"], "order": 4},
        "deploy_prod": {"id": "deploy_prod", "name": "Deploy To Production", "needs": ["scan_image"], "order": 5},
    }


def _extract_workflow_jobs_text_fallback(workflow_yaml: Optional[str]) -> Dict[str, Dict[str, Any]]:
    """Fallback parser for common workflow text when YAML parsing fails."""
    text = _sanitize_workflow_yaml_text(workflow_yaml or "")
    if not text.strip():
        return {}

    lines = text.splitlines()
    in_jobs = False
    current_job: Optional[str] = None
    reading_needs_block = False
    jobs: Dict[str, Dict[str, Any]] = {}

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if re.match(r"^jobs\s*:\s*$", stripped, flags=re.IGNORECASE):
            in_jobs = True
            current_job = None
            reading_needs_block = False
            continue

        if not in_jobs:
            continue

        top_level_match = re.match(r"^[A-Za-z0-9_.-]+\s*:\s*$", stripped)
        if top_level_match and not line.startswith(" "):
            break

        job_match = re.match(r"^\s{2}([A-Za-z0-9_.-]+)\s*:\s*$", line)
        if job_match:
            job_id = job_match.group(1)
            current_job = job_id
            reading_needs_block = False
            jobs[job_id] = {
                "id": job_id,
                "name": _prettify_job_name(job_id),
                "needs": [],
                "order": len(jobs),
            }
            continue

        if not current_job:
            continue

        needs_inline = re.match(r"^\s{4}needs\s*:\s*(.+)\s*$", line)
        if needs_inline:
            raw = needs_inline.group(1).strip()
            reading_needs_block = False
            if raw.startswith("[") and raw.endswith("]"):
                values = [item.strip().strip("'\"") for item in raw[1:-1].split(",") if item.strip()]
                jobs[current_job]["needs"] = values
            elif raw and raw not in {"[]", "null", "None"}:
                jobs[current_job]["needs"] = [raw.strip("'\"")]
            else:
                jobs[current_job]["needs"] = []
            continue

        if re.match(r"^\s{4}needs\s*:\s*$", line):
            reading_needs_block = True
            jobs[current_job]["needs"] = []
            continue

        if reading_needs_block:
            dep_match = re.match(r"^\s{6}-\s*([A-Za-z0-9_.-]+)\s*$", line)
            if dep_match:
                jobs[current_job]["needs"].append(dep_match.group(1))
                continue
            reading_needs_block = False

    known_ids = set(jobs.keys())
    for job in jobs.values():
        deps = job.get("needs", [])
        job["needs"] = [dep for dep in deps if dep in known_ids]

    return jobs


def _extract_workflow_jobs(workflow_yaml: Optional[str]) -> Dict[str, Dict[str, Any]]:
    """Parse GitHub Actions jobs and dependencies from workflow YAML."""
    if not workflow_yaml or not workflow_yaml.strip():
        return _default_pipeline_jobs()

    if yaml is None:
        fallback_jobs = _extract_workflow_jobs_text_fallback(workflow_yaml)
        return fallback_jobs or _default_pipeline_jobs()

    try:
        cleaned_yaml = _sanitize_workflow_yaml_text(workflow_yaml).strip() or workflow_yaml
        payload = yaml.safe_load(cleaned_yaml) or {}
        if isinstance(payload, dict) and True in payload and "on" not in payload:
            payload["on"] = payload.pop(True)
    except Exception:
        fallback_jobs = _extract_workflow_jobs_text_fallback(workflow_yaml)
        return fallback_jobs or _default_pipeline_jobs()

    jobs_raw = payload.get("jobs", {}) if isinstance(payload, dict) else {}
    if not isinstance(jobs_raw, dict) or not jobs_raw:
        fallback_jobs = _extract_workflow_jobs_text_fallback(workflow_yaml)
        return fallback_jobs or _default_pipeline_jobs()

    jobs: Dict[str, Dict[str, Any]] = {}
    known_ids = set(jobs_raw.keys())

    for idx, (job_id, job_data) in enumerate(jobs_raw.items()):
        item = job_data if isinstance(job_data, dict) else {}
        job_name = item.get("name") if isinstance(item.get("name"), str) else _prettify_job_name(job_id)
        needs_raw = item.get("needs", [])
        if isinstance(needs_raw, str):
            needs = [needs_raw]
        elif isinstance(needs_raw, list):
            needs = [dep for dep in needs_raw if isinstance(dep, str)]
        else:
            needs = []

        needs = [dep for dep in needs if dep in known_ids]
        jobs[job_id] = {
            "id": job_id,
            "name": job_name,
            "needs": needs,
            "order": idx,
        }

    return jobs or _default_pipeline_jobs()


def _resolve_pipeline_workflow_yaml(
    artifacts: Optional[Dict[str, Any]],
    orchestration_result: Optional[Dict[str, Any]],
) -> Optional[str]:
    """Resolve workflow YAML for pipeline rendering with robust fallback sources."""
    candidate = ""
    if isinstance(orchestration_result, dict):
        state = orchestration_result.get("state", {})
        if isinstance(state, dict):
            agent_outputs = state.get("agent_outputs", {})
            if isinstance(agent_outputs, dict):
                cicd_output = agent_outputs.get("cicd-agent", {})
                cicd_data = cicd_output.get("data", {}) if isinstance(cicd_output, dict) else {}
                if isinstance(cicd_data, dict):
                    candidate = str(cicd_data.get("workflow_yaml") or "")

    if not candidate.strip() and isinstance(artifacts, dict):
        candidate = str(artifacts.get("yaml") or "")

    cleaned = _sanitize_workflow_yaml_text(candidate)
    return cleaned if cleaned.strip() else None


def _extract_act_status_map(execution_result: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Map execution logs to pipeline step statuses."""
    if not isinstance(execution_result, dict):
        return {}

    act_data = execution_result.get("act", {})
    if not isinstance(act_data, dict):
        return {}

    logs = act_data.get("logs", [])
    if not isinstance(logs, list):
        return {}

    status_map: Dict[str, Dict[str, Any]] = {}
    for step in _parse_act_pipeline_steps(logs):
        key = _normalize_pipeline_key(str(step.get("name", "")))
        if not key:
            continue
        status_map[key] = {
            "status": step.get("status", "running"),
            "duration": step.get("duration"),
        }

    return status_map


def _extract_orchestrator_status_map(
    orchestration_result: Optional[Dict[str, Any]],
    jobs: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Map orchestrator agent outcomes to pipeline jobs when Act logs are unavailable."""
    if not isinstance(orchestration_result, dict) or not isinstance(jobs, dict) or not jobs:
        return {}

    state = orchestration_result.get("state", {})
    if not isinstance(state, dict):
        return {}

    agent_outputs = state.get("agent_outputs", {})
    if not isinstance(agent_outputs, dict):
        return {}

    def _status_from_agent(agent_key: str) -> str:
        output = agent_outputs.get(agent_key, {})
        if not isinstance(output, dict):
            return "pending"
        status = str(output.get("status", "")).lower()
        if status == "success":
            return "pass"
        if status in {"error", "failed"}:
            return "fail"
        if status in {"running", "in_progress", "in-progress"}:
            return "running"
        return "pending"

    cicd_status = _status_from_agent("cicd-agent")
    docker_status = _status_from_agent("docker-agent")
    iac_status = _status_from_agent("iac-agent")

    status_map: Dict[str, Dict[str, Any]] = {}
    for data in jobs.values():
        job_id = str(data.get("id", ""))
        job_name = str(data.get("name", ""))
        normalized = _normalize_pipeline_key(f"{job_id} {job_name}")

        mapped = "pending"
        if any(token in normalized for token in ["docker", "image", "container", "scan"]):
            mapped = docker_status
        elif any(token in normalized for token in ["terraform", "iac", "infra", "deploy", "provision"]):
            mapped = iac_status
        elif any(token in normalized for token in ["test", "lint", "quality", "build", "workflow", "ci", "cicd"]):
            mapped = cicd_status

        if mapped == "pending":
            overall = str(orchestration_result.get("status", "")).lower()
            if overall == "completed":
                mapped = "pass"
            elif overall in {"error", "failed", "blocked"}:
                mapped = "fail"

        duration_text = "agent result"
        if mapped == "pending":
            duration_text = "queued"
        elif mapped == "running":
            duration_text = "in progress"

        status_map[_normalize_pipeline_key(job_name)] = {"status": mapped, "duration": duration_text}
        status_map[_normalize_pipeline_key(job_id)] = {"status": mapped, "duration": duration_text}

    return status_map


def _extract_pipeline_status_map(
    execution_result: Optional[Dict[str, Any]],
    orchestration_result: Optional[Dict[str, Any]],
    jobs: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Prefer Act-derived statuses; fallback to orchestrator agent outcomes."""
    act_map = _extract_act_status_map(execution_result)
    if act_map:
        return act_map
    return _extract_orchestrator_status_map(orchestration_result, jobs)


def _build_job_levels(jobs: Dict[str, Dict[str, Any]]) -> List[List[str]]:
    """Topologically group jobs into dependency levels for fallback rendering."""
    if not jobs:
        return []

    indegree: Dict[str, int] = {job_id: 0 for job_id in jobs}
    dependents: Dict[str, List[str]] = defaultdict(list)

    for job_id, data in jobs.items():
        for dep in data.get("needs", []):
            if dep in jobs:
                indegree[job_id] += 1
                dependents[dep].append(job_id)

    queue = deque(
        sorted(
            [job_id for job_id, degree in indegree.items() if degree == 0],
            key=lambda item: jobs[item].get("order", 0),
        )
    )

    topo: List[str] = []
    while queue:
        current = queue.popleft()
        topo.append(current)
        for nxt in sorted(dependents.get(current, []), key=lambda item: jobs[item].get("order", 0)):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)

    if len(topo) != len(jobs):
        # Fallback for malformed/cyclic dependency graphs.
        topo = sorted(jobs.keys(), key=lambda item: jobs[item].get("order", 0))

    level_by_job: Dict[str, int] = {}
    for job_id in topo:
        deps = [dep for dep in jobs[job_id].get("needs", []) if dep in level_by_job]
        level_by_job[job_id] = max(level_by_job[dep] for dep in deps) + 1 if deps else 0

    grouped: Dict[int, List[str]] = defaultdict(list)
    for job_id in topo:
        grouped[level_by_job[job_id]].append(job_id)

    return [grouped[level] for level in sorted(grouped.keys())]


def _build_pipeline_graph_dot(
    jobs: Dict[str, Dict[str, Any]],
    status_map: Dict[str, Dict[str, Any]],
) -> str:
    """Build Graphviz DOT for a GitHub Actions style pipeline board."""

    def _escape(value: str) -> str:
        return (value or "").replace("\\", "\\\\").replace('"', '\\"')

    def _style_for(status: str) -> Dict[str, str]:
        if status == "pass":
            return {"fill": "#123928", "border": "#2da36b", "font": "#eafff1", "label": "SUCCESS"}
        if status == "fail":
            return {"fill": "#44202b", "border": "#d0677e", "font": "#ffe9ee", "label": "FAILED"}
        if status == "running":
            return {"fill": "#4a3516", "border": "#dcaa46", "font": "#fff2d5", "label": "RUNNING"}
        return {"fill": "#172842", "border": "#425b7e", "font": "#e7efff", "label": "PENDING"}

    dot_lines: List[str] = [
        "digraph Pipeline {",
        "rankdir=LR;",
        'graph [bgcolor="#0d1728", pad="0.35", nodesep="0.52", ranksep="0.72", splines="ortho"];',
        'node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=10, penwidth=1.2];',
        'edge [color="#6d88ab", arrowsize=0.7, penwidth=1.0];',
    ]

    ordered_jobs = sorted(jobs.values(), key=lambda item: item.get("order", 0))
    for data in ordered_jobs:
        job_id = data["id"]
        name = data.get("name") or _prettify_job_name(job_id)
        key_options = [_normalize_pipeline_key(name), _normalize_pipeline_key(job_id)]

        info = None
        for key in key_options:
            if key in status_map:
                info = status_map[key]
                break

        status = (info or {}).get("status", "pending")
        duration = (info or {}).get("duration") or "queued"
        style = _style_for(status)
        label = f"{name}\\n{style['label']} | {duration}"

        dot_lines.append(
            '"{job_id}" [label="{label}", fillcolor="{fill}", color="{border}", fontcolor="{font}"];'.format(
                job_id=_escape(job_id),
                label=_escape(label),
                fill=style["fill"],
                border=style["border"],
                font=style["font"],
            )
        )

    edge_count = 0
    for data in ordered_jobs:
        job_id = data["id"]
        needs = data.get("needs", []) or []
        for dep in needs:
            if dep in jobs:
                dot_lines.append(f'"{_escape(dep)}" -> "{_escape(job_id)}";')
                edge_count += 1

    if edge_count == 0 and len(ordered_jobs) > 1:
        for idx in range(len(ordered_jobs) - 1):
            left = ordered_jobs[idx]["id"]
            right = ordered_jobs[idx + 1]["id"]
            dot_lines.append(f'"{_escape(left)}" -> "{_escape(right)}";')

    dot_lines.append("}")
    return "\n".join(dot_lines)


def _render_pipeline_fallback_cards(
    jobs: Dict[str, Dict[str, Any]],
    status_map: Dict[str, Dict[str, Any]],
) -> None:
    """Render pipeline using HTML cards if Graphviz is unavailable."""
    levels = _build_job_levels(jobs)
    if not levels:
        st.info("No pipeline steps available.")
        return

    rows: List[str] = []
    for row_idx, level_jobs in enumerate(levels):
        segments: List[str] = []
        for idx, job_id in enumerate(level_jobs):
            data = jobs[job_id]
            name = data.get("name") or _prettify_job_name(job_id)
            key_options = [_normalize_pipeline_key(name), _normalize_pipeline_key(job_id)]
            info = None
            for key in key_options:
                if key in status_map:
                    info = status_map[key]
                    break
            status = (info or {}).get("status", "running")
            duration = (info or {}).get("duration") or "queued"

            icon = "SUCCESS" if status == "pass" else ("FAILED" if status == "fail" else ("RUNNING" if status == "running" else "PENDING"))
            safe_name = html.escape(str(name))
            subtitle = html.escape(f"{icon} | {duration}")

            segments.append(
                (
                    '<div class="pipeline-step {status}">'
                    '<div class="pipeline-step-title">{title}</div>'
                    '<div class="pipeline-step-subtitle">{subtitle}</div>'
                    "</div>"
                ).format(status=html.escape(status), title=safe_name, subtitle=subtitle)
            )
            if idx < len(level_jobs) - 1:
                segments.append('<div class="pipeline-arrow">→</div>')

        rows.append(f'<div class="pipeline-row">{"".join(segments)}</div>')
        if row_idx < len(levels) - 1:
            rows.append('<div class="pipeline-row" style="justify-content:center;"><div class="pipeline-arrow">↓</div></div>')

    st.markdown(f'<div class="pipeline-board">{"".join(rows)}</div>', unsafe_allow_html=True)


def display_workflow_pipeline(
    workflow_yaml: Optional[str],
    execution_result: Optional[Dict[str, Any]] = None,
    orchestration_result: Optional[Dict[str, Any]] = None,
    title: str = "CI/CD Pipeline",
) -> None:
    """Display pipeline graph similar to GitHub Actions execution flow."""
    jobs = _extract_workflow_jobs(workflow_yaml)
    status_map = _extract_pipeline_status_map(execution_result, orchestration_result, jobs)

    st.markdown(f"### {title}")
    st.caption("A pipeline board view inspired by the GitHub Actions graph.")

    total = len(jobs)
    passed = 0
    failed = 0
    running = 0
    pending = 0

    for data in jobs.values():
        key_name = _normalize_pipeline_key(data.get("name", ""))
        key_id = _normalize_pipeline_key(data.get("id", ""))
        status = status_map.get(key_name, status_map.get(key_id, {})).get("status", "pending")
        if status == "pass":
            passed += 1
        elif status == "fail":
            failed += 1
        elif status == "running":
            running += 1
        else:
            pending += 1

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Steps", total)
    with c2:
        st.metric("Passed", passed)
    with c3:
        st.metric("Failed", failed)
    with c4:
        st.metric("Running", running)
    with c5:
        st.metric("Pending", pending)

    dot = _build_pipeline_graph_dot(jobs, status_map)
    try:
        st.graphviz_chart(dot, width="stretch", height=400)
    except Exception:
        _render_pipeline_fallback_cards(jobs, status_map)


def _store_runtime_log(title: str, lines: List[str], return_code: int) -> None:
    """Store command logs in session state for the Logs menu view."""
    entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "title": title,
        "return_code": return_code,
        "lines": list(lines[-500:]),
    }
    current_logs = st.session_state.get("runtime_logs", [])
    current_logs.append(entry)
    st.session_state.runtime_logs = current_logs[-12:]


def display_logs_center(orchestration_result: Optional[Dict[str, Any]] = None) -> None:
    """Dedicated logs dashboard shown from the sidebar menu."""
    st.markdown("### Runtime Logs")
    st.markdown(
        '<div class="logs-note">Logs are now centralized in this menu so the main workspace stays focused on requests, pipeline flow, and artifacts.</div>',
        unsafe_allow_html=True,
    )

    active_task = st.session_state.get("orchestrator_task")
    if _is_orchestrator_task_running(active_task):
        started_at = float(active_task.get("started_at", time.time()))
        elapsed_s = max(0, int(time.time() - started_at))
        st.info(f"Orchestrator is running in background ({elapsed_s}s).")
        if st.button("Refresh Logs", key="refresh_active_logs", width="content"):
            st.rerun()
        with st.expander("Active Orchestrator Task Logs", expanded=True):
            lines = active_task.get("output_lines", []) if isinstance(active_task, dict) else []
            if lines:
                st.code("\n".join(lines[-300:]), language="text")
            else:
                st.caption("Waiting for first log lines...")

    last_task_error = st.session_state.get("orchestrator_task_error")
    if isinstance(last_task_error, dict):
        st.error(
            f"Last background run failed with exit code {last_task_error.get('exit_code', 'unknown')}."
        )
        with st.expander("Last Background Run Output", expanded=False):
            error_stdout = str(last_task_error.get("stdout", ""))
            if error_stdout:
                st.code(error_stdout[-20000:], language="text")
            else:
                st.caption("No output captured.")

    runtime_logs = st.session_state.get("runtime_logs", [])
    if not runtime_logs:
        st.info("No orchestrator command logs captured yet.")
    else:
        for idx, entry in enumerate(reversed(runtime_logs), start=1):
            title = entry.get("title", "Command Logs")
            code = entry.get("return_code", "n/a")
            timestamp = entry.get("timestamp", "")
            with st.expander(f"{idx}. {timestamp} | {title} | exit={code}", expanded=(idx == 1)):
                lines = entry.get("lines", [])
                if lines:
                    st.code("\n".join(lines[-300:]), language="text")
                else:
                    st.caption("No lines captured for this command.")

    act_logs = []
    if isinstance(st.session_state.get("execution_result"), dict):
        act_payload = st.session_state.execution_result.get("act", {})
        if isinstance(act_payload, dict):
            act_logs = [
                item.get("line", "")
                for item in act_payload.get("logs", [])
                if isinstance(item, dict) and item.get("line")
            ]

    if act_logs:
        with st.expander("Latest Act Logs", expanded=False):
            st.code("\n".join(act_logs[-300:]), language="text")

    if orchestration_result and isinstance(orchestration_result, dict):
        with st.expander("Raw Orchestrator JSON", expanded=False):
            st.json(_json_safe(orchestration_result))

    c1, _ = st.columns([1, 5])
    with c1:
        if st.button("Clear Logs", key="clear_runtime_logs"):
            st.session_state.runtime_logs = []
            st.rerun()


def display_artifacts(artifacts: Dict[str, Any]):
    """Display generated artifacts"""
    st.markdown("### 📦 Generated Artifacts")
    
    tabs = st.tabs(["GitHub Actions Workflow", "Dockerfile", "Terraform/IaC", "Kubernetes", "Metadata"])
    
    # CI/CD Workflow Tab
    with tabs[0]:
        if artifacts.get("yaml"):
            st.markdown("#### GitHub Actions Workflow")
            st.code(artifacts["yaml"], language="yaml")
            
            st.download_button(
                label="📥 Download workflow.yml",
                data=artifacts["yaml"],
                file_name=".github/workflows/ci-cd.yml",
                mime="text/yaml",
                key="download_yaml"
            )
            
            if "cicd" in artifacts.get("metadata", {}):
                meta = artifacts["metadata"]["cicd"]
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Generation Time", f"{meta.get('latency_s', 0):.0f}s")
                with col2:
                    st.metric("Attempts", meta.get('attempts', 1))
                with col3:
                    validation = meta.get('validation', {})
                    is_valid = validation.get('is_valid', False)
                    st.metric("Validation", "✅ Passed" if is_valid else "⚠️ Check")
        else:
            st.info("No GitHub Actions workflow generated. Try requesting a CI/CD pipeline.")
    
    # Dockerfile Tab
    with tabs[1]:
        if artifacts.get("dockerfile"):
            st.markdown("#### Dockerfile")
            st.code(artifacts["dockerfile"], language="dockerfile")
            
            st.download_button(
                label="📥 Download Dockerfile",
                data=artifacts["dockerfile"],
                file_name="Dockerfile",
                mime="text/plain",
                key="download_dockerfile"
            )
            
            if "docker" in artifacts.get("metadata", {}):
                meta = artifacts["metadata"]["docker"]
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Generation Time", f"{meta.get('build_time_s', 0):.0f}s")
                with col2:
                    st.metric("Stack Type", meta.get('stack', 'Unknown'))
                with col3:
                    st.metric("Base Image", meta.get('base_image', 'Unknown'))
        else:
            st.info("No Dockerfile generated. Try requesting a Docker configuration.")
    
    # Terraform Tab
    with tabs[2]:
        if artifacts.get("terraform") and isinstance(artifacts["terraform"], dict):
            terraform_files = artifacts["terraform"]
            has_any_file = any(terraform_files.values())
            
            if has_any_file:
                st.markdown("#### Terraform Configuration Files")
                
                # Display each terraform file if it exists
                file_order = [
                    ("providers_tf", "providers.tf", "hcl"),
                    ("variables_tf", "variables.tf", "hcl"),
                    ("main_tf", "main.tf", "hcl"),
                    ("outputs_tf", "outputs.tf", "hcl")
                ]
                
                for key, filename, language in file_order:
                    content = terraform_files.get(key)
                    if content and isinstance(content, str) and content.strip():
                        st.markdown(f"**{filename}**")
                        st.code(content, language=language)
                        
                        st.download_button(
                            label=f"📥 Download {filename}",
                            data=content,
                            file_name=filename,
                            mime="text/plain",
                            key=f"download_{key}"
                        )
                
                # Download all terraform files as zip
                if len([v for v in terraform_files.values() if v]) > 1:
                    st.markdown("---")
                    import zipfile
                    import io
                    
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                        for key, filename, _ in file_order:
                            content = terraform_files.get(key)
                            if content:
                                zip_file.writestr(filename, content)
                    
                    st.download_button(
                        label="📦 Download All Terraform Files (.zip)",
                        data=zip_buffer.getvalue(),
                        file_name="terraform-config.zip",
                        mime="application/zip",
                        key="download_terraform_zip"
                    )
                
                # Display metadata
                if "terraform" in artifacts.get("metadata", {}):
                    meta = artifacts["metadata"]["terraform"]
                    st.markdown("---")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Provider", meta.get('provider', 'Unknown'))
                    with col2:
                        resources = meta.get('resources', [])
                        st.metric("Resources", len(resources) if resources else 0)
                    with col3:
                        is_valid = meta.get('is_valid', False)
                        st.metric("Validation", "✅ Valid" if is_valid else "⚠️ Check")
            else:
                st.info("No Terraform configuration generated. Try requesting infrastructure as code.")
        else:
            st.info("No Terraform configuration generated. Try requesting infrastructure as code.")
    
    # Kubernetes Tab
    with tabs[3]:
        if artifacts.get("kubernetes") and isinstance(artifacts["kubernetes"], dict):
            k8s_files = artifacts["kubernetes"]
            has_any_file = any(k8s_files.values())
            
            if has_any_file:
                st.markdown("#### Kubernetes Manifests")
                
                file_order = [
                    ("namespace_yaml", "namespace.yaml", "yaml"),
                    ("configmap_yaml", "configmap.yaml", "yaml"),
                    ("secret_yaml", "secret.yaml", "yaml"),
                    ("deployment_yaml", "deployment.yaml", "yaml"),
                    ("service_yaml", "service.yaml", "yaml"),
                    ("ingress_yaml", "ingress.yaml", "yaml"),
                    ("hpa_yaml", "hpa.yaml", "yaml"),
                ]
                
                for key, filename, language in file_order:
                    content = k8s_files.get(key)
                    if content and isinstance(content, str) and content.strip():
                        st.markdown(f"**{filename}**")
                        st.code(content, language=language)
                        
                        st.download_button(
                            label=f"📥 Download {filename}",
                            data=content,
                            file_name=filename,
                            mime="text/plain",
                            key=f"download_k8s_{key}"
                        )
                
                # Download all k8s files as zip
                if len([v for v in k8s_files.values() if v]) > 1:
                    st.markdown("---")
                    import zipfile
                    import io
                    
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                        for key, filename, _ in file_order:
                            content = k8s_files.get(key)
                            if content:
                                zip_file.writestr(filename, content)
                    
                    st.download_button(
                        label="📦 Download All Kubernetes Manifests (.zip)",
                        data=zip_buffer.getvalue(),
                        file_name="kubernetes-manifests.zip",
                        mime="application/zip",
                        key="download_k8s_zip"
                    )
                
                # Display metadata
                if "kubernetes" in artifacts.get("metadata", {}):
                    meta = artifacts["metadata"]["kubernetes"]
                    st.markdown("---")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Processing Time", f"{meta.get('processing_time_s', 0):.1f}s")
                    with col2:
                        is_valid = meta.get('is_valid', False)
                        st.metric("Validation", "✅ Valid" if is_valid else "⚠️ Check")
            else:
                st.info("No Kubernetes manifests generated.")
        else:
            st.info("No Kubernetes manifests generated. Try requesting a Kubernetes deployment.")
    
    # Metadata Tab
    with tabs[4]:
        if artifacts.get("metadata"):
            st.json(artifacts["metadata"])
        else:
            st.info("No metadata available.")


def _apply_feedback_edits_to_result(result: Dict[str, Any], edited_artifacts: Dict[str, Any]) -> Dict[str, Any]:
    """
    Persist user-edited artifacts into the orchestration result for downstream display.
    """
    if not isinstance(result, dict):
        return result

    updated = dict(result)
    updated["edited_artifacts"] = edited_artifacts
    return updated


def _extract_allowed_agents(plan: Dict[str, Any]) -> Set[str]:
    """Extract known agent ids from a planner execution plan."""
    allowed: Set[str] = set()

    for task in plan.get("tasks", []) or []:
        if isinstance(task, dict):
            task_id = task.get("id")
            task_agent = task.get("agent")
            if isinstance(task_id, str) and task_id:
                allowed.add(task_id)
            if isinstance(task_agent, str) and task_agent:
                allowed.add(task_agent)

    for key, value in (plan.get("dependencies", {}) or {}).items():
        if isinstance(key, str) and key:
            allowed.add(key)
        if isinstance(value, list):
            for dep in value:
                if isinstance(dep, str) and dep:
                    allowed.add(dep)

    for step in plan.get("execution_order", []) or []:
        if isinstance(step, list):
            for agent in step:
                if isinstance(agent, str) and agent:
                    allowed.add(agent)
        elif isinstance(step, str) and step:
            allowed.add(step)

    if not allowed:
        allowed = {"docker-agent", "cicd-agent", "iac-agent", "k8s-agent"}

    return allowed


def _normalize_agent_name(raw_name: str, allowed_agents: Set[str]) -> Optional[str]:
    """Normalize user-entered agent names into canonical agent ids."""
    candidate = (raw_name or "").strip().lower().replace("`", "")
    candidate = re.sub(r"\s+", " ", candidate)
    if not candidate:
        return None

    alias_map = {
        "docker": "docker-agent",
        "docker agent": "docker-agent",
        "cicd": "cicd-agent",
        "ci/cd": "cicd-agent",
        "ci cd": "cicd-agent",
        "cicd agent": "cicd-agent",
        "iac": "iac-agent",
        "terraform": "iac-agent",
        "iac agent": "iac-agent",
        "k8s": "k8s-agent",
        "kubernetes": "k8s-agent",
        "k8s agent": "k8s-agent",
    }

    if candidate in alias_map:
        candidate = alias_map[candidate]

    if candidate in allowed_agents:
        return candidate

    dashed = candidate.replace("_", "-")
    if dashed in allowed_agents:
        return dashed

    if not dashed.endswith("-agent"):
        with_suffix = f"{dashed}-agent"
        if with_suffix in allowed_agents:
            return with_suffix

    return None


def _plan_to_paragraph(plan: Dict[str, Any]) -> str:
    """Render execution_order as editable plain-text steps."""
    execution_order = plan.get("execution_order", []) or []
    if not execution_order:
        return ""

    lines: List[str] = []
    for idx, step in enumerate(execution_order, 1):
        if isinstance(step, list) and step:
            lines.append(f"Step {idx}: {', '.join(step)} (parallel)")
        elif isinstance(step, str) and step:
            lines.append(f"Step {idx}: {step}")

    return "\n".join(lines)


def _paragraph_to_execution_order(plan_text: str, allowed_agents: Set[str]) -> List[Any]:
    """Parse plain-text steps into planner execution_order format."""
    if not plan_text or not plan_text.strip():
        raise ValueError("Plan paragraph is empty. Add at least one step.")

    parsed_steps: List[Any] = []
    unknown_agents: Set[str] = set()

    for raw_line in plan_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        line = re.sub(r"^step\s*\d+\s*[:\-]\s*", "", line, flags=re.IGNORECASE).strip()
        line = line.rstrip(".")
        if not line:
            continue

        parallel_marker = bool(re.search(r"\bparallel\b", line, flags=re.IGNORECASE))
        line = re.sub(r"[\(\[]\s*parallel\s*[\)\]]", "", line, flags=re.IGNORECASE).strip()

        parts = [p.strip() for p in re.split(r",|\+|\band\b", line, flags=re.IGNORECASE) if p.strip()]
        resolved: List[str] = []

        for part in parts:
            normalized = _normalize_agent_name(part, allowed_agents)
            if not normalized:
                unknown_agents.add(part)
                continue
            if normalized not in resolved:
                resolved.append(normalized)

        if not resolved:
            continue

        if len(resolved) == 1 and not parallel_marker:
            parsed_steps.append(resolved[0])
        else:
            parsed_steps.append(resolved)

    if unknown_agents:
        raise ValueError(
            "Unknown agent names in plan paragraph: "
            f"{', '.join(sorted(unknown_agents))}. "
            f"Allowed: {', '.join(sorted(allowed_agents))}"
        )

    if not parsed_steps:
        raise ValueError("No valid steps were parsed. Use lines like: Step 1: docker-agent")

    return parsed_steps


def _sanitize_dockerfile_text(raw_content: str) -> str:
    """Extract Dockerfile content from raw or fenced output."""
    text = (raw_content or "").replace("\r\n", "\n").strip()
    if not text:
        return ""

    fenced = re.findall(r"```(?:dockerfile|docker|text|plaintext)?\s*\n(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    for block in fenced:
        candidate = block.strip()
        if candidate and re.search(r"^FROM\s+", candidate, flags=re.IGNORECASE | re.MULTILINE):
            return candidate + "\n"

    cleaned = "\n".join(line for line in text.splitlines() if not line.strip().startswith("```"))
    cleaned = cleaned.strip()
    if cleaned:
        return cleaned + "\n"
    return ""


def _extract_dockerfile_from_agent_payload(agent_payload: Dict[str, Any]) -> str:
    """Extract Dockerfile content from docker-agent structured response."""
    configuration = (agent_payload.get("configuration") or {}) if isinstance(agent_payload, dict) else {}
    dockerfile_raw = configuration.get("dockerfile_content") or ""
    return _sanitize_dockerfile_text(dockerfile_raw)


def _invoke_docker_agent_generation(
    user_prompt: str,
    repository_path: str,
    repo_context: Optional[Dict[str, Any]] = None,
    timeout_seconds: int = 240,
) -> Dict[str, Any]:
    """Invoke docker-agent subprocess and return structured payload."""
    docker_agent_root = project_root / "test_pfe" / "02-orchestration-agents-layer" / "docker-agent"
    if not docker_agent_root.exists():
        raise RuntimeError(f"docker-agent not found at {docker_agent_root}")

    context_payload = repo_context or {}
    args = [user_prompt, repository_path or "", json.dumps(context_payload)]
    args_json = json.dumps(args)

    run_code = (
        "from dataclasses import asdict; "
        "from src.pipeline import run_pipeline; "
        "user_prompt = args[0]; "
        "repo_path = args[1]; "
        "repo_ctx = __import__('json').loads(args[2]) if args[2] != '{}' else None; "
        "result = run_pipeline(user_prompt, repo_path, False, repo_ctx); "
        "print('DOCKER_RESULT_JSON=' + __import__('json').dumps(asdict(result), default=str))"
    )

    safe_run_code = (
        "import json, sys; "
        f"args = json.loads({repr(args_json)}); "
        "sys.argv = [''] + args; "
        f"{run_code}"
    )

    run_env = _apply_runtime_env_overrides(os.environ.copy())
    run_env["PYTHONPATH"] = str(docker_agent_root) + os.pathsep + run_env.get("PYTHONPATH", "")

    completed = subprocess.run(
        [sys.executable, "-c", safe_run_code],
        cwd=str(docker_agent_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=run_env,
        check=False,
        timeout=timeout_seconds,
    )

    if completed.returncode != 0:
        error_msg = (completed.stderr or completed.stdout or "docker-agent execution failed").strip()
        raise RuntimeError(error_msg)

    for line in (completed.stdout or "").splitlines():
        if line.startswith("DOCKER_RESULT_JSON="):
            return json.loads(line[len("DOCKER_RESULT_JSON="):])

    raise RuntimeError("docker-agent returned no structured Docker output")


def _copy_repository_to_workspace(repository_path: str, workspace_path: Path) -> Dict[str, Any]:
    """Copy repository content into isolated workspace for docker build validation."""
    if not repository_path:
        return {"copied": False, "reason": "No repository path provided"}

    source_path = Path(repository_path)
    if not source_path.exists() or not source_path.is_dir():
        return {
            "copied": False,
            "reason": f"Repository path not found or invalid: {repository_path}",
        }

    ignore_dirs = {
        ".git", ".hg", ".svn",
        "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
        ".venv", "venv", "node_modules",
    }

    copied_entries = 0
    for child in source_path.iterdir():
        if child.name in ignore_dirs:
            continue

        target = workspace_path / child.name
        if child.is_dir():
            shutil.copytree(child, target, dirs_exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child, target)
        copied_entries += 1

    return {
        "copied": True,
        "source": str(source_path),
        "destination": str(workspace_path),
        "copied_entries": copied_entries,
        "mode": "local-copy",
    }


def _run_command_with_timeout(command: List[str], cwd: str, timeout_seconds: int, step_name: str) -> Dict[str, Any]:
    """Run shell command with timeout and capture combined logs."""
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
        combined_logs = []
        if completed.stdout:
            combined_logs.extend({"stream": "stdout", "line": line} for line in completed.stdout.splitlines())
        if completed.stderr:
            combined_logs.extend({"stream": "stderr", "line": line} for line in completed.stderr.splitlines())

        return {
            "step": step_name,
            "command": command,
            "cwd": cwd,
            "exit_code": completed.returncode,
            "timed_out": False,
            "logs": combined_logs,
            "success": completed.returncode == 0,
        }
    except subprocess.TimeoutExpired as exc:
        timeout_logs = []
        if exc.stdout:
            timeout_logs.extend({"stream": "stdout", "line": line} for line in exc.stdout.splitlines())
        if exc.stderr:
            timeout_logs.extend({"stream": "stderr", "line": line} for line in exc.stderr.splitlines())
        timeout_logs.append({"stream": "stderr", "line": f"Command timed out after {timeout_seconds}s"})
        return {
            "step": step_name,
            "command": command,
            "cwd": cwd,
            "exit_code": -1,
            "timed_out": True,
            "logs": timeout_logs,
            "success": False,
        }


def _validate_dockerfile_build(dockerfile_content: str, repository_path: str, timeout_seconds: int = 600) -> Dict[str, Any]:
    """Validate a Dockerfile by running docker build in an isolated workspace."""
    workspace = tempfile.mkdtemp(prefix="docker-validate-")
    workspace_path = Path(workspace)

    try:
        copy_result = _copy_repository_to_workspace(repository_path, workspace_path)
        if not copy_result.get("copied"):
            return {
                "success": False,
                "message": copy_result.get("reason", "failed to copy repository"),
                "repo_copy": copy_result,
                "docker_build": {
                    "exit_code": -1,
                    "timed_out": False,
                    "logs": [],
                    "success": False,
                },
            }

        dockerfile_path = workspace_path / "Dockerfile"
        dockerfile_path.write_text(_sanitize_dockerfile_text(dockerfile_content), encoding="utf-8")

        image_name = f"user-validation-{int(time.time())}"
        docker_build = _run_command_with_timeout(
            command=["docker", "build", "-t", f"{image_name}:latest", "."],
            cwd=str(workspace_path),
            timeout_seconds=timeout_seconds,
            step_name="docker-build",
        )

        return {
            "success": docker_build.get("success", False),
            "message": "Docker image build succeeded" if docker_build.get("success") else "Docker image build failed",
            "image_name": image_name,
            "repo_copy": copy_result,
            "docker_build": docker_build,
        }
    except FileNotFoundError:
        return {
            "success": False,
            "message": "Docker CLI not found. Install Docker and ensure it is in PATH.",
            "docker_build": {
                "exit_code": -1,
                "timed_out": False,
                "logs": [{"stream": "stderr", "line": "docker command not found"}],
                "success": False,
            },
        }
    finally:
        shutil.rmtree(workspace_path, ignore_errors=True)


def _summarize_docker_build_failure(build_result: Dict[str, Any]) -> str:
    """Summarize docker build failure for docker-agent repair prompts."""
    docker_build = build_result.get("docker_build") or {}
    lines = [
        f"exit_code={docker_build.get('exit_code')}",
        f"timed_out={docker_build.get('timed_out')}",
    ]

    logs = docker_build.get("logs", [])
    tail = logs[-40:] if isinstance(logs, list) else []
    if tail:
        lines.append("recent_logs:")
        for entry in tail:
            if isinstance(entry, dict):
                stream = entry.get("stream", "stdout")
                line = entry.get("line", "")
                lines.append(f"[{stream}] {line}")
            else:
                lines.append(str(entry))

    return "\n".join(lines)


def _sanitize_workflow_yaml_text(raw_content: str) -> str:
    """Extract GitHub Actions workflow YAML from raw or fenced output."""
    text = (raw_content or "").replace("\r\n", "\n").strip()
    if not text:
        return ""

    fenced = re.findall(r"```(?:yaml|yml|github-actions|text|plaintext)?\s*\n(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    for block in fenced:
        candidate = block.strip()
        if candidate and ("jobs:" in candidate.lower() or re.search(r"^on\s*:", candidate, flags=re.IGNORECASE | re.MULTILINE)):
            return candidate + "\n"

    cleaned = "\n".join(line for line in text.splitlines() if not line.strip().startswith("```"))
    cleaned = cleaned.strip()
    if cleaned:
        return cleaned + "\n"
    return ""


def _extract_cicd_workflow_from_agent_payload(agent_payload: Dict[str, Any]) -> str:
    """Extract workflow YAML from cicd-agent structured response."""
    workflow_raw = ""
    if isinstance(agent_payload, dict):
        workflow_raw = agent_payload.get("workflow_yaml") or ""
    return _sanitize_workflow_yaml_text(workflow_raw)


def _invoke_cicd_agent_generation(
    user_prompt: str,
    repository_path: str,
    repo_context: Optional[Dict[str, Any]] = None,
    timeout_seconds: int = 300,
) -> Dict[str, Any]:
    """Invoke cicd-agent subprocess and return structured payload."""
    cicd_agent_root = project_root / "test_pfe" / "02-orchestration-agents-layer" / "cicd-agent"
    if not cicd_agent_root.exists():
        raise RuntimeError(f"cicd-agent not found at {cicd_agent_root}")

    context_payload = repo_context or {}
    args = [user_prompt, repository_path or "", json.dumps(context_payload)]
    args_json = json.dumps(args)

    run_code = (
        "from dataclasses import asdict; "
        "from src.pipeline import CICDPipeline; "
        "from src.models.types import UserRequest; "
        "user_prompt = args[0]; "
        "repo_path = args[1]; "
        "repo_ctx = __import__('json').loads(args[2]) if args[2] != '{}' else None; "
        "req = UserRequest(text=user_prompt); "
        "result = CICDPipeline().process_request(req, repo_path=repo_path, repo_context=repo_ctx); "
        "print('CICD_RESULT_JSON=' + __import__('json').dumps(asdict(result), default=str))"
    )

    safe_run_code = (
        "import json, sys; "
        f"args = json.loads({repr(args_json)}); "
        "sys.argv = [''] + args; "
        f"{run_code}"
    )

    run_env = _apply_runtime_env_overrides(os.environ.copy())
    run_env["PYTHONPATH"] = str(cicd_agent_root) + os.pathsep + run_env.get("PYTHONPATH", "")

    completed = subprocess.run(
        [sys.executable, "-c", safe_run_code],
        cwd=str(cicd_agent_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=run_env,
        check=False,
        timeout=timeout_seconds,
    )

    if completed.returncode != 0:
        error_msg = (completed.stderr or completed.stdout or "cicd-agent execution failed").strip()
        raise RuntimeError(error_msg)

    for line in (completed.stdout or "").splitlines():
        if line.startswith("CICD_RESULT_JSON="):
            return json.loads(line[len("CICD_RESULT_JSON="):])

    raise RuntimeError("cicd-agent returned no structured CI/CD output")


def _summarize_act_failure(execution_result: Dict[str, Any]) -> str:
    """Summarize Act execution failure for cicd-agent repair prompts."""
    act = execution_result.get("act") or {}
    lines = [
        f"exit_code={act.get('exit_code')}",
        f"timed_out={act.get('timed_out')}",
    ]

    logs = act.get("logs", [])
    tail = logs[-60:] if isinstance(logs, list) else []
    if tail:
        lines.append("recent_logs:")
        for entry in tail:
            if isinstance(entry, dict):
                stream = entry.get("stream", "stdout")
                line = entry.get("line", "")
                lines.append(f"[{stream}] {line}")
            else:
                lines.append(str(entry))

    return "\n".join(lines)


def _ensure_executable_cicd_workflow_via_agent(
    initial_workflow: str,
    dockerfile_content: str,
    prebuilt_image_name: Optional[str],
    user_prompt: str,
    repository_path: str,
    run_execution_fn,
    max_attempts: int = 4,
    act_timeout: int = 600,
    runtime_secrets: Optional[Dict[str, str]] = None,
    required_java_version: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Keep sending Act failures back to cicd-agent until workflow executes successfully
    or retry budget is exhausted.
    """
    current_workflow = _sanitize_workflow_yaml_text(initial_workflow)
    if not current_workflow:
        return {
            "status": "error",
            "message": "CI/CD workflow is empty; cannot validate with Act.",
            "attempts": [],
            "workflow_yaml": "",
        }

    def _normalize_java_major(version_text: Optional[str]) -> Optional[str]:
        match = re.search(r"\d+", str(version_text or ""))
        return match.group(0) if match else None

    def _extract_workflow_java_major(workflow_yaml: str) -> Optional[str]:
        match = re.search(
            r"java-version\s*:\s*['\"]?([0-9]+(?:\.[0-9]+)?)['\"]?",
            workflow_yaml or "",
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        return _normalize_java_major(match.group(1))

    locked_java_major = _normalize_java_major(required_java_version) or _extract_workflow_java_major(current_workflow)

    attempts: List[Dict[str, Any]] = []
    prompt_seed = (user_prompt or "Generate a valid GitHub Actions workflow").strip()
    current_dockerfile = _sanitize_dockerfile_text(dockerfile_content)
    prebuilt_image = str(prebuilt_image_name or "").strip()
    repo_context = {
        "is_available": True,
        "source": "local",
        "path": repository_path,
    }
    if locked_java_major:
        repo_context["java_version"] = locked_java_major
        repo_context["languages"] = ["java"]
        repo_context["build_system"] = "maven"

    for attempt in range(1, max_attempts + 1):
        execution_result = run_execution_fn(
            dockerfile_content=current_dockerfile,
            cicd_workflow_content=current_workflow,
            repository_path=repository_path,
            act_timeout=act_timeout,
            secrets=runtime_secrets,
            prebuilt_image_name=prebuilt_image,
        )
        attempts.append({
            "attempt": attempt,
            "execution_result": execution_result,
        })

        if execution_result.get("status") == "success" and (execution_result.get("act") or {}).get("success"):
            return {
                "status": "success",
                "message": "CI/CD workflow validated successfully with Act.",
                "workflow_yaml": current_workflow,
                "attempts": attempts,
                "total_attempts": attempt,
                "execution_result": execution_result,
            }

        if attempt >= max_attempts:
            break

        failure_summary = _summarize_act_failure(execution_result)
        java_lock_requirement = ""
        if locked_java_major:
            java_lock_requirement = (
                f"IMPORTANT: Keep Java version pinned to {locked_java_major}. "
                "Do NOT downgrade java-version to 17 or any other value. "
                "Use actions/setup-java@v4 with distribution: temurin.\n\n"
            )

        repair_prompt = (
            f"{prompt_seed}\n\n"
            "The GitHub Actions workflow below fails when executed with `act`.\n"
            "Regenerate a corrected workflow YAML so Act passes successfully.\n"
            "Keep it production-ready and executable.\n\n"
            f"{java_lock_requirement}"
            "Current workflow:\n"
            "```yaml\n"
            f"{current_workflow}"
            "```\n\n"
            "Act failure details:\n"
            f"{failure_summary}\n"
        )

        try:
            cicd_agent_payload = _invoke_cicd_agent_generation(
                user_prompt=repair_prompt,
                repository_path=repository_path,
                repo_context=repo_context,
            )
        except Exception as exc:
            return {
                "status": "error",
                "message": f"cicd-agent failed during repair attempt {attempt}: {exc}",
                "attempts": attempts,
                "workflow_yaml": current_workflow,
            }

        if not cicd_agent_payload.get("success"):
            payload_errors = cicd_agent_payload.get("errors", [])
            payload_error_text = "; ".join(str(item) for item in payload_errors) if payload_errors else "unknown cicd-agent failure"
            return {
                "status": "error",
                "message": f"cicd-agent returned unsuccessful repair result: {payload_error_text}",
                "attempts": attempts,
                "workflow_yaml": current_workflow,
            }

        regenerated_workflow = _extract_cicd_workflow_from_agent_payload(cicd_agent_payload)
        if not regenerated_workflow:
            return {
                "status": "error",
                "message": "cicd-agent returned empty workflow during repair loop.",
                "attempts": attempts,
                "workflow_yaml": current_workflow,
            }

        if locked_java_major:
            regenerated_java_major = _extract_workflow_java_major(regenerated_workflow)
            if regenerated_java_major != locked_java_major:
                return {
                    "status": "error",
                    "message": (
                        "cicd-agent changed required Java version during repair "
                        f"(expected {locked_java_major}, got {regenerated_java_major or 'missing'})."
                    ),
                    "attempts": attempts,
                    "workflow_yaml": current_workflow,
                }

        current_workflow = regenerated_workflow

    return {
        "status": "error",
        "message": "CI/CD workflow could not be repaired to a passing Act state within retry limit.",
        "attempts": attempts,
        "workflow_yaml": current_workflow,
    }


def _ensure_buildable_dockerfile_via_agent(
    initial_dockerfile: str,
    user_prompt: str,
    repository_path: str,
    max_attempts: int = 4,
) -> Dict[str, Any]:
    """
    Keep returning Dockerfile generation to docker-agent until docker build succeeds
    or retry budget is exhausted.
    """
    current_dockerfile = _sanitize_dockerfile_text(initial_dockerfile)
    if not current_dockerfile:
        return {
            "status": "error",
            "message": "Dockerfile is empty; cannot validate build.",
            "attempts": [],
        }

    repo_context = {
        "is_available": True,
        "source": "local",
        "path": repository_path,
    }

    attempts: List[Dict[str, Any]] = []
    prompt_seed = (user_prompt or "Generate a production-ready Dockerfile").strip()

    for attempt in range(1, max_attempts + 1):
        build_result = _validate_dockerfile_build(current_dockerfile, repository_path)
        attempts.append(
            {
                "attempt": attempt,
                "build_result": build_result,
            }
        )

        if build_result.get("success"):
            return {
                "status": "success",
                "message": "Dockerfile validated successfully.",
                "dockerfile_content": current_dockerfile,
                "attempts": attempts,
                "total_attempts": attempt,
            }

        if attempt >= max_attempts:
            break

        failure_summary = _summarize_docker_build_failure(build_result)
        repair_prompt = (
            f"{prompt_seed}\n\n"
            "The Dockerfile below must build successfully with `docker build .` in the target repository.\n"
            "Regenerate a corrected Dockerfile and prioritize build reliability.\n\n"
            "Current Dockerfile:\n"
            "```dockerfile\n"
            f"{current_dockerfile}"
            "```\n\n"
            "Build failure details:\n"
            f"{failure_summary}\n"
        )

        try:
            docker_agent_payload = _invoke_docker_agent_generation(
                user_prompt=repair_prompt,
                repository_path=repository_path,
                repo_context=repo_context,
            )
        except Exception as exc:
            return {
                "status": "error",
                "message": f"docker-agent failed during repair attempt {attempt}: {exc}",
                "attempts": attempts,
                "dockerfile_content": current_dockerfile,
            }

        regenerated_dockerfile = _extract_dockerfile_from_agent_payload(docker_agent_payload)
        if not regenerated_dockerfile:
            return {
                "status": "error",
                "message": "docker-agent returned empty Dockerfile during repair loop.",
                "attempts": attempts,
                "dockerfile_content": current_dockerfile,
            }

        current_dockerfile = regenerated_dockerfile

    return {
        "status": "error",
        "message": "Dockerfile could not be repaired to a buildable state within retry limit.",
        "attempts": attempts,
        "dockerfile_content": current_dockerfile,
    }


def apply_artifacts_to_repository(repo_path: str, artifacts: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply generated artifacts to the target repository.
    
    Args:
        repo_path: Path to the target repository
        artifacts: Dictionary containing the artifacts to write
    
    Returns:
        Dictionary with application results
    """
    try:
        # Import here to avoid module loading issues at startup
        orchestrator_path = project_root / "test_pfe" / "02-orchestration-agents-layer" / "orchestrator-agent"
        if str(orchestrator_path) not in sys.path:
            sys.path.insert(0, str(orchestrator_path))
        
        from src.artifact_writer import ArtifactWriter
        
        writer = ArtifactWriter(repo_path)
        result = writer.write_all_artifacts(artifacts, backup=True)
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "artifacts_written": [],
            "errors": [str(e)]
        }


def main():
    # Header
    st.markdown(
        '''
        <div class="hero-card">
            <div class="main-header">Multi-Agent DevOps Orchestrator</div>
            <div class="sub-header">AI-powered CI/CD, Docker, and Infrastructure-as-Code generation with planner-driven execution and validation loops.</div>
        </div>
        ''',
        unsafe_allow_html=True,
    )
    
    # Sidebar
    with st.sidebar:
        st.markdown('<span class="menu-badge">Menu</span>', unsafe_allow_html=True)
        ui_menu = st.radio(
            "Workspace Menu",
            ["Workspace", "Pipeline", "Logs"],
            key="ui_menu",
            label_visibility="collapsed",
        )

        st.markdown("---")
        st.markdown("## ⚙️ Configuration")
        
        # Environment check
        env_checks = check_environment()
        
        with st.expander("🔍 System Status", expanded=False):
            for component, status in env_checks.items():
                if status:
                    st.success(f"✅ {component}")
                else:
                    st.error(f"❌ {component}")
        
        st.markdown("---")
        
        # Mode selection
        mode = st.radio(
            "🎯 Input Mode",
            ["Natural Language Prompt", "GitHub Repository", "Local Repository Path"],
            help="Choose how you want to provide your project information"
        )
        
        st.markdown("---")
        
        # Advanced options
        with st.expander("⚙️ Advanced Options", expanded=False):
            create_pr = st.checkbox("Create Pull Request", value=False, help="Automatically create a PR with generated artifacts")
            
            if create_pr:
                branch_name = st.text_input("Branch Name", value="devops/auto-generated", help="Branch name for the PR")
                pr_title = st.text_input("PR Title", value="Auto-generated DevOps configurations")
                pr_body = st.text_area("PR Description", value="Generated by Multi-Agent DevOps Orchestrator")
            else:
                branch_name = ""
                pr_title = ""
                pr_body = ""
            
            output_scope = st.selectbox(
                "Output Scope",
                ["asked", "all"],
                help="Show only requested artifacts or all generated artifacts"
            )

            with st.expander("🔐 Runtime Secrets (Session Only)", expanded=False):
                st.caption(
                    "Used for validation/deploy steps (for example Docker Hub login in Act). "
                    "Secrets stay in this Streamlit session and are not written to files."
                )

                runtime_secret_values = st.session_state.get("runtime_secrets", {})
                if not isinstance(runtime_secret_values, dict):
                    runtime_secret_values = {}

                dockerhub_username_input = st.text_input(
                    "Docker Hub Username",
                    value=str(runtime_secret_values.get("DOCKERHUB_USERNAME", "") or ""),
                    key="secret_dockerhub_username",
                )
                dockerhub_token_input = st.text_input(
                    "Docker Hub Token",
                    value=str(runtime_secret_values.get("DOCKERHUB_TOKEN", "") or ""),
                    type="password",
                    key="secret_dockerhub_token",
                )
                sonar_token_input = st.text_input(
                    "Sonar Token",
                    value=str(runtime_secret_values.get("SONAR_TOKEN", "") or ""),
                    type="password",
                    key="secret_sonar_token",
                )
                sonar_host_input = st.text_input(
                    "Sonar Host URL",
                    value=str(runtime_secret_values.get("SONAR_HOST_URL", "") or ""),
                    key="secret_sonar_host_url",
                )
                additional_secret_lines = st.text_area(
                    "Additional Secrets (KEY=VALUE per line)",
                    key="runtime_secret_lines",
                    height=130,
                    placeholder="DOCKERHUB_USERNAME=my-user\nDOCKERHUB_TOKEN=your-token\nGHCR_TOKEN=...",
                )

                parsed_additional_secrets, secret_line_errors = _parse_runtime_secret_lines(additional_secret_lines)

                runtime_secrets: Dict[str, str] = {}
                if dockerhub_username_input.strip():
                    runtime_secrets["DOCKERHUB_USERNAME"] = dockerhub_username_input.strip()
                if dockerhub_token_input.strip():
                    runtime_secrets["DOCKERHUB_TOKEN"] = dockerhub_token_input.strip()
                if sonar_token_input.strip():
                    runtime_secrets["SONAR_TOKEN"] = sonar_token_input.strip()
                if sonar_host_input.strip():
                    runtime_secrets["SONAR_HOST_URL"] = sonar_host_input.strip()
                runtime_secrets.update(parsed_additional_secrets)

                st.session_state.runtime_secrets = runtime_secrets

                if secret_line_errors:
                    st.warning("Ignored invalid additional secret lines:\n- " + "\n- ".join(secret_line_errors[:4]))
                if runtime_secrets:
                    st.success(f"{len(runtime_secrets)} secret(s) configured for this session.")
                else:
                    st.info("No runtime secrets configured.")

            if ui_menu == "Logs":
                st.markdown("---")
                st.caption("Live command output stays in the Logs menu to keep the main workspace clean.")
        
        st.markdown("---")
        
        # Examples
        with st.expander("💡 Example Prompts", expanded=False):
            st.markdown("""
            **CI/CD Examples:**
            - "Create a CI/CD pipeline for my Python project"
            - "Generate a GitHub Actions workflow for Java/Spring Boot with Maven and SonarQube"
            - "Set up a Node.js test and build pipeline"
            
            **Docker Examples:**
            - "Create a Dockerfile for my Python Flask application"
            - "Generate a Docker configuration for Java Spring Boot"
            - "Build a multi-stage Dockerfile for Go application"
            
            **Infrastructure Examples:**
            - "Create Terraform configuration for AWS EC2 deployment"
            - "Generate Kubernetes manifests for my FastAPI app with ConfigMap, Secret, Ingress, and HPA"
            - "Create k8s deployment + service with service type NodePort and Traefik ingress"
            - "Use kubernetes/examples style baseline for a production-ready web API deployment"
            - "Apply kubeflow/manifests-inspired defaults for an ML inference service"
            - "Set up cloud infrastructure on Azure"
            
            **Combined:**
            - "Generate everything I need to deploy my Python project"
            - "Create complete DevOps setup for my microservice"
            - "Create Dockerfile, CI/CD workflow, and Kubernetes manifests for my Node.js API"
            - "I need k8s manifests with secure env handling, ingress host routing, and autoscaling"
            - "I need to set up automated deployment for my Streamlit application. I want the deployment process to be containerized and automatically triggered whenever I push changes to the main branch."            
            """)

    # Finalize background orchestrator task if it completed during a previous rerun.
    if _finalize_orchestrator_task_if_done():
        st.rerun()

    active_task = st.session_state.get("orchestrator_task")
    task_running = _is_orchestrator_task_running(active_task)

    # Handle the edge case where the process exits between reruns so UI state
    # transitions immediately without requiring extra user interaction.
    if isinstance(active_task, dict) and not task_running:
        if _finalize_orchestrator_task_if_done():
            st.rerun()
    
    # Main content area
    if not env_checks["Ollama"]:
        st.error("⚠️ Ollama is not running. Please start Ollama before using the orchestrator.")
        st.info("Start Ollama with: `ollama serve` or run the Ollama desktop app")
        return

    if task_running:
        started_at = float(active_task.get("started_at", time.time())) if isinstance(active_task, dict) else time.time()
        elapsed_s = max(0, int(time.time() - started_at))
        st.info(f"🔄 Orchestrator run in progress ({elapsed_s}s).")
        if st.button("🔄 Refresh Running Task", key="refresh_running_task", width="content"):
            st.rerun()
    
    # Input section
    st.markdown("## 📝 Request Input")
    
    user_prompt = ""
    repo_path = None
    github_url = None
    
    if mode == "Natural Language Prompt":
        user_prompt = st.text_area(
            "Enter your request",
            height=100,
            placeholder="Example: Create a CI/CD pipeline and Dockerfile for my Python Flask application",
            help="Describe what DevOps artifacts you need in natural language"
        )
    
    elif mode == "GitHub Repository":
        github_url = st.text_input(
            "GitHub Repository URL",
            placeholder="https://github.com/username/repository",
            help="Provide a GitHub repository URL to analyze"
        )
        user_prompt = st.text_input(
            "What would you like to generate?",
            placeholder="Example: Generate CI/CD pipeline and Dockerfile",
            help="Optional: Specify what artifacts you need"
        )
        if not user_prompt:
            user_prompt = "Generate complete DevOps configuration for this repository"
    
    elif mode == "Local Repository Path":
        repo_path = st.text_input(
            "Local Repository Path",
            placeholder="C:\\path\\to\\your\\project",
            help="Provide the absolute path to your local repository"
        )
        user_prompt = st.text_input(
            "What would you like to generate?",
            placeholder="Example: Generate CI/CD pipeline and Dockerfile",
            help="Optional: Specify what artifacts you need"
        )
        if not user_prompt:
            user_prompt = "Generate complete DevOps configuration for this repository"
    
    # Generate button
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        generate_button = st.button("🚀 Generate", type="primary", width="stretch")
    with col2:
        if st.button("🗑️ Clear", width="stretch"
        ):
            st.session_state.orchestration_result = None
            st.session_state.execution_history = []
            st.rerun()
    
    # Check if there's a pending plan awaiting approval
    if st.session_state.pending_plan and not st.session_state.plan_approved and not task_running:
        st.markdown("---")
        st.markdown("## 🧠 Execution Plan Approval")
        
        plan_data = st.session_state.pending_plan
        plan = plan_data.get("execution_plan", {})

        current_plan_source = _plan_to_paragraph(plan)
        if st.session_state.plan_editor_source != current_plan_source:
            st.session_state.plan_editor_text = current_plan_source
            st.session_state.plan_editor_source = current_plan_source
        
        st.info("**The orchestrator has created an execution plan. Please review and approve to proceed.**")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            complexity = plan_data.get("complexity_score", 0)
            st.metric("Complexity Score", f"{complexity}/10")
        with col2:
            st.metric("Planned Tasks", len(plan.get("tasks", [])))
        with col3:
            est_time = plan.get("estimated_time_sec", 0)
            st.metric("Est. Time", f"{est_time}s")
        
        # Show execution plan
        st.markdown("### 📋 Execution Plan")
        plan_paragraph = _plan_to_paragraph(plan)
        if plan_paragraph:
            st.write(plan_paragraph)
        else:
            st.caption("No execution steps available.")
        
        if plan_data.get("planner_reasoning"):
            with st.expander("💡 Planner Reasoning", expanded=False):
                st.text(plan_data["planner_reasoning"])

        st.markdown("### ✏️ Edit Plan (Paragraph)")
        st.caption("Use one step per line. Example: Step 1: docker-agent")
        st.caption("For parallel steps, write: Step 2: cicd-agent, iac-agent (parallel)")
        st.text_area(
            "Execution Plan (Text)",
            key="plan_editor_text",
            height=320,
            label_visibility="collapsed"
        )
        
        st.markdown("---")
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            if st.button("✅ Approve & Execute", type="primary", width="content"):
                try:
                    allowed_agents = _extract_allowed_agents(plan)
                    edited_execution_order = _paragraph_to_execution_order(
                        st.session_state.plan_editor_text,
                        allowed_agents,
                    )
                except ValueError as exc:
                    st.error(str(exc))
                    return

                edited_plan = dict(plan)
                edited_plan["execution_order"] = edited_execution_order
                st.session_state.pending_plan["execution_plan"] = edited_plan
                st.session_state.plan_approved = True
                st.rerun()
        with col2:
            if st.button("❌ Cancel",width="stretch"):
                st.session_state.pending_plan = None
                st.session_state.plan_approved = False
                st.session_state.plan_editor_text = ""
                st.session_state.plan_editor_source = ""
                st.rerun()
        
        return  # Stop here, don't show the normal form
    
    # If plan was approved, execute it
    if st.session_state.plan_approved and st.session_state.pending_plan:
        plan_data = st.session_state.pending_plan
        st.session_state.last_user_prompt = (plan_data.get("prompt") or "").strip()

        if task_running:
            st.info("🔄 Approved plan execution is already running in the background.")
            if ui_menu == "Logs":
                display_logs_center(None)
            return

        try:
            orchestrator_script = project_root / "test_pfe" / "02-orchestration-agents-layer" / "orchestrator-agent" / "run_orchestrator.py"
            cmd = [sys.executable, str(orchestrator_script)]
            cmd.extend(["--prompt", plan_data.get("prompt", "")])

            if plan_data.get("execution_plan"):
                cmd.extend(["--execute-plan", json.dumps(plan_data["execution_plan"])])
            else:
                cmd.append("--skip-planner")

            if plan_data.get("repo_path"):
                cmd.extend(["--repo-path", plan_data["repo_path"]])
            if plan_data.get("github_url"):
                cmd.extend(["--github-url", plan_data["github_url"]])

            create_pr_requested = bool(plan_data.get("create_pr", False))
            if create_pr_requested:
                branch_name = str(plan_data.get("branch_name", "") or "").strip() or "devops/auto-generated"
                pr_title = str(plan_data.get("pr_title", "") or "").strip() or "Auto-generated DevOps configurations"
                pr_body = str(plan_data.get("pr_body", "") or "").strip() or "Generated by Multi-Agent DevOps Orchestrator"
                cmd.append("--create-pr")
                cmd.extend(["--branch-name", branch_name])
                cmd.extend(["--pr-title", pr_title])
                cmd.extend(["--pr-body", pr_body])

            user_feedback_for_execution = "accept" if create_pr_requested else st.session_state.user_feedback_choice
            cmd.extend(["--user-feedback", user_feedback_for_execution])

            run_env = _apply_runtime_env_overrides(os.environ.copy())

            _start_orchestrator_background_task(
                cmd=cmd,
                cwd=str(orchestrator_script.parent),
                env=run_env,
                panel_title="Approved Plan Execution Logs",
                task_type="approved-plan",
                payload={"plan_data": plan_data},
            )

            st.info("✅ Approved plan started in background. ")
            st.rerun()

        except Exception as e:
            st.error(f"❌ Error starting approved plan execution: {str(e)}")
            st.exception(e)
            st.session_state.pending_plan = None
            st.session_state.plan_approved = False

        return

    # Human feedback stage after execution (new graph: user_feedback -> create_pr/cleanup)
    if st.session_state.feedback_stage and st.session_state.pending_feedback_result:
        st.markdown("---")
        st.markdown("## 💬 Human Feedback & Review")
        st.info("✅ Execution completed. Review generated artifacts below.")
        
        # Show repository path information
        repo_path_available = st.session_state.current_repo_path and Path(st.session_state.current_repo_path).exists()
        if repo_path_available:
            st.success(f"📁 Repository Path: `{st.session_state.current_repo_path}` - Ready to apply artifacts")
        else:
            st.warning("⚠️ No local repository path available. You can download artifacts but cannot apply them directly to a repository.")

        feedback_result = st.session_state.pending_feedback_result
        feedback_artifacts = extract_artifacts(feedback_result)

        # Apply pending editor updates before widget creation to avoid
        # Streamlit errors when mutating widget-owned keys post-instantiation.
        pending_yaml_update = st.session_state.pop("_pending_feedback_edit_yaml", None)
        if pending_yaml_update is not None:
            st.session_state["feedback_edit_yaml"] = pending_yaml_update

        pending_docker_update = st.session_state.pop("_pending_feedback_edit_dockerfile", None)
        if pending_docker_update is not None:
            st.session_state["feedback_edit_dockerfile"] = pending_docker_update

        # Display generated artifacts with proper formatting
        st.markdown("### 📋 Generated Artifacts")
        
        # Track if any artifacts exist
        has_artifacts = False
        
        # Prepare terraform data
        terraform_data = feedback_artifacts.get("terraform") if isinstance(feedback_artifacts.get("terraform"), dict) else {}
        
        # Show YAML if available
        if feedback_artifacts.get("yaml"):
            has_artifacts = True
            st.markdown("#### GitHub Actions Workflow (YAML)")
            st.code(feedback_artifacts.get("yaml"), language="yaml")
            with st.expander("✏️ Edit YAML"):
                edited_yaml = st.text_area(
                    "Edit GitHub Actions Workflow",
                    value=feedback_artifacts.get("yaml") or "",
                    height=220,
                    key="feedback_edit_yaml",
                    label_visibility="collapsed"
                )
        else:
            edited_yaml = ""
        
        # Show Dockerfile if available
        if feedback_artifacts.get("dockerfile"):
            has_artifacts = True
            st.markdown("#### Dockerfile")
            st.code(feedback_artifacts.get("dockerfile"), language="dockerfile")
            with st.expander("✏️ Edit Dockerfile"):
                edited_dockerfile = st.text_area(
                    "Edit Dockerfile",
                    value=feedback_artifacts.get("dockerfile") or "",
                    height=220,
                    key="feedback_edit_dockerfile",
                    label_visibility="collapsed"
                )
        else:
            edited_dockerfile = ""
        
        # Show Terraform files if available
        if terraform_data:
            has_artifacts = True
            st.markdown("#### Terraform HCL Scripts")
            
            # Create list of available terraform files
            tf_tabs = []
            if terraform_data.get("main_tf"):
                tf_tabs.append(("main.tf", "main_tf"))
            if terraform_data.get("variables_tf"):
                tf_tabs.append(("variables.tf", "variables_tf"))
            if terraform_data.get("outputs_tf"):
                tf_tabs.append(("outputs.tf", "outputs_tf"))
            if terraform_data.get("providers_tf"):
                tf_tabs.append(("providers.tf", "providers_tf"))
            
            if tf_tabs:
                # Display tabs
                tabs = st.tabs([name for name, _ in tf_tabs])
                for tab, (name, key) in zip(tabs, tf_tabs):
                    with tab:
                        st.code(terraform_data.get(key), language="hcl")
        
        # Set terraform edited values
        edited_main_tf = terraform_data.get("main_tf") or ""
        edited_variables_tf = terraform_data.get("variables_tf") or ""
        edited_outputs_tf = terraform_data.get("outputs_tf") or ""
        edited_providers_tf = terraform_data.get("providers_tf") or ""
        
        if not has_artifacts:
            st.warning("⚠️ No artifacts were generated. Please check the execution logs above.")
            edited_yaml = ""
            edited_dockerfile = ""
        
        # Validation section (optional execution)
        st.markdown("---")
        st.markdown("### 🔬 Validation (Optional)")
        st.info("💡 Validation chain: Dockerfile is repaired via docker-agent until build succeeds, then CI/CD workflow is repaired via cicd-agent until Act succeeds.")
        
        repo_path_to_use = st.session_state.current_repo_path
        github_url_from_result = None
        required_java_version = None
        
        # Check if we have a GitHub URL in the result
        result_data = st.session_state.pending_feedback_result
        if result_data and isinstance(result_data, dict):
            state_data = result_data.get("state", {})
            if isinstance(state_data, dict):
                repo_context = state_data.get("repo_context", {})
                if isinstance(repo_context, dict):
                    github_url_from_result = repo_context.get("github_url") or repo_context.get("path")
                    java_version_candidate = str(repo_context.get("java_version") or "").strip()
                    if java_version_candidate:
                        required_java_version = java_version_candidate

        # Prefer prebuilt image from orchestrator docker ReAct validation when available.
        prebuilt_image_name = ""
        if result_data and isinstance(result_data, dict):
            state_data = result_data.get("state", {})
            if isinstance(state_data, dict):
                agent_outputs = state_data.get("agent_outputs", {})
                if isinstance(agent_outputs, dict):
                    docker_output = agent_outputs.get("docker-agent", {})
                    docker_data = docker_output.get("data", {}) if isinstance(docker_output, dict) else {}
                    if isinstance(docker_data, dict):
                        react_validation = docker_data.get("react_validation", {})
                        if isinstance(react_validation, dict):
                            prebuilt_image_name = str(react_validation.get("final_image_name") or "").strip()
        if prebuilt_image_name:
            st.info(f"🐳 Using prebuilt Docker image from orchestrator validation: `{prebuilt_image_name}`")
        
        # Determine if validation is possible
        has_local_path = repo_path_to_use and Path(repo_path_to_use).exists()
        has_github_url = github_url_from_result and (github_url_from_result.startswith("http://") or github_url_from_result.startswith("https://"))
        
        if not has_local_path and not has_github_url:
            st.warning("⚠️ Repository path or GitHub URL required for validation. Validation disabled.")
            validation_button_disabled = True
        elif not has_local_path and has_github_url:
            st.info(f"ℹ️ GitHub URL detected: `{github_url_from_result}` - Will clone temporarily for validation")
            validation_button_disabled = False
        else:
            validation_button_disabled = False
        
        if st.button("🔬 Execute & Validate", width="stretch", disabled=validation_button_disabled, help="Repair Dockerfile until build succeeds, then run CI/CD workflow with Act"):
            with st.spinner("🔄 Executing validation... This may take several minutes."):
                temp_clone_dir = None
                try:
                    # If we don't have a local path but have a GitHub URL, clone it first
                    if not has_local_path and has_github_url:
                        clone_url = str(github_url_from_result or "").strip()
                        if not clone_url:
                            raise Exception("GitHub URL is missing for validation clone")

                        st.info(f"🔄 Cloning repository from {clone_url}...")
                        temp_clone_dir = tempfile.mkdtemp(prefix="repo_validation_")
                        
                        try:
                            clone_result = subprocess.run(
                                ["git", "clone", clone_url, temp_clone_dir],
                                capture_output=True,
                                text=True,
                                encoding="utf-8",
                                errors="replace",
                                timeout=600  # 10 minute timeout for clone
                            )
                            
                            if clone_result.returncode != 0:
                                st.error(f"❌ Failed to clone repository: {clone_result.stderr}")
                                raise Exception(f"Git clone failed: {clone_result.stderr}")
                            
                            repo_path_to_use = temp_clone_dir
                            st.success(f"✅ Repository cloned to temporary directory")
                            
                        except subprocess.TimeoutExpired:
                            st.error("❌ Repository clone timed out after 10 minutes")
                            raise Exception("Git clone timed out")
                        except FileNotFoundError:
                            st.error("❌ Git is not installed or not in PATH. Please install Git to clone repositories.")
                            raise Exception("Git not found")

                    effective_dockerfile = edited_dockerfile.strip() or ""
                    docker_repair_result = {
                        "status": "skipped",
                        "message": "No Dockerfile provided; skipped Docker build verification.",
                        "attempts": [],
                        "total_attempts": 0,
                    }

                    # Enforce docker-agent self-repair loop before Act execution.
                    if effective_dockerfile:
                        st.info("🐳 Verifying Dockerfile build and repairing through docker-agent if needed...")
                        docker_repair_result = _ensure_buildable_dockerfile_via_agent(
                            initial_dockerfile=effective_dockerfile,
                            user_prompt=st.session_state.get("last_user_prompt", ""),
                            repository_path=repo_path_to_use,
                            max_attempts=4,
                        )

                        if docker_repair_result.get("status") != "success":
                            st.error(f"❌ Docker validation failed: {docker_repair_result.get('message', 'Unknown Docker validation error')}")
                            with st.expander("🐳 Docker Repair Attempts", expanded=True):
                                attempts = docker_repair_result.get("attempts", [])
                                if attempts:
                                    for attempt in attempts:
                                        attempt_number = attempt.get("attempt", 0)
                                        build_result = attempt.get("build_result", {})
                                        build_data = build_result.get("docker_build", {}) if isinstance(build_result, dict) else {}
                                        st.markdown(f"**Attempt {attempt_number}**")
                                        st.caption(build_result.get("message", "Build failed"))
                                        log_lines = [
                                            entry.get("line", "")
                                            for entry in build_data.get("logs", [])
                                            if isinstance(entry, dict)
                                        ]
                                        if log_lines:
                                            if ui_menu == "Logs":
                                                st.code("\n".join(log_lines[-80:]), language="text")
                                            else:
                                                st.caption("Detailed Docker repair logs are available in the Logs menu.")
                                else:
                                    st.info("No Docker repair attempts recorded.")

                            exec_result = {
                                "status": "error",
                                "message": docker_repair_result.get("message", "Docker validation failed"),
                                "docker_repair": docker_repair_result,
                                "act": {"exit_code": -1, "timed_out": False, "logs": [], "success": False},
                            }
                            st.session_state.execution_result = exec_result
                        else:
                            repaired_dockerfile = docker_repair_result.get("dockerfile_content", effective_dockerfile)
                            if repaired_dockerfile.strip() != effective_dockerfile.strip():
                                st.warning("⚠️ Dockerfile was repaired by docker-agent to reach a buildable image.")
                                edited_dockerfile = repaired_dockerfile
                                st.session_state["_pending_feedback_edit_dockerfile"] = repaired_dockerfile
                            else:
                                st.success("✅ Docker image build verified successfully.")

                    if docker_repair_result.get("status") != "error":
                        # Import execution agent
                        exec_agent_path = project_root / "test_pfe" / "02-orchestration-agents-layer" / "execution-sandbox"
                        if str(exec_agent_path) not in sys.path:
                            sys.path.insert(0, str(exec_agent_path))
                        
                        from pipeline import run_execution  # pyright: ignore[reportMissingImports]

                        effective_yaml = edited_yaml.strip() or ""
                        cicd_repair_result = {
                            "status": "skipped",
                            "message": "No CI/CD workflow provided; skipped Act validation.",
                            "attempts": [],
                            "total_attempts": 0,
                        }

                        if not effective_yaml:
                            cicd_repair_result = {
                                "status": "error",
                                "message": "CI/CD workflow is empty; cannot validate with Act.",
                                "attempts": [],
                                "total_attempts": 0,
                            }
                            exec_result = {
                                "status": "error",
                                "message": cicd_repair_result["message"],
                                "act": {"exit_code": -1, "timed_out": False, "logs": [], "success": False},
                            }
                        else:
                            st.info("⚡ Verifying CI/CD workflow with Act and repairing through cicd-agent if needed...")
                            cicd_repair_result = _ensure_executable_cicd_workflow_via_agent(
                                initial_workflow=effective_yaml,
                                dockerfile_content=edited_dockerfile.strip() or "",
                                prebuilt_image_name=prebuilt_image_name,
                                user_prompt=st.session_state.get("last_user_prompt", ""),
                                repository_path=repo_path_to_use,
                                run_execution_fn=run_execution,
                                max_attempts=4,
                                act_timeout=int(os.environ.get("EXECUTION_ACT_TIMEOUT", 1800)),
                                runtime_secrets=_collect_runtime_secrets(),
                                required_java_version=required_java_version,
                            )

                            if cicd_repair_result.get("status") != "success":
                                st.error(f"❌ CI/CD validation failed: {cicd_repair_result.get('message', 'Unknown CI/CD validation error')}")
                                with st.expander("⚡ CI/CD Repair Attempts", expanded=True):
                                    attempts = cicd_repair_result.get("attempts", [])
                                    if attempts:
                                        for attempt in attempts:
                                            attempt_number = attempt.get("attempt", 0)
                                            execution_attempt = attempt.get("execution_result", {})
                                            act_attempt = execution_attempt.get("act", {}) if isinstance(execution_attempt, dict) else {}
                                            st.markdown(f"**Attempt {attempt_number}**")
                                            st.caption(execution_attempt.get("message", "Act execution failed"))
                                            log_lines = [
                                                entry.get("line", "")
                                                for entry in act_attempt.get("logs", [])
                                                if isinstance(entry, dict)
                                            ]
                                            if log_lines:
                                                if ui_menu == "Logs":
                                                    st.code("\n".join(log_lines[-100:]), language="text")
                                                else:
                                                    st.caption("Detailed CI/CD repair logs are available in the Logs menu.")
                                    else:
                                        st.info("No CI/CD repair attempts recorded.")

                                exec_result = cicd_repair_result.get("execution_result") or {
                                    "status": "error",
                                    "message": cicd_repair_result.get("message", "CI/CD validation failed before final Act execution."),
                                    "act": {"exit_code": -1, "timed_out": False, "logs": [], "success": False},
                                }
                            else:
                                repaired_yaml = cicd_repair_result.get("workflow_yaml", effective_yaml)
                                if repaired_yaml.strip() != effective_yaml.strip():
                                    st.warning("⚠️ CI/CD workflow was repaired by cicd-agent to reach a passing Act execution.")
                                    edited_yaml = repaired_yaml
                                    st.session_state["_pending_feedback_edit_yaml"] = repaired_yaml
                                else:
                                    st.success("✅ CI/CD workflow validated successfully with Act.")

                                exec_result = cicd_repair_result.get("execution_result") or {
                                    "status": "success",
                                    "message": "CI/CD workflow validated successfully with Act.",
                                    "act": {"exit_code": 0, "timed_out": False, "logs": [], "success": True},
                                }

                        exec_result["docker_repair"] = docker_repair_result
                        exec_result["cicd_repair"] = cicd_repair_result
                    else:
                        exec_result = st.session_state.execution_result or {
                            "status": "error",
                            "message": "Docker validation failed before Act execution.",
                            "docker_repair": docker_repair_result,
                            "cicd_repair": {
                                "status": "skipped",
                                "message": "Skipped because Docker validation failed.",
                                "attempts": [],
                            },
                            "act": {"exit_code": -1, "timed_out": False, "logs": [], "success": False},
                        }
                    
                    # Store result
                    st.session_state.execution_result = exec_result
                    
                    # Display results
                    if exec_result["status"] == "success":
                        st.success("✅ Validation completed successfully! Docker image is buildable and CI/CD workflow executed with Act without errors.")
                        display_act_pipeline(exec_result, expanded=True)
                        
                        with st.expander("📊 Validation Details", expanded=True):
                            docker_repair = exec_result.get("docker_repair", {})
                            if docker_repair and docker_repair.get("status") != "skipped":
                                st.markdown("**🐳 Docker Repair Loop**")
                                st.metric("Attempts", docker_repair.get("total_attempts", len(docker_repair.get("attempts", []))))
                                st.metric("Status", "✅ Build Verified" if docker_repair.get("status") == "success" else "❌ Failed")

                            cicd_repair = exec_result.get("cicd_repair", {})
                            if cicd_repair and cicd_repair.get("status") != "skipped":
                                st.markdown("**⚡ CI/CD Repair Loop**")
                                st.metric("Attempts", cicd_repair.get("total_attempts", len(cicd_repair.get("attempts", []))))
                                st.metric("Status", "✅ Act Verified" if cicd_repair.get("status") == "success" else "❌ Failed")

                            act_result = exec_result.get("act", {})
                            st.markdown("**⚡ Act Workflow**")
                            st.metric("Exit Code", act_result.get("exit_code", "N/A"))
                            st.metric("Status", "✅ Success" if act_result.get("success") else "❌ Failed")
                            if act_result.get("timed_out"):
                                st.warning("⏱️ Timed out")
                            
                            # Show workspace info
                            st.caption(f"Workspace: `{exec_result.get('workspace', 'N/A')}`")

                            if ui_menu == "Logs":
                                with st.expander("⚡ Act Execution Logs (last 50 lines)"):
                                    act_logs = [log.get("line", "") for log in act_result.get("logs", []) if isinstance(log, dict)]
                                    if act_logs:
                                        st.code("\n".join(act_logs[-50:]), language="text")
                                    else:
                                        st.info("No logs available")
                            else:
                                st.caption("Open the Logs menu for full Act execution logs.")

                    else:
                        st.error(f"❌ Validation failed: {exec_result.get('message', 'Unknown error')}")
                        display_act_pipeline(exec_result, expanded=True)
                        
                        with st.expander("🔍 Error Details", expanded=True):
                            docker_repair = exec_result.get("docker_repair", {})
                            if docker_repair and docker_repair.get("status") != "skipped":
                                st.markdown("**🐳 Docker Repair Loop**")
                                st.metric("Attempts", docker_repair.get("total_attempts", len(docker_repair.get("attempts", []))))
                                st.metric("Status", "✅ Build Verified" if docker_repair.get("status") == "success" else "❌ Failed")

                            cicd_repair = exec_result.get("cicd_repair", {})
                            if cicd_repair and cicd_repair.get("status") != "skipped":
                                st.markdown("**⚡ CI/CD Repair Loop**")
                                st.metric("Attempts", cicd_repair.get("total_attempts", len(cicd_repair.get("attempts", []))))
                                st.metric("Status", "✅ Act Verified" if cicd_repair.get("status") == "success" else "❌ Failed")

                            act_result = exec_result.get("act", {})

                            st.markdown("**⚡ Act Workflow**")
                            st.metric("Exit Code", act_result.get("exit_code", "N/A"))
                            st.metric("Success", "✅" if act_result.get("success") else "❌")

                            if ui_menu == "Logs":
                                with st.expander("⚡ Act Execution Logs"):
                                    act_logs = [log.get("line", "") for log in act_result.get("logs", []) if isinstance(log, dict)]
                                    if act_logs:
                                        st.code("\n".join(act_logs[-100:]), language="text")
                                    else:
                                        st.info("No logs available")
                            else:
                                st.caption("Open the Logs menu for full Act execution logs.")

                            
                            # Show full result for debugging
                            with st.expander("📋 Full Execution Result (Debug)"):
                                st.json(_json_safe(exec_result))
                
                except ImportError as e:
                    st.error(f"❌ Failed to import execution agent: {str(e)}")
                    st.info("Make sure the execution-sandbox directory structure is set up correctly. Run create_structure.bat if needed.")
                except Exception as e:
                    st.error(f"❌ Validation failed with exception: {str(e)}")
                    st.exception(e)
                finally:
                    if temp_clone_dir and Path(temp_clone_dir).exists():
                        st.info("🧹 Cleaning up temporary clone directory...")
                        shutil.rmtree(temp_clone_dir, ignore_errors=True)

        st.markdown("---")
        st.markdown("### 🎯 Action Options")
        
        # Check if repo path is available
        repo_path_available = st.session_state.current_repo_path and Path(st.session_state.current_repo_path).exists()
        
        # Check if we have GitHub URL but no local path
        has_github_only = (not repo_path_available) and github_url_from_result and (github_url_from_result.startswith("http://") or github_url_from_result.startswith("https://"))
        
        if has_github_only:
            st.info(f"ℹ️ **GitHub URL Mode**: Repository is on GitHub (`{github_url_from_result}`). You can download artifacts or clone the repo locally to apply them.")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            apply_button_disabled = not repo_path_available
            apply_button_help = "Save artifacts to your repository" if repo_path_available else "Clone the repository locally first to apply artifacts"
            
            if st.button(
                "✅ Accept & Apply to Repository", 
                type="primary", 
                width="stretch",
                help=apply_button_help,
                disabled=apply_button_disabled
            ):
                # Check if we have a valid repository path
                repo_path_to_use = st.session_state.current_repo_path
                if not repo_path_to_use or not Path(repo_path_to_use).exists():
                    st.error("⚠️ No valid repository path available. Please clone the repository locally first.")
                    if has_github_only:
                        st.code(f"git clone {github_url_from_result}", language="bash")
                else:
                    st.session_state.user_feedback_choice = "accept"
                    edited_artifacts = {
                        "yaml": edited_yaml.strip() or None,
                        "dockerfile": edited_dockerfile.strip() or None,
                        "terraform": {
                            "main_tf": edited_main_tf.strip(),
                            "variables_tf": edited_variables_tf.strip(),
                            "outputs_tf": edited_outputs_tf.strip(),
                            "providers_tf": edited_providers_tf.strip(),
                        },
                        "metadata": feedback_artifacts.get("metadata", {}),
                    }
                    st.session_state.feedback_edits = edited_artifacts
                    
                    # Apply artifacts to repository
                    with st.spinner("🔄 Applying artifacts to repository..."):
                        apply_result = apply_artifacts_to_repository(repo_path_to_use, edited_artifacts)
                        st.session_state.apply_result = apply_result
                        st.session_state.artifacts_applied = True
                    
                    st.session_state.orchestration_result = _apply_feedback_edits_to_result(feedback_result, edited_artifacts)
                    st.session_state.feedback_stage = False
                    st.session_state.pending_feedback_result = None
                    st.rerun()
        
        with col2:
            if st.button("📥 Accept (Download Only)", width="stretch", help="Accept without writing to repository"):
                st.session_state.user_feedback_choice = "accept"
                edited_artifacts = {
                    "yaml": edited_yaml.strip() or None,
                    "dockerfile": edited_dockerfile.strip() or None,
                    "terraform": {
                        "main_tf": edited_main_tf.strip(),
                        "variables_tf": edited_variables_tf.strip(),
                        "outputs_tf": edited_outputs_tf.strip(),
                        "providers_tf": edited_providers_tf.strip(),
                    },
                    "metadata": feedback_artifacts.get("metadata", {}),
                }
                st.session_state.feedback_edits = edited_artifacts
                st.session_state.orchestration_result = _apply_feedback_edits_to_result(feedback_result, edited_artifacts)
                st.session_state.feedback_stage = False
                st.session_state.pending_feedback_result = None
                st.session_state.artifacts_applied = False  # Not applied
                st.rerun()
        
        with col3:
            if st.button("❌ Reject", width="stretch", help="Reject the generated artifacts"):
                st.session_state.user_feedback_choice = "not"
                edited_artifacts = {
                    "yaml": edited_yaml.strip() or None,
                    "dockerfile": edited_dockerfile.strip() or None,
                    "terraform": {
                        "main_tf": edited_main_tf.strip(),
                        "variables_tf": edited_variables_tf.strip(),
                        "outputs_tf": edited_outputs_tf.strip(),
                        "providers_tf": edited_providers_tf.strip(),
                    },
                    "metadata": feedback_artifacts.get("metadata", {}),
                }
                st.session_state.feedback_edits = edited_artifacts
                feedback_result["user_feedback"] = "not"
                st.session_state.orchestration_result = _apply_feedback_edits_to_result(feedback_result, edited_artifacts)
                st.session_state.feedback_stage = False
                st.session_state.pending_feedback_result = None
                st.session_state.artifacts_applied = False  # Not applied
                st.warning("Feedback marked as 'not'. PR creation path is skipped.")
                st.rerun()

        return
    
    # Process request
    if generate_button:
        if task_running:
            st.warning("An orchestrator run is already in progress. Wait for it to finish before starting a new one.")
            return

        if not user_prompt.strip():
            st.error("Please provide a prompt or request description.")
            return

        st.session_state.last_user_prompt = user_prompt.strip()

        try:
            orchestrator_script = project_root / "test_pfe" / "02-orchestration-agents-layer" / "orchestrator-agent" / "run_orchestrator.py"

            if not orchestrator_script.exists():
                st.error(f"❌ Orchestrator script not found: {orchestrator_script}")
                return

            cmd = [sys.executable, str(orchestrator_script)]
            cmd.extend(["--prompt", user_prompt])
            cmd.append("--plan-only")

            if repo_path:
                cmd.extend(["--repo-path", str(repo_path)])
                st.session_state.current_repo_path = str(repo_path)
            else:
                st.session_state.current_repo_path = None

            if github_url:
                cmd.extend(["--github-url", github_url])
            if 'output_scope' in locals():
                cmd.extend(["--output-scope", output_scope])
            cmd.extend(["--user-feedback", st.session_state.user_feedback_choice])

            run_env = _apply_runtime_env_overrides(os.environ.copy())

            _start_orchestrator_background_task(
                cmd=cmd,
                cwd=str(orchestrator_script.parent),
                env=run_env,
                panel_title="Orchestrator Runtime Logs",
                task_type="plan-only",
                payload={
                    "user_prompt": user_prompt,
                    "repo_path": repo_path,
                    "github_url": github_url,
                    "create_pr": bool(create_pr),
                    "branch_name": str(branch_name or "").strip(),
                    "pr_title": str(pr_title or "").strip(),
                    "pr_body": str(pr_body or "").strip(),
                },
            )

            st.info("🔄 Orchestrator started in background. Switch between Workspace, Pipeline, and Logs without interrupting it.")
            st.rerun()

        except Exception as e:
            st.error(f"❌ Error starting orchestration: {str(e)}")
            st.exception(e)
            return
    
    # Display results
    if st.session_state.orchestration_result:
        result = st.session_state.orchestration_result
        
        st.markdown("---")
        st.markdown("## 📊 Orchestration Results")
        
        # Display artifacts application status if applicable
        if st.session_state.artifacts_applied and st.session_state.apply_result:
            apply_result = st.session_state.apply_result
            if apply_result.get("success"):
                st.success(f"✅ **Artifacts Applied Successfully** - {len(apply_result.get('artifacts_written', []))} artifact(s) written to repository")
                
                # Show details of what was written
                with st.expander("📝 Application Details", expanded=True):
                    for artifact_name in apply_result.get("artifacts_written", []):
                        st.markdown(f"✅ **{artifact_name}** - Applied")
                    
                    # Show file paths
                    if apply_result.get("dockerfile"):
                        df_info = apply_result["dockerfile"]
                        st.markdown(f"**Dockerfile:** `{df_info.get('path')}`")
                        if df_info.get("backup_path"):
                            st.caption(f"  Backup created: `{df_info.get('backup_path')}`")
                    
                    if apply_result.get("cicd_workflow"):
                        wf_info = apply_result["cicd_workflow"]
                        st.markdown(f"**CI/CD Workflow:** `{wf_info.get('path')}`")
                        if wf_info.get("backup_path"):
                            st.caption(f"  Backup created: `{wf_info.get('backup_path')}`")
                    
                    if apply_result.get("terraform"):
                        tf_info = apply_result["terraform"]
                        st.markdown(f"**Terraform:** `{tf_info.get('terraform_dir')}`")
                        for file_key, file_info in tf_info.get("files", {}).items():
                            if file_info.get("success"):
                                st.caption(f"  ✅ {Path(file_info.get('path')).name}")
            else:
                st.error("❌ **Failed to Apply Artifacts**")
                for error in apply_result.get("errors", []):
                    st.error(f"  • {error}")
        
        # Display execution/validation status if applicable
        if st.session_state.execution_result:
            exec_result = st.session_state.execution_result
            if exec_result.get("status") == "success":
                st.success("✅ **Validation Completed Successfully** - Docker image build verified and CI/CD workflow executed with Act without errors")
                
                with st.expander("🔬 Validation Summary", expanded=False):
                    col1, col2, col3 = st.columns(3)

                    with col1:
                        docker_repair = exec_result.get("docker_repair", {})
                        st.markdown("**🐳 Docker Repair**")
                        if docker_repair and docker_repair.get("status") != "skipped":
                            st.metric("Attempts", docker_repair.get("total_attempts", len(docker_repair.get("attempts", []))))
                            if docker_repair.get("status") == "success":
                                st.success("✅ Build Verified")
                            else:
                                st.error("❌ Build Failed")
                        else:
                            st.caption("No Dockerfile validation performed.")

                    with col2:
                        cicd_repair = exec_result.get("cicd_repair", {})
                        st.markdown("**⚡ CI/CD Repair**")
                        if cicd_repair and cicd_repair.get("status") != "skipped":
                            st.metric("Attempts", cicd_repair.get("total_attempts", len(cicd_repair.get("attempts", []))))
                            if cicd_repair.get("status") == "success":
                                st.success("✅ Act Verified")
                            else:
                                st.error("❌ Repair Failed")
                        else:
                            st.caption("No CI/CD repair loop performed.")

                    with col3:
                        act_result = exec_result.get("act", {})
                        st.markdown("**⚡ Act Workflow**")
                        st.metric("Exit Code", act_result.get("exit_code", "N/A"))
                        if act_result.get("success"):
                            st.success("✅ Success")
                        else:
                            st.error("❌ Failed")

                    st.markdown("**📁 Workspace**")
                    st.caption(f"`{exec_result.get('workspace', 'N/A')}`")

                display_act_pipeline(exec_result, expanded=False)
            else:
                st.warning(f"⚠️ **Validation Failed** - {exec_result.get('message', 'Unknown error')}")
                with st.expander("🔍 Validation Error Details"):
                    st.json(_json_safe(exec_result))

                display_act_pipeline(exec_result, expanded=True)
        
        # Display planner usage indicator
        if result.get("used_planner"):
            st.info("🧠 **Strategic Planner Used** - This complex request required intelligent planning")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                complexity = result.get("complexity_score", 0)
                st.metric("Complexity Score", f"{complexity}/10")
            with col2:
                if "execution_plan" in result:
                    plan = result["execution_plan"]
                    st.metric("Planned Tasks", len(plan.get("tasks", [])))
                else:
                    st.metric("Planned Tasks", "N/A")
            with col3:
                if "execution_plan" in result:
                    plan = result["execution_plan"]
                    est_time = plan.get("estimated_time_sec", 0)
                    st.metric("Est. Time", f"{est_time}s")
                else:
                    st.metric("Est. Time", "N/A")
            
            # Show execution plan details
            if "execution_plan" in result:
                with st.expander("📋 View Execution Plan", expanded=False):
                    plan = result["execution_plan"]
                    
                    st.markdown("**Planned Execution Order (Paragraph):**")
                    plan_paragraph = _plan_to_paragraph(plan)
                    if plan_paragraph:
                        st.write(plan_paragraph)
                    else:
                        st.caption("No execution steps available.")
                    
                    if result.get("planner_reasoning"):
                        st.markdown("---")
                        st.markdown("**Planner Reasoning:**")
                        st.text(result["planner_reasoning"])
                    
                    st.markdown("---")
                    st.markdown("**Full Plan:**")
                    st.json(plan)
        else:
            complexity = result.get("complexity_score", 0)
            st.success(f"⚡ **Direct Execution** - Simple request routed directly to agents (complexity: {complexity})")
        
        st.markdown("---")
        
        # Status overview
        status = result.get("status", "unknown")
        if status == "completed":
            st.markdown('<div class="success-box">✅ Orchestration completed successfully</div>', unsafe_allow_html=True)
        elif status == "blocked":
            st.markdown('<div class="error-box">🚫 Orchestration blocked by guardrails</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="warning-box">⚠️ Orchestration status: {}</div>'.format(status), unsafe_allow_html=True)
        
        st.markdown("")

        artifacts = result.get("edited_artifacts") if isinstance(result.get("edited_artifacts"), dict) else extract_artifacts(result)

        # DEBUG: Show more context
        k8s_data = artifacts.get("kubernetes")
        k8s_keys = "None" if not k8s_data else "dict" if isinstance(k8s_data, dict) else type(k8s_data).__name__
        st.caption(f"DEBUG: status={status}, ui_menu={ui_menu}, k8s={k8s_keys}")

        if ui_menu == "Logs":
            display_logs_center(result)
        else:
            # Agent status
            display_agent_status(result)

            # Local docker/act execution details (metrics always, raw logs only in Logs menu)
            display_pipeline_execution(result, show_logs=False)

            st.markdown("")

            # CI/CD pipeline board (GitHub Actions style)
            workflow_yaml = _resolve_pipeline_workflow_yaml(artifacts, result)
            if ui_menu == "Pipeline":
                display_workflow_pipeline(
                    workflow_yaml=workflow_yaml,
                    execution_result=st.session_state.execution_result,
                    orchestration_result=result,
                    title="Delivery Pipeline",
                )

            if ui_menu == "Workspace" and status == "completed":
                st.write("DEBUG: calling display_artifacts with k8s =", "kubernetes" in artifacts)
                display_artifacts(artifacts)
            elif ui_menu == "Pipeline":
                st.info("Pipeline view is focused on execution flow. Switch to Workspace from the menu to edit or download artifacts.")

            # Errors
            state = result.get("state", {})
            errors = state.get("errors", [])
            if errors:
                st.markdown("### ⚠️ Errors")
                for error in errors:
                    st.error(error)
    elif ui_menu == "Logs":
        st.markdown("---")
        display_logs_center(None)
    elif ui_menu == "Pipeline":
        st.markdown("---")
        st.info("Run a generation request to render your exact workflow graph. Showing a professional preview layout below.")
        display_workflow_pipeline(
            workflow_yaml=None,
            execution_result=st.session_state.execution_result,
            orchestration_result=st.session_state.orchestration_result,
            title="Pipeline Preview",
        )
    
    # Execution history
    if st.session_state.execution_history:
        st.markdown("---")
        st.markdown("## 📜 Execution History")
        
        for idx, entry in enumerate(reversed(st.session_state.execution_history[-5:])):  # Show last 5
            with st.expander(f"{entry['timestamp']} - {entry['status']}", expanded=False):
                st.write(f"**Prompt:** {entry['prompt']}")
                st.write(f"**Status:** {entry['status']}")
                st.write(f"**Duration:** {entry['elapsed_time']:.2f}s")


if __name__ == "__main__":
    main()
