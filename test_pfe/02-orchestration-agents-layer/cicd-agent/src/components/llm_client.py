"""LLM integration with Ollama Cloud (primary) and Groq (fallback) with retry, circuit breaker, and timeout."""

import os
import time
import logging
from typing import Optional, Any, Callable, List, Dict, cast
from threading import Lock
from src.config import Config
from src.models.types import IntentMetadata, RequestType

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
    """Unified LLM client supporting Ollama Cloud and Groq with retry, circuit breaker, and timeout."""

    def __init__(self, provider: Optional[str] = None):
        self.provider = provider or Config.LLM_PROVIDER
        self.max_tokens = Config.LLM_MAX_TOKENS
        self.temperature = Config.LLM_TEMPERATURE
        self.client = None
        self.model: str = "llama-3.3-70b-versatile"
        self.fallback_models: List[str] = []

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
        self.model = Config.OLLAMA_MODEL
        self.provider = "ollama"
        logger.info(f"Using Ollama with model: {self.model}")

    def _init_groq(self) -> None:
        """Initialize Groq client."""
        if Groq is None:
            raise RuntimeError("groq package is not installed. Run: pip install groq")
        if not Config.GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY not set in environment")
        self.client = Groq(api_key=Config.GROQ_API_KEY)
        self.model = Config.GROQ_MODEL
        self.fallback_models = [m for m in Config.GROQ_FALLBACK_MODELS if m != self.model]
        self.provider = "groq"
        logger.info(f"Using Groq with model: {self.model}")

    def _run_groq_fallback(self, prompt: str, max_tokens: Optional[int] = None) -> str:
        """Run one Groq fallback attempt while preserving the current provider state."""
        previous_provider = self.provider
        previous_model = self.model
        previous_fallback_models = list(self.fallback_models)
        previous_client = self.client

        try:
            self._init_groq()
            groq_result = self._groq_completion(self.model, prompt, max_tokens)
            if groq_result and groq_result.strip():
                return groq_result
            raise RuntimeError("Groq returned empty response")
        finally:
            self.provider = previous_provider
            self.model = previous_model
            self.fallback_models = previous_fallback_models
            self.client = previous_client

    def _ollama_completion(self, prompt: str) -> str:
        """Generate completion using Ollama with timeout."""
        if not self.model:
            raise RuntimeError("Ollama model is not configured")

        if not self.ollama_circuit.can_execute():
            logger.warning("Ollama circuit breaker is open, skipping")
            raise RuntimeError("Ollama circuit breaker is open")

        timeout = getattr(Config, 'LLM_TIMEOUT', 120)
        try:
            chat_fn = cast(Any, chat)
            response = chat_fn(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens,
                    "timeout": timeout,
                }
            )
            self.ollama_circuit.record_success()
            content = getattr(response.message, "content", "")
            return content or ""
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
            content = response.choices[0].message.content
            return content or ""
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
        logger.info(f"Generating text with provider: {self.provider}")

        if self.provider == "ollama":
            ollama_error: Optional[Exception] = None
            try:
                ollama_result = self._ollama_completion(prompt)
                if ollama_result and ollama_result.strip():
                    return ollama_result
            except Exception as e:
                ollama_error = e
                logger.warning(f"Ollama generation failed: {e}, trying Groq fallback")

            try:
                groq_result = self._run_groq_fallback(prompt, max_tokens)
                if groq_result and groq_result.strip():
                    return groq_result
                raise RuntimeError("Groq returned empty response")
            except Exception as e2:
                if ollama_error is not None:
                    raise RuntimeError(f"Both Ollama and Groq failed: ollama={ollama_error}; groq={e2}")
                raise RuntimeError(f"Both Ollama and Groq failed: groq={e2}")

        try:
            groq_result = self._groq_completion(self.model, prompt, max_tokens)
            if groq_result and groq_result.strip():
                return groq_result
            raise RuntimeError("Primary Groq model returned empty response")
        except Exception as e:
            error_text = str(e).lower()
            should_try_fallbacks = (
                "model_decommissioned" in error_text
                or "decommissioned" in error_text
                or "not found" in error_text
                or "empty response" in error_text
            )

            if should_try_fallbacks:
                for fallback_model in self.fallback_models:
                    try:
                        result = self._groq_completion(fallback_model, prompt, max_tokens)
                        if not result or not result.strip():
                            continue
                        self.model = fallback_model
                        logger.warning(f"Falling back to model: {fallback_model}")
                        return result
                    except Exception:
                        continue

            raise Exception(f"Error generating text: {str(e)}")

    def generate_text(self, prompt: str, max_tokens: Optional[int] = None) -> str:
        """Generate text using the configured LLM provider with retry."""
        if retry is not None:
            return self._generate_text_retry(prompt, max_tokens)
        return self._generate_text_no_retry(prompt, max_tokens)

    def extract_intent(self, user_request: str) -> IntentMetadata:
        """Extract intent from user request."""
        prompt = f"""Analyze the following user request for a CI/CD workflow and extract the intent:

User Request: "{user_request}"

Respond in the following format:
INTENT: [Main intent in 1 sentence]
KEYWORDS: [Comma-separated keywords]
REQUEST_TYPE: [CREATE_WORKFLOW|MIGRATE_WORKFLOW|OPTIMIZE_WORKFLOW|VALIDATE_WORKFLOW]
TOOLS_NEEDED: [Comma-separated tools needed]
CONFIDENCE: [0.0-1.0]
"""
        response = self.generate_text(prompt)
        return self._parse_intent_response(response, user_request)

    def _parse_intent_response(self, response: str, fallback_intent: str = "Create CI/CD workflow") -> IntentMetadata:
        """Parse LLM response into IntentMetadata."""
        lines = response.strip().split('\n')
        intent_dict = {}

        for line in lines:
            if ':' in line:
                key, value = line.split(':', 1)
                intent_dict[key.strip().lower()] = value.strip()

        request_type = RequestType.CREATE_WORKFLOW
        if 'migrate' in intent_dict.get('request_type', '').lower():
            request_type = RequestType.MIGRATE_WORKFLOW
        elif 'optimize' in intent_dict.get('request_type', '').lower():
            request_type = RequestType.OPTIMIZE_WORKFLOW
        elif 'validate' in intent_dict.get('request_type', '').lower():
            request_type = RequestType.VALIDATE_WORKFLOW

        keywords = [k.strip() for k in intent_dict.get('keywords', '').split(',') if k.strip()]
        tools = [t.strip() for t in intent_dict.get('tools_needed', '').split(',') if t.strip()]

        try:
            confidence = float(intent_dict.get('confidence', '0.5'))
        except ValueError:
            confidence = 0.5

        return IntentMetadata(
            intent=intent_dict.get('intent', fallback_intent),
            keywords=keywords,
            request_type=request_type,
            required_tools=tools,
            confidence=confidence
        )

    def generate_workflow_yaml(self, prompt: str, rag_context: Optional[List[Dict[str, Any]]] = None) -> str:
        """Generate GitHub Actions workflow YAML with optional RAG context."""
        rag_examples = ""
        if rag_context:
            rag_examples = "\n\n**Reference Workflows from Knowledge Base:**\n"
            for i, workflow in enumerate(rag_context, 1):
                title = workflow.get("title", f"Example {i}")
                content = workflow.get("content", "")[:500]
                rag_examples += f"\n{i}. {title}:\n```\n{content}\n```\n"
        
        expanded_prompt = f"""{prompt}{rag_examples}

Generate a complete GitHub Actions workflow in YAML format. The output MUST be valid YAML and include:
1. name
2. on (with appropriate triggers)
3. jobs with at least one job
4. steps in each job
5. Proper indentation

Output ONLY the YAML content, no explanations."""

        return self.generate_text(expanded_prompt, max_tokens=3000)

    def validate_workflow_logic(self, yaml_content: str, errors: list) -> str:
        """Use LLM to suggest fixes for workflow errors."""
        prompt = f"""Review this GitHub Actions workflow YAML and the validation errors.
Suggest fixes for the errors:

YAML:
{yaml_content}

Validation Errors:
{chr(10).join(errors)}

Provide fixed YAML that addresses these errors."""

        return self.generate_text(prompt, max_tokens=3000)


# Backward compatibility alias
GroqLLMClient = LLMClient