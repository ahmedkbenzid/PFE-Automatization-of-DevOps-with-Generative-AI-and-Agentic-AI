"""Validation Layer: trivy-like vulnerability gate."""

from __future__ import annotations


class TrivyValidator:
    """Provide lightweight vulnerability heuristics without remote scans."""

    def run(self, dockerfile_content: str) -> dict:
        findings = []

        if "ubuntu:latest" in dockerfile_content or "alpine:latest" in dockerfile_content:
            findings.append("Base image uses floating latest tag.")

        if "curl | sh" in dockerfile_content:
            findings.append("Piped shell install detected; integrity verification missing.")

        return {"passed": len(findings) == 0, "findings": findings}
