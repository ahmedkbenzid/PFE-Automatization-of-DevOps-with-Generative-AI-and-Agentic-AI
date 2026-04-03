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
from typing import Dict, Any, Optional
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
        execution_order = plan.get("execution_order", [])
        for i, step in enumerate(execution_order, 1):
            if isinstance(step, list):
                st.markdown(f"**Step {i}:** Parallel execution")
                for agent in step:
                    st.markdown(f"  - `{agent}`")
            else:
                st.markdown(f"**Step {i}:** `{step}`")
        
        if plan_data.get("planner_reasoning"):
            with st.expander("💡 Planner Reasoning", expanded=False):
                st.text(plan_data["planner_reasoning"])
        
        st.markdown("---")
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            if st.button("✅ Approve & Execute", type="primary", use_container_width=True):
                st.session_state.plan_approved = True
                st.rerun()
        with col2:
            if st.button("❌ Cancel", use_container_width=True):
                st.session_state.pending_plan = None
                st.session_state.plan_approved = False
                st.rerun()
        
        return  # Stop here, don't show the normal form
    
    # If plan was approved, execute it
    if st.session_state.plan_approved and st.session_state.pending_plan:
        plan_data = st.session_state.pending_plan
        
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
                    if var not in run_env and os.getenv(var):
                        run_env[var] = os.getenv(var)
                
                process = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=str(orchestrator_script.parent),
                    env=run_env,
                    encoding="utf-8",
                    errors="replace"
                )
                
                stdout_text = process.stdout or ""
                stderr_text = process.stderr or ""
                elapsed_time = time.time() - start_time
                
                progress_bar.progress(70)
                
                if process.returncode == 0:
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
                    st.error(f"❌ Execution failed with exit code {process.returncode}")
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
        st.markdown("## 💬 Human Feedback")
        st.info("Execution is done. Review and edit artifacts below, then confirm feedback.")

        feedback_result = st.session_state.pending_feedback_result
        feedback_artifacts = extract_artifacts(feedback_result)

        st.markdown("### ✍️ Edit Generated Artifacts")
        edited_yaml = st.text_area(
            "GitHub Actions Workflow (YAML)",
            value=feedback_artifacts.get("yaml") or "",
            height=220,
            key="feedback_edit_yaml",
        )
        edited_dockerfile = st.text_area(
            "Dockerfile",
            value=feedback_artifacts.get("dockerfile") or "",
            height=220,
            key="feedback_edit_dockerfile",
        )

        terraform_data = feedback_artifacts.get("terraform") if isinstance(feedback_artifacts.get("terraform"), dict) else {}
        edited_main_tf = st.text_area(
            "Terraform main.tf",
            value=(terraform_data.get("main_tf") or ""),
            height=180,
            key="feedback_edit_main_tf",
        )
        edited_variables_tf = st.text_area(
            "Terraform variables.tf",
            value=(terraform_data.get("variables_tf") or ""),
            height=140,
            key="feedback_edit_variables_tf",
        )
        edited_outputs_tf = st.text_area(
            "Terraform outputs.tf",
            value=(terraform_data.get("outputs_tf") or ""),
            height=120,
            key="feedback_edit_outputs_tf",
        )
        edited_providers_tf = st.text_area(
            "Terraform providers.tf",
            value=(terraform_data.get("providers_tf") or ""),
            height=120,
            key="feedback_edit_providers_tf",
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Accept Results", type="primary", use_container_width=True):
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
                st.rerun()
        with col2:
            if st.button("❌ Not Acceptable", use_container_width=True):
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
                st.warning("Feedback marked as 'not'. PR creation path is skipped.")
                st.rerun()

        return
    
    # Process request
    if generate_button:
        if not user_prompt.strip():
            st.error("Please provide a prompt or request description.")
            return
        
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
                
                if repo_path:
                    cmd.extend(["--repo-path", str(repo_path)])
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
                
                process = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=str(orchestrator_script.parent),
                    env=run_env,
                    encoding="utf-8",
                    errors="replace"
                )
                
                stdout_text = process.stdout or ""
                stderr_text = process.stderr or ""
                
                status_text.text("Processing results...")
                progress_bar.progress(70)
                
                elapsed_time = time.time() - start_time
                
                # Parse output
                if process.returncode == 0:
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
                    st.error(f"❌ Orchestrator failed with exit code {process.returncode}")
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
                    
                    st.markdown("**Planned Execution Order:**")
                    execution_order = plan.get("execution_order", [])
                    for i, step in enumerate(execution_order, 1):
                        if isinstance(step, list):
                            st.markdown(f"**Step {i}:** Parallel execution")
                            for agent in step:
                                st.markdown(f"  - `{agent}`")
                        else:
                            st.markdown(f"**Step {i}:** `{step}`")
                    
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
