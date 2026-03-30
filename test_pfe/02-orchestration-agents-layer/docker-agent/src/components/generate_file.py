"""Tools Layer: generate_file component."""

from __future__ import annotations

from src.models.types import GeneratedConfiguration, RepositoryContext, UserRequest
from src.components.llm_client import LLMClient


class GenerateFile:
    """Generate Dockerfile content aligned with detected project stack."""

    def __init__(self, use_llm: bool = True):
        """
        Initialize generator.
        
        Args:
            use_llm: If True, use LLM for generation. If False, use templates only.
        """
        self.use_llm = use_llm
        self.llm_client = None
        if use_llm:
            try:
                self.llm_client = LLMClient()
            except Exception as e:
                print(f"[Docker Agent] LLM client initialization failed: {e}")
                print("[Docker Agent] Falling back to template-only generation")
                self.use_llm = False

    def generate(self, request: UserRequest, context: RepositoryContext, stack_type: str) -> GeneratedConfiguration:
        # Try LLM generation first if enabled
        if self.use_llm and self.llm_client:
            try:
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
        if stack_type == "node":
            dockerfile = self._node_template(context)
        elif stack_type == "python":
            dockerfile = self._python_template(context)
        elif stack_type == "spring":
            dockerfile = self._java_template(context)
        else:
            dockerfile = self._generic_template(context)

        return GeneratedConfiguration(
            dockerfile_content=dockerfile,
            metadata={
                "stack_type": stack_type,
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
CMD [\"/bin/sh\"]
"""
