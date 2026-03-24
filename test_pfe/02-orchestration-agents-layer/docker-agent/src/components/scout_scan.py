"""Tools Layer: scout_scan component for security flags."""

from __future__ import annotations

from src.models.types import GeneratedConfiguration, SecurityAuditResult


class ScoutScan:
    """Run basic static security checks over generated Dockerfile content."""

    def run(self, configuration: GeneratedConfiguration) -> SecurityAuditResult:
        content = configuration.dockerfile_content or ""
        risks = []
        patterns = []
        fixes = []

        if "USER " not in content:
            risks.append("Container may run as root user.")
            patterns.append("missing-user")
            fixes.append("Add a non-root USER instruction before runtime commands.")

        if "ADD http" in content or "ADD https" in content:
            risks.append("Remote ADD instructions may bypass integrity checks.")
            patterns.append("remote-add")
            fixes.append("Use curl/wget with checksum verification in RUN instead of ADD URL.")

        if "apt-get install" in content and "--no-install-recommends" not in content:
            risks.append("Package install may include unnecessary packages.")
            patterns.append("apt-install-without-no-install-recommends")
            fixes.append("Use --no-install-recommends and clean apt cache.")

        return SecurityAuditResult(
            is_safe=len(risks) == 0,
            identified_risks=risks,
            unsafe_patterns_found=patterns,
            recommended_fixes=fixes,
            base_image_vulnerabilities=[],
        )
