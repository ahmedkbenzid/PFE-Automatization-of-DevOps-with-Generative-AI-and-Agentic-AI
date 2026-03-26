"""Data models for GitHub MCP integration."""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


class AgentType(Enum):
    """Supported agent types for artifact generation."""
    CICD = "cicd-agent"
    DOCKER = "docker-agent"
    IAC = "iac-agent"


class ChangeCategory(Enum):
    """Categories of code changes."""
    DEPENDENCIES = "dependencies"
    BUILD_CONFIG = "build_config"
    INFRASTRUCTURE = "infrastructure"
    SOURCE_CODE = "source_code"
    OTHER = "other"


@dataclass
class GitHubRepoInfo:
    """Parsed GitHub repository information."""
    owner: str
    repo: str
    branch: str = "main"
    commit_sha: Optional[str] = None

    @property
    def url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}"

    @property
    def api_url(self) -> str:
        return f"https://api.github.com/repos/{self.owner}/{self.repo}"


@dataclass
class ChangedFile:
    """Represents a changed file in a commit."""
    path: str
    status: str  # "added", "modified", "deleted"
    additions: int = 0
    deletions: int = 0
    changes: int = 0
    patch: Optional[str] = None

    @property
    def filename(self) -> str:
        return self.path.split('/')[-1]

    @property
    def extension(self) -> str:
        return self.path.split('.')[-1] if '.' in self.path else ''


@dataclass
class CommitComparison:
    """Result of comparing two commits."""
    base_sha: str
    head_sha: str
    files_changed: List[ChangedFile] = field(default_factory=list)
    total_additions: int = 0
    total_deletions: int = 0

    @property
    def has_changes(self) -> bool:
        return len(self.files_changed) > 0


@dataclass
class ChangeAnalysis:
    """Analysis of what changed and what needs updating."""
    commit_sha: str
    comparison: CommitComparison
    categories: Dict[ChangeCategory, List[str]] = field(default_factory=dict)
    affected_agents: set = field(default_factory=set)
    requires_update: bool = False
    summary: str = ""


@dataclass
class ArtifactMetadata:
    """Metadata about a generated artifact."""
    agent_name: AgentType
    artifact_type: str  # "yaml", "dockerfile", "terraform", etc.
    commit_sha: str
    changed_files: List[str] = field(default_factory=list)
    content_hash: str = ""
    created_at: str = ""
    description: str = ""


@dataclass
class RepositoryState:
    """Tracks repository processing state."""
    github_url: str
    owner: str
    repo: str
    branch: str = "main"
    last_commit_sha: Optional[str] = None
    last_analyzed_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
