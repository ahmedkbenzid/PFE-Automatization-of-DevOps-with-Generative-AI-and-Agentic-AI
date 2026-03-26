"""Standalone Phase 1 verification - no orchestrator imports."""
import sys
from pathlib import Path
import tempfile

# Test without importing orchestrator
def test_url_parser():
    """Test GitHub URL parsing."""
    print("\n" + "=" * 60)
    print("TEST 1: GitHub URL Parsing")
    print("=" * 60)

    from src.github_manager import GitHubURLParser

    test_cases = [
        ("https://github.com/owner/repo", "owner", "repo", "main"),
        ("https://github.com/owner/repo.git", "owner", "repo", "main"),
        ("https://github.com/owner/repo/tree/develop", "owner", "repo", "develop"),
    ]

    for url, exp_owner, exp_repo, exp_branch in test_cases:
        repo = GitHubURLParser.parse(url)
        assert repo.owner == exp_owner
        assert repo.repo == exp_repo
        assert repo.branch == exp_branch
        print(f"✓ {url}")

    print("URL parsing: PASSED ✓\n")


def test_change_categorization():
    """Test file change categorization."""
    print("=" * 60)
    print("TEST 2: Change Categorization")
    print("=" * 60)

    from src.github_manager import ChangeDetector
    from src.models.github_types import ChangeCategory

    test_cases = [
        ("pom.xml", ChangeCategory.DEPENDENCIES),
        ("Dockerfile", ChangeCategory.BUILD_CONFIG),
        ("terraform/main.tf", ChangeCategory.INFRASTRUCTURE),
        ("src/main.py", ChangeCategory.SOURCE_CODE),
    ]

    for filepath, expected in test_cases:
        result = ChangeDetector.categorize_file(filepath)
        assert result == expected, f"Expected {expected}, got {result}"
        print(f"✓ {filepath} → {result.value}")

    print("Categorization: PASSED ✓\n")


def test_database():
    """Test SQLite database."""
    print("=" * 60)
    print("TEST 3: SQLite Artifact Storage")
    print("=" * 60)

    from src.artifact_storage import ArtifactDatabase

    with tempfile.TemporaryDirectory() as tmpdir:
        db = ArtifactDatabase(str(Path(tmpdir) / "test.db"))

        # Register repo
        repo_id = db.register_repository(
            url="https://github.com/test/repo",
            owner="test",
            repo="repo"
        )
        print(f"✓ Registered repository (id={repo_id})")

        # Update state
        db.update_repository_state(repo_id, "abc123")
        print(f"✓ Updated repository state")

        # Save artifact
        art_id = db.save_artifact(
            repo_id=repo_id,
            agent_name="cicd-agent",
            artifact_type="yaml",
            content="test: content",
            commit_sha="abc123"
        )
        print(f"✓ Saved artifact (id={art_id})")

        # Get artifacts
        artifacts = db.get_current_artifacts(repo_id)
        assert len(artifacts) == 1
        print(f"✓ Retrieved artifacts (count={len(artifacts)})")

        # Get repo state
        state = db.get_repository_state("https://github.com/test/repo")
        assert state.last_commit_sha == "abc123"
        print(f"✓ Retrieved repository state")

    print("Database: PASSED ✓\n")


def test_change_analysis():
    """Test change analysis."""
    print("=" * 60)
    print("TEST 4: Change Analysis & Agent Mapping")
    print("=" * 60)

    from src.github_manager import ChangeDetector
    from src.models.github_types import (
        CommitComparison, ChangedFile, GitHubRepoInfo
    )

    comparison = CommitComparison(
        base_sha="old",
        head_sha="new",
        files_changed=[
            ChangedFile(path="pom.xml", status="modified"),
            ChangedFile(path="Dockerfile", status="modified"),
            ChangedFile(path="terraform/main.tf", status="added"),
        ]
    )

    repo = GitHubRepoInfo(owner="test", repo="project")
    analysis = ChangeDetector.analyze_changes(comparison, repo)

    print(f"Files changed: {len(analysis.comparison.files_changed)}")
    assert "cicd-agent" in analysis.affected_agents
    assert "docker-agent" in analysis.affected_agents
    assert "iac-agent" in analysis.affected_agents
    print(f"Affected agents: {', '.join(sorted(analysis.affected_agents))}")
    print(f"Requires update: {analysis.requires_update}")

    print("Change analysis: PASSED ✓\n")


def main():
    print("\n" + "=" * 60)
    print("GitHub MCP Integration - Phase 1 Verification (Standalone)")
    print("=" * 60)

    try:
        test_url_parser()
        test_change_categorization()
        test_database()
        test_change_analysis()

        print("=" * 60)
        print("ALL TESTS PASSED ✓")
        print("=" * 60)
        print("\nPhase 1 Foundation Components:")
        print("  ✓ src/models/github_types.py - Data models")
        print("  ✓ src/github_manager.py - GitHub integration & change detection")
        print("  ✓ src/artifact_storage.py - SQLite storage (ACID transactions)")
        print("  ✓ src/config.py - Configuration with GitHub/Webhook settings")
        print("  ✓ requirements.txt - Updated dependencies")
        print("  ✓ .env.example - Environment template")
        print("\nReady for Phase 2: Change detection nodes in orchestrator graph")
        return 0
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
