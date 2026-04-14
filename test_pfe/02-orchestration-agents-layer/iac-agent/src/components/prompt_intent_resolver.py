"""Prompt intent resolver for Terraform provider/resource targeting."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List, Optional, Tuple


class PromptIntentResolver:
    """Infer cloud provider and resource intent from user prompt."""

    _PROVIDER_PROTOTYPES: Dict[str, str] = {
        "aws": "aws ec2 s3 vpc ecr ecs lambda cloudfront rds terraform",
        "azure": "azure azurerm aks appservice function storage sql terraform",
        "gcp": "gcp google cloud run gke gcs compute sql terraform",
    }

    _RESOURCE_HINTS: Dict[str, List[str]] = {
        "networking": ["vpc", "subnet", "network", "firewall", "security group"],
        "compute": ["ec2", "vm", "virtual machine", "instance", "compute engine"],
        "container": ["docker", "container", "ecs", "ecr", "cloud run", "acr", "artifact registry"],
        "database": ["database", "rds", "postgres", "mysql", "sql", "cloud sql"],
        "storage": ["storage", "bucket", "s3", "blob", "gcs"],
        "serverless": ["lambda", "function", "functions", "faas"],
        "kubernetes": ["kubernetes", "k8s", "eks", "aks", "gke"],
        "static-site": ["static site", "website", "cdn", "cloudfront"],
    }

    def resolve(
        self,
        prompt: str,
        min_confidence: float = 0.08,
    ) -> Tuple[Optional[str], float, Dict[str, float], List[str]]:
        """Return best provider, confidence, full score map, and resource hints."""
        prompt_vec = self._vectorize(prompt)
        if not prompt_vec:
            return None, 0.0, {}, []

        scores: Dict[str, float] = {}
        for provider, prototype in self._PROVIDER_PROTOTYPES.items():
            proto_vec = self._vectorize(prototype)
            scores[provider] = self._cosine_similarity(prompt_vec, proto_vec)

        best_provider, best_score = max(scores.items(), key=lambda item: item[1])
        selected_provider = best_provider if best_score >= min_confidence else None

        resource_hints = self._extract_resource_hints(prompt.lower())
        return selected_provider, best_score, scores, resource_hints

    def _extract_resource_hints(self, prompt_lower: str) -> List[str]:
        hints: List[str] = []
        for hint, keywords in self._RESOURCE_HINTS.items():
            if any(keyword in prompt_lower for keyword in keywords):
                hints.append(hint)
        return hints

    def _vectorize(self, text: str) -> Counter[str]:
        tokens = re.findall(r"[a-zA-Z0-9_+.-]+", text.lower())
        return Counter(tokens)

    def _cosine_similarity(self, left: Counter[str], right: Counter[str]) -> float:
        if not left or not right:
            return 0.0

        dot = 0.0
        for token, value in left.items():
            dot += value * right.get(token, 0)

        left_norm = math.sqrt(sum(v * v for v in left.values()))
        right_norm = math.sqrt(sum(v * v for v in right.values()))
        if left_norm == 0.0 or right_norm == 0.0:
            return 0.0

        return dot / (left_norm * right_norm)
