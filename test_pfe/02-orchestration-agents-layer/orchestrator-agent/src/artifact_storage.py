"""SQLite storage for artifacts and repository state."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from .models.github_types import ArtifactMetadata, RepositoryState, AgentType


class ArtifactDatabase:
    """SQLite database for storing artifacts and repository state."""

    SCHEMA_VERSION = 1

    def __init__(self, db_path: str):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self):
        """Create schema if not exists."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Repositories table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS repositories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    github_url TEXT UNIQUE NOT NULL,
                    owner TEXT NOT NULL,
                    repo TEXT NOT NULL,
                    branch TEXT DEFAULT 'main',
                    last_commit_sha TEXT,
                    last_analyzed_at TIMESTAMP,
                    metadata_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Artifacts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    repository_id INTEGER NOT NULL,
                    agent_name TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT,
                    commit_sha TEXT NOT NULL,
                    is_current BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (repository_id) REFERENCES repositories(id)
                )
            """)

            # Artifact history table (for audit trail)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS artifact_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    artifact_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    trigger_type TEXT,
                    changed_files_json TEXT,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (artifact_id) REFERENCES artifacts(id)
                )
            """)

            # Create indices for performance
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_repo_url
                ON repositories(github_url)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_artifact_repo
                ON artifacts(repository_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_artifact_current
                ON artifacts(repository_id, is_current)
            """)

            conn.commit()

    def register_repository(self, url: str, owner: str, repo: str,
                           branch: str = "main",
                           metadata: Optional[Dict] = None) -> int:
        """Register a GitHub repository.

        Args:
            url: Full GitHub URL
            owner: Repository owner
            repo: Repository name
            branch: Default branch
            metadata: Optional metadata dict

        Returns:
            Repository ID
        """
        metadata_json = json.dumps(metadata or {})

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Try insert, or update if exists
            cursor.execute("""
                INSERT OR IGNORE INTO repositories
                (github_url, owner, repo, branch, metadata_json)
                VALUES (?, ?, ?, ?, ?)
            """, (url, owner, repo, branch, metadata_json))

            cursor.execute("""
                SELECT id FROM repositories WHERE github_url = ?
            """, (url,))

            repo_id = cursor.fetchone()[0]
            conn.commit()

        return repo_id

    def update_repository_state(self, repo_id: int, commit_sha: str,
                                analyzed_at: Optional[str] = None):
        """Update repository's last commit and analysis time.

        Args:
            repo_id: Repository ID
            commit_sha: Latest commit SHA
            analyzed_at: Analysis timestamp (defaults to now)
        """
        analyzed_at = analyzed_at or datetime.utcnow().isoformat()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE repositories
                SET last_commit_sha = ?, last_analyzed_at = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (commit_sha, analyzed_at, repo_id))
            conn.commit()

    def save_artifact(self, repo_id: int, agent_name: str,
                     artifact_type: str, content: str,
                     commit_sha: str, content_hash: str = "") -> int:
        """Save generated artifact.

        Args:
            repo_id: Repository ID
            agent_name: Agent that generated (cicd-agent, docker-agent, iac-agent)
            artifact_type: Type of artifact (yaml, dockerfile, terraform)
            content: Artifact content
            commit_sha: Commit SHA when artifact was generated
            content_hash: SHA256 hash of content (optional)

        Returns:
            Artifact ID
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Mark previous artifacts of same type as not current
            cursor.execute("""
                UPDATE artifacts
                SET is_current = 0
                WHERE repository_id = ? AND agent_name = ? AND artifact_type = ?
            """, (repo_id, agent_name, artifact_type))

            # Insert new artifact
            cursor.execute("""
                INSERT INTO artifacts
                (repository_id, agent_name, artifact_type, content, content_hash, commit_sha, is_current)
                VALUES (?, ?, ?, ?, ?, ?, 1)
            """, (repo_id, agent_name, artifact_type, content, content_hash, commit_sha))

            artifact_id = cursor.lastrowid
            conn.commit()

        return artifact_id

    def get_current_artifacts(self, repo_id: int) -> List[Dict[str, Any]]:
        """Get current artifacts for repository.

        Args:
            repo_id: Repository ID

        Returns:
            List of artifact dictionaries
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, agent_name, artifact_type, content_hash, commit_sha, created_at
                FROM artifacts
                WHERE repository_id = ? AND is_current = 1
                ORDER BY created_at DESC
            """, (repo_id,))

            return [dict(row) for row in cursor.fetchall()]

    def get_artifact_content(self, artifact_id: int) -> Optional[str]:
        """Get content of specific artifact.

        Args:
            artifact_id: Artifact ID

        Returns:
            Artifact content or None
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT content FROM artifacts WHERE id = ?
            """, (artifact_id,))

            row = cursor.fetchone()
            return row[0] if row else None

    def get_repository_state(self, url: str) -> Optional[RepositoryState]:
        """Get repository state.

        Args:
            url: GitHub repository URL

        Returns:
            RepositoryState or None if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, github_url, owner, repo, branch, last_commit_sha,
                       last_analyzed_at, metadata_json
                FROM repositories
                WHERE github_url = ?
            """, (url,))

            row = cursor.fetchone()
            if not row:
                return None

            metadata = json.loads(row["metadata_json"] or "{}")

            return RepositoryState(
                github_url=row["github_url"],
                owner=row["owner"],
                repo=row["repo"],
                branch=row["branch"],
                last_commit_sha=row["last_commit_sha"],
                last_analyzed_at=row["last_analyzed_at"],
                metadata=metadata,
            )

    def add_history_entry(self, artifact_id: int, action: str,
                         trigger_type: Optional[str] = None,
                         changed_files: Optional[List[str]] = None,
                         description: str = ""):
        """Add artifact history entry.

        Args:
            artifact_id: Artifact ID
            action: Action performed (created, updated, unchanged, deleted)
            trigger_type: Type of trigger (webhook, manual, scheduled)
            changed_files: List of files that changed
            description: Optional description
        """
        changed_files_json = json.dumps(changed_files or [])

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO artifact_history
                (artifact_id, action, trigger_type, changed_files_json, description)
                VALUES (?, ?, ?, ?, ?)
            """, (artifact_id, action, trigger_type, changed_files_json, description))
            conn.commit()

    def get_artifact_history(self, artifact_id: int,
                            limit: int = 10) -> List[Dict[str, Any]]:
        """Get history for artifact.

        Args:
            artifact_id: Artifact ID
            limit: Maximum number of entries

        Returns:
            List of history entries
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, action, trigger_type, changed_files_json, description, created_at
                FROM artifact_history
                WHERE artifact_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (artifact_id, limit))

            entries = []
            for row in cursor.fetchall():
                entry = dict(row)
                entry["changed_files"] = json.loads(entry["changed_files_json"] or "[]")
                del entry["changed_files_json"]
                entries.append(entry)

            return entries
