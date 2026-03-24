"""Validation Layer: hadolint-like lint gate."""

from __future__ import annotations


class HadolintValidator:
    """Simulate key hadolint rules for offline validation."""

    def run(self, dockerfile_content: str) -> dict:
        issues = []
        lines = dockerfile_content.splitlines()

        if any(line.startswith("FROM ") and ":latest" in line for line in lines):
            issues.append("Use pinned image tags instead of latest.")

        if not any(line.startswith("USER ") for line in lines):
            issues.append("Specify a non-root USER.")

        return {"passed": len(issues) == 0, "issues": issues}
