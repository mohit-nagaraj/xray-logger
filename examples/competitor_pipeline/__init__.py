"""Competitor Analysis RAG Pipeline Example.

This example demonstrates X-Ray SDK instrumentation for a
Retrieval-Augmented Generation (RAG) workflow with:
- Document retrieval
- Relevance filtering
- Importance ranking
- LLM summarization (simulated)
"""

from .pipeline import run_competitor_analysis

__all__ = ["run_competitor_analysis"]
