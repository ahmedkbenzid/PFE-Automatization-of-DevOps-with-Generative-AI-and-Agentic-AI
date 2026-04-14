"""Dependency Analyzer - Extract versions and requirements from project files.

CI/CD agent uses this analyzer to detect runtime/framework versions so generated
workflows can configure compatible setup-* actions and build steps.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class DependencyInfo:
    """Extracted dependency and version information."""

    # Language/runtime versions
    python_version: Optional[str] = None
    java_version: Optional[str] = None
    node_version: Optional[str] = None
    go_version: Optional[str] = None

    # Framework versions
    django_version: Optional[str] = None
    fastapi_version: Optional[str] = None
    flask_version: Optional[str] = None
    spring_boot_version: Optional[str] = None
    express_version: Optional[str] = None

    # Build tool versions
    maven_version: Optional[str] = None
    gradle_version: Optional[str] = None
    npm_version: Optional[str] = None
    pip_version: Optional[str] = None

    # Critical dependencies
    critical_packages: Dict[str, str] = field(default_factory=dict)

    # Metadata
    has_version_conflicts: bool = False
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


class DependencyAnalyzer:
    """Analyze project dependency files to extract version constraints."""

    def __init__(self, repository_path: str):
        self.repo = Path(repository_path)
        self.info = DependencyInfo()

    def analyze(self) -> DependencyInfo:
        self._analyze_python_dependencies()
        self._analyze_java_dependencies()
        self._analyze_nodejs_dependencies()
        self._analyze_go_dependencies()
        self._validate_compatibility()
        return self.info

    # ---------------------------------------------------------------------
    # Python
    # ---------------------------------------------------------------------

    def _analyze_python_dependencies(self) -> None:
        req_file = self.repo / "requirements.txt"
        if req_file.exists():
            self._parse_requirements_txt(req_file)

        pyproject = self.repo / "pyproject.toml"
        if pyproject.exists():
            self._parse_pyproject_toml(pyproject)

        setup_py = self.repo / "setup.py"
        if setup_py.exists():
            self._parse_setup_py(setup_py)

        if not self.info.python_version:
            self.info.python_version = self._infer_python_version()

    def _parse_requirements_txt(self, file_path: Path) -> None:
        try:
            content = file_path.read_text(encoding="utf-8")
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("-r") or line.startswith("-e"):
                    continue

                match = re.match(r"^([a-zA-Z0-9_\-\.]+)\s*(==|>=|<=|~=|>|<)\s*([0-9\.]+)", line)
                if not match:
                    continue

                package, _operator, version = match.groups()
                package = package.lower()
                self.info.critical_packages[package] = version

                if package == "django":
                    self.info.django_version = version
                    self.info.critical_packages["Django"] = version
                    self._check_django_python_compatibility(version)
                elif package == "fastapi":
                    self.info.fastapi_version = version
                    self.info.critical_packages["FastAPI"] = version
                elif package == "flask":
                    self.info.flask_version = version
                    self.info.critical_packages["Flask"] = version
        except Exception as exc:
            self.info.warnings.append(f"Failed to parse requirements.txt: {exc}")

    def _parse_pyproject_toml(self, file_path: Path) -> None:
        try:
            content = file_path.read_text(encoding="utf-8")

            py_match = re.search(r"python\s*=\s*[\"']([^\"']+)[\"']", content)
            if py_match:
                version = re.search(r"(\d+\.\d+)", py_match.group(1))
                if version:
                    self.info.python_version = version.group(1)

            django_match = re.search(r"[Dd]jango\s*=\s*[\"']([^\"']+)[\"']", content)
            if django_match:
                version = re.search(r"(\d+\.\d+\.\d+)", django_match.group(1))
                if version:
                    self.info.django_version = version.group(1)
        except Exception as exc:
            self.info.warnings.append(f"Failed to parse pyproject.toml: {exc}")

    def _parse_setup_py(self, file_path: Path) -> None:
        try:
            content = file_path.read_text(encoding="utf-8")
            py_req = re.search(r"python_requires\s*=\s*[\"']([^\"']+)[\"']", content)
            if py_req:
                version = re.search(r"(\d+\.\d+)", py_req.group(1))
                if version:
                    self.info.python_version = version.group(1)
        except Exception as exc:
            self.info.warnings.append(f"Failed to parse setup.py: {exc}")

    def _infer_python_version(self) -> Optional[str]:
        if self.info.django_version:
            major, minor = map(int, self.info.django_version.split(".")[:2])
            if major >= 4:
                return "3.11"
            if major == 3:
                return "3.8"
        if self.info.fastapi_version:
            return "3.11"
        if self.info.flask_version:
            major = int(self.info.flask_version.split(".")[0])
            if major >= 3:
                return "3.11"
            return "3.9"
        return "3.11"

    def _check_django_python_compatibility(self, django_version: str) -> None:
        try:
            major, minor = map(int, django_version.split(".")[:2])
            if major >= 5:
                self.info.recommendations.append(
                    f"Django {django_version} requires Python 3.10+. Recommend Python 3.11 or 3.12."
                )
            elif major == 4 and minor >= 2:
                self.info.recommendations.append(
                    f"Django {django_version} requires Python 3.8+. Recommend Python 3.11."
                )
        except ValueError:
            return

    # ---------------------------------------------------------------------
    # Java
    # ---------------------------------------------------------------------

    def _analyze_java_dependencies(self) -> None:
        pom_xml = self.repo / "pom.xml"
        if pom_xml.exists():
            self._parse_pom_xml(pom_xml)

        build_gradle = self.repo / "build.gradle"
        if build_gradle.exists():
            self._parse_build_gradle(build_gradle)

    def _parse_pom_xml(self, file_path: Path) -> None:
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            ns_url = "http://maven.apache.org/POM/4.0.0"

            properties = root.find(".//properties")
            if properties is None:
                properties = root.find(f".//{{{ns_url}}}properties")

            if properties is not None:
                for java_prop in ["java.version", "maven.compiler.source", "maven.compiler.target", "project.java.version"]:
                    elem = properties.find(java_prop)
                    if elem is None:
                        elem = properties.find(f"{{{ns_url}}}{java_prop}")
                    if elem is not None and elem.text:
                        self.info.java_version = elem.text.strip()
                        break

                spring_boot_elem = properties.find("spring-boot.version")
                if spring_boot_elem is None:
                    spring_boot_elem = properties.find(f"{{{ns_url}}}spring-boot.version")
                if spring_boot_elem is not None and spring_boot_elem.text:
                    self.info.spring_boot_version = spring_boot_elem.text.strip()
                    self.info.critical_packages["Spring Boot"] = self.info.spring_boot_version
                    self._check_spring_boot_java_compatibility()

            if not self.info.spring_boot_version:
                parent = root.find(".//parent")
                if parent is None:
                    parent = root.find(f".//{{{ns_url}}}parent")
                if parent is not None:
                    artifact_id = parent.find("artifactId")
                    version_elem = parent.find("version")
                    if artifact_id is None:
                        artifact_id = parent.find(f"{{{ns_url}}}artifactId")
                    if version_elem is None:
                        version_elem = parent.find(f"{{{ns_url}}}version")

                    if artifact_id is not None and "spring-boot" in (artifact_id.text or "").lower():
                        if version_elem is not None and version_elem.text:
                            self.info.spring_boot_version = version_elem.text.strip()
                            self.info.critical_packages["Spring Boot"] = self.info.spring_boot_version
                            self._check_spring_boot_java_compatibility()
        except Exception as exc:
            self.info.warnings.append(f"Failed to parse pom.xml: {exc}")

    def _parse_build_gradle(self, file_path: Path) -> None:
        try:
            content = file_path.read_text(encoding="utf-8")
            java_match = re.search(r"sourceCompatibility\s*=\s*[\"']?([0-9\.]+)[\"']?", content)
            if java_match:
                self.info.java_version = java_match.group(1)

            spring_match = re.search(r"org\.springframework\.boot[\"'].*version\s+[\"']([0-9\.]+)[\"']", content)
            if spring_match:
                self.info.spring_boot_version = spring_match.group(1)
                self.info.critical_packages["Spring Boot"] = self.info.spring_boot_version
                self._check_spring_boot_java_compatibility()
        except Exception as exc:
            self.info.warnings.append(f"Failed to parse build.gradle: {exc}")

    def _check_spring_boot_java_compatibility(self) -> None:
        if not self.info.spring_boot_version:
            return
        try:
            major = int(self.info.spring_boot_version.split(".")[0])
            if major >= 3:
                if self.info.java_version and int(float(self.info.java_version)) < 17:
                    self.info.has_version_conflicts = True
                    self.info.warnings.append(
                        f"CONFLICT: Spring Boot {self.info.spring_boot_version} requires Java 17+, "
                        f"but detected Java {self.info.java_version}"
                    )
                self.info.recommendations.append(
                    f"Spring Boot {self.info.spring_boot_version} requires Java 17 or higher."
                )
            elif major == 2:
                self.info.recommendations.append(
                    f"Spring Boot {self.info.spring_boot_version} works with Java 8+, but Java 11 or 17 is recommended."
                )
        except ValueError:
            return

    # ---------------------------------------------------------------------
    # Node.js
    # ---------------------------------------------------------------------

    def _analyze_nodejs_dependencies(self) -> None:
        package_json = self.repo / "package.json"
        if package_json.exists():
            self._parse_package_json(package_json)

    def _parse_package_json(self, file_path: Path) -> None:
        try:
            content = json.loads(file_path.read_text(encoding="utf-8"))

            if "engines" in content and "node" in content["engines"]:
                node_version_spec = content["engines"]["node"]
                version = re.search(r"(\d+)", node_version_spec)
                if version:
                    self.info.node_version = version.group(1)

            dependencies = content.get("dependencies", {})
            if "express" in dependencies:
                clean_version = re.sub(r"[\^~]", "", dependencies["express"])
                self.info.express_version = clean_version
                self.info.critical_packages["Express"] = clean_version
        except Exception as exc:
            self.info.warnings.append(f"Failed to parse package.json: {exc}")

    # ---------------------------------------------------------------------
    # Go
    # ---------------------------------------------------------------------

    def _analyze_go_dependencies(self) -> None:
        go_mod = self.repo / "go.mod"
        if go_mod.exists():
            self._parse_go_mod(go_mod)

    def _parse_go_mod(self, file_path: Path) -> None:
        try:
            content = file_path.read_text(encoding="utf-8")
            go_match = re.search(r"^go\s+(\d+\.\d+)", content, re.MULTILINE)
            if go_match:
                self.info.go_version = go_match.group(1)
        except Exception as exc:
            self.info.warnings.append(f"Failed to parse go.mod: {exc}")

    # ---------------------------------------------------------------------
    # Validation
    # ---------------------------------------------------------------------

    def _validate_compatibility(self) -> None:
        if self.info.python_version and self.info.django_version:
            py_major, py_minor = map(int, self.info.python_version.split(".")[:2])
            dj_major, _dj_minor = map(int, self.info.django_version.split(".")[:2])
            if dj_major >= 4 and py_major == 3 and py_minor < 8:
                self.info.has_version_conflicts = True
                self.info.warnings.append(
                    f"Django {self.info.django_version} requires Python 3.8+, but Python {self.info.python_version} is specified"
                )

        if not self.info.java_version and self.info.spring_boot_version:
            major = int(self.info.spring_boot_version.split(".")[0])
            if major >= 3:
                self.info.java_version = "17"
                self.info.recommendations.append(
                    "Java version not specified in pom.xml. Auto-detected Java 17 based on Spring Boot 3.x requirement."
                )

    def get_ci_setup_recommendation(self) -> Dict[str, Any]:
        """Recommend CI setup actions based on detected versions."""
        recommendations: Dict[str, Any] = {}

        if self.info.python_version:
            recommendations["python"] = {
                "action": "actions/setup-python@v4",
                "version": self.info.python_version,
            }

        if self.info.java_version:
            recommendations["java"] = {
                "action": "actions/setup-java@v4",
                "version": self.info.java_version,
                "distribution": "temurin",
            }

        if self.info.node_version:
            recommendations["node"] = {
                "action": "actions/setup-node@v4",
                "version": self.info.node_version,
            }

        if self.info.go_version:
            recommendations["go"] = {
                "action": "actions/setup-go@v4",
                "version": self.info.go_version,
            }

        return recommendations
