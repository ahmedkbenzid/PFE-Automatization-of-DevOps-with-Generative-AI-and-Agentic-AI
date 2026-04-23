"""GitHub integration for workflow management with real API calls."""

import logging
from typing import Optional, Dict, Any, List
import os
from github import Github, GithubException
from github.Repository import Repository
from github.PullRequest import PullRequest
from github.WorkflowRun import WorkflowRun

logger = logging.getLogger(__name__)


class GitHubIntegration:
    """Handle GitHub interactions for workflow management with real API calls."""

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token or os.getenv("GITHUB_TOKEN")
        self.client: Optional[Github] = None
        self._repo: Optional[Repository] = None
        self.pr_info: Optional[Dict[str, Any]] = None
        self.repo_info: Optional[Dict[str, Any]] = None

        if self.access_token:
            try:
                self.client = Github(self.access_token)
                logger.info("GitHub client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize GitHub client: {e}")
        else:
            logger.warning("No GITHUB_TOKEN provided, using mock mode")

    def _get_repo(self, repo_owner: str, repo_name: str) -> Optional[Repository]:
        """Get repository object with caching."""
        if not self.client:
            logger.warning("GitHub client not initialized")
            return None

        cache_key = f"{repo_owner}/{repo_name}"
        if self._repo is None or self.repo_info.get('full_name') != cache_key:
            try:
                self._repo = self.client.get_repo(f"{repo_owner}/{repo_name}")
                self.repo_info = {
                    'full_name': self._repo.full_name,
                    'default_branch': self._repo.default_branch,
                    'is_private': self._repo.private,
                }
                logger.info(f"Loaded repository: {cache_key}")
            except GithubException as e:
                logger.error(f"Failed to get repository {cache_key}: {e}")
                return None
        return self._repo

    def create_pr(self, repo_owner: str, repo_name: str, branch_name: str,
                workflow_yaml: str, title: str, description: str) -> Optional[Dict[str, Any]]:
        """Create a pull request with the generated workflow."""
        repo = self._get_repo(repo_owner, repo_name)
        if not repo:
            return self._mock_create_pr(repo_owner, repo_name, branch_name, workflow_yaml, title, description)

        try:
            source_branch = repo.get_branch(repo.default_branch)
            try:
                target_branch = repo.get_branch(branch_name)
            except GithubException:
                logger.info(f"Creating branch '{branch_name}' from '{repo.default_branch}'")
                ref = f"refs/heads/{branch_name}"
                target_branch = repo.create_git_ref(ref, source_branch.commit.sha)

            workflow_path = f".github/workflows/generated-workflow.yml"
            repo.create_file(workflow_path, f"Add {workflow_path}", workflow_yaml, branch=branch_name)

            pr = repo.create_pull(
                title=title,
                body=description,
                head=branch_name,
                base=repo.default_branch,
            )

            self.pr_info = {
                'status': 'success',
                'pr_number': pr.number,
                'branch': branch_name,
                'title': pr.title,
                'description': description,
                'files_changed': [workflow_path],
                'author': pr.user.login,
                'created_at': str(pr.created_at),
                'url': pr.html_url,
            }
            logger.info(f"Created PR #{pr.number}: {pr.html_url}")
            return self.pr_info

        except GithubException as e:
            logger.error(f"Failed to create PR: {e}")
            return None

    def commit_workflow(self, repo_owner: str, repo_name: str, workflow_yaml: str,
                       branch: str, commit_message: str, additional_files: Dict[str, str] = None) -> bool:
        """Commit workflow to repository."""
        repo = self._get_repo(repo_owner, repo_name)
        if not repo:
            logger.warning(f"Mock: Would commit workflow to {repo_owner}/{repo_name}")
            return True

        try:
            files_to_commit = {'.github/workflows/generated-workflow.yml': workflow_yaml}
            if additional_files:
                files_to_commit.update(additional_files)

            for file_path, content in files_to_commit.items():
                try:
                    existing_file = repo.get_contents(file_path, ref=branch)
                    repo.update_file(file_path, commit_message, content, existing_file.sha, branch=branch)
                    logger.info(f"Updated {file_path}")
                except GithubException:
                    repo.create_file(file_path, commit_message, content, branch=branch)
                    logger.info(f"Created {file_path}")

            return True

        except GithubException as e:
            logger.error(f"Failed to commit workflow: {e}")
            return False

    def comment_on_pr(self, repo_owner: str, repo_name: str, pr_number: int, comment: str) -> bool:
        """Add a comment to a pull request."""
        repo = self._get_repo(repo_owner, repo_name)
        if not repo:
            logger.warning(f"Mock: Would comment on PR #{pr_number}")
            return True

        try:
            pr = repo.get_pull(pr_number)
            pr.create_issue_comment(comment)
            logger.info(f"Commented on PR #{pr_number}")
            return True
        except GithubException as e:
            logger.error(f"Failed to comment on PR: {e}")
            return False

    def get_workflow_runs(self, repo_owner: str, repo_name: str,
                        workflow_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent workflow runs."""
        repo = self._get_repo(repo_owner, repo_name)
        if not repo:
            return self._mock_get_workflow_runs(workflow_name, limit)

        try:
            workflow = repo.get_workflow(workflow_name)
            runs = workflow.get_runs(limit=limit)

            return [
                {
                    'id': run.id,
                    'name': run.name,
                    'status': run.status,
                    'conclusion': run.conclusion,
                    'run_number': run.run_number,
                    'created_at': str(run.created_at),
                    'html_url': run.html_url,
                }
                for run in runs
            ]
        except GithubException as e:
            logger.error(f"Failed to get workflow runs: {e}")
            return []

    def approve_workflow(self, repo_owner: str, repo_name: str, run_id: int) -> bool:
        """Approve a workflow run that's awaiting approval."""
        logger.warning(f"Workflow approval requires explicit user action for security")
        return False

    def fetch_file(self, repo_owner: str, repo_name: str, file_path: str,
              branch: str = 'main') -> Optional[str]:
        """Fetch a file from the repository."""
        repo = self._get_repo(repo_owner, repo_name)
        if not repo:
            logger.warning(f"Mock: Would fetch {file_path}")
            return None

        try:
            content = repo.get_contents(file_path, ref=branch)
            return content.decoded_content.decode('utf-8')
        except GithubException as e:
            logger.error(f"Failed to fetch {file_path}: {e}")
            return None

    def get_repo_info(self, repo_owner: str, repo_name: str) -> Dict[str, Any]:
        """Get repository information."""
        repo = self._get_repo(repo_owner, repo_name)
        if not repo:
            return {
                'owner': repo_owner,
                'name': repo_name,
                'url': f'https://github.com/{repo_owner}/{repo_name}',
                'default_branch': 'main',
                'is_private': False,
            }

        try:
            return {
                'owner': repo.owner.login,
                'name': repo.name,
                'full_name': repo.full_name,
                'url': repo.html_url,
                'default_branch': repo.default_branch,
                'is_private': repo.private,
                'language': repo.language,
                'topics': repo.get_topics() if hasattr(repo, 'get_topics') else [],
            }
        except GithubException as e:
            logger.error(f"Failed to get repo info: {e}")
            return {}

    def create_workflow_dispatch(self, repo_owner: str, repo_name: str,
                            workflow_name: str, inputs: Dict[str, str] = None) -> bool:
        """Trigger a workflow_dispatch event."""
        repo = self._get_repo(repo_owner, repo_name)
        if not repo:
            logger.warning(f"Mock: Would dispatch {workflow_name}")
            return True

        try:
            workflow = repo.get_workflow(workflow_name)
            workflow.create_dispatch(inputs=inputs or {})
            logger.info(f"Triggered workflow dispatch: {workflow_name}")
            return True
        except GithubException as e:
            logger.error(f"Failed to dispatch workflow: {e}")
            return False

    def get_action_usage(self, repo_owner: str, repo_name: str) -> Dict[str, int]:
        """Get usage statistics of GitHub Actions."""
        repo = self._get_repo(repo_owner, repo_name)
        if not repo:
            return {
                'workflow_runs_last_30_days': 0,
                'total_storage_used_gb': 0.0,
                'minutes_used': 0,
                'minutes_available': 0,
            }

        try:
            usage = repo.get_workflow_usage()
            return {
                'workflow_runs_last_30_days': usage.get('billable', {}).get('UBUNTU', {}).get('runners', {}).get('minutes', 0),
                'total_storage_used_gb': usage.get('osum', 0) / 1_000_000_000,
                'minutes_used': usage.get('billable', {}).get('UBUNTU', {}).get('runners', {}).get('minutes', 0),
                'minutes_available': 2000,
            }
        except (GithubException, AttributeError) as e:
            logger.warning(f"Could not get action usage: {e}")
            return {
                'workflow_runs_last_30_days': 0,
                'total_storage_used_gb': 0.0,
                'minutes_used': 0,
                'minutes_available': 0,
            }

    def _mock_create_pr(self, repo_owner: str, repo_name: str, branch_name: str,
                        workflow_yaml: str, title: str, description: str) -> Dict[str, Any]:
        """Mock PR creation when no token available."""
        logger.warning("Running in mock mode - no actual GitHub operations")
        return {
            'status': 'mock',
            'pr_number': 1,
            'branch': branch_name,
            'title': title,
            'description': description,
            'files_changed': ['.github/workflows/generated-workflow.yml'],
            'author': 'ci-cd-agent',
            'url': f'https://github.com/{repo_owner}/{repo_name}/pull/1',
        }

    def _mock_get_workflow_runs(self, workflow_name: str, limit: int) -> List[Dict[str, Any]]:
        """Mock workflow runs."""
        return [
            {
                'id': i,
                'name': workflow_name,
                'status': 'completed',
                'conclusion': 'success' if i % 3 != 0 else 'failure',
                'run_number': 100 - i,
                'created_at': f'2024-01-{(i % 28) + 1:02d}T00:00:00Z',
            }
            for i in range(limit)
        ]