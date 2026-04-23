from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class UserRequest:
    text: str
    repository_path: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class RepositoryContext:
    repository_path: str
    project_languages: List[str] = field(default_factory=list)
    frameworks: List[str] = field(default_factory=list)
    package_managers: List[str] = field(default_factory=list)
    build_system: Optional[str] = None
    has_dockerfile: bool = False
    has_k8s_manifests: bool = False
    image_name: Optional[str] = None
    service_port: int = 80
    container_port: int = 8000


@dataclass
class KubernetesManifests:
    namespace_yaml: str = ""
    configmap_yaml: str = ""
    secret_yaml: str = ""
    deployment_yaml: str = ""
    service_yaml: str = ""
    ingress_yaml: str = ""
    hpa_yaml: str = ""
    namespace: str = ""
    app_name: str = ""
    image: str = ""
    replicas: int = 1
    is_valid: bool = False
    files: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class PipelineResult:
    success: bool
    request: UserRequest
    k8s_manifests: KubernetesManifests
    context: Optional[RepositoryContext] = None
    validation: Optional[ValidationResult] = None
    error_message: Optional[str] = None
    processing_time_ms: int = 0
