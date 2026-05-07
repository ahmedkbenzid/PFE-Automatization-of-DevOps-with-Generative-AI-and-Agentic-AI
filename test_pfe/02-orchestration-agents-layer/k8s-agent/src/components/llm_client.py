"""LLM integration for K8s agent with retry, circuit breaker, and timeout."""

import os
import time
import logging
from typing import Optional, Any, Callable, List, cast
from threading import Lock
from src.config import LLM_CONFIG

try:
    from ollama import chat
except ModuleNotFoundError:
    chat = None

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


class LLMClient:
    """Unified LLM client with retry, circuit breaker, and timeout."""

    def __init__(self, provider: Optional[str] = None):
        self.provider = (provider or LLM_CONFIG.get("provider", "ollama")).lower()
        self.max_tokens = LLM_CONFIG.get("max_tokens", 2048)
        self.temperature = LLM_CONFIG.get("temperature", 0.2)
        self.client: Optional[Groq] = None
        self.model: str = ""
        self.fallback_model = "llama-3.3-70b-versatile"

        self.ollama_circuit = CircuitBreaker(3, 60)
        self.groq_circuit = CircuitBreaker(3, 60)

        self._initialize_providers()

    def _initialize_providers(self) -> None:
        providers = [self.provider, "groq" if self.provider == "ollama" else "ollama"]
        errors = []
        for p in providers:
            try:
                if p == "ollama":
                    self._init_ollama()
                else:
                    self._init_groq()
                self.provider = p
                logger.info(f"LLM client initialized: {p}")
                return
            except Exception as e:
                errors.append(f"{p}: {e}")
                logger.error(f"Failed to init {p}: {e}")
        raise RuntimeError(f"Failed to init LLM: {'; '.join(errors)}")

    def _init_ollama(self) -> None:
        if chat is None:
            raise RuntimeError("ollama not installed")
        self.model = LLM_CONFIG.get("model", "gpt-oss:20b:cloud")
        self.provider = "ollama"
        logger.info(f"Using Ollama: {self.model}")

    def _init_groq(self) -> None:
        if Groq is None:
            raise RuntimeError("groq not installed")
        api_key = os.getenv("GROQ_API_KEY", "")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY not set")
        self.client = Groq(api_key=api_key)
        self.model = LLM_CONFIG.get("groq_model", "llama-3.3-70b-versatile")
        self.provider = "groq"
        logger.info(f"Using Groq: {self.model}")

    def _ollama_completion(self, prompt: str) -> str:
        if not self.ollama_circuit.can_execute():
            raise RuntimeError("Ollama circuit open")

        timeout = LLM_CONFIG.get("timeout", 120)
        try:
            response = cast(Any, chat)(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": self.temperature, "num_predict": self.max_tokens, "timeout": timeout}
            )
            self.ollama_circuit.record_success()
            return response.message.content or ""
        except Exception as e:
            self.ollama_circuit.record_failure()
            logger.error(f"Ollama error: {e}")
            raise

    def _groq_completion(self, prompt: str, max_tokens: Optional[int] = None) -> str:
        if not self.groq_circuit.can_execute():
            raise RuntimeError("Groq circuit open")

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens or self.max_tokens,
                temperature=self.temperature,
                top_p=0.95,
                stream=False,
            )
            self.groq_circuit.record_success()
            return response.choices[0].message.content or ""
        except Exception as e:
            self.groq_circuit.record_failure()
            logger.error(f"Groq error: {e}")
            raise

    def _generate_text_no_retry(self, prompt: str, max_tokens: Optional[int] = None) -> str:
        logger.info(f"Generating with {self.provider}")

        if self.provider == "ollama":
            try:
                result = self._ollama_completion(prompt)
                if result.strip():
                    return result
            except Exception as ollama_error:
                logger.warning(f"Ollama failed: {ollama_error}, trying Groq")
                try:
                    self._init_groq()
                    result = self._groq_completion(prompt, max_tokens)
                    if result.strip():
                        return result
                except Exception:
                    pass
                raise RuntimeError(f"Both failed: {ollama_error}")

        result = self._groq_completion(prompt, max_tokens)
        if result.strip():
            return result
        raise RuntimeError("Empty response")

    def generate_text(self, prompt: str, max_tokens: Optional[int] = None) -> str:
        if retry is not None:
            @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10), reraise=True)
            def _retry_wrapper():
                return self._generate_text_no_retry(prompt, max_tokens)
            return _retry_wrapper()
        return self._generate_text_no_retry(prompt, max_tokens)

    def generate_manifests(self, request: str, context: dict, rag_hints: dict = None) -> dict:
        """Generate Kubernetes manifests using LLM."""
        app_name = context.get("app_name", "app")
        namespace = context.get("namespace", app_name)
        image = context.get("image", f"{app_name}:latest")
        replicas = context.get("replicas", 1)
        service_type = rag_hints.get("service_type", "ClusterIP") if rag_hints else "ClusterIP"
        host = context.get("host", f"{app_name}.local")

        rag_examples = ""
        if rag_hints and rag_hints.get("source_pages"):
            rag_examples = "\n\nUse best practices from the knowledge base."

        prompt = f"""Generate Kubernetes manifests for:
- App: {app_name}
- Namespace: {namespace}
- Image: {image}
- Replicas: {replicas}
- Service Type: {service_type}
- Host: {host}
{rag_examples}

Generate YAML for these manifests (each as separate YAML document):
1. Namespace
2. ConfigMap (with APP_ENV=production)
3. Secret (with APP_SECRET=replace-me)
4. Deployment (with env from ConfigMap and Secret)
5. Service (type: {service_type})
6. Ingress (with host: {host})
7. HorizontalPodAutoscaler

Output as YAML with `---` separators. No explanations."""

        result = self.generate_text(prompt, max_tokens=3000)
        return {"raw_yaml": result}

    def generate_with_fallback(self, request: str, context: dict, rag_hints: dict = None, template_manifests: dict = None) -> dict:
        """Try LLM, fall back to template if fails."""
        try:
            return self.generate_manifests(request, context, rag_hints)
        except Exception as e:
            logger.warning(f"LLM generation failed: {e}, using template")
            return template_manifests or {}