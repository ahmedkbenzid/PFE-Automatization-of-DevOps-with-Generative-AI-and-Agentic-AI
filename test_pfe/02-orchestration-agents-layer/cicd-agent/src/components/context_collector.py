"""Context collection from repositories"""
import os
import json
from typing import Dict, List, Any, Optional
from pathlib import Path
from src.models.types import RepositoryContext

class ContextCollector:
    """Collect repository context for workflow generation"""
    
    def __init__(self):
        self.repo_context: Optional[RepositoryContext] = None
        
    def collect_from_local_repo(self, repo_path: str) -> Dict[str, Any]:
        """Collect context from a local repository"""
        context = {
            "languages": self._detect_languages(repo_path),
            "build_system": self._detect_build_system(repo_path),
            "workflows": self._find_existing_workflows(repo_path),
            "repo_files": self._get_important_files(repo_path),
            "package_managers": self._detect_package_managers(repo_path),
        }
        return context
    
    def _detect_languages(self, repo_path: str) -> List[str]:
        """Detect programming languages in repository"""
        languages = set()
        
        extensions_map = {
            '.py': 'Python',
            '.js': 'JavaScript',
            '.ts': 'TypeScript',
            '.java': 'Java',
            '.go': 'Go',
            '.rb': 'Ruby',
            '.php': 'PHP',
            '.cpp': 'C++',
            '.cs': 'C#',
            '.rs': 'Rust',
        }
        
        try:
            for root, dirs, files in os.walk(repo_path):
                # Skip hidden and common ignore folders
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', 'venv', '__pycache__']]
                
                for file in files:
                    for ext, lang in extensions_map.items():
                        if file.endswith(ext):
                            languages.add(lang)
        except Exception as e:
            print(f"Error detecting languages: {e}")
        
        return list(languages)
    
    def _detect_build_system(self, repo_path: str) -> Optional[str]:
        """Detect build system/package manager"""
        indicators = {
            'package.json': 'npm/Node.js',
            'requirements.txt': 'Python/pip',
            'setup.py': 'Python/setuptools',
            'pyproject.toml': 'Python/Poetry',
            'Cargo.toml': 'Rust',
            'go.mod': 'Go',
            'pom.xml': 'Maven',
            'build.gradle': 'Gradle',
            'Gemfile': 'Ruby/Bundler',
        }
        
        for file, system in indicators.items():
            if os.path.exists(os.path.join(repo_path, file)):
                return system
        
        return None
    
    def _detect_package_managers(self, repo_path: str) -> List[str]:
        """Detect package managers used"""
        managers = []
        
        checks = {
            'package.json': 'npm',
            'yarn.lock': 'yarn',
            'pnpm-lock.yaml': 'pnpm',
            'Pipfile': 'pipenv',
            'poetry.lock': 'poetry',
            'requirements.txt': 'pip',
            'go.mod': 'go modules',
            'Cargo.lock': 'cargo',
        }
        
        for file, manager in checks.items():
            if os.path.exists(os.path.join(repo_path, file)):
                managers.append(manager)
        
        return managers
    
    def _find_existing_workflows(self, repo_path: str) -> List[str]:
        """Find existing GitHub Actions workflows"""
        workflows = []
        workflow_dir = os.path.join(repo_path, '.github', 'workflows')
        
        if os.path.exists(workflow_dir):
            try:
                for file in os.listdir(workflow_dir):
                    if file.endswith(('.yml', '.yaml')):
                        workflows.append(file)
            except Exception as e:
                print(f"Error finding workflows: {e}")
        
        return workflows
    
    def _get_important_files(self, repo_path: str) -> Dict[str, bool]:
        """Check for important configuration files"""
        important_files = {
            'README.md': False,
            'Dockerfile': False,
            'docker-compose.yml': False,
            '.dockerignore': False,
            'Makefile': False,
            'tox.ini': False,
            '.eslintrc': False,
            '.flake8': False,
        }
        
        for file in important_files:
            important_files[file] = os.path.exists(os.path.join(repo_path, file))
        
        return important_files
    
    def create_repo_context(self, owner: str, name: str, url: str, repo_path: Optional[str] = None) -> RepositoryContext:
        """Create a RepositoryContext object"""
        context_data = self.collect_from_local_repo(repo_path) if repo_path else {}
        
        self.repo_context = RepositoryContext(
            owner=owner,
            name=name,
            url=url,
            languages=context_data.get('languages', []),
            existing_workflows=context_data.get('workflows', []),
            build_system=context_data.get('build_system'),
        )
        
        return self.repo_context
