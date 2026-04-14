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
from typing import Dict, Any, Optional, List, Set
import tempfile
import shutil
import subprocess

# Load environment variables from .env file
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent

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

sys.path.insert(0, str(project_root / "test_pfe" / "02-orchestration-agents-layer" / "orchestrator-agent"))
sys.path.insert(0, str(project_root / "test_pfe" / "02-orchestration-agents-layer" / "cicd-agent"))
sys.path.insert(0, str(project_root / "test_pfe" / "02-orchestration-agents-layer" / "docker-agent"))

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
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    .agent-box {
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid;
        margin: 0.5rem 0;
    }
    .cicd-box {
        border-left-color: #4CAF50;
        background-color: #f1f8f4;
    }
    .docker-box {
        border-left-color: #2196F3;
        background-color: #e3f2fd;
    }
    .iac-box {
        border-left-color: #FF9800;
        background-color: #fff3e0;
    }
    .success-box {
        padding: 1rem;
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 0.25rem;
        color: #155724;
    }
    .error-box {
        padding: 1rem;
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        border-radius: 0.25rem;
        color: #721c24;
    }
    .warning-box {
        padding: 1rem;
        background-color: #fff3cd;
        border: 1px solid #ffeaa7;
        border-radius: 0.25rem;
        color: #856404;
    }
    .code-output {
        background-color: #f8f9fa;
        border: 1px solid #dee2e6;
        border-radius: 0.25rem;
        padding: 1rem;
        font-family: 'Courier New', monospace;
        white-space: pre-wrap;
        word-wrap: break-word;
    }
    .metric-card {
        background-color: white;
        padding: 1rem;
        border-radius: 0.5rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        text-align: center;
    }
    .pipeline-row {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
        align-items: stretch;
        margin: 0.5rem 0 1rem 0;
    }
    .pipeline-step {
        min-width: 200px;
        max-width: 280px;
        padding: 0.75rem;
        border-radius: 0.5rem;
        border-left: 5px solid #9E9E9E;
        background: #fafafa;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
    }
    .pipeline-step.pass {
        border-left-color: #2e7d32;
        background: #f1f8f4;
    }
    .pipeline-step.fail {
        border-left-color: #c62828;
        background: #ffebee;
    }
    .pipeline-step.running {
        border-left-color: #ef6c00;
        background: #fff3e0;
    }
    .pipeline-step-title {
        font-weight: 700;
        font-size: 0.95rem;
        margin-bottom: 0.35rem;
    }
    .pipeline-step-subtitle {
        font-size: 0.85rem;
        color: #424242;
    }
    .pipeline-arrow {
        font-size: 1.2rem;
        color: #90a4ae;
        align-self: center;
        padding: 0 0.1rem;
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


def check_environment() -> Dict[str, bool]:
    """Check if required environment variables and dependencies are configured"""
    # Check if Ollama is running
    ollama_running = False
    try:
        import requests
        response = requests.get("http://localhost:11434", timeout=2)
        ollama_running = response.status_code == 200 and "ollama is running" in response.text.lower()
    except:
        ollama_running = False
    
    checks = {
        "Ollama": ollama_running,
        "Orchestrator": True,
        "CI/CD Agent": True,
        "Docker Agent": True,
        "IaC Agent": True
    }
    
    try:
        from src.orchestrator import Orchestrator
        checks["Orchestrator"] = True
    except Exception:
        pass
    
    try:
        sys.path.insert(0, str(project_root / "test_pfe" / "02-orchestration-agents-layer" / "cicd-agent"))
        from src.pipeline import CICDPipeline
        checks["CI/CD Agent"] = True
    except Exception:
        pass
    
    try:
        sys.path.insert(0, str(project_root / "test_pfe" / "02-orchestration-agents-layer" / "docker-agent"))
        from src.pipeline import DockerPipeline
        checks["Docker Agent"] = True
    except Exception:
        pass
    
    return checks


def extract_artifacts(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract artifacts from orchestrator result.
    Handles both JSON response format and console output parsing.
    """
    artifacts = {
        "yaml": None,
        "dockerfile": None,
        "terraform": None,
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
) -> Dict[str, Any]:
    """Run orchestrator command while streaming combined stdout/stderr in the UI."""
    log_panel = st.expander(f"🖥️ {panel_title}", expanded=True)
    live_log = log_panel.empty()
    output_lines = []
    ui_render_enabled = True
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
        if not ui_render_enabled:
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
            _render_logs()

    _render_logs(force=True)

    return_code = process.wait()
    stdout_text = "\n".join(output_lines)

    try:
        if return_code == 0:
            log_panel.caption("Command completed successfully.")
        else:
            log_panel.caption(f"Command failed with exit code {return_code}.")
    except Exception:
        pass

    return {
        "returncode": return_code,
        "stdout": stdout_text,
        "stderr": "",
    }


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


def display_pipeline_execution(result: Dict[str, Any]):
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
                if isinstance(logs, list) and logs:
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


def _json_safe(value: Any, seen: set = None) -> Any:
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


def display_artifacts(artifacts: Dict[str, Any]):
    """Display generated artifacts"""
    st.markdown("### 📦 Generated Artifacts")
    
    tabs = st.tabs(["GitHub Actions Workflow", "Dockerfile", "Terraform/IaC", "Metadata"])
    
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
    
    # Metadata Tab
    with tabs[3]:
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

    run_env = os.environ.copy()
    run_env["PYTHONPATH"] = str(docker_agent_root) + os.pathsep + run_env.get("PYTHONPATH", "")
    run_env["PYTHONIOENCODING"] = "utf-8"

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

    run_env = os.environ.copy()
    run_env["PYTHONPATH"] = str(cicd_agent_root) + os.pathsep + run_env.get("PYTHONPATH", "")
    run_env["PYTHONIOENCODING"] = "utf-8"

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
    user_prompt: str,
    repository_path: str,
    run_execution_fn,
    max_attempts: int = 4,
    act_timeout: int = 600,
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

    attempts: List[Dict[str, Any]] = []
    prompt_seed = (user_prompt or "Generate a valid GitHub Actions workflow").strip()
    repo_context = {
        "is_available": True,
        "source": "local",
        "path": repository_path,
    }

    for attempt in range(1, max_attempts + 1):
        execution_result = run_execution_fn(
            dockerfile_content="",
            cicd_workflow_content=current_workflow,
            repository_path=repository_path,
            act_timeout=act_timeout,
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
        repair_prompt = (
            f"{prompt_seed}\n\n"
            "The GitHub Actions workflow below fails when executed with `act`.\n"
            "Regenerate a corrected workflow YAML so Act passes successfully.\n"
            "Keep it production-ready and executable.\n\n"
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
    st.markdown('<div class="main-header">🤖 Multi-Agent DevOps Orchestrator</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">AI-Powered CI/CD, Docker, and Infrastructure as Code Generation</div>', unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
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
            - "Generate IaC for a Kubernetes cluster"
            - "Set up cloud infrastructure on Azure"
            
            **Combined:**
            - "Generate everything I need to deploy my Python project"
            - "Create complete DevOps setup for my microservice"
            - "I need to set up automated deployment for my Streamlit application. I want the deployment process to be containerized and automatically triggered whenever I push changes to the main branch."            
            """)
    
    # Main content area
    if not env_checks["Ollama"]:
        st.error("⚠️ Ollama is not running. Please start Ollama before using the orchestrator.")
        st.info("Start Ollama with: `ollama serve` or run the Ollama desktop app")
        return
    
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
        generate_button = st.button("🚀 Generate", type="primary", use_container_width=True)
    with col2:
        if st.button("🗑️ Clear", use_container_width=True):
            st.session_state.orchestration_result = None
            st.session_state.execution_history = []
            st.rerun()
    
    # Check if there's a pending plan awaiting approval
    if st.session_state.pending_plan and not st.session_state.plan_approved:
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
            if st.button("✅ Approve & Execute", type="primary", use_container_width=True):
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
            if st.button("❌ Cancel", use_container_width=True):
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
        
        with st.spinner("🔄 Executing approved plan..."):
            try:
                # Progress tracking
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                status_text.text("Executing agents...")
                progress_bar.progress(30)
                
                # Build command with execution plan
                orchestrator_script = project_root / "test_pfe" / "02-orchestration-agents-layer" / "orchestrator-agent" / "run_orchestrator.py"
                
                cmd = [sys.executable, str(orchestrator_script)]
                cmd.extend(["--prompt", plan_data.get("prompt", "")])
                
                # Pass the approved execution plan
                if plan_data.get("execution_plan"):
                    cmd.extend(["--execute-plan", json.dumps(plan_data["execution_plan"])])
                else:
                    cmd.append("--skip-planner")  # Fallback if no plan
                
                if plan_data.get("repo_path"):
                    cmd.extend(["--repo-path", plan_data["repo_path"]])
                if plan_data.get("github_url"):
                    cmd.extend(["--github-url", plan_data["github_url"]])
                cmd.extend(["--user-feedback", st.session_state.user_feedback_choice])
                
                # Execute orchestrator
                start_time = time.time()
                run_env = os.environ.copy()
                run_env["PYTHONIOENCODING"] = "utf-8"
                
                # Ensure LLM configuration is propagated to subprocess
                llm_env_vars = [
                    "LLM_PROVIDER", "USE_LLM", 
                    "OLLAMA_MODEL", 
                    "GROQ_API_KEY", "GROQ_MODEL", "GROQ_FALLBACK_MODEL"
                ]
                for var in llm_env_vars:
                    env_value = os.getenv(var)
                    if var not in run_env and env_value is not None:
                        run_env[var] = env_value
                
                run_result = run_orchestrator_command_with_live_logs(
                    cmd=cmd,
                    cwd=str(orchestrator_script.parent),
                    env=run_env,
                    panel_title="Approved Plan Execution Logs",
                )

                stdout_text = run_result.get("stdout", "")
                stderr_text = run_result.get("stderr", "")
                elapsed_time = time.time() - start_time
                
                progress_bar.progress(70)
                
                if run_result.get("returncode", 1) == 0:
                    # Parse output
                    output_lines = stdout_text.strip().split('\n') if stdout_text else []
                    result_data = {
                        "status": "completed",
                        "stdout": stdout_text,
                        "stderr": stderr_text,
                        "artifacts": [],
                        "raw_output": stdout_text
                    }
                    
                    # Parse JSON
                    json_found = False
                    for line in output_lines:
                        line = line.strip()
                        if line.startswith('{'):
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
                    
                    # Add plan info to result
                    result_data["execution_plan"] = plan_data.get("execution_plan")
                    result_data["planner_reasoning"] = plan_data.get("planner_reasoning")
                    result_data["used_planner"] = True
                    result_data["complexity_score"] = plan_data.get("complexity_score", 0)
                    
                    # Route through explicit human feedback stage before finalizing UI
                    st.session_state.pending_feedback_result = result_data
                    st.session_state.feedback_stage = True
                    
                    # Clear pending plan
                    st.session_state.pending_plan = None
                    st.session_state.plan_approved = False
                    
                    progress_bar.progress(100)
                    status_text.text("✅ Execution done")
                    time.sleep(0.5)
                    progress_bar.empty()
                    status_text.empty()
                    
                    st.success(f"✅ Execution completed in {elapsed_time:.2f}s")
                    st.info("Please provide human feedback to continue the flow.")
                    st.rerun()
                else:
                    st.error(f"❌ Execution failed with exit code {run_result.get('returncode', 'unknown')}")
                    if stderr_text:
                        st.code(stderr_text, language="text")
                    if stdout_text:
                        st.code(stdout_text, language="text")
                    
                    # Clear pending plan
                    st.session_state.pending_plan = None
                    st.session_state.plan_approved = False
                    
            except Exception as e:
                st.error(f"❌ Error during execution: {str(e)}")
                st.exception(e)
                st.session_state.pending_plan = None
                st.session_state.plan_approved = False
        
        return  # Stop here after execution

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
        
        # Check if we have a GitHub URL in the result
        result_data = st.session_state.pending_feedback_result
        if result_data and isinstance(result_data, dict):
            state_data = result_data.get("state", {})
            if isinstance(state_data, dict):
                repo_context = state_data.get("repo_context", {})
                if isinstance(repo_context, dict):
                    github_url_from_result = repo_context.get("github_url") or repo_context.get("path")
        
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
        
        if st.button("🔬 Execute & Validate", use_container_width=True, disabled=validation_button_disabled, help="Repair Dockerfile until build succeeds, then run CI/CD workflow with Act"):
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
                                            st.code("\n".join(log_lines[-80:]), language="text")
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
                        
                        from pipeline import run_execution

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
                                user_prompt=st.session_state.get("last_user_prompt", ""),
                                repository_path=repo_path_to_use,
                                run_execution_fn=run_execution,
                                max_attempts=4,
                                act_timeout=int(os.environ.get("EXECUTION_ACT_TIMEOUT", 1800)),
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
                                                st.code("\n".join(log_lines[-100:]), language="text")
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
                            
                            with st.expander("⚡ Act Execution Logs (last 50 lines)"):
                                act_logs = [log.get("line", "") for log in act_result.get("logs", []) if isinstance(log, dict)]
                                if act_logs:
                                    st.code("\n".join(act_logs[-50:]), language="text")
                                else:
                                    st.info("No logs available")

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
                            
                            with st.expander("⚡ Act Execution Logs"):
                                act_logs = [log.get("line", "") for log in act_result.get("logs", []) if isinstance(log, dict)]
                                if act_logs:
                                    st.code("\n".join(act_logs[-100:]), language="text")
                                else:
                                    st.info("No logs available")

                            
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
                use_container_width=True, 
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
            if st.button("📥 Accept (Download Only)", use_container_width=True, help="Accept without writing to repository"):
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
            if st.button("❌ Reject", use_container_width=True, help="Reject the generated artifacts"):
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
        if not user_prompt.strip():
            st.error("Please provide a prompt or request description.")
            return

        st.session_state.last_user_prompt = user_prompt.strip()
        
        with st.spinner("🔄 Orchestrating agents and generating artifacts..."):
            try:
                # Progress tracking
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                status_text.text("Preparing orchestrator command...")
                progress_bar.progress(10)
                
                # Build command to run orchestrator
                orchestrator_script = project_root / "test_pfe" / "02-orchestration-agents-layer" / "orchestrator-agent" / "run_orchestrator.py"
                
                if not orchestrator_script.exists():
                    st.error(f"❌ Orchestrator script not found: {orchestrator_script}")
                    return
                
                # Build command arguments
                cmd = [sys.executable, str(orchestrator_script)]
                cmd.extend(["--prompt", user_prompt])
                cmd.append("--plan-only")  # First, get the plan
                
                # Store repo_path in session state
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
                
                status_text.text("Running orchestrator...")
                progress_bar.progress(30)
                
                # Execute orchestrator
                start_time = time.time()
                
                # Set up environment with UTF-8 encoding
                run_env = os.environ.copy()
                run_env["PYTHONIOENCODING"] = "utf-8"
                
                run_result = run_orchestrator_command_with_live_logs(
                    cmd=cmd,
                    cwd=str(orchestrator_script.parent),
                    env=run_env,
                    panel_title="Orchestrator Runtime Logs",
                )

                stdout_text = run_result.get("stdout", "")
                stderr_text = run_result.get("stderr", "")
                
                status_text.text("Processing results...")
                progress_bar.progress(70)
                
                elapsed_time = time.time() - start_time
                
                # Parse output
                if run_result.get("returncode", 1) == 0:
                    # Try to extract JSON from output
                    output_lines = stdout_text.strip().split('\n') if stdout_text else []
                    result_data = {
                        "status": "completed",
                        "stdout": stdout_text,
                        "stderr": stderr_text,
                        "artifacts": [],
                        "raw_output": stdout_text
                    }
                    
                    # Try to parse any JSON in the output
                    json_found = False
                    for line in output_lines:
                        line = line.strip()
                        if line.startswith('{'):
                            try:
                                json_data = json.loads(line)
                                if "status" in json_data or "state" in json_data:
                                    result_data.update(json_data)
                                    json_found = True
                                    break
                            except json.JSONDecodeError:
                                continue
                    
                    # Also try to find JSON between markers
                    if not json_found and "=== JSON OUTPUT ===" in stdout_text:
                        try:
                            json_start = stdout_text.index("=== JSON OUTPUT ===") + len("=== JSON OUTPUT ===")
                            json_end = stdout_text.index("=== END JSON OUTPUT ===")
                            json_str = stdout_text[json_start:json_end].strip()
                            json_data = json.loads(json_str)
                            result_data.update(json_data)
                        except (ValueError, json.JSONDecodeError):
                            pass
                    
                    result = result_data
                    
                    status_text.text("Collecting results...")
                    progress_bar.progress(90)
                    
                    # Check if this is plan_ready status (needs approval)
                    if result.get("status") == "plan_ready" and result.get("used_planner"):
                        # Store plan for approval
                        st.session_state.pending_plan = {
                            "prompt": user_prompt,
                            "repo_path": repo_path,
                            "github_url": github_url,
                            "execution_plan": result.get("execution_plan"),
                            "planner_reasoning": result.get("planner_reasoning"),
                            "complexity_score": result.get("complexity_score", 0)
                        }
                        st.session_state.plan_approved = False
                        
                        progress_bar.progress(100)
                        status_text.text("✅ Plan ready!")
                        time.sleep(0.5)
                        progress_bar.empty()
                        status_text.empty()
                        
                        st.success(f"✅ Plan generated in {elapsed_time:.2f}s")
                        st.rerun()  # Refresh to show approval UI
                    else:
                        # Normal execution (no planner or low complexity)
                        # Route through explicit human feedback stage before finalizing UI
                        st.session_state.pending_feedback_result = result
                        st.session_state.feedback_stage = True

                        progress_bar.progress(100)
                        status_text.text("✅ Execution done")
                        time.sleep(0.5)
                        progress_bar.empty()
                        status_text.empty()

                        st.success(f"✅ Execution completed in {elapsed_time:.2f}s")
                        st.info("Please provide human feedback to continue the flow.")
                        st.rerun()
                else:
                    st.error(f"❌ Orchestrator failed with exit code {run_result.get('returncode', 'unknown')}")
                    if stderr_text:
                        st.code(stderr_text, language="text")
                    if stdout_text:
                        st.markdown("**Orchestrator stdout:**")
                        st.code(stdout_text, language="text")
                    return
                
            except Exception as e:
                st.error(f"❌ Error during orchestration: {str(e)}")
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
        
        # Agent status
        display_agent_status(result)

        # Local docker/act execution details
        display_pipeline_execution(result)
        
        st.markdown("")
        
        # Artifacts
        if status == "completed":
            artifacts = result.get("edited_artifacts") if isinstance(result.get("edited_artifacts"), dict) else extract_artifacts(result)
            display_artifacts(artifacts)
        
        # Errors
        state = result.get("state", {})
        errors = state.get("errors", [])
        if errors:
            st.markdown("### ⚠️ Errors")
            for error in errors:
                st.error(error)
        
        # Raw output (expandable)
        with st.expander("🔍 Raw Orchestrator Output", expanded=False):
            st.json(result)
    
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
