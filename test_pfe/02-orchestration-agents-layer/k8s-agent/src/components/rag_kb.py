"""RAG retrieval component for Kubernetes manifest guidance."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from ..datasets.pageindex_knowledge_base import PageIndexKnowledgeBase


class RAGKnowledgeBase:
    """Retrieve Kubernetes manifest hints from local PageIndex knowledge pages."""

    def __init__(self, knowledge_base_dir: str):
        self.knowledge_base_dir = Path(knowledge_base_dir)
        self.kb = PageIndexKnowledgeBase(str(self.knowledge_base_dir))

    def query(self, query_text: str, top_k: int = 3) -> List[Dict[str, Any]]:
        return self.kb.query(query_text=query_text, top_k=top_k)
