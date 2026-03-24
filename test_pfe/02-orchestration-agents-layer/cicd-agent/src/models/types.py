"""Data types and models for CI/CD Agent"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime

class RequestType(str, Enum):
    """Types of user requests"""
    CREATE_WORKFLOW = "create_workflow"
    MIGRATE_WORKFLOW = "migrate_workflow"
    OPTIMIZE_WORKFLOW = "optimize_workflow"
    VALIDATE_WORKFLOW = "validate_workflow"

@dataclass
class UserRequest:
    """User natural language request"""
    text: str
    request_type: RequestType = RequestType.CREATE_WORKFLOW
    context: Dict[str, Any] = field(default_factory=dict)
    repo_path: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class IntentMetadata:
    """Extracted intent and metadata from user request"""
    intent: str
    keywords: List[str]
    request_type: RequestType
    required_tools: List[str]
    confidence: float

@dataclass
class RepositoryContext:
    """Information about the repository"""
    owner: str
    name: str
    url: str
    default_branch: str = "main"
    languages: List[str] = field(default_factory=list)
    existing_workflows: List[str] = field(default_factory=list)
    build_system: Optional[str] = None

@dataclass
class WorkflowTemplate:
    """GitHub Actions workflow template"""
    name: str
    description: str
    triggers: List[str]
    jobs: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class GeneratedWorkflow:
    """Generated workflow from LLM"""
    yaml_content: str
    metadata: Dict[str, Any]
    is_valid: bool = False
    validation_errors: List[str] = field(default_factory=list)
    attempts: int = 0

@dataclass
class WorkflowLockFile:
    """Lock file for reproducible workflow execution"""
    workflow_name: str
    generated_at: datetime
    generator_version: str
    dependencies: Dict[str, str] = field(default_factory=dict)
    checksum: Optional[str] = None

@dataclass
class ValidationResult:
    """Result of workflow validation"""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)

@dataclass
class SecurityAuditResult:
    """Security audit result for workflow"""
    is_safe: bool
    risks: List[Dict[str, Any]] = field(default_factory=list)
    actions_used: List[str] = field(default_factory=list)
    unsafe_patterns: List[str] = field(default_factory=list)

@dataclass
class PipelineResult:
    """Final result from CI/CD pipeline"""
    success: bool
    workflow_yaml: str
    lock_file: Optional[WorkflowLockFile]
    validation_result: Optional[ValidationResult]
    security_audit: Optional[SecurityAuditResult]
    generation_latency_ms: float
    attempts: int
    errors: List[str] = field(default_factory=list)
