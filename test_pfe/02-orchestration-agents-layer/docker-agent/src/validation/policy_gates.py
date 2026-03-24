"""Validation Layer: policy gate checks."""

from __future__ import annotations


class PolicyGates:
    """Evaluate organization policy constraints for Docker artifacts."""

    def run(self, dockerfile_content: str) -> dict:
        violations = []

        if "ADD http" in dockerfile_content or "ADD https" in dockerfile_content:
            violations.append("Policy forbids remote ADD URLs.")

        if "USER root" in dockerfile_content:
            violations.append("Policy forbids running as root.")

        return {"passed": len(violations) == 0, "violations": violations}
