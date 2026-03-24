"""GitHub Actions template management"""
import os
import json
from typing import Dict, List, Optional
from src.models.types import WorkflowTemplate

class TemplateManager:
    """Manage workflow templates and action schemas"""
    
    # Common GitHub Actions schemas
    COMMON_ACTIONS = {
        "checkout": {
            "uses": "actions/checkout@v4",
            "with": {
                "fetch-depth": "0",
            }
        },
        "setup-python": {
            "uses": "actions/setup-python@v4",
            "with": {
                "python-version": "3.11",
                "cache": "pip",
            }
        },
        "setup-node": {
            "uses": "actions/setup-node@v4",
            "with": {
                "node-version": "18",
                "cache": "npm",
            }
        },
        "setup-go": {
            "uses": "actions/setup-go@v4",
            "with": {
                "go-version": "1.21",
            }
        },
        "setup-java": {
            "uses": "actions/setup-java@v4",
            "with": {
                "java-version": "17",
                "distribution": "temurin",
            }
        },
    }
    
    # Common workflow templates
    TEMPLATES = {
        "python-test": WorkflowTemplate(
            name="Python Tests",
            description="Run Python tests with pytest",
            triggers=["push", "pull_request"],
            jobs={
                "test": {
                    "runs-on": "ubuntu-latest",
                    "strategy": {
                        "matrix": {
                            "python-version": ["3.9", "3.11"]
                        }
                    },
                    "steps": [
                        "checkout",
                        "setup-python",
                        {"run": "pip install -e '.[test]'"},
                        {"run": "pytest --cov"},
                    ]
                }
            },
        ),
        "nodejs-test": WorkflowTemplate(
            name="Node.js Tests",
            description="Run JavaScript/Node.js tests",
            triggers=["push", "pull_request"],
            jobs={
                "test": {
                    "runs-on": "ubuntu-latest",
                    "strategy": {
                        "matrix": {
                            "node-version": ["16", "18", "20"]
                        }
                    },
                    "steps": [
                        "checkout",
                        "setup-node",
                        {"run": "npm ci"},
                        {"run": "npm test"},
                    ]
                }
            },
        ),
        "docker-build": WorkflowTemplate(
            name="Docker Build",
            description="Build and push Docker image",
            triggers=["push"],
            jobs={
                "build": {
                    "runs-on": "ubuntu-latest",
                    "steps": [
                        "checkout",
                        {
                            "uses": "docker/setup-buildx-action@v2",
                        },
                        {
                            "uses": "docker/setup-qemu-action@v2",
                        },
                        {
                            "uses": "docker/build-push-action@v4",
                            "with": {
                                "context": ".",
                                "push": False,
                                "tags": "myimage:latest",
                            }
                        }
                    ]
                }
            },
        ),
    }
    
    def __init__(self):
        self.custom_templates: Dict[str, WorkflowTemplate] = {}
    
    def get_template(self, template_name: str) -> Optional[WorkflowTemplate]:
        """Get a template by name"""
        if template_name in self.TEMPLATES:
            return self.TEMPLATES[template_name]
        return self.custom_templates.get(template_name)
    
    def get_available_templates(self) -> List[str]:
        """Get list of available templates"""
        return list(self.TEMPLATES.keys()) + list(self.custom_templates.keys())
    
    def get_action_schema(self, action_name: str) -> Optional[Dict]:
        """Get schema for a common action"""
        return self.COMMON_ACTIONS.get(action_name)
    
    def add_custom_template(self, name: str, template: WorkflowTemplate) -> None:
        """Add a custom template"""
        self.custom_templates[name] = template
    
    def get_matching_templates(self, languages: List[str], build_system: Optional[str]) -> List[str]:
        """Suggest templates based on detected languages and build system"""
        suggestions = []
        
        language_template_map = {
            'Python': 'python-test',
            'JavaScript': 'nodejs-test',
            'TypeScript': 'nodejs-test',
            'Docker': 'docker-build',
        }
        
        for lang in languages:
            if lang in language_template_map:
                template = language_template_map[lang]
                if template not in suggestions:
                    suggestions.append(template)
        
        return suggestions
    
    def expand_template_shortcuts(self, jobs: Dict) -> Dict:
        """Expand shortcuts like 'checkout' to full action definitions"""
        expanded_jobs = {}
        
        for job_name, job_config in jobs.items():
            expanded_jobs[job_name] = self._expand_steps(job_config)
        
        return expanded_jobs
    
    def _expand_steps(self, job_config: Dict) -> Dict:
        """Expand action shortcuts in steps"""
        if "steps" not in job_config:
            return job_config
        
        expanded_steps = []
        for step in job_config["steps"]:
            if isinstance(step, str):
                # It's a shortcut
                action_schema = self.get_action_schema(step)
                if action_schema:
                    expanded_steps.append(action_schema)
                else:
                    expanded_steps.append({"run": step})
            else:
                expanded_steps.append(step)
        
        job_config["steps"] = expanded_steps
        return job_config
    
    def get_validation_schema(self) -> Dict:
        """Get JSON schema for GitHub Actions workflow validation"""
        return {
            "type": "object",
            "required": ["name", "on", "jobs"],
            "properties": {
                "name": {"type": "string"},
                "on": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "object"},
                        {"type": "array"}
                    ]
                },
                "jobs": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "object",
                    }
                },
                "env": {"type": "object"},
                "concurrency": {"oneOf": [{"type": "string"}, {"type": "object"}]},
            }
        }
