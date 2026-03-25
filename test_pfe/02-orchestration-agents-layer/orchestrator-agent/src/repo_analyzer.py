"""
Repository Analyzer - Centralized repo reading for the orchestrator.
This component is OPTIONAL - the system works without it (prompt-only mode).
"""
import json
import os
import subprocess
import tempfile
import shutil
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict


@dataclass
class RepoContext:
    """Repository context extracted from analysis"""
    path: str = ""
    is_available: bool = False
    source: str = "none"  # "local", "github", "none"

    # Detected characteristics
    languages: List[str] = field(default_factory=list)
    build_system: Optional[str] = None
    package_managers: List[str] = field(default_factory=list)
    frameworks: List[str] = field(default_factory=list)

    # Existing configurations
    has_dockerfile: bool = False
    has_docker_compose: bool = False
    has_ci_workflows: bool = False
    existing_workflows: List[str] = field(default_factory=list)

    # Important files found
    config_files: Dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RepoAnalyzer:
    """
    Centralized repository analyzer for the orchestrator.
    Supports both local paths and GitHub URLs.
    Falls back gracefully when no repo is provided.
    """

    # File extension to language mapping
    LANGUAGE_EXTENSIONS = {
        '.py': 'Python',
        '.js': 'JavaScript',
        '.ts': 'TypeScript',
        '.jsx': 'React',
        '.tsx': 'React/TypeScript',
        '.java': 'Java',
        '.kt': 'Kotlin',
        '.go': 'Go',
        '.rb': 'Ruby',
        '.php': 'PHP',
        '.cpp': 'C++',
        '.c': 'C',
        '.cs': 'C#',
        '.rs': 'Rust',
        '.swift': 'Swift',
        '.scala': 'Scala',
    }

    # Build system indicators
    BUILD_SYSTEMS = {
        'package.json': 'Node.js/npm',
        'requirements.txt': 'Python/pip',
        'setup.py': 'Python/setuptools',
        'pyproject.toml': 'Python/Poetry',
        'Pipfile': 'Python/Pipenv',
        'pom.xml': 'Java/Maven',
        'build.gradle': 'Java/Gradle',
        'build.gradle.kts': 'Kotlin/Gradle',
        'Cargo.toml': 'Rust/Cargo',
        'go.mod': 'Go',
        'Gemfile': 'Ruby/Bundler',
        'composer.json': 'PHP/Composer',
        'Makefile': 'Make',
        'CMakeLists.txt': 'CMake',
    }

    # Package manager indicators
    PACKAGE_MANAGERS = {
        'package.json': 'npm',
        'yarn.lock': 'yarn',
        'pnpm-lock.yaml': 'pnpm',
        'package-lock.json': 'npm',
        'Pipfile.lock': 'pipenv',
        'poetry.lock': 'poetry',
        'requirements.txt': 'pip',
        'go.sum': 'go modules',
        'Cargo.lock': 'cargo',
        'Gemfile.lock': 'bundler',
        'composer.lock': 'composer',
    }

    # Framework indicators (file -> framework)
    FRAMEWORK_INDICATORS = {
        'manage.py': 'Django',
        'app.py': 'Flask',
        'fastapi': 'FastAPI',
        'next.config.js': 'Next.js',
        'nuxt.config.js': 'Nuxt.js',
        'angular.json': 'Angular',
        'vue.config.js': 'Vue.js',
        'svelte.config.js': 'Svelte',
        'spring': 'Spring Boot',
        'rails': 'Ruby on Rails',
        'laravel': 'Laravel',
    }

    # Important config files to check
    CONFIG_FILES = [
        'README.md',
        'Dockerfile',
        'docker-compose.yml',
        'docker-compose.yaml',
        '.dockerignore',
        'Makefile',
        '.env.example',
        '.gitignore',
        'sonar-project.properties',
        'Jenkinsfile',
        '.travis.yml',
        'azure-pipelines.yml',
        'kubernetes.yml',
        'k8s/',
        'helm/',
    ]

    def __init__(self):
        self._temp_dir: Optional[str] = None

    def analyze(self, repo_path: Optional[str] = None, github_url: Optional[str] = None) -> RepoContext:
        """
        Main entry point for repo analysis.

        Args:
            repo_path: Local path to repository (optional)
            github_url: GitHub URL to clone (optional)

        Returns:
            RepoContext with analysis results, or empty context if no repo provided
        """
        context = RepoContext()

        # Determine the effective path
        effective_path = self._resolve_repo_path(repo_path, github_url, context)

        if not effective_path or not context.is_available:
            print("[RepoAnalyzer] No repository provided - using prompt-only mode")
            return context

        context.path = effective_path

        # Run analysis
        print(f"[RepoAnalyzer] Analyzing repository at: {effective_path}")

        context.languages = self._detect_languages(effective_path)
        context.build_system = self._detect_build_system(effective_path)
        context.package_managers = self._detect_package_managers(effective_path)
        context.frameworks = self._detect_frameworks(effective_path)
        context.config_files = self._check_config_files(effective_path)

        # Docker-related
        context.has_dockerfile = context.config_files.get('Dockerfile', False)
        context.has_docker_compose = (
            context.config_files.get('docker-compose.yml', False) or
            context.config_files.get('docker-compose.yaml', False)
        )

        # CI/CD workflows
        context.existing_workflows = self._find_ci_workflows(effective_path)
        context.has_ci_workflows = len(context.existing_workflows) > 0

        print(f"[RepoAnalyzer] Analysis complete: {len(context.languages)} languages, "
              f"build system: {context.build_system or 'unknown'}")

        return context

    def _resolve_repo_path(
        self,
        repo_path: Optional[str],
        github_url: Optional[str],
        context: RepoContext
    ) -> Optional[str]:
        """Resolve the repository path from local path or GitHub URL"""

        # Priority 1: Local path
        if repo_path and os.path.isdir(repo_path):
            context.is_available = True
            context.source = "local"
            return repo_path

        # Priority 2: GitHub URL (clone to temp)
        if github_url:
            cloned_path = self._clone_github_repo(github_url)
            if cloned_path:
                context.is_available = True
                context.source = "github"
                return cloned_path

        # No repo available
        context.is_available = False
        context.source = "none"
        return None

    def _clone_github_repo(self, github_url: str) -> Optional[str]:
        """Clone a GitHub repository to a temporary directory"""
        try:
            self._temp_dir = tempfile.mkdtemp(prefix="repo_analysis_")
            print(f"[RepoAnalyzer] Cloning {github_url}...")

            result = subprocess.run(
                ["git", "clone", "--depth", "1", github_url, self._temp_dir],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                print(f"[RepoAnalyzer] Clone successful")
                return self._temp_dir
            else:
                print(f"[RepoAnalyzer] Clone failed: {result.stderr}")
                return None

        except Exception as e:
            print(f"[RepoAnalyzer] Error cloning repo: {e}")
            return None

    def _detect_languages(self, repo_path: str) -> List[str]:
        """Detect programming languages in the repository"""
        languages = set()

        try:
            for root, dirs, files in os.walk(repo_path):
                # Skip hidden and common ignore folders
                dirs[:] = [d for d in dirs if not d.startswith('.')
                          and d not in ['node_modules', 'venv', '__pycache__',
                                       'target', 'build', 'dist', 'vendor']]

                for file in files:
                    ext = os.path.splitext(file)[1].lower()
                    if ext in self.LANGUAGE_EXTENSIONS:
                        languages.add(self.LANGUAGE_EXTENSIONS[ext])
        except Exception as e:
            print(f"[RepoAnalyzer] Error detecting languages: {e}")

        return list(languages)

    def _detect_build_system(self, repo_path: str) -> Optional[str]:
        """Detect the primary build system"""
        for file, system in self.BUILD_SYSTEMS.items():
            if os.path.exists(os.path.join(repo_path, file)):
                return system
        return None

    def _detect_package_managers(self, repo_path: str) -> List[str]:
        """Detect package managers used"""
        managers = []
        for file, manager in self.PACKAGE_MANAGERS.items():
            if os.path.exists(os.path.join(repo_path, file)):
                if manager not in managers:
                    managers.append(manager)
        return managers

    def _detect_frameworks(self, repo_path: str) -> List[str]:
        """Detect frameworks used in the project"""
        frameworks = []

        for indicator, framework in self.FRAMEWORK_INDICATORS.items():
            # Check if it's a file
            if os.path.exists(os.path.join(repo_path, indicator)):
                if framework not in frameworks:
                    frameworks.append(framework)
                continue

            # Check in package.json dependencies (for JS frameworks)
            package_json_path = os.path.join(repo_path, 'package.json')
            if os.path.exists(package_json_path):
                try:
                    with open(package_json_path, 'r', encoding='utf-8') as f:
                        pkg = json.load(f)
                        deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}
                        if indicator in deps and framework not in frameworks:
                            frameworks.append(framework)
                except (json.JSONDecodeError, IOError, OSError):
                    pass

            # Check in pom.xml for Spring
            pom_path = os.path.join(repo_path, 'pom.xml')
            if indicator == 'spring' and os.path.exists(pom_path):
                try:
                    with open(pom_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if 'spring-boot' in content.lower() and framework not in frameworks:
                            frameworks.append(framework)
                except (IOError, OSError):
                    pass

        return frameworks

    def _check_config_files(self, repo_path: str) -> Dict[str, bool]:
        """Check for important configuration files"""
        config_status = {}

        for config in self.CONFIG_FILES:
            path = os.path.join(repo_path, config)
            config_status[config] = os.path.exists(path)

        return config_status

    def _find_ci_workflows(self, repo_path: str) -> List[str]:
        """Find existing CI/CD workflow files"""
        workflows = []

        # GitHub Actions
        gh_workflow_dir = os.path.join(repo_path, '.github', 'workflows')
        if os.path.exists(gh_workflow_dir):
            try:
                for file in os.listdir(gh_workflow_dir):
                    if file.endswith(('.yml', '.yaml')):
                        workflows.append(f".github/workflows/{file}")
            except (IOError, OSError):
                pass

        # GitLab CI
        if os.path.exists(os.path.join(repo_path, '.gitlab-ci.yml')):
            workflows.append('.gitlab-ci.yml')

        # Jenkins
        if os.path.exists(os.path.join(repo_path, 'Jenkinsfile')):
            workflows.append('Jenkinsfile')

        # Azure Pipelines
        if os.path.exists(os.path.join(repo_path, 'azure-pipelines.yml')):
            workflows.append('azure-pipelines.yml')

        # Travis CI
        if os.path.exists(os.path.join(repo_path, '.travis.yml')):
            workflows.append('.travis.yml')

        # CircleCI
        if os.path.exists(os.path.join(repo_path, '.circleci', 'config.yml')):
            workflows.append('.circleci/config.yml')

        return workflows

    def cleanup(self):
        """Clean up temporary directories"""
        if self._temp_dir and os.path.exists(self._temp_dir):
            try:
                shutil.rmtree(self._temp_dir)
                print(f"[RepoAnalyzer] Cleaned up temp directory")
            except Exception as e:
                print(f"[RepoAnalyzer] Error cleaning up: {e}")
            self._temp_dir = None


# Convenience function for quick analysis
def analyze_repo(
    repo_path: Optional[str] = None,
    github_url: Optional[str] = None
) -> RepoContext:
    """
    Quick function to analyze a repository.

    Usage:
        # Local repo
        context = analyze_repo(repo_path="/path/to/repo")

        # GitHub URL
        context = analyze_repo(github_url="https://github.com/user/repo")

        # No repo (prompt-only mode)
        context = analyze_repo()  # Returns empty context
    """
    analyzer = RepoAnalyzer()
    try:
        return analyzer.analyze(repo_path, github_url)
    finally:
        analyzer.cleanup()


if __name__ == "__main__":
    # Test the analyzer
    import sys

    if len(sys.argv) > 1:
        test_path = sys.argv[1]
        print(f"Testing with: {test_path}")

        if test_path.startswith("http"):
            ctx = analyze_repo(github_url=test_path)
        else:
            ctx = analyze_repo(repo_path=test_path)
    else:
        print("Testing prompt-only mode (no repo)")
        ctx = analyze_repo()

    print("\n=== Repository Context ===")
    for key, value in ctx.to_dict().items():
        print(f"  {key}: {value}")
