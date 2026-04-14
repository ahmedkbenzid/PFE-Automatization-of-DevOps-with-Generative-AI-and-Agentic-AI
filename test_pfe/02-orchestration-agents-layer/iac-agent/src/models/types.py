from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class RequestType(str, Enum):
    """Types of IaC requests."""

    TERRAFORM = "terraform"
    OPTIMIZE = "optimize"
    VALIDATE = "validate"
    UNKNOWN = "unknown"


@dataclass
class UserRequest:
    """User request for infrastructure generation."""

    text: str
    request_type: RequestType = RequestType.UNKNOWN
    context: Dict[str, Any] = field(default_factory=dict)
    repository_path: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class RepositoryContext:
    """Context gathered from repository analysis."""

    repository_path: str
    project_languages: List[str] = field(default_factory=list)
    frameworks: List[str] = field(default_factory=list)
    existing_terraform_files: List[str] = field(default_factory=list)
    detected_cloud_provider: Optional[str] = None
    detected_resources: List[str] = field(default_factory=list)
    has_dockerfile: bool = False
    has_k8s_manifests: bool = False


@dataclass
class TerraformConfiguration:
    """Generated Terraform configuration payload expected by orchestrator."""

    providers_tf: Optional[str] = None
    variables_tf: Optional[str] = None
    main_tf: Optional[str] = None
    outputs_tf: Optional[str] = None
    provider: str = "aws"
    resources: List[str] = field(default_factory=list)
    is_valid: bool = False
    combined_hcl: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    generation_attempts: int = 1


@dataclass
class ValidationResult:
    """Terraform validation summary."""

    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)


@dataclass
class PipelineResult:
    """Final output of IaC pipeline."""

    success: bool
    request: UserRequest
    terraform_config: TerraformConfiguration
    context: Optional[RepositoryContext] = None
    validation: Optional[ValidationResult] = None
    error_message: Optional[str] = None
    processing_time_ms: int = 0
