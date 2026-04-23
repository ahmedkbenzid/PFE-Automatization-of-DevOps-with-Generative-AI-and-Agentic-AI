"""PageIndex-backed local knowledge base for Kubernetes retrieval."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List


class PageIndexKnowledgeBase:
    """Load PageIndex trees and retrieve relevant Kubernetes pages."""

    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.page_index_path = self.base_dir / "page_index.json"

    def query(self, query_text: str, top_k: int = 3) -> List[Dict[str, Any]]:
        pages = self._load_pages()
        if not pages:
            return []

        query_tokens = self._tokenize(query_text)
        query_lower = query_text.lower()

        scored: List[tuple[float, Dict[str, Any]]] = []
        for idx, page in enumerate(pages):
            searchable = " ".join(
                [
                    str(page.get("title", "")),
                    str(page.get("source", "")),
                    " ".join(page.get("tags", [])),
                    str(page.get("content", "")),
                ]
            )

            overlap = len(query_tokens.intersection(self._tokenize(searchable)))
            score = float(overlap)
            score += self._k8s_semantic_bonus(query_lower, page)
            score += max(0.0, 0.001 * (1000 - idx))

            page_copy = dict(page)
            page_copy["score"] = score
            scored.append((score, page_copy))

        scored.sort(key=lambda item: item[0], reverse=True)

        deduped: List[Dict[str, Any]] = []
        seen = set()
        for _, page in scored:
            page_key = page.get("page_id") or page.get("title") or page.get("source")
            if page_key in seen:
                continue
            seen.add(page_key)
            deduped.append(page)
            if len(deduped) >= top_k:
                break

        return deduped

    def _load_pages(self) -> List[Dict[str, Any]]:
        if not self.page_index_path.exists():
            return []

        try:
            raw = json.loads(self.page_index_path.read_text(encoding="utf-8-sig"))
        except Exception:
            return []

        page_refs: List[str] = []
        if isinstance(raw, dict) and isinstance(raw.get("structure"), list):
            nodes = self._flatten_structure(raw["structure"])
            page_refs = [
                str(node["page_ref"]) for node in nodes if isinstance(node.get("page_ref"), str)
            ]

        pages: List[Dict[str, Any]] = []
        for ref in page_refs:
            page_path = self.base_dir / ref
            if not page_path.exists():
                continue
            try:
                pages.append(json.loads(page_path.read_text(encoding="utf-8-sig")))
            except Exception:
                continue

        return pages

    def _flatten_structure(self, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        flat: List[Dict[str, Any]] = []
        for node in nodes:
            flat.append(node)
            children = node.get("nodes", [])
            if isinstance(children, list) and children:
                flat.extend(self._flatten_structure(children))
        return flat

    def _tokenize(self, text: str) -> set[str]:
        return set(re.findall(r"[a-zA-Z0-9_+.-]+", text.lower()))

    def _k8s_semantic_bonus(self, query_lower: str, page: Dict[str, Any]) -> float:
        tags = " ".join(page.get("tags", [])).lower()
        bonus = 0.0

        if any(k in query_lower for k in ["ingress", "route", "host"]):
            if any(k in tags for k in ["ingress", "traefik", "routing"]):
                bonus += 3.0

        if any(k in query_lower for k in ["configmap", "env", "configuration"]):
            if any(k in tags for k in ["configmap", "configuration"]):
                bonus += 3.0

        if any(k in query_lower for k in ["secret", "token", "password", "credential"]):
            if any(k in tags for k in ["secret", "security"]):
                bonus += 3.0

        if any(k in query_lower for k in ["rbac", "serviceaccount", "role", "rolebinding"]):
            if any(k in tags for k in ["rbac", "security", "authorization"]):
                bonus += 3.0

        if any(k in query_lower for k in ["networkpolicy", "egress", "ingress policy"]):
            if any(k in tags for k in ["networkpolicy", "network", "security"]):
                bonus += 3.0

        if any(k in query_lower for k in ["service", "clusterip", "nodeport", "loadbalancer"]):
            if any(k in tags for k in ["service", "clusterip", "nodeport", "loadbalancer"]):
                bonus += 3.0

        if any(k in query_lower for k in ["kubeflow", "ml", "pipeline", "notebook"]):
            if any(k in tags for k in ["kubeflow", "ml", "pipelines"]):
                bonus += 3.0

        return bonus
