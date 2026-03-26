#!/usr/bin/env python3
"""
Test GitHub Actions workflow generation using orchestrator.

Usage:
    python test_gha.py "https://github.com/owner/repo"
    python test_gha.py "https://github.com/spring-projects/spring-boot"
"""

import subprocess
import sys
from pathlib import Path


def test_gha_generation(github_url: str) -> int:
    """Test GitHub Actions generation for a repository."""

    orchestrator_dir = Path(__file__).parent

    print("=" * 70)
    print("GitHub Actions Workflow Generation Test")
    print("=" * 70)
    print(f"\nRepository: {github_url}\n")

    # Run orchestrator with GitHub URL and GHA prompt
    cmd = [
        sys.executable,
        "run_orchestrator.py",
        "--github-url", github_url,
        "--prompt", (
            "Generate a complete GitHub Actions workflow that:\n"
            "1. Installs dependencies\n"
            "2. Builds the project\n"
            "3. Runs tests\n"
            "4. Reports results"
        ),
        "--output-scope", "asked"
    ]

    print("Running orchestrator...\n")

    result = subprocess.run(
        cmd,
        cwd=orchestrator_dir,
        capture_output=False,
        text=True
    )

    print("\n" + "=" * 70)
    if result.returncode == 0:
        print("✓ Test completed successfully")
    else:
        print(f"✗ Test failed with exit code: {result.returncode}")
    print("=" * 70 + "\n")

    return result.returncode


def main():
    if len(sys.argv) < 2:
        github_url = "https://github.com/spring-projects/spring-boot"
        print(f"No URL provided, using default: {github_url}\n")
    else:
        github_url = sys.argv[1]

    return test_gha_generation(github_url)


if __name__ == "__main__":
    sys.exit(main())
