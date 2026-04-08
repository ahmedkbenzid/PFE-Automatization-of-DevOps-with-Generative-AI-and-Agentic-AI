"""Dependency Analyzer - Extract versions and requirements from project files.

This module analyzes project dependency files to extract:
- Language/runtime versions (Python, Java, Node.js, etc.)
- Framework versions (Spring Boot, Django, FastAPI, etc.)
- Build tool versions (Maven, Gradle, npm, etc.)
- Critical dependency constraints

This information ensures generated Dockerfiles and CI/CD scripts use
compatible base images and tool versions.
"""

from __future__ import annotations

import re
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class DependencyInfo:
    """Extracted dependency and version information."""
    
    # Language/Runtime versions
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
        """Analyze all dependency files and return consolidated information."""
        self._analyze_python_dependencies()
        self._analyze_java_dependencies()
        self._analyze_nodejs_dependencies()
        self._analyze_go_dependencies()
        self._validate_compatibility()
        return self.info
    
    # =========================================================================
    # PYTHON ANALYSIS
    # =========================================================================
    
    def _analyze_python_dependencies(self) -> None:
        """Analyze Python dependency files."""
        # Check requirements.txt
        req_file = self.repo / "requirements.txt"
        if req_file.exists():
            self._parse_requirements_txt(req_file)
        
        # Check pyproject.toml (Poetry, PEP 621)
        pyproject = self.repo / "pyproject.toml"
        if pyproject.exists():
            self._parse_pyproject_toml(pyproject)
        
        # Check setup.py
        setup_py = self.repo / "setup.py"
        if setup_py.exists():
            self._parse_setup_py(setup_py)
        
        # Infer Python version from dependencies
        if not self.info.python_version:
            self.info.python_version = self._infer_python_version()
    
    def _parse_requirements_txt(self, file_path: Path) -> None:
        """Parse requirements.txt file."""
        try:
            content = file_path.read_text(encoding='utf-8')
            
            for line in content.splitlines():
                line = line.strip()
                
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                
                # Skip -r includes and -e editable installs
                if line.startswith('-r') or line.startswith('-e'):
                    continue
                
                # Parse package==version or package>=version
                match = re.match(r'^([a-zA-Z0-9_\-\.]+)\s*(==|>=|<=|~=|>|<)\s*([0-9\.]+)', line)
                if match:
                    package, operator, version = match.groups()
                    package = package.lower()
                    
                    # Track critical frameworks
                    if package == 'django':
                        self.info.django_version = version
                        self.info.critical_packages['Django'] = version
                        self._check_django_python_compatibility(version)
                    
                    elif package == 'fastapi':
                        self.info.fastapi_version = version
                        self.info.critical_packages['FastAPI'] = version
                    
                    elif package == 'flask':
                        self.info.flask_version = version
                        self.info.critical_packages['Flask'] = version
                    
                    # Track all packages
                    self.info.critical_packages[package] = version
        
        except Exception as e:
            self.info.warnings.append(f"Failed to parse requirements.txt: {str(e)}")
    
    def _parse_pyproject_toml(self, file_path: Path) -> None:
        """Parse pyproject.toml file (basic parsing without toml library)."""
        try:
            content = file_path.read_text(encoding='utf-8')
            
            # Extract Python version constraint
            python_match = re.search(r'python\s*=\s*["\']([^"\']+)["\']', content)
            if python_match:
                version_constraint = python_match.group(1)
                # Convert "^3.9" to "3.9", ">=3.8,<4.0" to "3.8"
                version = re.search(r'(\d+\.\d+)', version_constraint)
                if version:
                    self.info.python_version = version.group(1)
            
            # Extract Django version
            django_match = re.search(r'[Dd]jango\s*=\s*["\']([^"\']+)["\']', content)
            if django_match:
                version = re.search(r'(\d+\.\d+\.\d+)', django_match.group(1))
                if version:
                    self.info.django_version = version.group(1)
        
        except Exception as e:
            self.info.warnings.append(f"Failed to parse pyproject.toml: {str(e)}")
    
    def _parse_setup_py(self, file_path: Path) -> None:
        """Parse setup.py file (regex-based, no AST parsing)."""
        try:
            content = file_path.read_text(encoding='utf-8')
            
            # Extract python_requires
            python_req = re.search(r'python_requires\s*=\s*["\']([^"\']+)["\']', content)
            if python_req:
                version = re.search(r'(\d+\.\d+)', python_req.group(1))
                if version:
                    self.info.python_version = version.group(1)
        
        except Exception as e:
            self.info.warnings.append(f"Failed to parse setup.py: {str(e)}")
    
    def _infer_python_version(self) -> Optional[str]:
        """Infer minimum Python version from framework requirements."""
        # Django 4.2+ requires Python 3.8+
        if self.info.django_version:
            major, minor = map(int, self.info.django_version.split('.')[:2])
            if major >= 4:
                return "3.11"  # Recommended for Django 4.x
            elif major == 3:
                return "3.8"
        
        # FastAPI 0.100+ works best with Python 3.9+
        if self.info.fastapi_version:
            return "3.11"  # Modern FastAPI best practices
        
        # Flask 3.0+ requires Python 3.8+
        if self.info.flask_version:
            major = int(self.info.flask_version.split('.')[0])
            if major >= 3:
                return "3.11"
            return "3.9"
        
        # Default to Python 3.11 (current stable)
        return "3.11"
    
    def _check_django_python_compatibility(self, django_version: str) -> None:
        """Check Django version compatibility with Python."""
        try:
            major, minor = map(int, django_version.split('.')[:2])
            
            if major >= 5:
                # Django 5.0+ requires Python 3.10+
                self.info.recommendations.append(
                    f"Django {django_version} requires Python 3.10+. Recommend Python 3.11 or 3.12."
                )
            elif major == 4 and minor >= 2:
                # Django 4.2+ requires Python 3.8+
                self.info.recommendations.append(
                    f"Django {django_version} requires Python 3.8+. Recommend Python 3.11."
                )
        except ValueError:
            pass
    
    # =========================================================================
    # JAVA ANALYSIS
    # =========================================================================
    
    def _analyze_java_dependencies(self) -> None:
        """Analyze Java dependency files."""
        pom_xml = self.repo / "pom.xml"
        if pom_xml.exists():
            self._parse_pom_xml(pom_xml)
        
        build_gradle = self.repo / "build.gradle"
        if build_gradle.exists():
            self._parse_build_gradle(build_gradle)
    
    def _parse_pom_xml(self, file_path: Path) -> None:
        """Parse Maven pom.xml file."""
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            
            # Define namespace (Maven POM uses default namespace)
            ns = {'m': 'http://maven.apache.org/POM/4.0.0'}
            
            print(f"[DependencyAnalyzer] Parsing pom.xml: {file_path}")
            print(f"[DependencyAnalyzer] Root tag: {root.tag}")
            
            # Try to extract Java version from properties
            properties = root.find('.//properties')
            if properties is None:
                properties = root.find('.//{http://maven.apache.org/POM/4.0.0}properties')
            
            if properties is not None:
                print(f"[DependencyAnalyzer] Found <properties> section")
                
                # Extract Java version - try multiple property names
                for java_prop in ['java.version', 'maven.compiler.source', 'maven.compiler.target', 'project.java.version']:
                    # Try without namespace
                    elem = properties.find(java_prop)
                    if elem is None:
                        # Try with namespace
                        elem = properties.find(f'{{{ns["m"]}}}{java_prop}')
                    
                    if elem is not None and elem.text:
                        self.info.java_version = elem.text.strip()
                        print(f"[DependencyAnalyzer] ✓ Detected Java version {self.info.java_version} from <{java_prop}>")
                        break
                
                if not self.info.java_version:
                    print(f"[DependencyAnalyzer] ⚠️  Java version property not found in <properties>")
                    # List all properties found for debugging
                    for child in properties:
                        print(f"[DependencyAnalyzer]   Found property: {child.tag} = {child.text}")
                
                # Extract Spring Boot version
                spring_boot_elem = properties.find('spring-boot.version')
                if spring_boot_elem is None:
                    spring_boot_elem = properties.find(f'{{{ns["m"]}}}spring-boot.version')
                
                if spring_boot_elem is not None and spring_boot_elem.text:
                    self.info.spring_boot_version = spring_boot_elem.text.strip()
                    print(f"[DependencyAnalyzer] ✓ Detected Spring Boot version {self.info.spring_boot_version}")
                    self.info.critical_packages['Spring Boot'] = self.info.spring_boot_version
                    self._check_spring_boot_java_compatibility()
            else:
                print(f"[DependencyAnalyzer] ⚠️  <properties> section not found in pom.xml")
            
            # Check parent POM for Spring Boot version
            if not self.info.spring_boot_version:
                parent = root.find('.//parent')
                if parent is None:
                    parent = root.find('.//{http://maven.apache.org/POM/4.0.0}parent')
                
                if parent is not None:
                    print(f"[DependencyAnalyzer] Checking parent POM for Spring Boot version")
                    artifact_id = parent.find('artifactId')
                    version_elem = parent.find('version')
                    
                    if artifact_id is None:
                        artifact_id = parent.find(f'{{{ns["m"]}}}artifactId')
                    if version_elem is None:
                        version_elem = parent.find(f'{{{ns["m"]}}}version')
                    
                    if artifact_id is not None and 'spring-boot' in (artifact_id.text or '').lower():
                        if version_elem is not None and version_elem.text:
                            self.info.spring_boot_version = version_elem.text.strip()
                            print(f"[DependencyAnalyzer] ✓ Detected Spring Boot {self.info.spring_boot_version} from parent POM")
                            self.info.critical_packages['Spring Boot'] = self.info.spring_boot_version
                            self._check_spring_boot_java_compatibility()
        
        except Exception as e:
            print(f"[DependencyAnalyzer] ❌ Error parsing pom.xml: {str(e)}")
            self.info.warnings.append(f"Failed to parse pom.xml: {str(e)}")
    
    def _parse_build_gradle(self, file_path: Path) -> None:
        """Parse Gradle build.gradle file."""
        try:
            content = file_path.read_text(encoding='utf-8')
            
            # Extract Java version
            java_match = re.search(r'sourceCompatibility\s*=\s*["\']?([0-9\.]+)["\']?', content)
            if java_match:
                self.info.java_version = java_match.group(1)
            
            # Extract Spring Boot version
            spring_match = re.search(r'org\.springframework\.boot["\'].*version\s+["\']([0-9\.]+)["\']', content)
            if spring_match:
                self.info.spring_boot_version = spring_match.group(1)
                self.info.critical_packages['Spring Boot'] = self.info.spring_boot_version
                self._check_spring_boot_java_compatibility()
        
        except Exception as e:
            self.info.warnings.append(f"Failed to parse build.gradle: {str(e)}")
    
    def _check_spring_boot_java_compatibility(self) -> None:
        """Check Spring Boot version compatibility with Java."""
        if not self.info.spring_boot_version:
            return
        
        try:
            major = int(self.info.spring_boot_version.split('.')[0])
            
            if major >= 3:
                # Spring Boot 3.0+ requires Java 17+
                if self.info.java_version and int(self.info.java_version) < 17:
                    self.info.has_version_conflicts = True
                    self.info.warnings.append(
                        f"CONFLICT: Spring Boot {self.info.spring_boot_version} requires Java 17+, "
                        f"but pom.xml specifies Java {self.info.java_version}"
                    )
                self.info.recommendations.append(
                    f"Spring Boot {self.info.spring_boot_version} requires Java 17 or higher."
                )
            elif major == 2:
                # Spring Boot 2.x requires Java 8+ (recommends 11+)
                self.info.recommendations.append(
                    f"Spring Boot {self.info.spring_boot_version} works with Java 8+, but Java 11 or 17 is recommended."
                )
        
        except ValueError:
            pass
    
    # =========================================================================
    # NODE.JS ANALYSIS
    # =========================================================================
    
    def _analyze_nodejs_dependencies(self) -> None:
        """Analyze Node.js dependency files."""
        package_json = self.repo / "package.json"
        if package_json.exists():
            self._parse_package_json(package_json)
    
    def _parse_package_json(self, file_path: Path) -> None:
        """Parse package.json file."""
        try:
            content = json.loads(file_path.read_text(encoding='utf-8'))
            
            # Extract Node.js version
            if 'engines' in content and 'node' in content['engines']:
                node_version = content['engines']['node']
                # Extract version number from constraints like ">=14.0.0"
                version = re.search(r'(\d+)', node_version)
                if version:
                    self.info.node_version = version.group(1)
            
            # Extract Express version
            dependencies = content.get('dependencies', {})
            if 'express' in dependencies:
                version = dependencies['express']
                # Remove ^ or ~ prefix
                clean_version = re.sub(r'[\^~]', '', version)
                self.info.express_version = clean_version
                self.critical_packages['Express'] = clean_version
        
        except Exception as e:
            self.info.warnings.append(f"Failed to parse package.json: {str(e)}")
    
    # =========================================================================
    # GO ANALYSIS
    # =========================================================================
    
    def _analyze_go_dependencies(self) -> None:
        """Analyze Go dependency files."""
        go_mod = self.repo / "go.mod"
        if go_mod.exists():
            self._parse_go_mod(go_mod)
    
    def _parse_go_mod(self, file_path: Path) -> None:
        """Parse go.mod file."""
        try:
            content = file_path.read_text(encoding='utf-8')
            
            # Extract Go version
            go_match = re.search(r'^go\s+(\d+\.\d+)', content, re.MULTILINE)
            if go_match:
                self.info.go_version = go_match.group(1)
        
        except Exception as e:
            self.info.warnings.append(f"Failed to parse go.mod: {str(e)}")
    
    # =========================================================================
    # VALIDATION
    # =========================================================================
    
    def _validate_compatibility(self) -> None:
        """Validate version compatibility and add recommendations."""
        # Python + Django
        if self.info.python_version and self.info.django_version:
            py_major, py_minor = map(int, self.info.python_version.split('.')[:2])
            dj_major, dj_minor = map(int, self.info.django_version.split('.')[:2])
            
            if dj_major >= 4 and py_major == 3 and py_minor < 8:
                self.info.has_version_conflicts = True
                self.info.warnings.append(
                    f"Django {self.info.django_version} requires Python 3.8+, "
                    f"but Python {self.info.python_version} is specified"
                )
        
        # Java + Spring Boot (already checked in _check_spring_boot_java_compatibility)
        
        # If no Java version specified but Spring Boot 3+ detected
        if not self.info.java_version and self.info.spring_boot_version:
            major = int(self.info.spring_boot_version.split('.')[0])
            if major >= 3:
                self.info.java_version = "17"  # Auto-set to minimum required
                self.info.recommendations.append(
                    "Java version not specified in pom.xml. Auto-detected Java 17 based on Spring Boot 3.x requirement."
                )
    
    def get_dockerfile_base_image_recommendation(self) -> Optional[str]:
        """Recommend Docker base image based on detected versions."""
        if self.info.python_version:
            py_version = self.info.python_version
            return f"python:{py_version}-slim"
        
        if self.info.java_version:
            java_version = self.info.java_version
            return f"eclipse-temurin:{java_version}-jre-jammy"
        
        if self.info.node_version:
            node_version = self.info.node_version
            return f"node:{node_version}-alpine"
        
        if self.info.go_version:
            go_version = self.info.go_version
            return f"golang:{go_version}-alpine"
        
        return None
    
    def get_ci_setup_recommendation(self) -> Dict[str, Any]:
        """Recommend CI/CD setup based on detected versions."""
        recommendations = {}
        
        if self.info.python_version:
            recommendations['python'] = {
                'action': 'actions/setup-python@v4',
                'version': self.info.python_version,
            }
        
        if self.info.java_version:
            recommendations['java'] = {
                'action': 'actions/setup-java@v4',
                'version': self.info.java_version,
                'distribution': 'temurin',
            }
        
        if self.info.node_version:
            recommendations['node'] = {
                'action': 'actions/setup-node@v4',
                'version': self.info.node_version,
            }
        
        if self.info.go_version:
            recommendations['go'] = {
                'action': 'actions/setup-go@v4',
                'version': self.info.go_version,
            }
        
        return recommendations
