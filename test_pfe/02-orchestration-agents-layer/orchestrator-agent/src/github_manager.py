"""GitHub API integration via MCP (Model Context Protocol)."""
import os
import re
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

from .models.github_types import (
    GitHubRepoInfo,
    CommitComparison,
    ChangedFile,
    ChangeAnalysis,
    ChangeCategory,
)


class GitHubURLParser:
    """Parse GitHub URLs into structured repo info."""

    @staticmethod
    def parse(url: str) -> GitHubRepoInfo:
        """Parse GitHub URL into components.

        Supports:
        - https://github.com/owner/repo
        - https://github.com/owner/repo.git
        - https://github.com/owner/repo/tree/branch
        - git@github.com:owner/repo.git
        """
        url = url.strip()

        # HTTPS format: https://github.com/owner/repo[.git][/tree/branch]
        https_match = re.match(r'https://github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/tree/(.+?))?/?$', url)
        if https_match:
            owner, repo, branch = https_match.groups()
            return GitHubRepoInfo(
                owner=owner,
                repo=repo,
                branch=branch or "main"
            )

        # SSH format: git@github.com:owner/repo[.git]
        ssh_match = re.match(r'git@github\.com:([^/]+)/([^/]+?)(?:\.git)?/?$', url)
        if ssh_match:
            owner, repo = ssh_match.groups()
            return GitHubRepoInfo(owner=owner, repo=repo)

        raise ValueError(f"Invalid GitHub URL: {url}")


class GitHubMCPClient:
    """Wrapper around GitHub MCP server tools.

    NOTE: Requires @modelcontextprotocol/server-github to be installed and configured.
    The actual GitHub API calls are performed through the MCP server's tools,
    which are automatically available in the LLM context when properly configured.
    """

    def __init__(self, token: Optional[str] = None):
        """Initialize GitHub client.

        Args:
            token: GitHub personal access token. If not provided, uses GITHUB_TOKEN env var.
        """
        self.token = token or os.getenv("GITHUB_TOKEN", "")
        if not self.token:
            raise ValueError(
                "GITHUB_TOKEN environment variable not set. "
                "Set it via .env file or environment."
            )

    def parse_url(self, url: str) -> GitHubRepoInfo:
        """Parse GitHub URL into structured info."""
        return GitHubURLParser.parse(url)

    def get_repo_metadata(self, owner: str, repo: str) -> Dict[str, Any]:
        """Get repository metadata via MCP.

        This method should be called with the MCP search_repositories tool available.
        Implementation depends on MCP server integration.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Dictionary with repo metadata (name, description, language, stars, etc.)
        """
        # NOTE: This will be resolved via MCP tool context when available
        return {
            "owner": owner,
            "repo": repo,
            "message": "Use MCP search_repositories tool for full metadata"
        }

    def get_file_at_commit(self, owner: str, repo: str, path: str,
                          sha: str) -> Optional[str]:
        """Get file content at specific commit via MCP.

        Args:
            owner: Repository owner
            repo: Repository name
            path: File path within repo
            sha: Commit SHA

        Returns:
            File content or None if not found
        """
        # NOTE: This will be resolved via MCP get_file_contents tool
        return None

    def get_latest_commit(self, owner: str, repo: str,
                         branch: str = "main") -> Optional[str]:
        """Get latest commit SHA for branch.

        Args:
            owner: Repository owner
            repo: Repository name
            branch: Branch name

        Returns:
            Latest commit SHA on branch
        """
        # NOTE: This will be resolved via MCP get_file_contents or similar
        return None

    def compare_commits(self, owner: str, repo: str,
                       base_sha: str, head_sha: str) -> CommitComparison:
        """Compare two commits and get changed files.

        Args:
            owner: Repository owner
            repo: Repository name
            base_sha: Base commit SHA (usually previous commit)
            head_sha: Head commit SHA (usually new commit)

        Returns:
            CommitComparison with list of changed files
        """
        # NOTE: This will be resolved via MCP tools
        # Should return actual file changes via GitHub API
        return CommitComparison(
            base_sha=base_sha,
            head_sha=head_sha,
            files_changed=[],
        )


class ChangeDetector:
    """Detect what changed and which agents need rerun."""

    # File patterns that trigger specific agents
    CICD_TRIGGERS = {
        'pom.xml', 'package.json', 'requirements.txt', 'Cargo.toml', 'go.mod',
        'build.gradle', 'setup.py', 'yarn.lock', 'poetry.lock', 'Gemfile',
        'tox.ini', 'pytest.ini', '.github/workflows/', 'azure-pipelines.yml',
        '.travis.yml', 'Jenkinsfile', '.circleci/'
    }

    DOCKER_TRIGGERS = {
        'Dockerfile', 'docker-compose.yml', 'docker-compose.yaml',
        '.dockerignore', 'Dockerfile.prod', 'docker-entrypoint.sh'
    }

    IAC_TRIGGERS = {
        '.tf', 'terraform/', 'main.tf', 'variables.tf', 'outputs.tf',
        'providers.tf', 'ansible/', 'playbook.yml', 'roles/'
    }

    @staticmethod
    def categorize_file(path: str) -> ChangeCategory:
        """Categorize a changed file."""
        path_lower = path.lower()

        # Check dependencies
        for pattern in ChangeDetector.CICD_TRIGGERS:
            if pattern in path_lower:
                return ChangeCategory.DEPENDENCIES

        # Check build config
        for pattern in ChangeDetector.DOCKER_TRIGGERS:
            if pattern in path_lower:
                return ChangeCategory.BUILD_CONFIG

        # Check infrastructure
        for pattern in ChangeDetector.IAC_TRIGGERS:
            if pattern in path_lower:
                return ChangeCategory.INFRASTRUCTURE

        # Check source code
        if any(path_lower.endswith(ext) for ext in
               ['.py', '.java', '.js', '.ts', '.go', '.rs', '.rb',
                '.php', '.cs', '.cpp', '.c', '.h']):
            return ChangeCategory.SOURCE_CODE

        return ChangeCategory.OTHER

    @staticmethod
    def analyze_changes(comparison: CommitComparison,
                       repo_info: GitHubRepoInfo) -> ChangeAnalysis:
        """Analyze changed files and determine which agents need rerun.

        Args:
            comparison: Commit comparison with changed files
            repo_info: Repository information

        Returns:
            ChangeAnalysis with affected agents and summary
        """
        categories: Dict[ChangeCategory, List[str]] = {}
        affected_agents = set()

        for file in comparison.files_changed:
            category = ChangeDetector.categorize_file(file.path)

            if category not in categories:
                categories[category] = []
            categories[category].append(file.path)

            # Map categories to agents
            if category in {ChangeCategory.DEPENDENCIES, ChangeCategory.SOURCE_CODE}:
                affected_agents.add("cicd-agent")
            if category == ChangeCategory.BUILD_CONFIG:
                affected_agents.add("docker-agent")
            if category == ChangeCategory.INFRASTRUCTURE:
                affected_agents.add("iac-agent")

        # If source code changed but no specific trigger, enable CICD agent
        if (ChangeCategory.SOURCE_CODE in categories and
            not affected_agents):
            affected_agents.add("cicd-agent")

        # Build summary
        summary_parts = []
        for category in sorted(categories.keys()):
            files = categories[category]
            if files:
                summary_parts.append(
                    f"{category.value}: {len(files)} file(s)"
                )

        summary = " | ".join(summary_parts) if summary_parts else "No changes detected"

        return ChangeAnalysis(
            commit_sha=comparison.head_sha,
            comparison=comparison,
            categories=categories,
            affected_agents=affected_agents,
            requires_update=bool(affected_agents),
            summary=summary,
        )
