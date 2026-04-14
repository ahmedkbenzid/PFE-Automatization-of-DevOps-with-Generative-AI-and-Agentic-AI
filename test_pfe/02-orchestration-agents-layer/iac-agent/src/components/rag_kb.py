"""RAG knowledge base retrieval for Terraform best practices."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List


class RAGKnowledgeBase:
    """Retrieve relevant Terraform knowledge pages from local PageIndex files."""

    def __init__(self, knowledge_base_dir: str):
        self.knowledge_base_dir = Path(knowledge_base_dir)
        self.page_index_path = self.knowledge_base_dir / "page_index.json"

    def query(self, query_text: str, top_k: int = 3) -> List[Dict[str, Any]]:
        pages = self._load_pages()
        if not pages:
            return []

        query_tokens = self._tokenize(query_text)
        query_lower = query_text.lower()
        provider = self._detect_provider(query_lower)

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
            if provider and provider in " ".join(page.get("tags", [])).lower():
                score += 8.0

            score += self._resource_bonus(query_lower, page)
            score += max(0.0, 0.001 * (1000 - idx))

            if score > 0.0 or len(pages) <= 5:
                page_copy = dict(page)
                page_copy["score"] = score
                scored.append((score, page_copy))

        if not scored:
            return pages[:top_k]

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
                str(node["page_ref"])
                for node in nodes
                if isinstance(node.get("page_ref"), str)
            ]

        pages: List[Dict[str, Any]] = []
        for ref in page_refs:
            path = self.knowledge_base_dir / ref
            if not path.exists():
                continue
            try:
                pages.append(json.loads(path.read_text(encoding="utf-8-sig")))
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

    def _detect_provider(self, query_lower: str) -> str:
        if any(k in query_lower for k in ["azure", "azurerm", "aks"]):
            return "azure"
        if any(k in query_lower for k in ["gcp", "google", "gke", "cloud run"]):
            return "gcp"
        if any(k in query_lower for k in ["aws", "ec2", "s3", "vpc", "lambda", "ecs"]):
            return "aws"
        return ""

    def _resource_bonus(self, query_lower: str, page: Dict[str, Any]) -> float:
        tags = " ".join(page.get("tags", [])).lower()
        bonus = 0.0

        resource_map = {
            "container": ["container", "ecs", "ecr", "cloud run", "acr"],
            "database": ["database", "rds", "sql", "postgres"],
            "storage": ["storage", "bucket", "s3", "blob", "gcs"],
            "networking": ["network", "vpc", "subnet", "firewall"],
            "serverless": ["serverless", "lambda", "function"],
        }

        for _, keywords in resource_map.items():
            if any(keyword in query_lower for keyword in keywords):
                if any(keyword in tags for keyword in keywords):
                    bonus += 3.0

        return bonus

    def _tokenize(self, text: str) -> set[str]:
        return set(re.findall(r"[a-zA-Z0-9_+.-]+", text.lower()))
