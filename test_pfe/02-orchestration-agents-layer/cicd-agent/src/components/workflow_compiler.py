"""Workflow compiler and lock file generation"""
import hashlib
import json
from datetime import datetime
from typing import Dict, Any, Optional
from src.models.types import WorkflowLockFile, GeneratedWorkflow
import yaml

class WorkflowCompiler:
    """Compile workflows and generate reproducible lock files"""
    
    VERSION = "1.0.0"
    
    def __init__(self):
        self.compiled_workflows = {}
    
    def compile_workflow(self, yaml_content: str, workflow_name: str, metadata: Dict[str, Any] = None) -> tuple[str, WorkflowLockFile]:
        """Compile workflow and generate lock file"""
        
        # Parse and normalize YAML
        parsed = yaml.safe_load(yaml_content)
        if not parsed:
            raise ValueError("Invalid YAML content")

        if isinstance(parsed, dict) and True in parsed and 'on' not in parsed:
            parsed['on'] = parsed.pop(True)
        
        # Normalize the workflow
        normalized_yaml = self._normalize_workflow(parsed)
        compiled_yaml = yaml.dump(normalized_yaml, default_flow_style=False, sort_keys=False)
        
        # Extract dependencies
        dependencies = self._extract_dependencies(parsed)
        
        # Generate checksum
        checksum = self._generate_checksum(compiled_yaml)
        
        # Create lock file
        lock_file = WorkflowLockFile(
            workflow_name=workflow_name,
            generated_at=datetime.now(),
            generator_version=self.VERSION,
            dependencies=dependencies,
            checksum=checksum,
        )
        
        self.compiled_workflows[workflow_name] = {
            'yaml': compiled_yaml,
            'lock_file': lock_file,
            'metadata': metadata or {},
        }
        
        return compiled_yaml, lock_file
    
    def _normalize_workflow(self, parsed_workflow: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize workflow structure"""
        normalized = {}
        
        # Preserve order of keys
        key_order = ['name', 'on', 'env', 'concurrency', 'jobs', 'permissions']
        
        for key in key_order:
            if key in parsed_workflow:
                normalized[key] = parsed_workflow[key]
        
        # Add any other keys
        for key, value in parsed_workflow.items():
            if key not in normalized:
                normalized[key] = value
        
        # Sort job names for consistency
        if 'jobs' in normalized:
            normalized['jobs'] = dict(sorted(normalized['jobs'].items()))
        
        return normalized
    
    def _extract_dependencies(self, parsed_workflow: Dict[str, Any]) -> Dict[str, str]:
        """Extract action dependencies from workflow"""
        dependencies = {}
        
        jobs = parsed_workflow.get('jobs', {})
        for job_name, job_config in jobs.items():
            steps = job_config.get('steps', [])
            for step in steps:
                if isinstance(step, dict) and 'uses' in step:
                    action = step['uses']
                    # Extract version/ref
                    if '@' in action:
                        name, version = action.rsplit('@', 1)
                        dependencies[name] = version
        
        return dependencies
    
    def _generate_checksum(self, yaml_content: str) -> str:
        """Generate SHA256 checksum for workflow"""
        return hashlib.sha256(yaml_content.encode()).hexdigest()
    
    def generate_lock_file_yaml(self, lock_file: WorkflowLockFile) -> str:
        """Generate lock file in YAML format"""
        lock_data = {
            'version': lock_file.generator_version,
            'workflow': lock_file.workflow_name,
            'generated': lock_file.generated_at.isoformat(),
            'checksum': lock_file.checksum,
            'dependencies': lock_file.dependencies,
        }
        
        return yaml.dump(lock_data, default_flow_style=False, sort_keys=False)
    
    def verify_workflow_integrity(self, yaml_content: str, lock_file: WorkflowLockFile) -> bool:
        """Verify workflow against lock file"""
        current_checksum = self._generate_checksum(yaml_content)
        return current_checksum == lock_file.checksum
    
    def get_compiled_workflow(self, workflow_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve compiled workflow"""
        return self.compiled_workflows.get(workflow_name)
    
    def export_compiled_workflow(self, workflow_name: str, output_dir: str) -> bool:
        """Export compiled workflow to files"""
        import os
        
        workflow_data = self.get_compiled_workflow(workflow_name)
        if not workflow_data:
            return False
        
        try:
            os.makedirs(output_dir, exist_ok=True)
            
            # Write workflow YAML
            workflow_path = os.path.join(output_dir, f"{workflow_name}.yml")
            with open(workflow_path, 'w') as f:
                f.write(workflow_data['yaml'])
            
            # Write lock file
            lock_path = os.path.join(output_dir, f"{workflow_name}.lock.yml")
            lock_yaml = self.generate_lock_file_yaml(workflow_data['lock_file'])
            with open(lock_path, 'w') as f:
                f.write(lock_yaml)
            
            # Write metadata
            metadata_path = os.path.join(output_dir, f"{workflow_name}.metadata.json")
            with open(metadata_path, 'w') as f:
                json.dump(workflow_data['metadata'], f, indent=2, default=str)
            
            return True
        except Exception as e:
            print(f"Error exporting workflow: {e}")
            return False
