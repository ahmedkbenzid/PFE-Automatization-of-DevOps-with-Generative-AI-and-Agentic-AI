"""
Repository Analyzer - centralized repo reading for the orchestrator.

Three analysis modes:
    1. GitHub mode (github_url provided) → uses GitHub MCP server by default,
                                                                                 with optional PyGithub fallback.
    2. Local mode (repo_path provided) → walks local filesystem.
    3. Prompt-only mode (nothing) → returns empty RepoContext.

GitHub integration strategy:
    - Primary: MCP server tools (`MCP_GITHUB_ENABLED=true`)
    - Fallback: PyGithub direct API when MCP is disabled or unavailable
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .github_manager import GitHubURLParser, GitHubMCPClient, ChangeDetector
from .models.github_types import GitHubRepoInfo, ChangeAnalysis, CommitComparison, ChangedFile


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class MCPClientConfig:
    """
    Connection config for GitHub MCP access.

    Environment variables:
      - MCP_GITHUB_ENABLED: enable MCP-based repository analysis
      - MCP_GITHUB_SERVER_COMMAND: command used to launch MCP server
      - MCP_GITHUB_SERVER_ARGS: arguments used to launch MCP server
      - MCP_GITHUB_CALL_TIMEOUT: timeout per MCP request
      - MCP_GITHUB_STRICT: if true, do not fallback to PyGithub
            - GITHUB_PERSONAL_ACCESS_TOKEN: official GitHub MCP token variable
            - GITHUB_HOST: GitHub or GHES host URL
    """
    enabled: bool = os.getenv("MCP_GITHUB_ENABLED", "true").lower() == "true"
    server_command: str = os.getenv("MCP_GITHUB_SERVER_COMMAND", "docker")
    server_args: str = os.getenv(
        "MCP_GITHUB_SERVER_ARGS",
        "run -i --rm -e GITHUB_PERSONAL_ACCESS_TOKEN -e GITHUB_HOST ghcr.io/github/github-mcp-server",
    )
    call_timeout: int = int(os.getenv("MCP_GITHUB_CALL_TIMEOUT", "30"))
    strict_mode: bool = os.getenv("MCP_GITHUB_STRICT", "false").lower() == "true"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class RepoContext:
    # -- Source ---------------------------------------------------------------
    owner: str = ""                        # GitHub owner
    repo_name: str = ""                    # GitHub repo name
    github_url: str = ""                   # Full GitHub URL for artifact tracking
    default_branch: str = ""              # e.g. "main"
    latest_commit_sha: str = ""
    latest_commit_message: str = ""

    # -- Change Detection (Phase 2) -------------------------------------------
    previous_commit_sha: Optional[str] = None  # SHA from storage/cache
    has_changes: bool = False
    changed_files: List[str] = field(default_factory=list)  # Files changed since last commit
    affected_agents: tuple = field(default_factory=tuple)  # Agents needing rerun
    change_summary: str = ""

    # -- Detected characteristics ---------------------------------------------
    languages: List[str] = field(default_factory=list)
    frameworks: List[str] = field(default_factory=list)
    build_system: Optional[str] = None
    package_managers: List[str] = field(default_factory=list)

    # -- Existing configurations ----------------------------------------------
    has_dockerfile: bool = False
    has_docker_compose: bool = False
    has_kubernetes: bool = False
    has_terraform: bool = False
    has_github_actions: bool = False
    has_helm: bool = False
    has_prometheus: bool = False

    # -- Important files found ------------------------------------------------
    ci_workflows: List[str] = field(default_factory=list)
    terraform_files: List[str] = field(default_factory=list)
    k8s_manifests: List[str] = field(default_factory=list)
    dockerfile_paths: List[str] = field(default_factory=list)

    # -- Raw tree snapshot (top-level paths) ----------------------------------
    tree_snapshot: List[str] = field(default_factory=list)

    # -- Analysis metadata ----------------------------------------------------
    analysis_mode: str = "prompt-only"    # "github" | "local" | "prompt-only"
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# GitHub API analysis using PyGithub
# ---------------------------------------------------------------------------

class _GitHubAPIAnalyzer:
    """Uses PyGithub to analyze a remote repository via GitHub API."""

    _EXT_LANGUAGES: Dict[str, str] = {
        ".py": "Python",      ".js": "JavaScript",  ".ts": "TypeScript",
        ".go": "Go",          ".rs": "Rust",         ".java": "Java",
        ".rb": "Ruby",        ".cs": "C#",           ".cpp": "C++",
        ".tf": "HCL",         ".yaml": "YAML",       ".yml": "YAML",
    }
    _FRAMEWORK_FILES: Dict[str, str] = {
        "requirements.txt": "Python",    "pyproject.toml": "Python",
        "package.json":     "Node.js",   "go.mod":         "Go",
        "pom.xml":          "Java/Maven","build.gradle":   "Java/Gradle",
        "Cargo.toml":       "Rust",      "Gemfile":        "Ruby",
        "composer.json":    "PHP",
    }
    _PACKAGE_MANAGERS: Dict[str, str] = {
        "package.json":     "npm/yarn",  "requirements.txt": "pip",
        "pyproject.toml":   "poetry/pip","go.mod":           "go modules",
        "Cargo.toml":       "cargo",     "pom.xml":          "maven",
        "build.gradle":     "gradle",
    }

    def __init__(self, token: str):
        """Initialize GitHub API client."""
        try:
            from github import Github
            self.github = Github(token)
            self.token = token
        except ImportError:
            raise RuntimeError("PyGithub not installed. Run: pip install PyGithub")

    def analyse(self, owner: str, repo: str,
                previous_commit_sha: Optional[str] = None,
                deep: bool = False) -> RepoContext:
        """Analyze repository using GitHub API.

        Args:
            owner: Repository owner
            repo: Repository name
            previous_commit_sha: Previous commit for change detection
            deep: If False (default), use fast shallow analysis (single API call).
                  If True, use deep recursive analysis (multiple API calls).
        """
        ctx = RepoContext(owner=owner, repo_name=repo, analysis_mode="github")
        ctx.github_url = f"https://github.com/{owner}/{repo}"

        try:
            # Get repository object
            repo_obj = self.github.get_user(owner).get_repo(repo)

            # Step 1 — latest commit
            self._fetch_latest_commit(repo_obj, ctx)

            # Step 2 — detect changes if previous commit is known
            if previous_commit_sha and ctx.latest_commit_sha != previous_commit_sha:
                self._detect_changes(repo_obj, owner, repo, previous_commit_sha, ctx)

            # Step 3 — get file tree (fast or deep)
            if deep:
                paths = self._fetch_tree_deep(repo_obj, ctx)
            else:
                paths = self._fetch_tree_fast(repo_obj, ctx.latest_commit_sha, ctx)

            # Step 4 — classify files
            self._classify_paths(paths, ctx)

            return ctx

        except Exception as e:
            ctx.error = f"GitHub API error: {str(e)}"
            return ctx

    def _fetch_latest_commit(self, repo_obj: Any, ctx: RepoContext) -> None:
        """Get latest commit info."""
        try:
            commits = repo_obj.get_commits()
            if commits.totalCount > 0:
                latest = commits[0]
                ctx.latest_commit_sha = latest.sha[:12]
                ctx.latest_commit_message = (
                    latest.commit.message.splitlines()[0][:120]
                )
                ctx.default_branch = repo_obj.default_branch
        except Exception as e:
            ctx.error = f"Failed to fetch commits: {str(e)}"

    def _detect_changes(self, repo_obj: Any, owner: str, repo: str,
                       previous_sha: str, ctx: RepoContext) -> None:
        """Detect changes between commits."""
        try:
            comparison = repo_obj.compare(previous_sha, ctx.latest_commit_sha)
            changed_files = []

            for file in comparison.files:
                changed_files.append(file.filename)
                ctx.changed_files.append(file.filename)

            # Use Phase 1 ChangeDetector
            comparison_obj = CommitComparison(
                base_sha=previous_sha,
                head_sha=ctx.latest_commit_sha,
                files_changed=[
                    ChangedFile(path=p, status="modified")
                    for p in changed_files
                ]
            )

            repo_info = GitHubRepoInfo(owner=owner, repo=ctx.repo_name)
            analysis = ChangeDetector.analyze_changes(comparison_obj, repo_info)

            ctx.has_changes = analysis.requires_update
            ctx.affected_agents = tuple(sorted(analysis.affected_agents))
            ctx.change_summary = analysis.summary
            ctx.previous_commit_sha = previous_sha

        except Exception as e:
            ctx.error = (ctx.error or "") + f" | change detection failed: {str(e)}"

    def _fetch_tree_fast(self, repo_obj: Any, commit_sha: str, ctx: RepoContext) -> List[str]:
        """Fast tree fetching using GitHub's tree API (single API call).

        Uses recursive=1 to get all files in one request, avoiding N+1 API calls.
        """
        paths: List[str] = []
        try:
            # Get the tree with recursive flag - single API call regardless of depth
            tree = repo_obj.get_git_tree(commit_sha, recursive=True)

            for item in tree.tree:
                if item.type == "blob":  # Only include files, not dirs
                    paths.append(item.path)

            ctx.tree_snapshot = paths[:200]  # cap for safety

        except Exception as e:
            ctx.error = f"Failed to fetch tree (fast mode): {str(e)}"

        return paths

    def _fetch_tree_deep(self, repo_obj: Any, ctx: RepoContext) -> List[str]:
        """Deep tree fetching using recursive get_contents (multiple API calls).

        This is the old behavior - makes many API calls but follows symlinks/nested repos.
        Only use when deep analysis is explicitly requested.
        """
        paths: List[str] = []
        try:
            # Get contents recursively
            def walk_tree(content_list, prefix=""):
                for item in content_list:
                    path = f"{prefix}{item.name}" if prefix else item.name
                    if item.type == "dir":
                        try:
                            walk_tree(repo_obj.get_contents(item.path), f"{path}/")
                        except:
                            pass
                    else:
                        paths.append(path)

            walk_tree(repo_obj.get_contents(""))
            ctx.tree_snapshot = paths[:200]  # cap for safety

        except Exception as e:
            ctx.error = f"Failed to fetch tree (deep mode): {str(e)}"

        return paths

    def _classify_paths(self, paths: List[str], ctx: RepoContext) -> None:
        """Classify files by extension and filename."""
        languages_seen: set = set()
        frameworks_seen: set = set()
        pm_seen: set = set()

        for path in paths:
            fname = Path(path).name
            ext = Path(path).suffix.lower()
            lower_path = path.lower()

            # Language detection
            if ext in self._EXT_LANGUAGES:
                languages_seen.add(self._EXT_LANGUAGES[ext])

            # Framework + package manager
            if fname in self._FRAMEWORK_FILES:
                frameworks_seen.add(self._FRAMEWORK_FILES[fname])
            if fname in self._PACKAGE_MANAGERS:
                pm_seen.add(self._PACKAGE_MANAGERS[fname])

            # Dockerfile
            if fname == "Dockerfile" or fname.startswith("Dockerfile."):
                ctx.has_dockerfile = True
                ctx.dockerfile_paths.append(path)

            # Docker Compose
            if fname in ("docker-compose.yml", "docker-compose.yaml"):
                ctx.has_docker_compose = True

            # Terraform
            if ext == ".tf":
                ctx.has_terraform = True
                ctx.terraform_files.append(path)

            # GitHub Actions
            if ".github/workflows" in lower_path and ext in (".yml", ".yaml"):
                ctx.has_github_actions = True
                ctx.ci_workflows.append(path)

            # Kubernetes
            is_k8s_dir = any(p in lower_path for p in ("k8s/", "kubernetes/", "manifests/"))
            is_k8s_filename = fname.lower() in (
                "deployment.yaml", "deployment.yml",
                "service.yaml", "service.yml",
            )
            if (is_k8s_dir or is_k8s_filename) and ext in (".yml", ".yaml"):
                ctx.has_kubernetes = True
                ctx.k8s_manifests.append(path)

            # Helm
            if fname == "Chart.yaml" or "helm/" in lower_path:
                ctx.has_helm = True

            # Prometheus
            if "prometheus" in lower_path:
                ctx.has_prometheus = True

            # Build system
            if not ctx.build_system:
                if fname == "Makefile":
                    ctx.build_system = "make"
                elif fname in ("build.gradle", "build.gradle.kts"):
                    ctx.build_system = "gradle"
                elif fname == "pom.xml":
                    ctx.build_system = "maven"
                elif fname == "CMakeLists.txt":
                    ctx.build_system = "cmake"

        ctx.languages = sorted(languages_seen)
        ctx.frameworks = sorted(frameworks_seen)
        ctx.package_managers = sorted(pm_seen)


class _GitHubMCPAnalyzer:
    """Uses GitHub MCP server tools to analyze a remote repository."""

    _EXT_LANGUAGES = _GitHubAPIAnalyzer._EXT_LANGUAGES
    _FRAMEWORK_FILES = _GitHubAPIAnalyzer._FRAMEWORK_FILES
    _PACKAGE_MANAGERS = _GitHubAPIAnalyzer._PACKAGE_MANAGERS

    def __init__(self, token: str, config: MCPClientConfig):
        self.token = token
        self.config = config

    def analyse(self, owner: str, repo: str, deep: bool = False) -> RepoContext:
        """Analyze repository via MCP server tools."""
        ctx = RepoContext(owner=owner, repo_name=repo, analysis_mode="mcp")
        ctx.github_url = f"https://github.com/{owner}/{repo}"

        try:
            with GitHubMCPClient(
                token=self.token,
                server_command=self.config.server_command,
                server_args=self.config.server_args,
                call_timeout=self.config.call_timeout,
            ) as client:
                metadata = client.get_repo_metadata(owner, repo)
                if isinstance(metadata, dict):
                    default_branch = metadata.get("default_branch")
                    if isinstance(default_branch, str):
                        ctx.default_branch = default_branch

                commit_sha = client.get_latest_commit(owner, repo, branch=ctx.default_branch or "main")
                if commit_sha:
                    ctx.latest_commit_sha = commit_sha[:12]

                # MCP path traversal already returns recursive files; deep flag kept for API compatibility.
                paths = client.list_repository_files(owner, repo)
                ctx.tree_snapshot = paths[:200]

                self._classify_paths(paths, ctx)

            return ctx

        except Exception as e:
            ctx.error = f"MCP analysis failed: {str(e)}"
            return ctx

    def _classify_paths(self, paths: List[str], ctx: RepoContext) -> None:
        """Classify files by extension and filename."""
        languages_seen: set = set()
        frameworks_seen: set = set()
        pm_seen: set = set()

        for path in paths:
            fname = Path(path).name
            ext = Path(path).suffix.lower()
            lower_path = path.lower()

            # Language detection
            if ext in self._EXT_LANGUAGES:
                languages_seen.add(self._EXT_LANGUAGES[ext])

            # Framework + package manager
            if fname in self._FRAMEWORK_FILES:
                frameworks_seen.add(self._FRAMEWORK_FILES[fname])
            if fname in self._PACKAGE_MANAGERS:
                pm_seen.add(self._PACKAGE_MANAGERS[fname])

            # Dockerfile
            if fname == "Dockerfile" or fname.startswith("Dockerfile."):
                ctx.has_dockerfile = True
                ctx.dockerfile_paths.append(path)

            # Docker Compose
            if fname in ("docker-compose.yml", "docker-compose.yaml"):
                ctx.has_docker_compose = True

            # Terraform
            if ext == ".tf":
                ctx.has_terraform = True
                ctx.terraform_files.append(path)

            # GitHub Actions
            if ".github/workflows" in lower_path and ext in (".yml", ".yaml"):
                ctx.has_github_actions = True
                ctx.ci_workflows.append(path)

            # Kubernetes
            is_k8s_dir = any(p in lower_path for p in ("k8s/", "kubernetes/", "manifests/"))
            is_k8s_filename = fname.lower() in (
                "deployment.yaml", "deployment.yml",
                "service.yaml", "service.yml",
            )
            if (is_k8s_dir or is_k8s_filename) and ext in (".yml", ".yaml"):
                ctx.has_kubernetes = True
                ctx.k8s_manifests.append(path)

            # Helm
            if fname == "Chart.yaml" or "helm/" in lower_path:
                ctx.has_helm = True

            # Prometheus
            if "prometheus" in lower_path:
                ctx.has_prometheus = True

            # Build system
            if not ctx.build_system:
                if fname == "Makefile":
                    ctx.build_system = "make"
                elif fname in ("build.gradle", "build.gradle.kts"):
                    ctx.build_system = "gradle"
                elif fname == "pom.xml":
                    ctx.build_system = "maven"
                elif fname == "CMakeLists.txt":
                    ctx.build_system = "cmake"

        ctx.languages = sorted(languages_seen)
        ctx.frameworks = sorted(frameworks_seen)
        ctx.package_managers = sorted(pm_seen)


# ---------------------------------------------------------------------------
# Local filesystem analysis (unchanged)
# ---------------------------------------------------------------------------

class _LocalRepoAnalyzer:
    """Walks a local filesystem path to produce a RepoContext."""

    _EXT_LANGUAGES = _GitHubAPIAnalyzer._EXT_LANGUAGES
    _FRAMEWORK_FILES = _GitHubAPIAnalyzer._FRAMEWORK_FILES
    _PACKAGE_MANAGERS = _GitHubAPIAnalyzer._PACKAGE_MANAGERS

    def analyse(self, repo_path: str) -> RepoContext:
        ctx = RepoContext(analysis_mode="local")
        languages_seen: set = set()
        frameworks_seen: set = set()
        pm_seen: set = set()

        _SKIP_DIRS = {"node_modules", "__pycache__", ".git", "dist", "build",
                      ".venv", "venv", ".tox"}

        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [
                d for d in dirs
                if not d.startswith(".") and d not in _SKIP_DIRS
            ]
            rel_root = os.path.relpath(root, repo_path)

            for fname in files:
                rel_path = os.path.join(rel_root, fname).lstrip("./")
                ext = Path(fname).suffix.lower()
                lower_rel = rel_path.lower()

                if ext in self._EXT_LANGUAGES:
                    languages_seen.add(self._EXT_LANGUAGES[ext])
                if fname in self._FRAMEWORK_FILES:
                    frameworks_seen.add(self._FRAMEWORK_FILES[fname])
                if fname in self._PACKAGE_MANAGERS:
                    pm_seen.add(self._PACKAGE_MANAGERS[fname])

                if fname == "Dockerfile" or fname.startswith("Dockerfile."):
                    ctx.has_dockerfile = True
                    ctx.dockerfile_paths.append(rel_path)
                if fname in ("docker-compose.yml", "docker-compose.yaml"):
                    ctx.has_docker_compose = True
                if ext == ".tf":
                    ctx.has_terraform = True
                    ctx.terraform_files.append(rel_path)
                if ".github/workflows" in lower_rel and ext in (".yml", ".yaml"):
                    ctx.has_github_actions = True
                    ctx.ci_workflows.append(rel_path)
                if fname == "Chart.yaml" or "helm/" in lower_rel:
                    ctx.has_helm = True
                if any(p in lower_rel for p in ("k8s/", "kubernetes/", "manifests/")):
                    if ext in (".yml", ".yaml"):
                        ctx.has_kubernetes = True
                        ctx.k8s_manifests.append(rel_path)

                if not ctx.build_system:
                    if fname == "Makefile":
                        ctx.build_system = "make"
                    elif fname in ("build.gradle", "build.gradle.kts"):
                        ctx.build_system = "gradle"
                    elif fname == "pom.xml":
                        ctx.build_system = "maven"

        ctx.languages = sorted(languages_seen)
        ctx.frameworks = sorted(frameworks_seen)
        ctx.package_managers = sorted(pm_seen)
        return ctx


# ---------------------------------------------------------------------------
# GitHub URL parser - delegates to Phase 1 GitHubURLParser
# ---------------------------------------------------------------------------

def _parse_github_url(url: str) -> Tuple[str, str]:
    """Extract (owner, repo) from GitHub URL using Phase 1 parser."""
    repo_info = GitHubURLParser.parse(url)
    return repo_info.owner, repo_info.repo


# ---------------------------------------------------------------------------
# Public facade
# ---------------------------------------------------------------------------

@dataclass
class RepoAnalyzer:
    """
    Centralized repository analyzer for the orchestrator.

    Supports three modes:
        - GitHub (GitHub URL)   : MCP-first analysis with optional PyGithub fallback.
        - Local (file path)     : walks local filesystem.
        - Prompt-only           : returns empty RepoContext.

    Usage:
        analyzer = RepoAnalyzer()

        # GitHub mode
        ctx = analyzer.analyze(github_url="https://github.com/user/repo")

        # Local mode
        ctx = analyzer.analyze(repo_path="/path/to/repo")

        # Prompt-only
        ctx = analyzer.analyze()
    """

    mcp_config: MCPClientConfig = field(default_factory=MCPClientConfig)
    _temp_dirs: List[str] = field(default_factory=list, repr=False)

    def analyze(
        self,
        repo_path: Optional[str] = None,
        github_url: Optional[str] = None,
        deep: bool = False,
    ) -> RepoContext:
        """
        Main entry point. Returns a RepoContext in all cases.
        Errors are recorded in ctx.error, never raised.

        Args:
            repo_path: Local repository path
            github_url: GitHub repository URL
            deep: If False (default), use fast shallow GitHub API analysis.
                  If True, use deep recursive analysis (slower but more thorough).
        """
        if github_url:
            return self._analyze_remote_github(github_url, deep=deep)
        if repo_path:
            return self._analyze_local(repo_path)
        return RepoContext(analysis_mode="prompt-only")

    def cleanup(self) -> None:
        """Remove any temporary directories created during analysis."""
        for d in self._temp_dirs:
            shutil.rmtree(d, ignore_errors=True)
        self._temp_dirs.clear()

    # -- Private --------------------------------------------------------------

    def _analyze_remote_github(self, github_url: str, deep: bool = False) -> RepoContext:
        """
        Parse URL and analyze remote repository through configured GitHub integration.

        Flow:
          1) Try MCP server when enabled.
          2) Fallback to PyGithub unless strict MCP mode is enabled.

        Args:
            github_url: GitHub repository URL
            deep: If False, use fast tree API in PyGithub fallback.
                  If True, use deep recursive analysis in PyGithub fallback.
        """
        try:
            owner, repo = _parse_github_url(github_url)
        except ValueError as exc:
            return RepoContext(analysis_mode="github", error=str(exc))

        # Get GitHub token
        token = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN", "") or os.getenv("GITHUB_TOKEN", "")
        if not token:
            return RepoContext(
                owner=owner, repo_name=repo,
                analysis_mode="github",
            error="GITHUB_PERSONAL_ACCESS_TOKEN (or GITHUB_TOKEN) environment variable not set. "
                      "Add it to .env file.",
            )

        mcp_enabled = self.mcp_config.enabled
        if mcp_enabled:
            mcp_ctx = _GitHubMCPAnalyzer(token, self.mcp_config).analyse(owner, repo, deep=deep)
            if not mcp_ctx.error:
                return mcp_ctx

            if self.mcp_config.strict_mode:
                return mcp_ctx

        try:
            api_ctx = _GitHubAPIAnalyzer(token).analyse(owner, repo, None, deep=deep)
            if mcp_enabled and api_ctx.error is None:
                # Preserve MCP failure hint for visibility when fallback was required.
                api_ctx.analysis_mode = "github"
            return api_ctx
        except Exception as exc:
            return RepoContext(
                owner=owner,
                repo_name=repo,
                analysis_mode="github",
                error=f"GitHub analysis failed: {str(exc)}",
            )

    def _analyze_local(self, repo_path: str) -> RepoContext:
        if not os.path.isdir(repo_path):
            return RepoContext(
                analysis_mode="local",
                error=f"Path does not exist or is not a directory: {repo_path}",
            )
        try:
            return _LocalRepoAnalyzer().analyse(repo_path)
        except Exception as exc:
            return RepoContext(
                analysis_mode="local",
                error=f"Local analysis failed: {str(exc)}",
            )


# ---------------------------------------------------------------------------
# Convenience function (backward-compatible with original API)
# ---------------------------------------------------------------------------

def analyze_repo(
    repo_path: Optional[str] = None,
    github_url: Optional[str] = None,
    mcp_config: Optional[MCPClientConfig] = None,
    deep: bool = False,
) -> RepoContext:
    """
    Quick function to analyze a repository.

    Args:
        repo_path: Local repository path
        github_url: GitHub repository URL
        mcp_config: Optional MCP client configuration
        deep: If False (default), use fast GitHub API tree endpoint.
              If True, use deep recursive analysis (slower).

    Examples:
        # GitHub mode (MCP-first) — fast shallow analysis fallback (default)
        ctx = analyze_repo(github_url="https://github.com/user/repo")

        # GitHub mode — deep analysis
        ctx = analyze_repo(github_url="https://github.com/user/repo", deep=True)

        # Local mode
        ctx = analyze_repo(repo_path="/path/to/repo")

        # Prompt-only
        ctx = analyze_repo()

    Returns:
        RepoContext — always, even on failure (check ctx.error).
    """
    config = mcp_config or MCPClientConfig()
    analyzer = RepoAnalyzer(mcp_config=config)
    try:
        return analyzer.analyze(repo_path=repo_path, github_url=github_url, deep=deep)
    finally:
        analyzer.cleanup()
