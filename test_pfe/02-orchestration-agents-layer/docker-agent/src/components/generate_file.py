"""Tools Layer: generate_file component."""

from __future__ import annotations

from src.models.types import GeneratedConfiguration, RepositoryContext, UserRequest
from src.components.llm_client import LLMClient


class GenerateFile:
    """Generate Dockerfile content aligned with detected project stack."""

    def __init__(self, use_llm: bool = False):
        """
        Initialize generator.
        
        Args:
            use_llm: If True, use LLM for generation. If False, use templates (default).
        """
        self.use_llm = use_llm
        self.llm_client = None
        if use_llm:
            try:
                self.llm_client = LLMClient()
                print(f"[Docker Agent] LLM client initialized: {self.llm_client.model}")
            except Exception as e:
                print(f"[Docker Agent] LLM client initialization failed: {e}")
                print("[Docker Agent] Falling back to template-only generation")
                self.use_llm = False
        else:
            print("[Docker Agent] Using template-based generation (LLM disabled)")

    def generate(self, request: UserRequest, context: RepositoryContext, stack_type: str) -> GeneratedConfiguration:
        print(f"[Docker Agent] Generation mode: {'LLM' if self.use_llm and self.llm_client else 'Template'}")
        
        # Try LLM generation first if enabled
        if self.use_llm and self.llm_client:
            try:
                print(f"[Docker Agent] Attempting LLM generation for stack: {stack_type}")
                return self._llm_generate(request, context, stack_type)
            except Exception as e:
                print(f"[Docker Agent] LLM generation failed: {e}")
                print("[Docker Agent] Falling back to template generation")
        
        # Fallback to template generation
        return self._template_generate(request, context, stack_type)

    def _llm_generate(self, request: UserRequest, context: RepositoryContext, stack_type: str) -> GeneratedConfiguration:
        """Generate Dockerfile using LLM"""
        context_dict = {
            "stack_type": stack_type,
            "detected_ports": context.detected_ports,
            "package_managers": context.package_managers,
            "build_tools": context.build_tools,
            "frameworks": context.frameworks,
        }
        
        dockerfile = self.llm_client.generate_dockerfile(request.text, context_dict)
        
        return GeneratedConfiguration(
            dockerfile_content=dockerfile,
            metadata={
                "stack_type": stack_type,
                "generator": "llm",
                "requested": request.text,
            },
            generation_attempts=1,
            llm_model_used=self.llm_client.model,
            is_valid=False,
        )

    def _template_generate(self, request: UserRequest, context: RepositoryContext, stack_type: str) -> GeneratedConfiguration:
        """Generate Dockerfile using templates"""
        print(f"[Docker Agent] Generating Dockerfile for stack: {stack_type}")
        
        # Normalize stack type
        stack_type_lower = (stack_type or "").lower()
        
        if stack_type_lower == "node" or "node" in stack_type_lower or "javascript" in stack_type_lower:
            dockerfile = self._node_template(context)
            normalized_stack = "node"
        elif stack_type_lower == "python" or "python" in stack_type_lower:
            dockerfile = self._python_template(context)
            normalized_stack = "python"
        elif stack_type_lower in ("spring", "java", "maven", "gradle") or "java" in stack_type_lower or "spring" in stack_type_lower:
            dockerfile = self._java_template(context)
            normalized_stack = "spring"
        elif stack_type_lower == "go" or "golang" in stack_type_lower:
            dockerfile = self._go_template(context)
            normalized_stack = "go"
        else:
            print(f"[Docker Agent] Unknown stack '{stack_type}', using generic template")
            dockerfile = self._generic_template(context)
            normalized_stack = "generic"

        return GeneratedConfiguration(
            dockerfile_content=dockerfile,
            metadata={
                "stack_type": normalized_stack,
                "original_stack_input": stack_type,
                "generator": "template",
                "requested": request.text,
            },
            generation_attempts=1,
            llm_model_used="template-engine",
            is_valid=False,
        )

    def _node_template(self, context: RepositoryContext) -> str:
        port = context.detected_ports[0] if context.detected_ports else 3000
        return f"""FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
COPY package*.json ./
RUN npm ci --omit=dev && npm cache clean --force
COPY --from=builder /app/dist ./dist
USER node
EXPOSE {port}
CMD [\"node\", \"dist/main.js\"]
"""

    def _python_template(self, context: RepositoryContext) -> str:
        port = context.detected_ports[0] if context.detected_ports else 8000
        return f"""FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -m appuser
USER appuser
EXPOSE {port}
CMD [\"python\", \"main.py\"]
"""

    def _java_template(self, context: RepositoryContext) -> str:
        port = context.detected_ports[0] if context.detected_ports else 8080
        return f"""FROM maven:3.9.8-eclipse-temurin-17 AS builder
WORKDIR /app
COPY pom.xml ./
COPY src ./src
RUN mvn -B -DskipTests package

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=builder /app/target/*.jar app.jar
RUN useradd -m appuser
USER appuser
EXPOSE {port}
CMD [\"java\", \"-jar\", \"app.jar\"]
"""

    def _generic_template(self, context: RepositoryContext) -> str:
        port = context.detected_ports[0] if context.detected_ports else 8080
        return f"""FROM ubuntu:24.04
WORKDIR /app
COPY . .
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
RUN useradd -m appuser
USER appuser
EXPOSE {port}
CMD ["/bin/sh"]
"""

    def _go_template(self, context: RepositoryContext) -> str:
        """Template for Go applications"""
        port = context.detected_ports[0] if context.detected_ports else 8080
        return f"""FROM golang:1.21-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o main .

FROM alpine:latest
RUN apk --no-cache add ca-certificates
WORKDIR /root/
COPY --from=builder /app/main .
RUN adduser -D appuser
USER appuser
EXPOSE {port}
CMD ["./main"]
"""

