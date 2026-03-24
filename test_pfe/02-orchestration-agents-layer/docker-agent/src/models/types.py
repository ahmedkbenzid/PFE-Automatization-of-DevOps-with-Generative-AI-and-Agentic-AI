from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum


class RequestType(str, Enum):
    """Types of Docker containerization requests."""
    DOCKERFILE = "dockerfile"
    COMPOSE = "compose"
    OPTIMIZATION = "optimization"
    SECURITY_SCAN = "security_scan"
    UNKNOWN = "unknown"

@dataclass
class UserRequest:
    """User request for containerization."""
    text: str
    request_type: RequestType = RequestType.UNKNOWN
    context: Dict[str, Any] = field(default_factory=dict)
    repository_path: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class IntentMetadata:
    """Extracted intent from user request."""
    primary_intent: str
    keywords: List[str]
    detected_request_type: RequestType
    required_components: List[str]
    confidence_score: float

@dataclass
class RepositoryContext:
    """Context gathered from the local repository."""
    repository_path: str
    project_languages: List[str]
    package_managers: List[str]
    frameworks: List[str]
    existing_dockerfiles: List[str]
    existing_compose_files: List[str]
    detected_ports: List[int]
    environment_variables: List[str]

@dataclass
class DatasetExample:
    """An example Dockerfile or Compose file from the knowledge base."""
    id: str
    description: str
    content: str
    tags: List[str]
    relevance_score: float = 0.0

@dataclass
class GeneratedConfiguration:
    """The generated Docker configuration."""
    dockerfile_content: Optional[str] = None
    compose_content: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    generation_attempts: int = 1
    llm_model_used: str = ""
    is_valid: bool = False

@dataclass
class ValidationResult:
    """Results from schema and best-practice validation."""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    suggestions: List[str]

@dataclass
class SecurityAuditResult:
    """Results from security guardrails."""
    is_safe: bool
    identified_risks: List[str]
    unsafe_patterns_found: List[str]
    recommended_fixes: List[str]
    base_image_vulnerabilities: List[str] = field(default_factory=list)

@dataclass
class DockerLockFile:
    """Pinned versions for reproducibility."""
    base_images: Dict[str, str]
    dependencies: Dict[str, str]
    created_at: datetime = field(default_factory=datetime.now)

@dataclass
class PipelineResult:
    """Final output of the Docker agent pipeline."""
    success: bool
    request: UserRequest
    configuration: GeneratedConfiguration
    intent: Optional[IntentMetadata] = None
    context: Optional[RepositoryContext] = None
    validation: Optional[ValidationResult] = None
    security: Optional[SecurityAuditResult] = None
    lock_file: Optional[DockerLockFile] = None
    error_message: Optional[str] = None
    processing_time_ms: int = 0
