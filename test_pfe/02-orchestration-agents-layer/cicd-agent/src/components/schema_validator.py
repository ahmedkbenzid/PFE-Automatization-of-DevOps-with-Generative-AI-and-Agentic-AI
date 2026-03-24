"""Schema validation for GitHub Actions workflows"""
import jsonschema
from typing import Tuple, List, Dict, Any
from src.models.types import ValidationResult
from src.components.yaml_generator import YAMLGenerator

class SchemaValidator:
    """Validate workflows against GitHub Actions schema"""
    
    def __init__(self):
        self.warnings = []
        self.suggestions = []
    
    def validate_workflow(self, parsed_yaml: Dict[str, Any], yaml_generator: YAMLGenerator) -> ValidationResult:
        """Comprehensive validation of workflow"""
        errors = []
        warnings = []
        suggestions = []
        
        # Check required fields
        is_valid, field_errors = yaml_generator.validate_required_fields(parsed_yaml)
        errors.extend(field_errors)
        
        # Check 'on' triggers
        on_errors = self._validate_triggers(parsed_yaml.get('on', {}))
        errors.extend(on_errors)
        
        # Check jobs
        job_errors, job_warnings = self._validate_jobs(parsed_yaml.get('jobs', {}))
        errors.extend(job_errors)
        warnings.extend(job_warnings)
        
        # Check environment variables
        env_warnings = self._validate_environment(parsed_yaml.get('env', {}))
        warnings.extend(env_warnings)
        
        # Performance suggestions
        perf_suggestions = self._check_performance(parsed_yaml)
        suggestions.extend(perf_suggestions)
        
        # Best practices
        best_practice_warnings = self._check_best_practices(parsed_yaml)
        warnings.extend(best_practice_warnings)
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            suggestions=suggestions,
        )
    
    def _validate_triggers(self, triggers: Any) -> List[str]:
        """Validate workflow triggers"""
        errors = []
        
        if not triggers:
            errors.append("At least one trigger is required in 'on'")
            return errors
        
        valid_triggers = {
            'branch_protection_rule', 'check_run', 'check_suite',
            'create', 'delete', 'deployment', 'deployment_status',
            'discussion', 'discussion_comment', 'fork', 'gollum',
            'issue_comment', 'issues', 'label', 'member', 'milestone',
            'page_build', 'project', 'project_card', 'project_column',
            'public', 'pull_request', 'pull_request_review',
            'pull_request_review_comment', 'pull_request_target',
            'push', 'registry_package', 'release', 'repository_dispatch',
            'schedule', 'status', 'watch', 'workflow_call', 'workflow_dispatch',
            'workflow_run'
        }
        
        if isinstance(triggers, dict):
            for trigger in triggers.keys():
                if trigger not in valid_triggers:
                    errors.append(f"Unknown trigger: '{trigger}'")
        
        return errors
    
    def _validate_jobs(self, jobs: Dict[str, Any]) -> Tuple[List[str], List[str]]:
        """Validate job definitions"""
        errors = []
        warnings = []
        
        if not jobs:
            errors.append("At least one job is required")
            return errors, warnings
        
        valid_job_configs = {
            'runs-on', 'environment', 'concurrency', 'outputs',
            'env', 'defaults', 'if', 'steps', 'strategy',
            'continue-on-error', 'container', 'services',
            'timeout-minutes'
        }
        
        for job_name, job_config in jobs.items():
            if not isinstance(job_config, dict):
                errors.append(f"Job '{job_name}' must be an object")
                continue
            
            # Check required fields
            if 'runs-on' not in job_config and job_config.get('container') is None:
                errors.append(f"Job '{job_name}' missing required 'runs-on' or 'container'")
            
            if 'steps' not in job_config:
                errors.append(f"Job '{job_name}' missing required 'steps'")
            else:
                step_errors = self._validate_steps(job_config['steps'], job_name)
                errors.extend(step_errors)
            
            # Validate unknown keys
            for key in job_config.keys():
                if key not in valid_job_configs:
                    warnings.append(f"Job '{job_name}' has unknown key: '{key}'")
        
        return errors, warnings
    
    def _validate_steps(self, steps: Any, job_name: str) -> List[str]:
        """Validate job steps"""
        errors = []
        
        if not isinstance(steps, list):
            errors.append(f"Job '{job_name}' steps must be a list")
            return errors
        
        if not steps:
            errors.append(f"Job '{job_name}' must have at least one step")
            return errors
        
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                errors.append(f"Job '{job_name}' step {i+1} must be an object")
                continue
            
            has_action = 'uses' in step or 'run' in step
            if not has_action:
                errors.append(f"Job '{job_name}' step {i+1} missing 'uses' or 'run'")
            
            if 'uses' in step and 'run' in step:
                errors.append(f"Job '{job_name}' step {i+1} cannot have both 'uses' and 'run'")
        
        return errors
    
    def _validate_environment(self, env: Any) -> List[str]:
        """Validate environment variables"""
        warnings = []
        
        if not isinstance(env, dict):
            return warnings
        
        # Check for common issues
        for key, value in env.items():
            if not isinstance(key, str) or not key.isupper():
                warnings.append(f"Environment variable '{key}' should be uppercase")
            
            if isinstance(value, bool):
                warnings.append(f"Environment variable '{key}' should not be boolean")
        
        return warnings
    
    def _check_performance(self, workflow: Dict[str, Any]) -> List[str]:
        """Check for performance issues and suggestions"""
        suggestions = []
        
        # Check for caching
        jobs = workflow.get('jobs', {})
        for job_name, job_config in jobs.items():
            steps = job_config.get('steps', [])
            has_cache = any(
                step.get('uses', '').startswith('actions/cache')
                for step in steps if isinstance(step, dict)
            )
            
            if not has_cache and any(
                'install' in str(step).lower() or 'dependencies' in str(step).lower()
                for step in steps if isinstance(step, dict)
            ):
                suggestions.append(f"Job '{job_name}' should use caching for dependencies")
        
        return suggestions
    
    def _check_best_practices(self, workflow: Dict[str, Any]) -> List[str]:
        """Check GitHub Actions best practices"""
        warnings = []
        
        # Check if using latest actions
        jobs = workflow.get('jobs', {})
        for job_name, job_config in jobs.items():
            steps = job_config.get('steps', [])
            for step in steps:
                if not isinstance(step, dict):
                    continue
                
                uses = step.get('uses', '')
                if '@' in uses and not uses.endswith(('@main', '@latest')):
                    # Check if pinned to specific SHA
                    if len(uses.split('@')[-1]) != 40:  # SHA should be 40 chars
                        warnings.append(f"Action '{uses}' should be pinned to a specific version or SHA")
        
        return warnings
