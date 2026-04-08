"""
Artifact Writer Module
Writes generated artifacts (Dockerfiles, CI/CD workflows, Terraform) to the target repository.
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
import shutil

logger = logging.getLogger(__name__)


class ArtifactWriter:
    """Writes generated DevOps artifacts to a target repository directory."""
    
    def __init__(self, repo_path: str):
        """
        Initialize the artifact writer.
        
        Args:
            repo_path: Path to the target repository where artifacts will be written
        """
        self.repo_path = Path(repo_path)
        if not self.repo_path.exists():
            raise ValueError(f"Repository path does not exist: {repo_path}")
        
        logger.info(f"ArtifactWriter initialized for repository: {self.repo_path}")
    
    def write_dockerfile(self, content: str, backup: bool = True) -> Dict[str, Any]:
        """
        Write Dockerfile to repository root.
        
        Args:
            content: Dockerfile content
            backup: If True, backup existing Dockerfile before overwriting
        
        Returns:
            Dictionary with status, path, and backup info
        """
        dockerfile_path = self.repo_path / "Dockerfile"
        result = {
            "success": False,
            "path": str(dockerfile_path),
            "backup_path": None,
            "action": None
        }
        
        try:
            # Backup existing file if requested
            if dockerfile_path.exists() and backup:
                backup_path = self.repo_path / "Dockerfile.backup"
                shutil.copy2(dockerfile_path, backup_path)
                result["backup_path"] = str(backup_path)
                result["action"] = "overwritten"
                logger.info(f"Backed up existing Dockerfile to {backup_path}")
            elif dockerfile_path.exists():
                result["action"] = "overwritten"
            else:
                result["action"] = "created"
            
            # Write new Dockerfile
            dockerfile_path.write_text(content, encoding="utf-8")
            result["success"] = True
            logger.info(f"Successfully wrote Dockerfile to {dockerfile_path}")
            
        except Exception as e:
            logger.error(f"Failed to write Dockerfile: {e}")
            result["error"] = str(e)
        
        return result
    
    def write_cicd_workflow(self, content: str, workflow_name: str = "ci-cd.yml", backup: bool = True) -> Dict[str, Any]:
        """
        Write CI/CD workflow to .github/workflows directory.
        
        Args:
            content: Workflow YAML content
            workflow_name: Name of the workflow file (default: ci-cd.yml)
            backup: If True, backup existing workflow before overwriting
        
        Returns:
            Dictionary with status, path, and backup info
        """
        workflows_dir = self.repo_path / ".github" / "workflows"
        workflow_path = workflows_dir / workflow_name
        
        result = {
            "success": False,
            "path": str(workflow_path),
            "backup_path": None,
            "action": None
        }
        
        try:
            # Create directory structure if it doesn't exist
            workflows_dir.mkdir(parents=True, exist_ok=True)
            
            # Backup existing file if requested
            if workflow_path.exists() and backup:
                backup_path = workflows_dir / f"{workflow_name}.backup"
                shutil.copy2(workflow_path, backup_path)
                result["backup_path"] = str(backup_path)
                result["action"] = "overwritten"
                logger.info(f"Backed up existing workflow to {backup_path}")
            elif workflow_path.exists():
                result["action"] = "overwritten"
            else:
                result["action"] = "created"
            
            # Write new workflow
            workflow_path.write_text(content, encoding="utf-8")
            result["success"] = True
            logger.info(f"Successfully wrote CI/CD workflow to {workflow_path}")
            
        except Exception as e:
            logger.error(f"Failed to write CI/CD workflow: {e}")
            result["error"] = str(e)
        
        return result
    
    def write_terraform_files(self, terraform_config: Dict[str, str], terraform_dir: str = "terraform", backup: bool = True) -> Dict[str, Any]:
        """
        Write Terraform configuration files to repository.
        
        Args:
            terraform_config: Dictionary with keys like 'main_tf', 'variables_tf', etc.
            terraform_dir: Directory name for Terraform files (default: terraform)
            backup: If True, backup existing files before overwriting
        
        Returns:
            Dictionary with overall status and individual file results
        """
        tf_dir = self.repo_path / terraform_dir
        result = {
            "success": True,
            "terraform_dir": str(tf_dir),
            "files": {},
            "errors": []
        }
        
        try:
            # Create terraform directory if it doesn't exist
            tf_dir.mkdir(parents=True, exist_ok=True)
            
            # Map config keys to filenames
            file_mapping = {
                "main_tf": "main.tf",
                "variables_tf": "variables.tf",
                "outputs_tf": "outputs.tf",
                "providers_tf": "providers.tf"
            }
            
            # Write each file
            for config_key, filename in file_mapping.items():
                content = terraform_config.get(config_key)
                if not content or not content.strip():
                    continue
                
                file_path = tf_dir / filename
                file_result = {
                    "success": False,
                    "path": str(file_path),
                    "backup_path": None,
                    "action": None
                }
                
                try:
                    # Backup existing file if requested
                    if file_path.exists() and backup:
                        backup_path = tf_dir / f"{filename}.backup"
                        shutil.copy2(file_path, backup_path)
                        file_result["backup_path"] = str(backup_path)
                        file_result["action"] = "overwritten"
                        logger.info(f"Backed up existing {filename} to {backup_path}")
                    elif file_path.exists():
                        file_result["action"] = "overwritten"
                    else:
                        file_result["action"] = "created"
                    
                    # Write file
                    file_path.write_text(content, encoding="utf-8")
                    file_result["success"] = True
                    logger.info(f"Successfully wrote {filename} to {file_path}")
                    
                except Exception as e:
                    logger.error(f"Failed to write {filename}: {e}")
                    file_result["error"] = str(e)
                    result["success"] = False
                    result["errors"].append(f"{filename}: {str(e)}")
                
                result["files"][config_key] = file_result
            
        except Exception as e:
            logger.error(f"Failed to create Terraform directory or write files: {e}")
            result["success"] = False
            result["error"] = str(e)
        
        return result
    
    def write_all_artifacts(self, artifacts: Dict[str, Any], backup: bool = True) -> Dict[str, Any]:
        """
        Write all generated artifacts to the repository.
        
        Args:
            artifacts: Dictionary containing generated artifacts (yaml, dockerfile, terraform)
            backup: If True, backup existing files before overwriting
        
        Returns:
            Dictionary with overall status and individual results for each artifact type
        """
        result = {
            "success": True,
            "artifacts_written": [],
            "errors": [],
            "dockerfile": None,
            "cicd_workflow": None,
            "terraform": None
        }
        
        # Write Dockerfile
        if artifacts.get("dockerfile"):
            dockerfile_result = self.write_dockerfile(artifacts["dockerfile"], backup=backup)
            result["dockerfile"] = dockerfile_result
            if dockerfile_result["success"]:
                result["artifacts_written"].append("Dockerfile")
            else:
                result["success"] = False
                result["errors"].append(f"Dockerfile: {dockerfile_result.get('error', 'Unknown error')}")
        
        # Write CI/CD workflow
        if artifacts.get("yaml"):
            workflow_result = self.write_cicd_workflow(artifacts["yaml"], backup=backup)
            result["cicd_workflow"] = workflow_result
            if workflow_result["success"]:
                result["artifacts_written"].append("CI/CD Workflow")
            else:
                result["success"] = False
                result["errors"].append(f"CI/CD Workflow: {workflow_result.get('error', 'Unknown error')}")
        
        # Write Terraform files
        terraform_data = artifacts.get("terraform")
        if terraform_data and isinstance(terraform_data, dict):
            # Check if any terraform file has content
            has_content = any(
                terraform_data.get(key) and str(terraform_data.get(key)).strip()
                for key in ["main_tf", "variables_tf", "outputs_tf", "providers_tf"]
            )
            
            if has_content:
                terraform_result = self.write_terraform_files(terraform_data, backup=backup)
                result["terraform"] = terraform_result
                if terraform_result["success"]:
                    result["artifacts_written"].append("Terraform Configuration")
                else:
                    result["success"] = False
                    result["errors"].extend(terraform_result.get("errors", []))
        
        if not result["artifacts_written"]:
            result["success"] = False
            result["errors"].append("No artifacts to write")
        
        logger.info(f"Artifact writing completed. Success: {result['success']}, Written: {result['artifacts_written']}")
        
        return result
