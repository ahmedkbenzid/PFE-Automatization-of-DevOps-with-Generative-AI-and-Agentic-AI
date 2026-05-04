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
        
    # Common monorepo subdirectory names
    _FRONTEND_SUBDIRS = ["frontend", "client", "ui", "web"]
    _BACKEND_SUBDIRS  = ["backend", "api", "server", "service"]

    def collect_from_local_repo(self, repo_path: str) -> Dict[str, Any]:
        """Collect context from a local repository"""
        build_system, frameworks, monorepo_info = self._detect_build_system_and_frameworks(repo_path)
        context = {
            "languages": self._detect_languages(repo_path),
            "build_system": build_system,
            "frameworks": frameworks,
            "workflows": self._find_existing_workflows(repo_path),
            "repo_files": self._get_important_files(repo_path),
            "package_managers": self._detect_package_managers(repo_path),
            **monorepo_info,
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
        """Detect build system/package manager (legacy shim — delegates to new method)."""
        build_system, _, _ = self._detect_build_system_and_frameworks(repo_path)
        return build_system

    def _detect_build_system_and_frameworks(
        self, repo_path: str
    ) -> tuple:
        """Detect build system, frameworks, and monorepo layout details.

        Returns:
            (build_system: str | None, frameworks: List[str], monorepo_info: Dict)
        """
        frameworks: List[str] = []
        monorepo_info: Dict[str, Any] = {}

        # ------------------------------------------------------------------
        # Detect Angular frontend in common subdirectory locations
        # ------------------------------------------------------------------
        angular_dir: Optional[str] = None
        angular_version: Optional[str] = None
        for subdir in self._FRONTEND_SUBDIRS:
            pkg_path = os.path.join(repo_path, subdir, "package.json")
            if os.path.exists(pkg_path):
                try:
                    with open(pkg_path, encoding="utf-8") as f:
                        pkg = json.load(f)
                    all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                    if "@angular/core" in all_deps:
                        angular_dir = subdir
                        angular_version = all_deps["@angular/core"].lstrip("^~")
                        frameworks.append("Angular")
                        monorepo_info["angular_dir"] = angular_dir
                        monorepo_info["angular_version"] = angular_version
                        monorepo_info["frontend_dir"] = angular_dir
                        monorepo_info["nodejs_package_path"] = f"{angular_dir}/package.json"
                        break
                except Exception:
                    pass

        # Also check root-level package.json for Angular
        if not angular_dir:
            root_pkg = os.path.join(repo_path, "package.json")
            if os.path.exists(root_pkg):
                try:
                    with open(root_pkg, encoding="utf-8") as f:
                        pkg = json.load(f)
                    all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                    if "@angular/core" in all_deps:
                        angular_version = all_deps["@angular/core"].lstrip("^~")
                        frameworks.append("Angular")
                        monorepo_info["angular_version"] = angular_version
                        monorepo_info["nodejs_package_path"] = "package.json"
                except Exception:
                    pass

        # ------------------------------------------------------------------
        # Detect Python/FastAPI/Django backend in common subdirectory locations
        # ------------------------------------------------------------------
        backend_dir: Optional[str] = None
        for subdir in self._BACKEND_SUBDIRS:
            req_path = os.path.join(repo_path, subdir, "requirements.txt")
            if os.path.exists(req_path):
                try:
                    content = open(req_path, encoding="utf-8").read().lower()
                    if "fastapi" in content:
                        frameworks.append("FastAPI")
                    elif "django" in content:
                        frameworks.append("Django")
                    elif "flask" in content:
                        frameworks.append("Flask")
                    backend_dir = subdir
                    monorepo_info["backend_dir"] = backend_dir
                    monorepo_info["python_requirements_path"] = f"{subdir}/requirements.txt"
                    break
                except Exception:
                    pass

        # Check root-level requirements.txt if no subdir found
        if not backend_dir:
            root_req = os.path.join(repo_path, "requirements.txt")
            if os.path.exists(root_req):
                try:
                    content = open(root_req, encoding="utf-8").read().lower()
                    if "fastapi" in content:
                        frameworks.append("FastAPI")
                    elif "django" in content:
                        frameworks.append("Django")
                    elif "flask" in content:
                        frameworks.append("Flask")
                    monorepo_info["python_requirements_path"] = "requirements.txt"
                except Exception:
                    pass

        # ------------------------------------------------------------------
        # Determine monorepo flag
        # ------------------------------------------------------------------
        if angular_dir or backend_dir:
            monorepo_info["is_monorepo"] = bool(angular_dir and backend_dir)

        # ------------------------------------------------------------------
        # Determine build system label
        # ------------------------------------------------------------------
        if angular_dir and backend_dir:
            build_system = "Angular + Python"
        elif angular_dir:
            build_system = "Angular/npm"
        else:
            # Fall back to root-level indicators
            root_indicators = {
                "package.json": "npm/Node.js",
                "requirements.txt": "Python/pip",
                "setup.py": "Python/setuptools",
                "pyproject.toml": "Python/Poetry",
                "Cargo.toml": "Rust",
                "go.mod": "Go",
                "pom.xml": "Maven",
                "build.gradle": "Gradle",
                "Gemfile": "Ruby/Bundler",
            }
            build_system = None
            for file, system in root_indicators.items():
                if os.path.exists(os.path.join(repo_path, file)):
                    build_system = system
                    break

        return build_system, frameworks, monorepo_info
    
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
