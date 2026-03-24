"""Tools Layer: generate_file component."""

from __future__ import annotations

from src.models.types import GeneratedConfiguration, RepositoryContext, UserRequest


class GenerateFile:
    """Generate Dockerfile content aligned with detected project stack."""

    def generate(self, request: UserRequest, context: RepositoryContext, stack_type: str) -> GeneratedConfiguration:
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
