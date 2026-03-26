"""
Repository Analyzer - Centralized repo reading for the orchestrator.

Three analysis modes:
  1. GitHub API mode (github_url provided) → uses PyGithub to read repo via GitHub API,
                                              no cloning, no Docker, no temp dirs.
  2. Local mode (repo_path provided) → walks local filesystem (unchanged behaviour).
  3. Prompt-only mode (nothing) → returns empty RepoContext (unchanged behaviour).

GitHub API Integration:
  - Uses PyGithub library with GITHUB_TOKEN
  - Direct API calls - no Docker container overhead
  - Analyzes file tree to detect languages, frameworks, build systems
  - Extracts commit info and detects existing configurations
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

from .github_manager import GitHubURLParser, ChangeDetector
from .models.github_types import GitHubRepoInfo, ChangeAnalysis, CommitComparison, ChangedFile


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class MCPClientConfig:
    """
    Connection config for GitHub API access.

    Uses PyGithub for direct API calls instead of Docker MCP.
    Required env vars (read from environment at runtime):
        GITHUB_TOKEN  - GitHub Personal Access Token with repo scope
    """
    # Timeout in seconds for each API call
    call_timeout: int = 30


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
                previous_commit_sha: Optional[str] = None) -> RepoContext:
        """Analyze repository using GitHub API."""
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

            # Step 3 — get file tree
            paths = self._fetch_tree(repo_obj, ctx)

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

    def _fetch_tree(self, repo_obj: Any, ctx: RepoContext) -> List[str]:
        """Get file tree from repository."""
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
            ctx.error = f"Failed to fetch tree: {str(e)}"

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
        - GitHub API (GitHub URL) : calls GitHub API via PyGithub, no cloning or Docker.
        - Local (file path)      : walks local filesystem.
        - Prompt-only           : returns empty RepoContext.

    Usage:
        analyzer = RepoAnalyzer()

        # GitHub API mode
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
    ) -> RepoContext:
        """
        Main entry point. Returns a RepoContext in all cases.
        Errors are recorded in ctx.error, never raised.
        """
        if github_url:
            return self._analyze_via_github_api(github_url)
        if repo_path:
            return self._analyze_local(repo_path)
        return RepoContext(analysis_mode="prompt-only")

    def cleanup(self) -> None:
        """Remove any temporary directories created during analysis."""
        for d in self._temp_dirs:
            shutil.rmtree(d, ignore_errors=True)
        self._temp_dirs.clear()

    # -- Private --------------------------------------------------------------

    def _analyze_via_github_api(self, github_url: str) -> RepoContext:
        """
        Parse URL → use PyGithub to analyze remotely → return.
        No cloning, no Docker, no temp dirs, no filesystem writes.
        """
        try:
            owner, repo = _parse_github_url(github_url)
        except ValueError as exc:
            return RepoContext(analysis_mode="github", error=str(exc))

        # Get GitHub token
        token = os.getenv("GITHUB_TOKEN", "")
        if not token:
            return RepoContext(
                owner=owner, repo_name=repo,
                analysis_mode="github",
                error="GITHUB_TOKEN environment variable not set. "
                      "Add it to .env file.",
            )

        # Try to retrieve previous commit SHA from artifact storage (Phase 2)
        previous_sha = None
        try:
            from .artifact_storage import ArtifactDatabase
            from .config import OrchestratorConfig
            db = ArtifactDatabase(OrchestratorConfig.ARTIFACT_DB_PATH)
            repo_state = db.get_repository_state(github_url)
            if repo_state:
                previous_sha = repo_state.last_commit_sha
        except Exception:
            pass

        try:
            analyzer = _GitHubAPIAnalyzer(token)
            return analyzer.analyse(owner, repo, previous_sha)
        except Exception as exc:
            return RepoContext(
                owner=owner, repo_name=repo,
                analysis_mode="github",
                error=f"GitHub API analysis failed: {str(exc)}",
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
) -> RepoContext:
    """
    Quick function to analyze a repository.

    Examples:
        # GitHub API mode — reads repo via API, no cloning or Docker
        ctx = analyze_repo(github_url="https://github.com/user/repo")

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
        return analyzer.analyze(repo_path=repo_path, github_url=github_url)
    finally:
        analyzer.cleanup()

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .github_manager import GitHubURLParser, ChangeDetector
from .models.github_types import GitHubRepoInfo, ChangeAnalysis, CommitComparison, ChangedFile


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class MCPClientConfig:
    """
    Connection config for the GitHub MCP server.

    The server is started as a subprocess (stdio transport).
    The container must already be pulled:
        docker pull ghcr.io/github/github-mcp-server

    Required env vars (read from environment at runtime):
        GITHUB_PERSONAL_ACCESS_TOKEN  - GitHub PAT with repo + read:org scopes
    """
    docker_image: str = "ghcr.io/github/github-mcp-server"
    # Toolsets we actually need — keeps context small for the LLM
    toolsets: str = "repos,git,actions"
    # Timeout in seconds for each MCP tool call
    call_timeout: int = 30
    # Fallback to PyGithub if Docker not available
    fallback_to_pygithub: bool = True


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class RepoContext:
    # -- Source ---------------------------------------------------------------
    owner: str = ""                        # GitHub owner  (MCP mode only)
    repo_name: str = ""                    # GitHub repo name (MCP mode only)
    github_url: str = ""                   # Full GitHub URL for artifact tracking
    default_branch: str = ""              # e.g. "main"
    latest_commit_sha: str = ""
    latest_commit_message: str = ""

    # -- Change Detection (Phase 2) -------------------------------------------
    previous_commit_sha: Optional[str] = None  # SHA from storage/cache
    has_changes: bool = False
    changed_files: List[str] = field(default_factory=list)  # Files changed since last commit
    affected_agents: tuple = field(default_factory=tuple)  # Agents needing rerun (cicd-agent, docker-agent, iac-agent)
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
    analysis_mode: str = "prompt-only"    # "mcp" | "local" | "prompt-only"
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# MCP stdio client (thin, no external SDK dependency)
# ---------------------------------------------------------------------------

class _MCPStdioClient:
    """
    Minimal JSON-RPC 2.0 client over stdio to the GitHub MCP server.

    Lifecycle:
        with _MCPStdioClient(config) as client:
            result = client.call("get_file_contents", {"owner": ..., ...})
    """

    def __init__(self, config: MCPClientConfig) -> None:
        self._config = config
        self._proc: Optional[subprocess.Popen] = None
        self._msg_id = 0

    # -- Context manager ------------------------------------------------------

    def __enter__(self) -> "_MCPStdioClient":
        token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")
        if not token:
            raise EnvironmentError(
                "GITHUB_PERSONAL_ACCESS_TOKEN is not set. "
                "Add it to your .env file and never commit it."
            )
        cmd = [
            "docker", "run", "-i", "--rm",
            "-e", "GITHUB_PERSONAL_ACCESS_TOKEN",
            "-e", f"GITHUB_TOOLSETS={self._config.toolsets}",
            self._config.docker_image,
        ]
        env = {**os.environ, "GITHUB_PERSONAL_ACCESS_TOKEN": token}
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            bufsize=1,
        )
        self._initialize()
        return self

    def __exit__(self, *_) -> None:
        if self._proc:
            try:
                self._proc.stdin.close()
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.kill()

    # -- Public API -----------------------------------------------------------

    def call(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """
        Call an MCP tool and return the parsed result content.
        Raises RuntimeError on protocol errors or tool errors.
        """
        self._msg_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._msg_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": params},
        }
        self._send(request)
        response = self._recv()

        if "error" in response:
            raise RuntimeError(
                f"MCP tool '{tool_name}' returned error: {response['error']}"
            )

        # MCP tools/call returns { result: { content: [...] } }
        content_blocks = response.get("result", {}).get("content", [])
        texts = [b["text"] for b in content_blocks if b.get("type") == "text"]
        raw = "\n".join(texts)

        # Try to parse as JSON — many tools return JSON strings
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    # -- Internal helpers -----------------------------------------------------

    def _initialize(self) -> None:
        """Send MCP initialize handshake."""
        self._msg_id += 1
        init_req = {
            "jsonrpc": "2.0",
            "id": self._msg_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "orchestrator-agent", "version": "1.0"},
                "capabilities": {},
            },
        }
        self._send(init_req)
        self._recv()  # consume initialize response
        # Send initialized notification (no response expected)
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _send(self, payload: Dict[str, Any]) -> None:
        line = json.dumps(payload) + "\n"
        self._proc.stdin.write(line)
        self._proc.stdin.flush()

    def _recv(self) -> Dict[str, Any]:
        line = self._proc.stdout.readline()
        if not line:
            stderr = self._proc.stderr.read()
            raise RuntimeError(
                f"MCP server closed stdout unexpectedly. stderr: {stderr}"
            )
        return json.loads(line)


# ---------------------------------------------------------------------------
# GitHub URL parser - delegates to Phase 1 GitHubURLParser
# ---------------------------------------------------------------------------

def _parse_github_url(url: str) -> Tuple[str, str]:
    """
    Extract (owner, repo) from GitHub URL using Phase 1 parser.

    Delegates to github_manager.GitHubURLParser for consistency.
    """
    repo_info = GitHubURLParser.parse(url)
    return repo_info.owner, repo_info.repo


# ---------------------------------------------------------------------------
# MCP-based analysis
# ---------------------------------------------------------------------------

class _MCPRepoAnalyzer:
    """Uses GitHub MCP tools to analyse a remote repository."""

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

    def __init__(self, client: _MCPStdioClient) -> None:
        self._client = client

    def analyse(self, owner: str, repo: str,
                previous_commit_sha: Optional[str] = None) -> RepoContext:
        ctx = RepoContext(owner=owner, repo_name=repo, analysis_mode="mcp")
        ctx.github_url = f"https://github.com/{owner}/{repo}"

        # Step 1 — latest commit (SHA + message)
        self._fetch_latest_commit(owner, repo, ctx)

        # Step 2 — detect changes if previous commit is known (Phase 2)
        if previous_commit_sha and ctx.latest_commit_sha != previous_commit_sha:
            self._detect_changes(owner, repo, previous_commit_sha, ctx)

        # Step 3 — full recursive tree of file paths
        paths = self._fetch_tree(owner, repo, ctx)

        # Step 4 — classify everything from paths, zero extra API calls
        self._classify_paths(paths, ctx)

        return ctx

    # -- Step implementations -------------------------------------------------

    def _fetch_latest_commit(
        self, owner: str, repo: str, ctx: RepoContext
    ) -> None:
        try:
            data = self._client.call("list_commits", {
                "owner": owner,
                "repo": repo,
                "perPage": 1,
            })
            if isinstance(data, list) and data:
                c = data[0]
                ctx.latest_commit_sha = c.get("sha", "")[:12]
                ctx.latest_commit_message = (
                    c.get("commit", {}).get("message", "").splitlines()[0][:120]
                )
        except Exception as exc:
            ctx.error = f"list_commits failed: {exc}"

    def _detect_changes(
        self, owner: str, repo: str,
        previous_sha: str, ctx: RepoContext
    ) -> None:
        """Detect what changed between commits using Phase 1 ChangeDetector."""
        try:
            # Get commit comparison
            data = self._client.call("get_commit", {
                "owner": owner,
                "repo": repo,
                "sha": ctx.latest_commit_sha,
                "include_diff": True,
            })

            if isinstance(data, dict):
                files = data.get("files", [])
                changed_files = []

                for file_data in files:
                    if isinstance(file_data, dict):
                        path = file_data.get("filename", "")
                        status = file_data.get("status", "modified")
                        if path:
                            changed_files.append(path)
                            ctx.changed_files.append(path)

                # Use Phase 1 ChangeDetector to categorize and map to agents
                comparison = CommitComparison(
                    base_sha=previous_sha,
                    head_sha=ctx.latest_commit_sha,
                    files_changed=[
                        ChangedFile(path=p, status="modified")
                        for p in changed_files
                    ]
                )

                repo_info = GitHubRepoInfo(owner=owner, repo=ctx.repo_name)
                analysis = ChangeDetector.analyze_changes(comparison, repo_info)

                ctx.has_changes = analysis.requires_update
                ctx.affected_agents = tuple(sorted(analysis.affected_agents))
                ctx.change_summary = analysis.summary
                ctx.previous_commit_sha = previous_sha

        except Exception as exc:
            ctx.error = (ctx.error or "") + f" | change detection failed: {exc}"

    def _fetch_tree(
        self, owner: str, repo: str, ctx: RepoContext
    ) -> List[str]:
        paths: List[str] = []
        try:
            data = self._client.call("get_repository_tree", {
                "owner": owner,
                "repo": repo,
                "recursive": True,
            })
            if isinstance(data, list):
                paths = [
                    item["path"] for item in data
                    if isinstance(item, dict) and "path" in item
                ]
            elif isinstance(data, dict):
                # Some server versions wrap under "tree"
                paths = [
                    item["path"] for item in data.get("tree", [])
                    if "path" in item
                ]
            ctx.tree_snapshot = paths[:200]   # cap for prompt safety
        except Exception as exc:
            ctx.error = (ctx.error or "") + f" | get_repository_tree failed: {exc}"
        return paths

    def _classify_paths(self, paths: List[str], ctx: RepoContext) -> None:
        """
        Single-pass classification of all repo paths.
        Derives all RepoContext flags and file lists without additional API calls.
        """
        languages_seen: set[str] = set()
        frameworks_seen: set[str] = set()
        pm_seen: set[str] = set()

        for path in paths:
            fname = Path(path).name
            ext = Path(path).suffix.lower()
            lower_path = path.lower()

            # Language detection
            if ext in self._EXT_LANGUAGES:
                languages_seen.add(self._EXT_LANGUAGES[ext])

            # Framework + package manager detection
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

            # Kubernetes manifests
            is_k8s_dir = any(
                p in lower_path
                for p in ("k8s/", "kubernetes/", "manifests/")
            )
            is_k8s_filename = fname.lower() in (
                "deployment.yaml", "deployment.yml",
                "service.yaml", "service.yml",
                "ingress.yaml", "ingress.yml",
                "statefulset.yaml", "statefulset.yml",
                "daemonset.yaml", "daemonset.yml",
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

            # Build system (first match wins)
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
# Local filesystem analysis (unchanged behaviour from original)
# ---------------------------------------------------------------------------

class _LocalRepoAnalyzer:
    """Walks a local filesystem path to produce a RepoContext."""

    _EXT_LANGUAGES = _MCPRepoAnalyzer._EXT_LANGUAGES
    _FRAMEWORK_FILES = _MCPRepoAnalyzer._FRAMEWORK_FILES
    _PACKAGE_MANAGERS = _MCPRepoAnalyzer._PACKAGE_MANAGERS

    def analyse(self, repo_path: str) -> RepoContext:
        ctx = RepoContext(analysis_mode="local")
        languages_seen: set[str] = set()
        frameworks_seen: set[str] = set()
        pm_seen: set[str] = set()

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
# Public facade
# ---------------------------------------------------------------------------

@dataclass
class RepoAnalyzer:
    """
    Centralized repository analyzer for the orchestrator.

    Supports three modes:
        - MCP (GitHub URL)  : calls GitHub MCP server tools, no cloning.
        - Local (file path) : walks local filesystem.
        - Prompt-only       : returns empty RepoContext.

    Usage:
        analyzer = RepoAnalyzer()

        # MCP mode
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
    ) -> RepoContext:
        """
        Main entry point. Returns a RepoContext in all cases.
        Errors are recorded in ctx.error, never raised.
        """
        if github_url:
            return self._analyze_via_mcp(github_url)
        if repo_path:
            return self._analyze_local(repo_path)
        return RepoContext(analysis_mode="prompt-only")

    def cleanup(self) -> None:
        """Remove any temporary directories created during analysis."""
        for d in self._temp_dirs:
            shutil.rmtree(d, ignore_errors=True)
        self._temp_dirs.clear()

    # -- Private --------------------------------------------------------------

    def _analyze_via_mcp(self, github_url: str) -> RepoContext:
        """
        Parse URL → start MCP server subprocess → analyse remotely → return.
        No cloning, no temp dirs, no filesystem writes.

        Optional: retrieves previous commit SHA from artifact storage for change detection.
        """
        try:
            owner, repo = _parse_github_url(github_url)
        except ValueError as exc:
            return RepoContext(analysis_mode="mcp", error=str(exc))

        # Try to retrieve previous commit SHA from artifact storage (Phase 2)
        previous_sha = None
        try:
            from .artifact_storage import ArtifactDatabase
            from .config import OrchestratorConfig
            db = ArtifactDatabase(OrchestratorConfig.ARTIFACT_DB_PATH)
            repo_state = db.get_repository_state(github_url)
            if repo_state:
                previous_sha = repo_state.last_commit_sha
        except Exception:
            # Artifact storage not available yet, proceed without change detection
            pass

        try:
            with _MCPStdioClient(self.mcp_config) as client:
                return _MCPRepoAnalyzer(client).analyse(owner, repo, previous_sha)
        except EnvironmentError as exc:
            # Missing PAT — surface clearly
            return RepoContext(
                owner=owner, repo_name=repo,
                analysis_mode="mcp",
                error=f"Auth error: {exc}",
            )
        except Exception as exc:
            return RepoContext(
                owner=owner, repo_name=repo,
                analysis_mode="mcp",
                error=f"MCP analysis failed: {exc}",
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
                error=f"Local analysis failed: {exc}",
            )


# ---------------------------------------------------------------------------
# Convenience function (backward-compatible with original API)
# ---------------------------------------------------------------------------

def analyze_repo(
    repo_path: Optional[str] = None,
    github_url: Optional[str] = None,
    mcp_config: Optional[MCPClientConfig] = None,
) -> RepoContext:
    """
    Quick function to analyze a repository.

    Examples:
        # MCP mode — reads repo remotely, no cloning
        ctx = analyze_repo(github_url="https://github.com/user/repo")

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
        return analyzer.analyze(repo_path=repo_path, github_url=github_url)
    finally:
        analyzer.cleanup()