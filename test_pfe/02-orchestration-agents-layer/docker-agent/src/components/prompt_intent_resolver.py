"""NLP-style prompt intent resolver for stack selection."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, Optional, Tuple


class PromptIntentResolver:
    """Infer target stack from user order using lightweight text similarity."""

    # Prototype corpora encode semantic intent per stack.
    _STACK_PROTOTYPES: Dict[str, str] = {
        "spring": "java spring maven gradle jar jdk",
        "python": "python fastapi flask django pip poetry",
        "node": "node nodejs javascript typescript npm yarn",
    }

    def resolve_stack(self, prompt: str, min_confidence: float = 0.10) -> Tuple[Optional[str], float, Dict[str, float]]:
        prompt_vec = self._vectorize(prompt)
        if not prompt_vec:
            return None, 0.0, {}

        scores: Dict[str, float] = {}
        for stack, prototype in self._STACK_PROTOTYPES.items():
            proto_vec = self._vectorize(prototype)
            scores[stack] = self._cosine_similarity(prompt_vec, proto_vec)

        best_stack, best_score = max(scores.items(), key=lambda item: item[1])
        if best_score < min_confidence:
            return None, best_score, scores
        return best_stack, best_score, scores

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
