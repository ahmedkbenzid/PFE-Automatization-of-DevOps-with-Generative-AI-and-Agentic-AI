"""NLP-style prompt intent resolver for CI/CD stack preference."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List


class PromptIntentResolver:
    """Infer preferred languages from user prompt using vector similarity."""

    _LANGUAGE_PROTOTYPES: Dict[str, str] = {
        "Java": "java spring springboot maven gradle sonarqube sonar jar",
        "Python": "python pytest pip poetry tox django flask fastapi",
        "JavaScript": "javascript node nodejs npm yarn react vue express",
        "TypeScript": "typescript ts-node pnpm nx angular nest",
        "Go": "go golang go.mod go test",
        "Ruby": "ruby bundler rspec rails",
        "Rust": "rust cargo clippy",
    }

    def infer_preferred_languages(
        self,
        request_text: str,
        intent_keywords: List[str],
        repo_languages: List[str],
        min_confidence: float = 0.08,
    ) -> List[str]:
        prompt = f"{request_text} {' '.join(intent_keywords)}"
        prompt_vec = self._vectorize(prompt)
        scores: Dict[str, float] = {}

        for language, prototype in self._LANGUAGE_PROTOTYPES.items():
            proto_vec = self._vectorize(prototype)
            scores[language] = self._cosine_similarity(prompt_vec, proto_vec)

        ranked_by_prompt = [
            language
            for language, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)
            if score >= min_confidence
        ]

        ordered: List[str] = []
        for language in ranked_by_prompt + repo_languages:
            if language not in ordered:
                ordered.append(language)

        return ordered

    def _vectorize(self, text: str) -> Counter[str]:
        tokens = re.findall(r"[a-zA-Z0-9_+.\-]+", text.lower())
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
