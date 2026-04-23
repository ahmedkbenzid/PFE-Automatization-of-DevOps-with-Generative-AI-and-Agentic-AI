"""Extract Kubernetes generation hints from user prompt."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional

from ..config import K8S_CONFIG

SENSITIVE_KEYWORDS = (
    "secret",
    "token",
    "password",
    "passwd",
    "key",
    "credential",
)


class PromptIntentResolver:
    def __init__(self) -> None:
        self._llm = self._build_llm()

    def resolve(self, prompt: str) -> dict:
        prompt = prompt or ""
        rule_based = self._resolve_with_rules(prompt)
        rule_based["_intent_source"] = "rules"
        rule_based["_llm_enabled"] = bool(self._llm)

        llm_based = self._resolve_with_llm(prompt)
        if not llm_based:
            return rule_based

        merged = dict(rule_based)
        for key in ["app_name", "namespace", "image", "replicas", "host", "service_type"]:
            value = llm_based.get(key)
            if value not in (None, ""):
                merged[key] = value

        llm_config_env = llm_based.get("config_env") if isinstance(llm_based.get("config_env"), dict) else {}
        llm_secret_env = llm_based.get("secret_env") if isinstance(llm_based.get("secret_env"), dict) else {}

        merged["config_env"] = llm_config_env or rule_based.get("config_env", {})
        merged["secret_env"] = llm_secret_env or rule_based.get("secret_env", {})
        # Current generator always emits ingress and HPA manifests.
        merged["needs_ingress"] = True
        merged["needs_hpa"] = True
        merged["_intent_source"] = "llm+rules"
        merged["_llm_enabled"] = bool(self._llm)
        return merged

    def _resolve_with_rules(self, prompt: str) -> Dict[str, Any]:
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

    def _build_llm(self):
        api_key_env = str(K8S_CONFIG.get("llm_api_key_env") or "GROQ_API_KEY")
        api_key = os.getenv(api_key_env, "").strip()
        if not api_key:
            return None

        model_name = str(K8S_CONFIG.get("llm_model_name") or "llama-3.1-8b-instant")
        temperature = float(K8S_CONFIG.get("llm_temperature", 0))

        try:
            from langchain_groq import ChatGroq

            return ChatGroq(api_key=api_key, model=model_name, temperature=temperature)
        except Exception:
            return None

    def _resolve_with_llm(self, prompt: str) -> Optional[Dict[str, Any]]:
        if not self._llm or not prompt.strip():
            return None

        llm_prompt = (
            "You are extracting Kubernetes deployment intent from a user request. "
            "Return ONLY valid JSON with these keys: "
            "app_name (string|null), namespace (string|null), image (string|null), replicas (int|null), "
            "host (string|null), service_type (ClusterIP|NodePort|LoadBalancer|null), "
            "config_env (object), secret_env (object), needs_ingress (boolean), needs_hpa (boolean).\n"
            "Rules:\n"
            "- If unknown, use null for scalar fields and {} for env objects.\n"
            "- Put sensitive env vars in secret_env and non-sensitive in config_env.\n"
            "- Keep keys uppercase snake_case for env vars.\n\n"
            f"User request: {prompt}"
        )

        try:
            response = self._llm.invoke(llm_prompt)
            content = getattr(response, "content", "")
            if isinstance(content, list):
                content = "".join(
                    chunk if isinstance(chunk, str) else str(getattr(chunk, "text", ""))
                    for chunk in content
                )
            content = str(content).strip()
            parsed = self._parse_json(content)
            if not isinstance(parsed, dict):
                return None
            return self._normalize_llm_intent(parsed)
        except Exception:
            return None

    def _parse_json(self, content: str) -> Optional[Dict[str, Any]]:
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text).strip()
            text = re.sub(r"```$", "", text).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    return None
        return None

    def _normalize_llm_intent(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        replicas = intent.get("replicas")
        try:
            replicas = int(replicas) if replicas is not None else None
            if replicas is not None and replicas < 1:
                replicas = 1
        except (TypeError, ValueError):
            replicas = None

        service_type = intent.get("service_type")
        if isinstance(service_type, str):
            normalized = service_type.strip().lower()
            mapping = {
                "clusterip": "ClusterIP",
                "nodeport": "NodePort",
                "loadbalancer": "LoadBalancer",
            }
            service_type = mapping.get(normalized)
        else:
            service_type = None

        config_env = intent.get("config_env") if isinstance(intent.get("config_env"), dict) else {}
        secret_env = intent.get("secret_env") if isinstance(intent.get("secret_env"), dict) else {}

        sanitized_config = {str(k): str(v) for k, v in config_env.items() if str(k).strip()}
        sanitized_secret = {str(k): str(v) for k, v in secret_env.items() if str(k).strip()}

        return {
            "app_name": self._safe_string(intent.get("app_name")),
            "namespace": self._safe_string(intent.get("namespace")),
            "image": self._safe_string(intent.get("image")),
            "replicas": replicas,
            "host": self._safe_string(intent.get("host")),
            "service_type": service_type,
            "config_env": sanitized_config,
            "secret_env": sanitized_secret,
            "needs_ingress": bool(intent.get("needs_ingress", True)),
            "needs_hpa": bool(intent.get("needs_hpa", True)),
        }

    def _safe_string(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text if text else None

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
