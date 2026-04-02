"""Tools Layer: RAG knowledge base retrieval for Docker best practices."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


class RAGKnowledgeBase:
    """Retrieve relevant Docker knowledge pages from local PageIndex-backed files."""

    def __init__(self, knowledge_base_dir: str, use_enhanced_chunking: bool = True):
        self.knowledge_base_dir = Path(knowledge_base_dir)
        self.page_index_path = self.knowledge_base_dir / "page_index.json"
        self.use_enhanced_chunking = use_enhanced_chunking
        self._enhanced_retriever = None

    def query(self, query_text: str, top_k: int = 3, use_enhanced: Optional[bool] = None) -> List[Dict[str, Any]]:
        """
        Query the knowledge base for relevant Dockerfile examples.
        
        Args:
            query_text: The search query
            top_k: Number of results to return
            use_enhanced: Override to force enhanced/basic chunking (None uses self.use_enhanced_chunking)
        
        Returns:
            List of relevant results with content chunks
        """
        pages = self._load_pages()
        if not pages:
            return []
        
        # Determine which retrieval method to use
        should_use_enhanced = use_enhanced if use_enhanced is not None else self.use_enhanced_chunking
        
        if should_use_enhanced:
            return self._query_with_enhanced_chunking(query_text, pages, top_k)
        else:
            return self._query_basic(query_text, pages, top_k)
    
    def _query_basic(self, query_text: str, pages: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
        """Original basic token-overlap query method."""
        query_tokens = self._tokenize(query_text)
        scored: List[tuple[int, Dict[str, Any]]] = []
        for page in pages:
            searchable = " ".join(
                [
                    str(page.get("title", "")),
                    str(page.get("source", "")),
                    " ".join(page.get("tags", [])),
                    str(page.get("content", "")),
                ]
            )
            overlap = len(query_tokens.intersection(self._tokenize(searchable)))
            if overlap > 0:
                scored.append((overlap, page))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [page for _, page in scored[:top_k]]
    
    def _query_with_enhanced_chunking(self, query_text: str, pages: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
        """Enhanced query using semantic Docker chunking."""
        if self._enhanced_retriever is None:
            try:
                from src.datasets.docker_enhanced_chunker import EnhancedDockerRetriever
                self._enhanced_retriever = EnhancedDockerRetriever()
            except ImportError:
                # Fallback to basic if enhanced chunker not available
                print("[Docker RAG] Warning: Enhanced chunker not available, falling back to basic retrieval")
                return self._query_basic(query_text, pages, top_k)
        
        return self._enhanced_retriever.query_with_chunks(query_text, pages, top_k)

    def _load_pages(self) -> List[Dict[str, Any]]:
        if not self.page_index_path.exists():
            return []

        raw = json.loads(self.page_index_path.read_text(encoding="utf-8"))
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
            if path.exists():
                pages.append(json.loads(path.read_text(encoding="utf-8")))
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
