"""Extract Kubernetes generation hints from user prompt."""

from __future__ import annotations

import re

SENSITIVE_KEYWORDS = (
    "secret",
    "token",
    "password",
    "passwd",
    "key",
    "credential",
)


class PromptIntentResolver:
    def resolve(self, prompt: str) -> dict:
        prompt = prompt or ""

        app_name = self._extract_named_value(prompt, [r"app(?:lication)?\s+name\s*(?:is|=|:)\s*([a-zA-Z0-9_-]+)"])
        namespace = self._extract_named_value(prompt, [r"namespace\s*(?:is|=|:)\s*([a-zA-Z0-9_-]+)"])
        image = self._extract_named_value(prompt, [r"image\s*(?:is|=|:)\s*([a-zA-Z0-9._/:-]+)"])
        replicas = self._extract_int(prompt, [r"replicas\s*(?:is|=|:)\s*(\d+)"])
        host = self._extract_named_value(prompt, [r"host\s*(?:is|=|:)\s*([a-zA-Z0-9.-]+)"])
        service_type = self._extract_named_value(prompt, [r"service\s*type\s*(?:is|=|:)\s*([a-zA-Z]+)"])

        env_pairs = self._extract_env_pairs(prompt)
        non_sensitive = {}
        sensitive = {}
        for key, value in env_pairs.items():
            if self._is_sensitive_key(key):
                sensitive[key] = value
            else:
                non_sensitive[key] = value

        return {
            "app_name": app_name,
            "namespace": namespace,
            "image": image,
            "replicas": replicas,
            "host": host,
            "service_type": service_type,
            "config_env": non_sensitive,
            "secret_env": sensitive,
            "needs_ingress": True,
            "needs_hpa": True,
        }

    def _extract_named_value(self, prompt: str, patterns: list[str]) -> str | None:
        for pattern in patterns:
            match = re.search(pattern, prompt, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _extract_int(self, prompt: str, patterns: list[str]) -> int | None:
        value = self._extract_named_value(prompt, patterns)
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def _extract_env_pairs(self, prompt: str) -> dict:
        pairs = {}
        for match in re.finditer(r"\b([A-Z][A-Z0-9_]{1,63})\s*=\s*([^\s,;]+)", prompt):
            pairs[match.group(1)] = match.group(2)
        return pairs

    def _is_sensitive_key(self, key: str) -> bool:
        lowered = key.lower()
        return any(token in lowered for token in SENSITIVE_KEYWORDS)
