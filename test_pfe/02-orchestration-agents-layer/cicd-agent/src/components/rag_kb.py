"""RAG knowledge base retrieval for CI/CD best practices and workflows."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


class RAGKnowledgeBase:
    """Retrieve relevant CI/CD workflow examples from knowledge base."""

    def __init__(self, knowledge_base_dir: str):
        self.knowledge_base_dir = Path(knowledge_base_dir)
        self.page_index_path = self.knowledge_base_dir / "page_index.json"

    def query(self, query_text: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Query knowledge base for relevant CI/CD workflows.
        
        Args:
            query_text: Search query
            top_k: Number of results to return
        
        Returns:
            List of relevant workflow examples
        """
        pages = self._load_pages()
        print(f"[CI/CD RAG] Loaded {len(pages)} pages from knowledge base")
        if not pages:
            print("[CI/CD RAG] Warning: No pages loaded from knowledge base")
            return []
        
        # Basic token overlap scoring
        query_tokens = self._tokenize(query_text)
        scored: List[tuple[float, Dict[str, Any]]] = []
        
        for idx, page in enumerate(pages):
            searchable = " ".join([
                str(page.get("title", "")),
                str(page.get("source", "")),
                " ".join(page.get("tags", [])),
                str(page.get("content", ""))[:500],  # Limit content to avoid huge text blocks
            ])
            
            overlap = len(query_tokens.intersection(self._tokenize(searchable)))
            # Include all pages if KB is small, otherwise filter by overlap
            if overlap > 0 or len(pages) <= 5:
                score = float(overlap) if overlap > 0 else 0.0
                
                # Boost for platform/provider matching
                platform_bonus = self._calculate_platform_bonus(query_text, searchable)
                score += platform_bonus
                
                scored.append((score, page))
        
        # If no results found, use all pages as fallback
        if not scored:
            print("[CI/CD RAG] No scoring results, using all pages as fallback")
            scored = [(float(idx), page) for idx, page in enumerate(pages)]
        
        scored.sort(key=lambda item: item[0], reverse=True)
        
        # De-duplicate by page_id and trim
        results: List[Dict[str, Any]] = []
        seen = set()
        for score, page in scored:
            page_id = page.get("page_id") or page.get("title")
            if page_id not in seen:
                results.append({
                    "page_id": page_id,
                    "title": page.get("title"),
                    "content": page.get("content", "")[:1000],
                    "score": score
                })
                seen.add(page_id)
                if len(results) >= top_k:
                    break
        
        print(f"[CI/CD RAG] Retrieved {len(results)} workflows for query: {query_text[:60]}...")
        return results
    
    def _calculate_platform_bonus(self, query: str, content: str) -> float:
        """Calculate bonus points for platform/provider matches."""
        bonus = 0.0
        query_lower = query.lower()
        content_lower = content.lower()
        
        # GitHub Actions
        if any(k in query_lower for k in ["github", "github actions"]):
            if "github" in content_lower or "github actions" in content_lower:
                bonus += 10.0
        
        # GitLab CI
        if "gitlab" in query_lower:
            if "gitlab" in content_lower or "gitlab-ci" in content_lower:
                bonus += 10.0
        
        # Jenkins
        if "jenkins" in query_lower:
            if "jenkins" in content_lower or "jenkinsfile" in content_lower:
                bonus += 10.0
        
        # Azure DevOps
        if "azure" in query_lower:
            if "azure" in content_lower or "azure devops" in content_lower:
                bonus += 10.0
        
        # Build tools
        build_tools = {
            "maven": ["maven", "pom.xml"],
            "gradle": ["gradle", "build.gradle"],
            "npm": ["npm", "package.json"],
            "docker": ["docker", "dockerfile"],
            "kubernetes": ["k8s", "kubernetes"],
            "terraform": ["terraform", "hcl"],
        }
        
        for tool, keywords in build_tools.items():
            if tool in query_lower:
                for keyword in keywords:
                    if keyword in content_lower:
                        bonus += 5.0
                        break
        
        return bonus
    
    def _load_pages(self) -> List[Dict[str, Any]]:
        """Load all knowledge base pages."""
        if not self.page_index_path.exists():
            print(f"[CI/CD RAG] Warning: Page index not found at {self.page_index_path}")
            return []
        
        try:
            raw = json.loads(self.page_index_path.read_text(encoding="utf-8-sig"))
        except Exception as e:
            print(f"[CI/CD RAG] Error loading page index: {e}")
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
            if path.exists():
                try:
                    pages.append(json.loads(path.read_text(encoding="utf-8-sig")))
                except Exception as e:
                    print(f"[CI/CD RAG] Error loading page {ref}: {e}")
                    continue
        
        print(f"[CI/CD RAG] Loaded {len(pages)} workflow pages from knowledge base")
        return pages
    
    def _flatten_structure(self, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Recursively flatten nested node structure."""
        flat: List[Dict[str, Any]] = []
        for node in nodes:
            flat.append(node)
            children = node.get("nodes", [])
            if isinstance(children, list) and children:
                flat.extend(self._flatten_structure(children))
        return flat
    
    def _tokenize(self, text: str) -> set[str]:
        """Tokenize text for similarity scoring."""
        return set(re.findall(r"[a-zA-Z0-9_\-.]+", text.lower()))
