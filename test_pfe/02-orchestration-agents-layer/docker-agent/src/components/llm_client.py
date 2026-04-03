"""LLM integration with Ollama and Groq for Docker Agent."""
import os
from typing import Optional, Any, Callable
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


class LLMClient:
    """Unified LLM client supporting Ollama and Groq with provider fallback."""

    def __init__(self, provider: Optional[str] = None):
        configured_provider = (provider or LLM_CONFIG.get("provider", "ollama")).lower()
        if configured_provider not in {"ollama", "groq"}:
            configured_provider = "ollama"

        self.provider = configured_provider
        self.max_tokens = LLM_CONFIG.get("max_tokens", 4096)
        self.temperature = LLM_CONFIG.get("temperature", 0.2)
        self.client = None
        self.fallback_model = LLM_CONFIG.get("fallback_model", "mixtral-8x7b-32768")

        # Try configured provider first, then automatically fail over.
        providers_to_try = [self.provider, "groq" if self.provider == "ollama" else "ollama"]
        init_errors = []
        for candidate in providers_to_try:
            try:
                if candidate == "ollama":
                    self._init_ollama()
                else:
                    self._init_groq()
                self.provider = candidate
                return
            except Exception as exc:
                init_errors.append(f"{candidate}: {exc}")

        raise RuntimeError(f"Failed to initialize any LLM provider ({'; '.join(init_errors)})")

    def _init_ollama(self):
        """Initialize Ollama client"""
        if chat is None:
            raise RuntimeError("ollama package is not installed. Run: pip install ollama")
        self.model = LLM_CONFIG.get("model", "glm-5:cloud")
        print(f"[Docker Agent] Using Ollama with model: {self.model}")

    def _init_groq(self):
        """Initialize Groq client"""
        if Groq is None:
            raise RuntimeError("groq package is not installed. Run: pip install groq")

        api_key = os.getenv("GROQ_API_KEY", "")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY environment variable is required for Groq provider")

        self.client = Groq(api_key=api_key)
        self.model = LLM_CONFIG.get("groq_model", "llama3-70b-8192")
        print(f"[Docker Agent] Using Groq with model: {self.model}")

    def _ollama_completion(self, prompt: str) -> str:
        """Generate completion using Ollama"""
        if chat is None:
            raise RuntimeError("Ollama chat function is not available")
        
        response = chat(  # type: ignore
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            options={
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            }
        )
        return response.message.content  # type: ignore

    def _groq_completion(self, model: str, prompt: str, max_tokens: Optional[int] = None) -> str:
        """Generate completion using Groq"""
        response = self.client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens or self.max_tokens,
            temperature=self.temperature,
            top_p=0.95,
            stream=False,
        )
        return response.choices[0].message.content

    def generate_text(self, prompt: str, max_tokens: Optional[int] = None) -> str:
        """Generate text using the configured LLM provider"""
        if self.provider == "ollama":
            try:
                return self._ollama_completion(prompt)
            except Exception as ollama_error:
                if Groq is None:
                    raise
                # Runtime failover to Groq if Ollama is unavailable in this environment.
                try:
                    self._init_groq()
                    self.provider = "groq"
                    return self._groq_completion(self.model, prompt, max_tokens)
                except Exception:
                    raise Exception(f"Error generating text with ollama: {str(ollama_error)}")

        # Groq with fallback support
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
                    return result
                except Exception:
                    pass

            raise Exception(f"Error generating text: {str(e)}")

    def generate_dockerfile(self, prompt: str, context: dict) -> str:
        """Generate Dockerfile content based on prompt and project context"""
        stack_type = context.get("stack_type", "generic")
        
        # Build context string
        context_items = []
        for k, v in context.items():
            if v and k != "stack_type":
                context_items.append(f"{k}: {v}")
        context_str = "\n".join(context_items) if context_items else "No additional context"
        
        # Map stack type to explicit language instructions
        stack_instructions = {
            "spring": "This is a Java/Spring Boot application using Maven. Use maven:3.9-eclipse-temurin base image for building and eclipse-temurin:17-jre for runtime.",
            "java": "This is a Java application. Use maven or gradle for building and a JRE base image for runtime.",
            "node": "This is a Node.js/JavaScript application. Use node:20-alpine base image with multi-stage build.",
            "python": "This is a Python application. Use python:3.11-slim base image.",
            "go": "This is a Go application. Use golang:1.21-alpine for building and alpine:latest for runtime.",
            "rust": "This is a Rust application. Use rust:1.75-alpine for building and alpine:latest for runtime.",
            "ruby": "This is a Ruby application. Use ruby:3.2-alpine base image.",
        }
        
        stack_instruction = stack_instructions.get(stack_type, f"This is a {stack_type} application.")
        
        full_prompt = f"""You are an expert Docker engineer. Generate a production-ready, secure, and optimized Dockerfile.

**CRITICAL: {stack_instruction}**

Project Context:
- Stack Type: {stack_type}
{context_str}

User Request: {prompt}

Requirements:
1. Use multi-stage builds when appropriate for the {stack_type} stack
2. Use the correct base image for {stack_type} (NOT Python unless stack is Python)
3. Minimize image size
4. Follow security best practices (non-root user, minimal packages)
5. Use specific version tags, not 'latest'
6. Optimize layer caching
7. Include health checks if applicable
8. Set appropriate environment variables for {stack_type}

Generate ONLY the Dockerfile content, no explanations or markdown formatting."""

        return self.generate_text(full_prompt, max_tokens=2048)

    def optimize_dockerfile(self, dockerfile_content: str, suggestions: list) -> str:
        """Suggest optimizations for an existing Dockerfile"""
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
        """Explain what a Dockerfile does"""
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
