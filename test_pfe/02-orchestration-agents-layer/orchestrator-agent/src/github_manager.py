"""GitHub integration helpers for MCP-based repository access."""
import json
import os
import queue
import re
import shlex
import subprocess
import threading
from typing import Optional, Dict, Any, List, Iterable

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

        # HTTPS format: https://<host>/owner/repo[.git][/tree/branch]
        https_match = re.match(r'https?://[^/]+/([^/]+)/([^/]+?)(?:\.git)?(?:/tree/(.+?))?/?$', url)
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

    def __init__(
        self,
        token: Optional[str] = None,
        server_command: Optional[str] = None,
        server_args: Optional[str] = None,
        call_timeout: int = 30,
    ):
        """Initialize MCP client for GitHub server.

        Args:
            token: GitHub personal access token.
                   If not provided, uses GITHUB_PERSONAL_ACCESS_TOKEN then GITHUB_TOKEN.
            server_command: Executable used to launch MCP server.
            server_args: Arguments string for server command.
            call_timeout: Timeout in seconds for MCP request/response cycles.
        """
        self.token = token or os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN", "") or os.getenv("GITHUB_TOKEN", "")
        if not self.token:
            raise ValueError(
                "GITHUB_PERSONAL_ACCESS_TOKEN (or GITHUB_TOKEN) environment variable not set. "
                "Set it via .env file or environment."
            )

        self.server_command = server_command or os.getenv("MCP_GITHUB_SERVER_COMMAND", "docker")
        raw_args = server_args or os.getenv(
            "MCP_GITHUB_SERVER_ARGS",
            "run -i --rm -e GITHUB_PERSONAL_ACCESS_TOKEN -e GITHUB_HOST ghcr.io/github/github-mcp-server"
        )
        self.server_args = shlex.split(raw_args, posix=(os.name != "nt"))
        self.call_timeout = max(5, int(call_timeout))
        self.github_host = os.getenv("GITHUB_HOST", "https://github.com")

        self._proc: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._message_queue: "queue.Queue[Optional[Dict[str, Any]]]" = queue.Queue()
        self._pending_messages: List[Dict[str, Any]] = []
        self._next_id = 1
        self._tools: Dict[str, Dict[str, Any]] = {}

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def connect(self) -> None:
        """Start MCP process and initialize session."""
        if self._proc is not None:
            return

        env = os.environ.copy()
        # Different servers use different variable names for GitHub PAT.
        env.setdefault("GITHUB_TOKEN", self.token)
        env.setdefault("GITHUB_PERSONAL_ACCESS_TOKEN", self.token)
        env.setdefault("GITHUB_HOST", self.github_host)

        cmd = [self.server_command] + self.server_args
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"MCP server command not found: {self.server_command}. "
                "Set MCP_GITHUB_SERVER_COMMAND/MCP_GITHUB_SERVER_ARGS correctly."
            ) from exc

        if not self._proc.stdin or not self._proc.stdout:
            self.close()
            raise RuntimeError("Failed to initialize MCP stdio streams")

        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

        self._initialize_session()
        self._tools = self._load_tools_map()

    def close(self) -> None:
        """Close MCP process and cleanup resources."""
        proc = self._proc
        self._proc = None

        if proc is None:
            return

        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass

        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

        self._pending_messages.clear()

    def _initialize_session(self) -> None:
        """Perform MCP initialize handshake."""
        self._send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "orchestrator-agent",
                    "version": "1.0.0",
                },
            },
        )

        self._send_notification("notifications/initialized", {})

    def _load_tools_map(self) -> Dict[str, Dict[str, Any]]:
        """Load available MCP tools as a name -> metadata map."""
        response = self._send_request("tools/list", {})
        result = response.get("result", {}) if isinstance(response, dict) else {}
        tools = result.get("tools", []) if isinstance(result, dict) else []

        tool_map: Dict[str, Dict[str, Any]] = {}
        for tool in tools:
            if isinstance(tool, dict) and tool.get("name"):
                tool_map[str(tool["name"])] = tool
        return tool_map

    def _reader_loop(self) -> None:
        """Background reader for Content-Length framed JSON-RPC messages."""
        try:
            while True:
                message = self._read_message()
                if message is None:
                    break
                self._message_queue.put(message)
        finally:
            # Sentinel to unblock waiting request readers.
            self._message_queue.put(None)

    def _read_message(self) -> Optional[Dict[str, Any]]:
        """Read one MCP message from stdout stream."""
        if not self._proc or not self._proc.stdout:
            return None

        headers: Dict[str, str] = {}
        while True:
            line = self._proc.stdout.readline()
            if not line:
                return None

            if line in (b"\r\n", b"\n"):
                break

            try:
                header_line = line.decode("ascii", errors="ignore").strip()
                key, value = header_line.split(":", 1)
                headers[key.strip().lower()] = value.strip()
            except ValueError:
                continue

        content_length = int(headers.get("content-length", "0"))
        if content_length <= 0:
            return None

        body = self._proc.stdout.read(content_length)
        if not body:
            return None

        try:
            payload = json.loads(body.decode("utf-8", errors="ignore"))
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            return None
        return None

    def _write_message(self, message: Dict[str, Any]) -> None:
        """Write one MCP message to stdin stream."""
        if not self._proc or not self._proc.stdin:
            raise RuntimeError("MCP process is not connected")

        raw = json.dumps(message).encode("utf-8")
        envelope = f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw
        self._proc.stdin.write(envelope)
        self._proc.stdin.flush()

    def _send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        payload: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            payload["params"] = params
        self._write_message(payload)

    def _send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if self._proc is None:
            self.connect()

        request_id = self._next_id
        self._next_id += 1

        payload: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }
        self._write_message(payload)

        return self._wait_for_response(request_id)

    def _wait_for_response(self, request_id: int) -> Dict[str, Any]:
        # First, check buffered messages from previous waits.
        for idx, msg in enumerate(self._pending_messages):
            if isinstance(msg, dict) and msg.get("id") == request_id:
                selected = self._pending_messages.pop(idx)
                return self._validate_response(selected)

        while True:
            try:
                message = self._message_queue.get(timeout=self.call_timeout)
            except queue.Empty as exc:
                raise RuntimeError(
                    f"Timed out waiting for MCP response to request id={request_id}"
                ) from exc

            if message is None:
                raise RuntimeError("MCP server closed unexpectedly")

            if message.get("id") == request_id:
                return self._validate_response(message)

            self._pending_messages.append(message)

    @staticmethod
    def _validate_response(message: Dict[str, Any]) -> Dict[str, Any]:
        if "error" in message:
            err = message["error"]
            if isinstance(err, dict):
                code = err.get("code", "unknown")
                text = err.get("message", "Unknown MCP error")
                raise RuntimeError(f"MCP error {code}: {text}")
            raise RuntimeError(f"MCP error: {err}")
        return message

    def _resolve_tool_name(self, candidates: Iterable[str]) -> str:
        if not self._tools:
            self._tools = self._load_tools_map()

        for name in candidates:
            if name in self._tools:
                return name

        available = ", ".join(sorted(self._tools.keys())[:20])
        raise RuntimeError(
            "No matching GitHub MCP tool found. "
            f"Candidates: {list(candidates)}. Available sample: {available}"
        )

    @staticmethod
    def _extract_tool_payload(call_result: Any) -> Any:
        """Normalize MCP tools/call result into a plain Python payload."""
        if not isinstance(call_result, dict):
            return call_result

        # MCP result shape usually contains {content: [...]}
        content = call_result.get("content")
        if not isinstance(content, list):
            return call_result

        for item in content:
            if not isinstance(item, dict):
                continue

            if "json" in item:
                return item["json"]

            text = item.get("text")
            if isinstance(text, str):
                stripped = text.strip()
                if stripped.startswith("```"):
                    stripped = stripped.strip("`")

                if stripped and stripped[0] in "[{":
                    try:
                        return json.loads(stripped)
                    except json.JSONDecodeError:
                        pass
                return text

        return call_result

    def call_tool(self, candidates: Iterable[str], arguments: Dict[str, Any]) -> Any:
        """Call first available tool from candidates with provided arguments."""
        tool_name = self._resolve_tool_name(candidates)
        response = self._send_request(
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments,
            },
        )
        result = response.get("result", {}) if isinstance(response, dict) else {}
        return self._extract_tool_payload(result)

    @staticmethod
    def _to_rel_path(path: str) -> str:
        return path.strip().lstrip("/")

    @staticmethod
    def _extract_entries(payload: Any) -> Optional[List[Dict[str, Any]]]:
        """Normalize directory listing payload across MCP server variants."""
        if isinstance(payload, list):
            return [p for p in payload if isinstance(p, dict)]

        if isinstance(payload, dict):
            for key in ("entries", "items", "files", "data"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [v for v in value if isinstance(v, dict)]

            # File payload (single file object)
            if payload.get("type") in {"file", "dir"}:
                return [payload]

        return None

    def list_repository_files(
        self,
        owner: str,
        repo: str,
        ref: Optional[str] = None,
        max_files: int = 5000,
    ) -> List[str]:
        """Recursively list repository file paths through MCP get_file_contents."""
        self.connect()

        files: List[str] = []
        directories: List[str] = ["/"]

        while directories and len(files) < max_files:
            current_dir = directories.pop(0)

            args: Dict[str, Any] = {
                "owner": owner,
                "repo": repo,
                "path": current_dir,
            }
            if ref:
                args["ref"] = ref

            payload = self.call_tool(
                candidates=(
                    "get_file_contents",
                    "mcp_io_github_git_get_file_contents",
                ),
                arguments=args,
            )

            entries = self._extract_entries(payload)
            if not entries:
                continue

            for entry in entries:
                entry_type = str(entry.get("type", "")).lower()
                path = entry.get("path") or entry.get("name")
                if not isinstance(path, str) or not path:
                    continue

                rel_path = self._to_rel_path(path)
                if not rel_path:
                    continue

                if entry_type == "dir":
                    directories.append(rel_path)
                elif entry_type == "file":
                    files.append(rel_path)
                    if len(files) >= max_files:
                        break

        return sorted(set(files))

    def get_repo_metadata(self, owner: str, repo: str) -> Dict[str, Any]:
        """Fetch repository metadata through MCP search tools when available."""
        self.connect()

        # Best-effort across common GitHub MCP tool variants.
        queries = [
            {
                "query": f"repo:{owner}/{repo}",
                "perPage": 1,
                "page": 1,
            },
            {
                "query": f"{owner}/{repo}",
                "perPage": 1,
                "page": 1,
            },
        ]

        last_error = None
        for q in queries:
            try:
                payload = self.call_tool(
                    candidates=(
                        "search_repositories",
                        "mcp_io_github_git_search_repositories",
                    ),
                    arguments=q,
                )
            except Exception as exc:
                last_error = exc
                continue

            if isinstance(payload, dict):
                for key in ("items", "repositories", "results"):
                    items = payload.get(key)
                    if isinstance(items, list) and items:
                        first = items[0]
                        if isinstance(first, dict):
                            return first
                return payload

            if isinstance(payload, list) and payload and isinstance(payload[0], dict):
                return payload[0]

        if last_error:
            raise RuntimeError(f"Unable to get repo metadata from MCP: {last_error}")

        return {}

    def get_latest_commit(self, owner: str, repo: str, branch: str = "main") -> Optional[str]:
        """Fetch latest commit SHA through MCP branch/commit tools when available."""
        self.connect()

        variants = [
            {"owner": owner, "repo": repo, "sha": branch, "perPage": 1, "page": 1},
            {"owner": owner, "repo": repo, "branch": branch, "perPage": 1, "page": 1},
            {"owner": owner, "repo": repo},
        ]

        for args in variants:
            try:
                payload = self.call_tool(
                    candidates=(
                        "list_commits",
                        "mcp_io_github_git_list_commits",
                    ),
                    arguments=args,
                )
            except Exception:
                continue

            sha = self._extract_sha_from_payload(payload)
            if sha:
                return sha

        # Fallback: attempt to infer commit SHA from get_file_contents URLs.
        try:
            payload = self.call_tool(
                candidates=(
                    "get_file_contents",
                    "mcp_io_github_git_get_file_contents",
                ),
                arguments={"owner": owner, "repo": repo, "path": "/"},
            )
            return self._extract_sha_from_payload(payload)
        except Exception:
            return None

    @staticmethod
    def _extract_sha_from_payload(payload: Any) -> Optional[str]:
        if isinstance(payload, dict):
            for key in ("sha", "commit_sha", "oid"):
                val = payload.get(key)
                if isinstance(val, str) and len(val) >= 7:
                    return val

            for key in ("items", "commits", "data", "results"):
                items = payload.get(key)
                if isinstance(items, list):
                    sha = GitHubMCPClient._extract_sha_from_payload(items)
                    if sha:
                        return sha

            url = payload.get("url")
            if isinstance(url, str) and "?ref=" in url:
                return url.split("?ref=", 1)[1].strip()

        if isinstance(payload, list):
            for item in payload:
                sha = GitHubMCPClient._extract_sha_from_payload(item)
                if sha:
                    return sha

        if isinstance(payload, str) and len(payload) >= 7:
            # Last-resort extraction from plain-text tool outputs.
            match = re.search(r"\b[0-9a-f]{7,40}\b", payload)
            if match:
                return match.group(0)

        return None

    def parse_url(self, url: str) -> GitHubRepoInfo:
        """Parse GitHub URL into structured info."""
        return GitHubURLParser.parse(url)

    def get_file_at_commit(self, owner: str, repo: str, path: str, sha: str) -> Optional[str]:
        """Get file content at specific commit via MCP get_file_contents."""
        payload = self.call_tool(
            candidates=(
                "get_file_contents",
                "mcp_io_github_git_get_file_contents",
            ),
            arguments={
                "owner": owner,
                "repo": repo,
                "path": path,
                "ref": sha,
            },
        )

        if isinstance(payload, dict):
            content = payload.get("content")
            if isinstance(content, str):
                return content
        if isinstance(payload, str):
            return payload
        return None

    def compare_commits(self, owner: str, repo: str,
                       base_sha: str, head_sha: str) -> CommitComparison:
        """Compare two commits and get changed files via MCP when available."""
        variants = [
            {"owner": owner, "repo": repo, "base": base_sha, "head": head_sha},
            {"owner": owner, "repo": repo, "base_sha": base_sha, "head_sha": head_sha},
        ]

        for args in variants:
            try:
                payload = self.call_tool(
                    candidates=(
                        "compare_commits",
                        "mcp_io_github_git_compare_commits",
                    ),
                    arguments=args,
                )
            except Exception:
                continue

            files_changed: List[ChangedFile] = []
            total_additions = 0
            total_deletions = 0

            items: List[Dict[str, Any]] = []
            if isinstance(payload, dict):
                for key in ("files", "files_changed", "changed_files", "items"):
                    value = payload.get(key)
                    if isinstance(value, list):
                        items = [v for v in value if isinstance(v, dict)]
                        break
            elif isinstance(payload, list):
                items = [v for v in payload if isinstance(v, dict)]

            for item in items:
                additions = int(item.get("additions") or 0)
                deletions = int(item.get("deletions") or 0)
                file_path = item.get("filename") or item.get("path") or ""
                if not file_path:
                    continue
                files_changed.append(
                    ChangedFile(
                        path=file_path,
                        status=str(item.get("status") or "modified"),
                        additions=additions,
                        deletions=deletions,
                        changes=int(item.get("changes") or (additions + deletions)),
                        patch=item.get("patch"),
                    )
                )
                total_additions += additions
                total_deletions += deletions

            return CommitComparison(
                base_sha=base_sha,
                head_sha=head_sha,
                files_changed=files_changed,
                total_additions=total_additions,
                total_deletions=total_deletions,
            )

        return CommitComparison(
            base_sha=base_sha,
            head_sha=head_sha,
            files_changed=[],
        )

    def create_pull_request(self, owner: str, repo: str,
                          title: str, body: str,
                          head: str, base: str) -> Dict[str, Any]:
        """Create a pull request via MCP with fallback to PyGithub.

        Args:
            owner: Repository owner
            repo: Repository name
            title: PR title
            body: PR description
            head: Head branch (feature branch with changes)
            base: Base branch (e.g., 'main')

        Returns:
            Dictionary with PR details (number, url, id, etc.) or error info
        """
        # Try MCP first
        variants = [
            {
                "owner": owner,
                "repo": repo,
                "title": title,
                "body": body,
                "head": head,
                "base": base,
            },
        ]

        for args in variants:
            try:
                payload = self.call_tool(
                    candidates=(
                        "create_pull_request",
                        "create_pull",
                        "mcp_io_github_github_create_pull_request",
                    ),
                    arguments=args,
                )

                if isinstance(payload, dict):
                    return {
                        "success": True,
                        "pr_number": payload.get("number"),
                        "pr_url": payload.get("html_url") or payload.get("url"),
                        "pr_id": payload.get("id"),
                        "head": payload.get("head", {}).get("ref") or head,
                        "base": payload.get("base", {}).get("ref") or base,
                        "state": payload.get("state", "open"),
                        "raw_response": payload,
                    }
            except Exception as e:
                # Log but continue to fallback
                if hasattr(self, 'logger'):
                    self.logger.warning(f"MCP create_pull_request failed: {e}")

        # Fallback to PyGithub if MCP not available or failed
        try:
            from github import Github

            client = Github(self.token)
            repo_obj = client.get_user(owner).get_repo(repo)

            pr = repo_obj.create_pull(
                title=title,
                body=body,
                head=head,
                base=base,
            )

            return {
                "success": True,
                "pr_number": pr.number,
                "pr_url": pr.html_url,
                "pr_id": pr.id,
                "head": pr.head.ref,
                "base": pr.base.ref,
                "state": pr.state,
                "source": "PyGithub",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "owner": owner,
                "repo": repo,
                "requested_head": head,
                "requested_base": base,
            }


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
        for category in sorted(categories.keys(), key=lambda c: c.value):
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
