"""LLM integration with Ollama and Groq for Docker Agent."""

import os
import time
import logging
from typing import Optional, Any, Callable
from threading import Lock
from src.config import LLM_CONFIG

try:
    from ollama import chat
    ChatFunction = Callable[..., Any]
except ModuleNotFoundError:
    chat = None  # type: ignore
    ChatFunction = None  # type: ignore

try:
    from groq import Groq
except ModuleNotFoundError:
    Groq = None

try:
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
except ImportError:
    retry = None


logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Circuit breaker to prevent cascade failures when LLM API is down."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, failure_threshold: int = 3, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = self.CLOSED
        self._lock = Lock()

    def record_success(self) -> None:
        with self._lock:
            self.failure_count = 0
            self.state = self.CLOSED

    def record_failure(self) -> None:
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = self.OPEN
                logger.warning(f"Circuit breaker opened after {self.failure_count} failures")

    def can_execute(self) -> bool:
        with self._lock:
            if self.state == self.CLOSED:
                return True
            if self.state == self.OPEN and self.last_failure_time:
                if time.time() - self.last_failure_time >= self.recovery_timeout:
                    self.state = self.HALF_OPEN
                    return True
            return False

    def get_state(self) -> str:
        with self._lock:
            return self.state


class LLMClient:
    """Unified LLM client supporting Ollama and Groq with retry, circuit breaker, and timeout."""

    def __init__(self, provider: Optional[str] = None):
        configured_provider = (provider or LLM_CONFIG.get("provider", "ollama")).lower()
        if configured_provider not in {"ollama", "groq"}:
            configured_provider = "ollama"

        self.provider = configured_provider
        self.max_tokens = LLM_CONFIG.get("max_tokens", 4096)
        self.temperature = LLM_CONFIG.get("temperature", 0.2)
        self.client = None
        self.fallback_model = LLM_CONFIG.get("fallback_model", "llama-3.3-70b-versatile")

        self.ollama_circuit = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        self.groq_circuit = CircuitBreaker(failure_threshold=3, recovery_timeout=60)

        self._initialize_providers()

    def _initialize_providers(self) -> None:
        """Initialize LLM providers with circuit breaker awareness."""
        providers_to_try = [self.provider, "groq" if self.provider == "ollama" else "ollama"]
        init_errors = []
        for candidate in providers_to_try:
            try:
                if candidate == "ollama":
                    self._init_ollama()
                else:
                    self._init_groq()
                self.provider = candidate
                logger.info(f"LLM client initialized with provider: {candidate}")
                return
            except Exception as exc:
                init_errors.append(f"{candidate}: {exc}")
                logger.error(f"Failed to initialize {candidate}: {exc}")

        raise RuntimeError(f"Failed to initialize any LLM provider ({'; '.join(init_errors)})")

    def _init_ollama(self) -> None:
        """Initialize Ollama client."""
        if chat is None:
            raise RuntimeError("ollama package is not installed. Run: pip install ollama")
        self.model = LLM_CONFIG.get("model", "gpt-oss:20b:cloud")
        logger.info(f"Using Ollama with model: {self.model}")

    def _init_groq(self) -> None:
        """Initialize Groq client."""
        if Groq is None:
            raise RuntimeError("groq package is not installed. Run: pip install groq")

        api_key = os.getenv("GROQ_API_KEY", "")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY environment variable is required for Groq provider")

        self.client = Groq(api_key=api_key)
        self.model = LLM_CONFIG.get("groq_model", "llama-3.3-70b-versatile")
        logger.info(f"Using Groq with model: {self.model}")

    def _ollama_completion(self, prompt: str) -> str:
        """Generate completion using Ollama with timeout."""
        if chat is None:
            raise RuntimeError("Ollama chat function is not available")

        if not self.ollama_circuit.can_execute():
            logger.warning("Ollama circuit breaker is open, skipping")
            raise RuntimeError("Ollama circuit breaker is open")

        timeout = LLM_CONFIG.get("timeout", 120)
        try:
            response = chat(  # type: ignore
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens,
                    "timeout": timeout,
                }
            )
            self.ollama_circuit.record_success()
            return response.message.content  # type: ignore
        except Exception as e:
            self.ollama_circuit.record_failure()
            logger.error(f"Ollama request failed: {e}")
            raise

    def _groq_completion(self, model: str, prompt: str, max_tokens: Optional[int] = None) -> str:
        """Generate completion using Groq with circuit breaker."""
        if not self.groq_circuit.can_execute():
            logger.warning("Groq circuit breaker is open, skipping")
            raise RuntimeError("Groq circuit breaker is open")

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens or self.max_tokens,
                temperature=self.temperature,
                top_p=0.95,
                stream=False,
            )
            self.groq_circuit.record_success()
            return response.choices[0].message.content
        except Exception as e:
            self.groq_circuit.record_failure()
            logger.error(f"Groq request failed: {e}")
            raise

    def _create_retry_decorator(self):
        """Create retry decorator with exponential backoff."""
        if retry is None:
            raise RuntimeError("tenacity not installed. Run: pip install tenacity")

        return retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(min=2, max=10),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        )

    @property
    def _generate_text_retry(self):
        """Retry-wrapped generate_text method."""
        if retry is None:
            return self._generate_text_no_retry

        @self._create_retry_decorator()
        def wrapped(prompt: str, max_tokens: Optional[int] = None) -> str:
            return self._generate_text_no_retry(prompt, max_tokens)
        return wrapped

    def _generate_text_no_retry(self, prompt: str, max_tokens: Optional[int] = None) -> str:
        """Generate text without retry (internal use)."""
        if self.provider == "ollama":
            try:
                return self._ollama_completion(prompt)
            except Exception as ollama_error:
                if Groq is None:
                    raise
                try:
                    self._init_groq()
                    self.provider = "groq"
                    logger.warning(f"Falling back to Groq after Ollama failure: {ollama_error}")
                    return self._groq_completion(self.model, prompt, max_tokens)
                except Exception:
                    raise Exception(f"Ollama error: {str(ollama_error)}")

        try:
            return self._groq_completion(self.model, prompt, max_tokens)
        except Exception as e:
            error_text = str(e).lower()
            should_try_fallback = (
                "model_decommissioned" in error_text
                or "decommissioned" in error_text
                or "not found" in error_text
            )

            if should_try_fallback and self.fallback_model:
                try:
                    result = self._groq_completion(self.fallback_model, prompt, max_tokens)
                    self.model = self.fallback_model
                    logger.warning(f"Falling back to model: {self.fallback_model}")
                    return result
                except Exception:
                    pass

            raise Exception(f"Error generating text: {str(e)}")

    def generate_text(self, prompt: str, max_tokens: Optional[int] = None) -> str:
        """Generate text using the configured LLM provider with retry."""
        logger.info(f"Generating text with provider: {self.provider}")

        if retry is not None:
            return self._generate_text_retry(prompt, max_tokens)
        return self._generate_text_no_retry(prompt, max_tokens)

    def generate_dockerfile(self, prompt: str, context: dict) -> str:
        """Generate Dockerfile content based on prompt and project context."""
        stack_type = context.get("stack_type", "generic")

        python_version = context.get("python_version", "3.11")
        java_version = context.get("java_version", "17")
        node_version = context.get("node_version", "20")
        go_version = context.get("go_version", "1.21")

        context_items = []
        for k, v in context.items():
            if v and k != "stack_type":
                context_items.append(f"{k}: {v}")
        context_str = "\n".join(context_items) if context_items else "No additional context"

        stack_examples = {
            "spring": f"""EXAMPLE for Java/Spring Boot (MUST FOLLOW THIS STRUCTURE):
```dockerfile
FROM maven:3.9-eclipse-temurin-{java_version}-alpine AS builder
WORKDIR /app
COPY pom.xml ./
COPY src ./src
RUN mvn -B -DskipTests package

FROM eclipse-temurin:{java_version}-jre-jammy
WORKDIR /app
COPY --from=builder /app/target/*.jar app.jar
RUN groupadd -r spring && useradd -r -g spring spring
USER spring
EXPOSE 8080
CMD ["java", "-jar", "app.jar"]
```
**YOU MUST USE THESE EXACT BASE IMAGES**: maven:3.9-eclipse-temurin-{java_version}-alpine and eclipse-temurin:{java_version}-jre-jammy
**DO NOT USE**: alpine, ubuntu, debian, or generic images for Java applications.""",

            "java": f"""EXAMPLE for Java/Maven (MUST FOLLOW THIS STRUCTURE):
```dockerfile
FROM maven:3.9-eclipse-temurin-{java_version}-alpine AS builder
WORKDIR /app
COPY pom.xml ./
COPY src ./src
RUN mvn -B -DskipTests package

FROM eclipse-temurin:{java_version}-jre-jammy
WORKDIR /app
COPY --from=builder /app/target/*.jar app.jar
RUN useradd -m appuser
USER appuser
EXPOSE 8080
CMD ["java", "-jar", "app.jar"]
```
**MANDATORY**: Use maven or gradle base image for building, eclipse-temurin for runtime.""",

            "node": f"""EXAMPLE for Node.js (MUST FOLLOW THIS STRUCTURE):
```dockerfile
FROM node:{node_version}-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:{node_version}-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
COPY package*.json ./
RUN npm ci --omit=dev
COPY --from=builder /app/dist ./dist
USER node
EXPOSE 3000
CMD ["node", "dist/main.js"]
```
**MANDATORY**: Use node:{node_version}-alpine base image, multi-stage build.""",

            "python": f"""EXAMPLE for Python (MUST FOLLOW THIS STRUCTURE):
```dockerfile
FROM python:{python_version}-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -m appuser
USER appuser
EXPOSE 8000
CMD ["python", "main.py"]
```
**MANDATORY**: Use python:{python_version}-slim base image.""",

            "go": f"""EXAMPLE for Go (MUST FOLLOW THIS STRUCTURE):
```dockerfile
FROM golang:{go_version}-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o app

FROM alpine:latest
WORKDIR /app
COPY --from=builder /app/app .
RUN adduser -D appuser
USER appuser
EXPOSE 8080
CMD ["./app"]
```
**MANDATORY**: Use golang:{go_version}-alpine for building, alpine for runtime."""
        }

        example = stack_examples.get(stack_type, "")

        version_critical = ""
        if stack_type in ["spring", "java"]:
            version_critical = f"""
🚨 ABSOLUTELY CRITICAL - READ THIS CAREFULLY 🚨
Java version {java_version} was detected in the project's pom.xml.
YOU MUST USE THESE EXACT BASE IMAGES (not alpine, not ubuntu, not debian):
- Build stage: maven:3.9-eclipse-temurin-{java_version}-alpine
- Runtime stage: eclipse-temurin:{java_version}-jre-jammy
FAILURE TO USE THESE IMAGES WILL CAUSE RUNTIME FAILURES.

DO NOT generate a generic Alpine/Ubuntu Dockerfile.
DO NOT use "FROM alpine" or "FROM ubuntu" for Java applications.
ONLY use Maven/Eclipse Temurin base images as shown in the example."""

        elif stack_type == "node":
            version_critical = f"""
🚨 CRITICAL 🚨
Node.js version {node_version} detected in package.json.
YOU MUST USE: node:{node_version}-alpine as the base image.
DO NOT use generic alpine, ubuntu, or debian images."""

        elif stack_type == "python":
            version_critical = f"""
🚨 CRITICAL 🚨
Python version {python_version} detected in project dependencies.
YOU MUST USE: python:{python_version}-slim as the base image.
DO NOT use generic alpine, ubuntu, or debian images."""

        full_prompt = f"""You are an expert Docker engineer generating production-ready Dockerfiles.

🎯 STACK TYPE: {stack_type}
{version_critical}

{example}

Project Context:
{context_str}

User Request: {prompt}

MANDATORY REQUIREMENTS:
1. You MUST follow the example structure shown above for {stack_type} applications
2. You MUST use the exact base images specified (with correct version numbers)
3. DO NOT use generic images (alpine, ubuntu, debian) when stack-specific images exist
4. Use multi-stage builds for compiled languages (Java, Go, Node.js)
5. Run as non-root user for security
6. Include EXPOSE for the appropriate port

Generate ONLY the Dockerfile content. No markdown formatting, no explanations, no comments before or after.
Start directly with "FROM" instruction."""

        return self.generate_text(full_prompt, max_tokens=2048)

    def optimize_dockerfile(self, dockerfile_content: str, suggestions: list) -> str:
        """Suggest optimizations for an existing Dockerfile."""
        prompt = f"""Review this Dockerfile and suggest improvements:

{dockerfile_content}

Known Issues:
{chr(10).join([f"- {s}" for s in suggestions]) if suggestions else "None identified"}

Provide an optimized version that:
1. Reduces image size
2. Improves security
3. Optimizes build time and layer caching
4. Follows Docker best practices

Generate ONLY the improved Dockerfile content."""

        return self.generate_text(prompt, max_tokens=2048)

    def explain_dockerfile(self, dockerfile_content: str) -> str:
        """Explain what a Dockerfile does."""
        prompt = f"""Explain this Dockerfile in simple terms:

{dockerfile_content}

Provide a clear explanation of:
1. What base images are used
2. What the build process does
3. What the final image contains
4. Any security or optimization features"""

        return self.generate_text(prompt, max_tokens=1024)


# Backward compatibility
DockerLLMClient = LLMClient