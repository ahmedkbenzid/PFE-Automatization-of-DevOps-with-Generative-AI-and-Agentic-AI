"""Lightweight page-index knowledge base for dataset scraping output."""
import json
import os
import re
from dataclasses import dataclass, asdict
from typing import Dict, Any, List


@dataclass
class KnowledgePage:
    """A single indexed page in the knowledge base."""
    page_id: str
    page_type: str
    title: str
    source: str
    tags: List[str]
    content: str
    metadata: Dict[str, Any]


class PageIndexKnowledgeBase:
    """Stores scraped dataset pages and enables simple relevance retrieval."""

    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self.pages_dir = os.path.join(base_dir, "pages")
        self.index_path = os.path.join(base_dir, "page_index.json")
        self.catalog_path = os.path.join(base_dir, "page_catalog.json")
        os.makedirs(self.pages_dir, exist_ok=True)

    def save_pages(self, pages: List[KnowledgePage]) -> None:
        """Persist pages and both official and compatibility indexes."""
        index_items: List[Dict[str, Any]] = []

        for page in pages:
            page_path = os.path.join(self.pages_dir, f"{page.page_id}.json")
            with open(page_path, "w", encoding="utf-8") as file:
                json.dump(asdict(page), file, indent=2, ensure_ascii=False)

            index_items.append(
                {
                    "page_id": page.page_id,
                    "title": page.title,
                    "source": page.source,
                    "tags": page.tags,
                    "page_type": page.page_type,
                    "path": page_path,
                }
            )

        # Keep a flat compatibility catalog for older tooling.
        with open(self.catalog_path, "w", encoding="utf-8") as file:
            json.dump(index_items, file, indent=2, ensure_ascii=False)

        # Save official PageIndex tree format.
        children = []
        for idx, item in enumerate(index_items, start=1):
            children.append(
                {
                    "title": item["title"],
                    "node_id": str(idx).zfill(4),
                    "start_index": idx,
                    "end_index": idx,
                    "summary": f"Knowledge page from {item['source']}",
                    "source": item["source"],
                    "page_ref": os.path.join("pages", os.path.basename(item["path"])).replace("\\", "/"),
                }
            )

        index_doc = {
            "doc_name": "cicd-agent-knowledge-base",
            "doc_description": "PageIndex tree for CI/CD workflow datasets and examples.",
            "structure": [
                {
                    "title": "CI/CD Knowledge Base",
                    "node_id": "0000",
                    "start_index": 1,
                    "end_index": max(len(children), 1),
                    "summary": "Root node for CI/CD datasets and workflow examples.",
                    "nodes": children,
                }
            ],
        }

        with open(self.index_path, "w", encoding="utf-8") as file:
            json.dump(index_doc, file, indent=2, ensure_ascii=False)

    def query(self, query_text: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Retrieve top-k relevant pages using token-overlap scoring."""
        pages = self._load_all_pages()
        if not pages:
            return []

        query_tokens = self._tokenize(query_text)
        scored = []
        for page in pages:
            searchable_text = " ".join(
                [
                    page.get("title", ""),
                    page.get("source", ""),
                    " ".join(page.get("tags", [])),
                    page.get("content", ""),
                ]
            )
            page_tokens = self._tokenize(searchable_text)
            overlap = len(query_tokens.intersection(page_tokens))
            if overlap > 0:
                scored.append((overlap, page))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            {
                "score": score,
                "page_id": page.get("page_id"),
                "title": page.get("title"),
                "source": page.get("source"),
                "tags": page.get("tags", []),
                "content": page.get("content", "")[:1000],
            }
            for score, page in scored[:top_k]
        ]

    def _load_all_pages(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.index_path):
            return []

        with open(self.index_path, "r", encoding="utf-8") as file:
            raw_index = json.load(file)

        index_items: List[Dict[str, Any]] = []
        if isinstance(raw_index, list):
            # Legacy flat index format.
            index_items = raw_index
        elif isinstance(raw_index, dict) and isinstance(raw_index.get("structure"), list):
            # Official PageIndex tree format.
            for node in self._flatten_structure(raw_index["structure"]):
                page_ref = node.get("page_ref")
                if page_ref:
                    index_items.append({"path": os.path.join(self.base_dir, page_ref)})

        pages = []
        for item in index_items:
            path = item.get("path")
            if path and os.path.exists(path):
                with open(path, "r", encoding="utf-8") as page_file:
                    pages.append(json.load(page_file))
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
        return set(re.findall(r"[a-zA-Z0-9_\-.]+", text.lower()))
