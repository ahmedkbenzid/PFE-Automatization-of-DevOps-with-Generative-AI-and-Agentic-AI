"""LLM client for IaC agent Terraform generation and repair."""

from __future__ import annotations

import os
from typing import Optional

from ..config import IAC_CONFIG


class IACLLMClient:
    """Thin LLM wrapper supporting Groq and Ollama backends."""

    def __init__(self):
        self.provider = IAC_CONFIG.get("llm_provider", "ollama")
        self.temperature = IAC_CONFIG.get("llm_temperature", 0.1)
        self.max_tokens = IAC_CONFIG.get("llm_max_tokens", 4096)
        self.groq_model = IAC_CONFIG.get("groq_model", "llama-3.1-8b-instant")
        self.ollama_model = IAC_CONFIG.get("ollama_model", "minimax-m2.7:cloud")

    def generate(self, prompt: str) -> str:
        if self.provider == "ollama":
            return self._ollama_completion(prompt)
        return self._groq_completion(prompt)

    def _groq_completion(self, prompt: str) -> str:
        try:
            from groq import Groq

            api_key = os.getenv("GROQ_API_KEY", "")
            if not api_key:
                raise RuntimeError("GROQ_API_KEY not configured")

            client = Groq(api_key=api_key)
            response = client.chat.completions.create(
                model=self.groq_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            return response.choices[0].message.content or ""
        except Exception:
            return ""

    def _ollama_completion(self, prompt: str) -> str:
        try:
            from ollama import chat

            response = chat(
                model=self.ollama_model,
                messages=[{"role": "user", "content": prompt}],
                options={
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens,
                },
            )
            return response.message.content or ""
        except Exception:
            return ""
