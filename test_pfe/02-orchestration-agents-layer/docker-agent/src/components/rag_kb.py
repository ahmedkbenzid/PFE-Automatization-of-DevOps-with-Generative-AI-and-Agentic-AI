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
        print(f"[Docker RAG] Loaded {len(pages)} pages from knowledge base")
        if not pages:
            print("[Docker RAG] ERROR: No pages found in knowledge base!")
            return []
        
        # Force basic query for reliability - enhanced chunker has issues
        results = self._query_basic(query_text, pages, top_k * 3)
        print(f"[Docker RAG] Query returned {len(results)} raw results before post-processing")
        
        # Ensure we have results
        if not results:
            print("[Docker RAG] WARNING: No results from query, using all pages as fallback")
            results = [
                {**page, "score": float(idx)} 
                for idx, page in enumerate(pages[:top_k])
            ]

        # Normalize, stack-bias, de-duplicate and trim.
        return self._post_process_results(query_text, results, top_k)
    
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
            # Always include page even if no overlap, but with score 0
            if overlap > 0 or len(pages) <= 5:  # Include all pages if KB is small, otherwise filter
                scored.append((overlap, page))

        scored.sort(key=lambda item: item[0], reverse=True)
        # Add score field to results
        results = []
        for score, page in scored[:top_k]:
            page_with_score = dict(page)
            page_with_score["score"] = float(score)
            results.append(page_with_score)
        return results
    
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
        print(f"[Docker RAG] _load_pages: knowledge_base_dir = {self.knowledge_base_dir}")
        print(f"[Docker RAG] _load_pages: page_index_path = {self.page_index_path}")
        print(f"[Docker RAG] _load_pages: page_index exists? {self.page_index_path.exists()}")
        
        if not self.page_index_path.exists():
            print("[Docker RAG] ERROR: page_index.json not found")
            return []

        raw = json.loads(self.page_index_path.read_text(encoding="utf-8-sig"))
        page_refs: List[str] = []

        if isinstance(raw, dict) and isinstance(raw.get("structure"), list):
            nodes = self._flatten_structure(raw["structure"])
            print(f"[Docker RAG] Found {len(nodes)} nodes in page_index")
            page_refs = [
                str(node["page_ref"])
                for node in nodes
                if isinstance(node.get("page_ref"), str)
            ]
            print(f"[Docker RAG] Extracted {len(page_refs)} page_refs from nodes")

        pages: List[Dict[str, Any]] = []
        for ref in page_refs:
            path = self.knowledge_base_dir / ref
            print(f"[Docker RAG] Loading page: {ref} from {path} (exists={path.exists()})")
            if path.exists():
                try:
                    page_data = json.loads(path.read_text(encoding="utf-8-sig"))
                    pages.append(page_data)
                    print(f"[Docker RAG]   ✓ Loaded page_id={page_data.get('page_id')}")
                except Exception as e:
                    print(f"[Docker RAG]   ✗ Error loading: {e}")
        
        print(f"[Docker RAG] Successfully loaded {len(pages)} pages")
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

    def _post_process_results(self, query_text: str, results: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
        expected_stack = self._detect_stack(query_text)
        print(f"[Docker RAG] Post-processing {len(results)} results for stack: {expected_stack}")
        
        if not results:
            print("[Docker RAG] No results to post-process, returning empty list")
            return []
        
        scored: List[tuple[float, Dict[str, Any]]] = []

        for idx, page in enumerate(results):
            searchable = " ".join(
                [
                    str(page.get("title", "")),
                    str(page.get("source", "")),
                    " ".join(page.get("tags", [])),
                    str(page.get("content", "")),
                ]
            ).lower()
            score = float(page.get("score", 0.0))
            page_id = page.get("page_id", "unknown")
            
            # Stack matching: subtle boost for matching stacks
            if expected_stack:
                if self._is_stack_match(searchable, expected_stack):
                    score += 10.0  # Moderate boost for matching stack
                    print(f"[Docker RAG] MATCH: {page_id} matches {expected_stack} (+10.0)")
                else:
                    # Very subtle penalty for wrong stack - don't eliminate results
                    for other_stack in ["node", "python", "go", "rust", "java"]:
                        if other_stack != expected_stack and self._is_stack_match(searchable, other_stack):
                            score -= 5.0  # Soft penalty for wrong stack
                            print(f"[Docker RAG] MISMATCH: {page_id} is {other_stack}, not {expected_stack} (-5.0)")
                            break
            
            # Stable tie-breaker by original order
            score += max(0.0, 0.001 * (1000 - idx))
            scored.append((score, page))

        scored.sort(key=lambda item: item[0], reverse=True)
        
        print(f"[Docker RAG] After scoring and sorting:")
        for i, (s, page) in enumerate(scored[:top_k]):
            print(f"  - {page.get('page_id', 'unknown')}: {s:.2f}")

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

        print(f"[Docker RAG] Final results: {[p.get('page_id') for p in deduped]}")
        return deduped

    def _detect_stack(self, query_text: str) -> Optional[str]:
        query = query_text.lower()
        if any(k in query for k in ["java", "maven", "gradle", "spring"]):
            return "java"
        if any(k in query for k in ["node", "npm", "yarn", "javascript", "typescript"]):
            return "node"
        if any(k in query for k in ["python", "pip", "django", "flask", "fastapi"]):
            return "python"
        if any(k in query for k in ["go", "golang"]):
            return "go"
        if any(k in query for k in ["rust", "cargo"]):
            return "rust"
        return None

    def _is_stack_match(self, searchable_text: str, stack: str) -> bool:
        stack_keywords = {
            "java": ["java", "maven", "gradle", "spring", "temurin", "openjdk"],
            "node": ["node", "npm", "yarn", "javascript", "typescript"],
            "python": ["python", "pip", "django", "flask", "fastapi"],
            "go": ["go", "golang"],
            "rust": ["rust", "cargo"],
        }
        return any(keyword in searchable_text for keyword in stack_keywords.get(stack, []))
