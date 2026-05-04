"""
Artifact management endpoints for the DevOps Orchestrator.
Handles applying, downloading, and rejecting generated artifacts.
"""

import logging
import json
import zipfile
import tempfile
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from fastapi import APIRouter, HTTPException, File, UploadFile
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Request/Response models
class TerraformArtifacts(BaseModel):
    main_tf: str
    variables_tf: str
    outputs_tf: str
    providers_tf: str

class KubernetesArtifacts(BaseModel):
    namespace_yaml: str
    configmap_yaml: str
    secret_yaml: str
    deployment_yaml: str
    service_yaml: str
    ingress_yaml: str
    hpa_yaml: str

class EditedArtifactsRequest(BaseModel):
    yaml: Optional[str] = None
    dockerfile: Optional[str] = None
    terraform: TerraformArtifacts
    kubernetes: KubernetesArtifacts
    metadata: Dict[str, Any] = {}

class ApplyArtifactsRequest(BaseModel):
    repo_path: str
    artifacts: EditedArtifactsRequest

class ApplyArtifactsResponse(BaseModel):
    success: bool
    artifacts_written: List[str] = []
    paths: Dict[str, str] = {}
    error: Optional[str] = None
    message: Optional[str] = None

class DownloadArtifactsRequest(BaseModel):
    artifacts: EditedArtifactsRequest

class DownloadArtifactsResponse(BaseModel):
    success: bool
    download_url: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None

class RejectArtifactsRequest(BaseModel):
    artifacts: EditedArtifactsRequest

class RejectArtifactsResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    error: Optional[str] = None

class ValidateArtifactsRequest(BaseModel):
    artifacts: EditedArtifactsRequest

class ValidateArtifactsResponse(BaseModel):
    valid: bool
    errors: List[str] = []

# Router
router = APIRouter(prefix="/artifacts", tags=["artifacts"])


def _create_directory_structure(base_path: str) -> None:
    """Create necessary directory structure for artifacts."""
    paths = [
        Path(base_path) / ".github" / "workflows",
        Path(base_path) / "terraform",
        Path(base_path) / "k8s",
    ]
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def _write_artifact(path: str, content: str, encoding: str = "utf-8") -> bool:
    """Write artifact to file."""
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding=encoding) as f:
            f.write(content)
        logger.info(f"✅ Written artifact: {path}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to write artifact {path}: {str(e)}")
        return False


def _validate_yaml(content: str) -> tuple[bool, Optional[str]]:
    """Basic YAML validation."""
    try:
        import yaml
        yaml.safe_load(content)
        return True, None
    except Exception as e:
        return False, f"Invalid YAML: {str(e)}"


def _validate_dockerfile(content: str) -> tuple[bool, Optional[str]]:
    """Basic Dockerfile validation."""
    if not content.strip():
        return False, "Dockerfile is empty"
    
    required_keywords = ["FROM"]
    content_upper = content.upper()
    
    for keyword in required_keywords:
        if keyword not in content_upper:
            return False, f"Dockerfile missing required keyword: {keyword}"
    
    return True, None


def _validate_hcl(content: str) -> tuple[bool, Optional[str]]:
    """Basic HCL validation."""
    if not content.strip():
        return True, None  # Empty HCL is acceptable
    
    # Basic checks for HCL syntax
    if content.count("{") != content.count("}"):
        return False, "HCL syntax error: mismatched braces"
    
    return True, None


@router.post("/apply", response_model=ApplyArtifactsResponse)
async def apply_artifacts(request: ApplyArtifactsRequest) -> ApplyArtifactsResponse:
    """
    Apply generated artifacts to a local repository.
    
    This endpoint writes all generated DevOps artifacts to the specified
    local repository path.
    """
    try:
        repo_path = Path(request.repo_path)
        
        # Validate repository path
        if not repo_path.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Repository path does not exist: {request.repo_path}"
            )
        
        if not repo_path.is_dir():
            raise HTTPException(
                status_code=400,
                detail=f"Repository path is not a directory: {request.repo_path}"
            )
        
        # Create directory structure
        _create_directory_structure(str(repo_path))
        
        artifacts_written: List[str] = []
        paths_written: Dict[str, str] = {}
        
        # Write GitHub Actions Workflow
        if request.artifacts.yaml:
            workflow_path = repo_path / ".github" / "workflows" / "devops-generated.yml"
            if _write_artifact(str(workflow_path), request.artifacts.yaml):
                artifacts_written.append("GitHub Actions Workflow")
                paths_written["workflow"] = str(workflow_path)
        
        # Write Dockerfile
        if request.artifacts.dockerfile:
            dockerfile_path = repo_path / "Dockerfile"
            if _write_artifact(str(dockerfile_path), request.artifacts.dockerfile):
                artifacts_written.append("Dockerfile")
                paths_written["dockerfile"] = str(dockerfile_path)
        
        # Write Terraform files
        terraform_artifacts = request.artifacts.terraform
        if terraform_artifacts.main_tf:
            tf_path = repo_path / "terraform" / "main.tf"
            if _write_artifact(str(tf_path), terraform_artifacts.main_tf):
                artifacts_written.append("Terraform main.tf")
                paths_written["terraform_main"] = str(tf_path)
        
        if terraform_artifacts.variables_tf:
            tf_path = repo_path / "terraform" / "variables.tf"
            if _write_artifact(str(tf_path), terraform_artifacts.variables_tf):
                artifacts_written.append("Terraform variables.tf")
                paths_written["terraform_variables"] = str(tf_path)
        
        if terraform_artifacts.outputs_tf:
            tf_path = repo_path / "terraform" / "outputs.tf"
            if _write_artifact(str(tf_path), terraform_artifacts.outputs_tf):
                artifacts_written.append("Terraform outputs.tf")
                paths_written["terraform_outputs"] = str(tf_path)
        
        if terraform_artifacts.providers_tf:
            tf_path = repo_path / "terraform" / "providers.tf"
            if _write_artifact(str(tf_path), terraform_artifacts.providers_tf):
                artifacts_written.append("Terraform providers.tf")
                paths_written["terraform_providers"] = str(tf_path)
        
        # Write Kubernetes manifests
        k8s_artifacts = request.artifacts.kubernetes
        k8s_files = {
            "namespace.yaml": k8s_artifacts.namespace_yaml,
            "configmap.yaml": k8s_artifacts.configmap_yaml,
            "secret.yaml": k8s_artifacts.secret_yaml,
            "deployment.yaml": k8s_artifacts.deployment_yaml,
            "service.yaml": k8s_artifacts.service_yaml,
            "ingress.yaml": k8s_artifacts.ingress_yaml,
            "hpa.yaml": k8s_artifacts.hpa_yaml,
        }
        
        for filename, content in k8s_files.items():
            if content:
                k8s_path = repo_path / "k8s" / filename
                if _write_artifact(str(k8s_path), content):
                    artifacts_written.append(f"Kubernetes {filename}")
                    paths_written[f"k8s_{filename.split('.')[0]}"] = str(k8s_path)
        
        logger.info(f"✅ Applied {len(artifacts_written)} artifacts to {request.repo_path}")
        
        return ApplyArtifactsResponse(
            success=True,
            artifacts_written=artifacts_written,
            paths=paths_written,
            message=f"Successfully applied {len(artifacts_written)} artifacts to repository"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error applying artifacts: {str(e)}")
        return ApplyArtifactsResponse(
            success=False,
            error=str(e),
            message="Failed to apply artifacts"
        )


@router.post("/download", response_model=DownloadArtifactsResponse)
async def download_artifacts(request: DownloadArtifactsRequest) -> DownloadArtifactsResponse:
    """
    Download generated artifacts as a compressed ZIP file.
    
    This endpoint creates a ZIP archive containing all generated artifacts
    and returns a download URL.
    """
    try:
        # Create temporary directory for artifacts
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create directory structure
            _create_directory_structure(str(temp_path))
            
            # Write artifacts to temporary directory
            if request.artifacts.yaml:
                workflow_path = temp_path / ".github" / "workflows" / "devops-generated.yml"
                _write_artifact(str(workflow_path), request.artifacts.yaml)
            
            if request.artifacts.dockerfile:
                dockerfile_path = temp_path / "Dockerfile"
                _write_artifact(str(dockerfile_path), request.artifacts.dockerfile)
            
            terraform_artifacts = request.artifacts.terraform
            if terraform_artifacts.main_tf:
                _write_artifact(str(temp_path / "terraform" / "main.tf"), terraform_artifacts.main_tf)
            if terraform_artifacts.variables_tf:
                _write_artifact(str(temp_path / "terraform" / "variables.tf"), terraform_artifacts.variables_tf)
            if terraform_artifacts.outputs_tf:
                _write_artifact(str(temp_path / "terraform" / "outputs.tf"), terraform_artifacts.outputs_tf)
            if terraform_artifacts.providers_tf:
                _write_artifact(str(temp_path / "terraform" / "providers.tf"), terraform_artifacts.providers_tf)
            
            k8s_artifacts = request.artifacts.kubernetes
            k8s_files = {
                "namespace.yaml": k8s_artifacts.namespace_yaml,
                "configmap.yaml": k8s_artifacts.configmap_yaml,
                "secret.yaml": k8s_artifacts.secret_yaml,
                "deployment.yaml": k8s_artifacts.deployment_yaml,
                "service.yaml": k8s_artifacts.service_yaml,
                "ingress.yaml": k8s_artifacts.ingress_yaml,
                "hpa.yaml": k8s_artifacts.hpa_yaml,
            }
            
            for filename, content in k8s_files.items():
                if content:
                    _write_artifact(str(temp_path / "k8s" / filename), content)
            
            # Create ZIP file
            zip_filename = f"devops-artifacts-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
            zip_path = Path(tempfile.gettempdir()) / zip_filename
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in temp_path.rglob('*'):
                    if file_path.is_file():
                        arcname = file_path.relative_to(temp_path)
                        zipf.write(file_path, arcname)
            
            logger.info(f"✅ Created artifact download package: {zip_filename}")
            
            return DownloadArtifactsResponse(
                success=True,
                download_url=f"/api/artifacts/download/{zip_filename}",
                message="Artifacts packaged for download"
            )
            
    except Exception as e:
        logger.error(f"❌ Error creating download package: {str(e)}")
        return DownloadArtifactsResponse(
            success=False,
            error=str(e),
            message="Failed to prepare artifacts for download"
        )


@router.post("/reject", response_model=RejectArtifactsResponse)
async def reject_artifacts(request: RejectArtifactsRequest) -> RejectArtifactsResponse:
    """
    Reject the generated artifacts.
    
    This endpoint logs the rejection and marks the artifacts as not accepted.
    PR creation path is skipped.
    """
    try:
        logger.warning("⚠️ Artifacts rejected by user. PR creation path is skipped.")
        logger.debug(f"Rejected artifacts metadata: {request.artifacts.metadata}")
        
        return RejectArtifactsResponse(
            success=True,
            message="Artifacts rejected. PR creation path is skipped."
        )
        
    except Exception as e:
        logger.error(f"❌ Error rejecting artifacts: {str(e)}")
        return RejectArtifactsResponse(
            success=False,
            error=str(e)
        )


@router.post("/validate", response_model=ValidateArtifactsResponse)
async def validate_artifacts(request: ValidateArtifactsRequest) -> ValidateArtifactsResponse:
    """
    Validate the syntax and format of generated artifacts.
    
    This endpoint performs basic validation checks on all artifacts.
    """
    errors: List[str] = []
    
    try:
        # Validate YAML
        if request.artifacts.yaml:
            valid, error = _validate_yaml(request.artifacts.yaml)
            if not valid:
                errors.append(f"GitHub Actions Workflow: {error}")
        
        # Validate Dockerfile
        if request.artifacts.dockerfile:
            valid, error = _validate_dockerfile(request.artifacts.dockerfile)
            if not valid:
                errors.append(f"Dockerfile: {error}")
        
        # Validate Terraform files
        tf = request.artifacts.terraform
        for name, content in [
            ("main.tf", tf.main_tf),
            ("variables.tf", tf.variables_tf),
            ("outputs.tf", tf.outputs_tf),
            ("providers.tf", tf.providers_tf),
        ]:
            if content:
                valid, error = _validate_hcl(content)
                if not valid:
                    errors.append(f"Terraform {name}: {error}")
        
        # Validate Kubernetes manifests
        k8s = request.artifacts.kubernetes
        for name, content in [
            ("namespace.yaml", k8s.namespace_yaml),
            ("configmap.yaml", k8s.configmap_yaml),
            ("secret.yaml", k8s.secret_yaml),
            ("deployment.yaml", k8s.deployment_yaml),
            ("service.yaml", k8s.service_yaml),
            ("ingress.yaml", k8s.ingress_yaml),
            ("hpa.yaml", k8s.hpa_yaml),
        ]:
            if content:
                valid, error = _validate_yaml(content)
                if not valid:
                    errors.append(f"Kubernetes {name}: {error}")
        
        is_valid = len(errors) == 0
        logger.info(f"{'✅' if is_valid else '❌'} Artifact validation: {len(errors)} error(s)")
        
        return ValidateArtifactsResponse(
            valid=is_valid,
            errors=errors
        )
        
    except Exception as e:
        logger.error(f"❌ Validation error: {str(e)}")
        return ValidateArtifactsResponse(
            valid=False,
            errors=[f"Validation exception: {str(e)}"]
        )
