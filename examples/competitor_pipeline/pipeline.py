"""Competitor analysis RAG pipeline instrumented with X-Ray SDK.

Demonstrates a Retrieval-Augmented Generation (RAG) workflow with:
- @step decorator for function instrumentation
- attach_reasoning() for decision explanation
- attach_candidates() for capturing ranked results
- Different step types: retrieval, filter, rank, llm
"""

from sdk import attach_candidates, attach_reasoning, step

from .data import DOCUMENTS


@step(step_type="retrieval")
def retrieve_documents(query: str, max_results: int = 10) -> list[dict]:
    """Retrieve documents matching the query.

    Simulates a vector similarity search by performing keyword matching.
    In a real system, this would query a vector database.
    """
    query_lower = query.lower()
    query_terms = query_lower.split()

    results = []
    for doc in DOCUMENTS:
        # Simple keyword matching (simulating vector search)
        content_lower = doc["content"].lower()
        title_lower = doc["title"].lower()
        matches = sum(
            1 for term in query_terms if term in content_lower or term in title_lower
        )
        if matches > 0:
            result = doc.copy()
            result["match_score"] = matches / len(query_terms)
            results.append(result)

    # Sort by match score and limit
    results = sorted(results, key=lambda x: x["match_score"], reverse=True)[:max_results]

    attach_reasoning(
        {
            "query": query,
            "query_terms": query_terms,
            "search_method": "keyword_match",
            "total_corpus_size": len(DOCUMENTS),
            "matching_documents": len(results),
        }
    )

    return results


@step(step_type="filter")
def filter_by_relevance(
    documents: list[dict], min_relevance: float = 0.7
) -> list[dict]:
    """Filter documents below relevance threshold.

    Removes documents that don't meet the minimum relevance score,
    tracking which documents were removed and why.
    """
    initial_count = len(documents)

    filtered = []
    removed_docs = []

    for doc in documents:
        score = doc.get("relevance_score", 0)
        if score >= min_relevance:
            filtered.append(doc)
        else:
            removed_docs.append(
                {
                    "id": doc["id"],
                    "title": doc["title"],
                    "relevance_score": score,
                    "reason": f"below_threshold ({score:.2f} < {min_relevance})",
                }
            )

    attach_reasoning(
        {
            "filter_type": "relevance_threshold",
            "threshold": min_relevance,
            "input_count": initial_count,
            "output_count": len(filtered),
            "removed_count": len(removed_docs),
            "removed_documents": removed_docs,
        }
    )

    return filtered


@step(step_type="rank")
def rank_by_importance(documents: list[dict]) -> list[dict]:
    """Rank documents by composite importance score.

    Computes importance as a combination of:
    - relevance_score (base quality)
    - recency_bonus (prefer newer documents)
    - source_weight (prefer authoritative sources)
    """
    source_weights = {
        "analyst_report": 1.0,
        "white_paper": 0.9,
        "case_study": 0.85,
        "industry_report": 0.8,
        "press_release": 0.7,
        "news_article": 0.6,
        "review": 0.5,
        "regulatory_update": 0.75,
    }

    for doc in documents:
        relevance = doc.get("relevance_score", 0.5)
        source_weight = source_weights.get(doc.get("source", ""), 0.5)

        # Recency bonus: documents from 2024 get a boost
        recency_bonus = 0.1 if "2024" in doc.get("date", "") else 0

        # Composite score
        doc["importance_score"] = round(
            relevance * 0.5 + source_weight * 0.3 + recency_bonus * 0.2, 3
        )
        doc["score_breakdown"] = {
            "relevance_contribution": round(relevance * 0.5, 3),
            "source_contribution": round(source_weight * 0.3, 3),
            "recency_contribution": round(recency_bonus * 0.2, 3),
        }

    ranked = sorted(documents, key=lambda x: x["importance_score"], reverse=True)

    # Attach candidates with their scores
    attach_candidates(ranked, phase="output")

    attach_reasoning(
        {
            "ranking_algorithm": "weighted_composite",
            "formula": "importance = relevance*0.5 + source_weight*0.3 + recency_bonus*0.2",
            "weights": {"relevance": 0.5, "source": 0.3, "recency": 0.2},
            "top_results": [
                {"id": d["id"], "title": d["title"], "score": d["importance_score"]}
                for d in ranked[:3]
            ],
        }
    )

    return ranked


@step(step_type="llm")
def generate_summary(documents: list[dict], max_docs: int = 3) -> dict:
    """Generate summary using top documents.

    Simulates an LLM call that would synthesize insights from
    the top-ranked documents. In production, this would call
    an actual LLM API.
    """
    top_docs = documents[:max_docs]

    if not top_docs:
        attach_reasoning(
            {
                "model": "gpt-4-simulated",
                "status": "skipped",
                "reason": "no_documents_provided",
            }
        )
        return {
            "summary": None,
            "error": "No documents to summarize",
        }

    # Simulate LLM summarization
    doc_titles = [d["title"] for d in top_docs]
    sources = list(set(d["source"] for d in top_docs))

    summary = (
        f"Analysis based on {len(top_docs)} documents: "
        f"Key topics include {', '.join(doc_titles[:2])}. "
        f"Sources consulted: {', '.join(sources)}."
    )

    attach_reasoning(
        {
            "model": "gpt-4-simulated",
            "prompt_tokens": 150 * len(top_docs),
            "completion_tokens": 75,
            "documents_used": [d["id"] for d in top_docs],
            "generation_strategy": "extractive_summary",
            "temperature": 0.7,
        }
    )

    return {
        "summary": summary,
        "sources": [d["id"] for d in top_docs],
        "document_count": len(top_docs),
        "confidence": 0.85,
    }


def run_competitor_analysis(query: str, min_relevance: float = 0.7) -> dict:
    """Execute the full RAG pipeline for competitor analysis.

    Args:
        query: Search query for document retrieval
        min_relevance: Minimum relevance score threshold (0.0-1.0)

    Returns:
        Dictionary with summary and metadata, or error information
    """
    # Step 1: Retrieve documents
    docs = retrieve_documents(query)

    if not docs:
        return {
            "summary": None,
            "error": f"No documents found for query: {query}",
            "query": query,
        }

    # Step 2: Filter by relevance
    filtered = filter_by_relevance(docs, min_relevance=min_relevance)

    if not filtered:
        return {
            "summary": None,
            "error": "All documents filtered out due to low relevance",
            "query": query,
            "original_count": len(docs),
        }

    # Step 3: Rank by importance
    ranked = rank_by_importance(filtered)

    # Step 4: Generate summary
    result = generate_summary(ranked)
    result["query"] = query

    return result
