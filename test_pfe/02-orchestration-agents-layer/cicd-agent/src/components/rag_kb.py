"""RAG knowledge base retrieval for CI/CD best practices and workflows."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


class RAGKnowledgeBase:
    """Retrieve relevant CI/CD workflow examples from a PageIndex-structured knowledge base."""

    def __init__(self, knowledge_base_dir: str):
        self.knowledge_base_dir = Path(knowledge_base_dir)
        self.page_index_path = self.knowledge_base_dir / "page_index.json"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def query(self, query_text: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Query knowledge base for relevant CI/CD workflows.

        Args:
            query_text: Natural-language search query (user prompt).
            top_k:      Maximum number of results to return.

        Returns:
            List of dicts with keys: page_id, title, content, score.
            Returns [] if knowledge base is empty or unavailable.
        """
        pages = self._load_pages()

        if not pages:
            print(
                "[CI/CD RAG] No pages loaded from knowledge base. "
                "Verify page_index.json exists and references valid page files."
            )
            return []

        print(f"[CI/CD RAG] Scoring {len(pages)} pages against query: {query_text[:80]}...")

        query_tokens = self._tokenize(query_text)
        scored: List[tuple[float, Dict[str, Any]]] = []

        for page in pages:
            searchable = " ".join([
                str(page.get("title", "")),
                str(page.get("source", "")),
                " ".join(page.get("tags", [])),
                str(page.get("content", ""))[:500],
            ])

            overlap = len(query_tokens.intersection(self._tokenize(searchable)))
            platform_bonus = self._calculate_platform_bonus(query_text, searchable)
            score = float(overlap) + platform_bonus

            # Always include if KB is tiny (≤5 pages) to avoid empty results
            if score > 0 or len(pages) <= 5:
                scored.append((score, page))

        if not scored:
            # Last resort: return all pages ranked by index order
            print("[CI/CD RAG] No token overlap found — returning all pages as fallback")
            scored = [(float(i), page) for i, page in enumerate(pages)]

        scored.sort(key=lambda item: item[0], reverse=True)

        results: List[Dict[str, Any]] = []
        seen: set = set()

        for score, page in scored:
            page_id = page.get("page_id") or page.get("title")
            if page_id in seen:
                continue
            results.append({
                "page_id": page_id,
                "title": page.get("title"),
                "content": page.get("content", "")[:1000],
                "score": round(score, 2),
            })
            seen.add(page_id)
            if len(results) >= top_k:
                break

        print(f"[CI/CD RAG] Returning {len(results)} result(s) (top_k={top_k})")
        for r in results:
            print(f"  - [{r['score']}] {r['title']} (page_id={r['page_id']})")

        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_pages(self) -> List[Dict[str, Any]]:
        """Load and validate all knowledge base pages via page_index.json."""

        if not self.page_index_path.exists():
            print(f"[CI/CD RAG] page_index.json not found at: {self.page_index_path}")
            return []

        # --- Parse the index file ---
        try:
            raw = json.loads(self.page_index_path.read_text(encoding="utf-8-sig"))
        except Exception as e:
            print(f"[CI/CD RAG] Failed to parse page_index.json: {e}")
            return []

        # --- Validate expected structure ---
        if not isinstance(raw, dict):
            print(
                f"[CI/CD RAG] page_index.json root must be a JSON object, "
                f"got {type(raw).__name__}. Cannot load pages."
            )
            return []

        if "structure" not in raw:
            print(
                f"[CI/CD RAG] page_index.json missing 'structure' key. "
                f"Top-level keys found: {list(raw.keys())}. Cannot load pages."
            )
            return []

        if not isinstance(raw["structure"], list):
            print(
                f"[CI/CD RAG] page_index.json 'structure' must be a list, "
                f"got {type(raw['structure']).__name__}. Cannot load pages."
            )
            return []

        # --- Extract page refs from nested structure ---
        nodes = self._flatten_structure(raw["structure"])
        page_refs = [
            str(node["page_ref"])
            for node in nodes
            if isinstance(node.get("page_ref"), str)
        ]

        if not page_refs:
            print(
                "[CI/CD RAG] No 'page_ref' entries found in page_index.json structure. "
                "Check that each node has a 'page_ref' string field."
            )
            return []

        print(f"[CI/CD RAG] Found {len(page_refs)} page references in index")

        # --- Load each page file ---
        pages: List[Dict[str, Any]] = []
        missing: List[str] = []

        for ref in page_refs:
            path = self.knowledge_base_dir / ref
            if not path.exists():
                missing.append(ref)
                continue
            try:
                pages.append(json.loads(path.read_text(encoding="utf-8-sig")))
            except Exception as e:
                print(f"[CI/CD RAG] Failed to load page '{ref}': {e}")

        if missing:
            print(
                f"[CI/CD RAG] {len(missing)} page file(s) referenced in index but missing on disk: "
                f"{missing[:5]}{'...' if len(missing) > 5 else ''}"
            )

        print(f"[CI/CD RAG] Successfully loaded {len(pages)}/{len(page_refs)} pages")
        return pages

    def _flatten_structure(self, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Recursively flatten nested node tree into a flat list."""
        flat: List[Dict[str, Any]] = []
        for node in nodes:
            flat.append(node)
            children = node.get("nodes", [])
            if isinstance(children, list) and children:
                flat.extend(self._flatten_structure(children))
        return flat

    def _tokenize(self, text: str) -> set[str]:
        """Simple whitespace/punctuation tokenizer for overlap scoring."""
        return set(re.findall(r"[a-zA-Z0-9_\-.]+", text.lower()))

    def _calculate_platform_bonus(self, query: str, content: str) -> float:
        """Boost score when query and content share platform/tool keywords."""
        bonus = 0.0
        query_lower = query.lower()
        content_lower = content.lower()

        platform_keywords = {
            "github actions": (["github", "github actions"], ["github", "github actions"], 10.0),
            "gitlab":         (["gitlab"],                   ["gitlab", "gitlab-ci"],      10.0),
            "jenkins":        (["jenkins"],                  ["jenkins", "jenkinsfile"],   10.0),
            "azure":          (["azure"],                    ["azure", "azure devops"],    10.0),
        }

        for _, (query_kws, content_kws, weight) in platform_keywords.items():
            if any(k in query_lower for k in query_kws):
                if any(k in content_lower for k in content_kws):
                    bonus += weight

        build_tools = {
            "maven":      ["maven", "pom.xml"],
            "gradle":     ["gradle", "build.gradle"],
            "npm":        ["npm", "package.json"],
            "docker":     ["docker", "dockerfile"],
            "kubernetes": ["k8s", "kubernetes"],
            "terraform":  ["terraform", "hcl"],
            "junit":      ["junit", "surefire"],
        }

        for tool, keywords in build_tools.items():
            if tool in query_lower:
                if any(kw in content_lower for kw in keywords):
                    bonus += 5.0

        return bonus