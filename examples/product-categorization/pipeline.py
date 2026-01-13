"""Product categorization pipeline instrumented with X-Ray SDK.

This pipeline demonstrates automatic product categorization with decision transparency:
- Extract attributes from product title/description
- Match against category requirements
- Score candidates by keyword and signal matching
- Handle ambiguous cases (multiple matches)
- Select best-fit category with confidence score
"""

from sdk import attach_reasoning, step

from data import CATEGORY_TAXONOMY


@step(step_type="transform")
def extract_attributes(title: str, description: str) -> dict:
    """Extract product attributes from title and description."""
    text = (title + " " + description).lower()

    # Simple attribute extraction (in production, this might use NLP/LLM)
    words = text.split()

    # Extract key terms
    keywords = [
        w for w in words
        if len(w) > 3 and w not in {"with", "this", "that", "from", "have", "been"}
    ]

    attributes = {
        "all_text": text,
        "keywords": list(set(keywords))[:20],  # Dedupe and limit
        "word_count": len(words),
        "has_brand": any(brand in text for brand in ["apple", "samsung", "sony", "lg"]),
    }

    attach_reasoning({
        "extraction_method": "simple_tokenization",
        "keywords_extracted": len(attributes["keywords"]),
        "sample_keywords": attributes["keywords"][:5],
    })

    return attributes


@step(step_type="retrieval")
def find_candidate_categories(attributes: dict) -> list[dict]:
    """Find all categories that could potentially match this product."""
    candidates = []
    text = attributes["all_text"]

    # Scan taxonomy for matches
    for parent_name, parent_data in CATEGORY_TAXONOMY.items():
        for sub_name, sub_data in parent_data["subcategories"].items():
            # Check if any category keywords appear in product text
            keyword_matches = sum(1 for kw in sub_data["keywords"] if kw in text)
            signal_matches = sum(1 for sig in sub_data["signals"] if sig in text)

            if keyword_matches > 0 or signal_matches > 0:
                candidates.append({
                    "id": sub_data["id"],
                    "parent": parent_name,
                    "name": sub_name,
                    "keyword_matches": keyword_matches,
                    "signal_matches": signal_matches,
                    "total_matches": keyword_matches + signal_matches,
                })

    attach_reasoning({
        "taxonomy_size": sum(
            len(p["subcategories"]) for p in CATEGORY_TAXONOMY.values()
        ),
        "candidates_found": len(candidates),
        "had_matches": len(candidates) > 0,
    })

    return candidates


@step(step_type="filter")
def filter_weak_candidates(candidates: list[dict], min_score: int = 2) -> list[dict]:
    """Filter out categories with too few matches."""
    filtered = [c for c in candidates if c["total_matches"] >= min_score]

    removed_candidates = [
        {"id": c["id"], "name": c["name"], "score": c["total_matches"]}
        for c in candidates
        if c["total_matches"] < min_score
    ]

    attach_reasoning({
        "filter_criterion": "minimum_match_score",
        "threshold": min_score,
        "input_count": len(candidates),
        "output_count": len(filtered),
        "removed_count": len(removed_candidates),
        "removed_candidates": removed_candidates,
    })

    return filtered


@step(step_type="rank")
def score_categories(candidates: list[dict]) -> list[dict]:
    """Score and rank categories by relevance."""
    # Weighted scoring: signals are more important than general keywords
    for candidate in candidates:
        candidate["score"] = (
            candidate["keyword_matches"] * 1.0 +
            candidate["signal_matches"] * 2.0
        )

    ranked = sorted(candidates, key=lambda x: x["score"], reverse=True)

    attach_reasoning({
        "scoring_formula": "keyword_matches * 1.0 + signal_matches * 2.0",
        "weights": {"keywords": 1.0, "signals": 2.0},
        "top_3_scores": [
            {"id": c["id"], "name": c["name"], "score": c["score"]}
            for c in ranked[:3]
        ],
    })

    return ranked


@step(step_type="llm")  # In production, this would use an actual LLM
def resolve_ambiguity(
    candidates: list[dict], product_title: str, product_desc: str
) -> dict:
    """Handle ambiguous cases where multiple categories match well."""
    if not candidates:
        attach_reasoning({
            "model": "rule-based-fallback",
            "decision": "no_candidates",
            "confidence": 0.0,
        })
        return {
            "category_id": None,
            "category_name": None,
            "confidence": 0.0,
            "reason": "No matching categories found",
        }

    # Simulated LLM decision-making (in reality, would send to LLM)
    top_candidate = candidates[0]

    # Calculate confidence based on score gap
    if len(candidates) > 1:
        score_gap = top_candidate["score"] - candidates[1]["score"]
        confidence = min(0.9, 0.5 + (score_gap * 0.1))
        ambiguous = score_gap < 1.0
    else:
        confidence = 0.95
        ambiguous = False

    # Context for reasoning
    reasoning_data = {
        "model": "simulated-llm-v1",
        "candidates_considered": len(candidates),
        "ambiguous": ambiguous,
        "confidence": round(confidence, 2),
        "selected_category": top_candidate["name"],
        "runner_up": candidates[1]["name"] if len(candidates) > 1 else None,
    }

    if ambiguous:
        reasoning_data["ambiguity_reason"] = "Multiple categories scored similarly"
        reasoning_data["score_gap"] = round(
            top_candidate["score"] - candidates[1]["score"], 2
        )

    attach_reasoning(reasoning_data)

    return {
        "category_id": top_candidate["id"],
        "category_name": f"{top_candidate['parent']} > {top_candidate['name']}",
        "confidence": round(confidence, 2),
        "reason": f"Best match with {top_candidate['total_matches']} signals",
    }


def categorize_product(title: str, description: str) -> dict:
    """Run the full categorization pipeline.

    Args:
        title: Product title
        description: Product description

    Returns:
        Category assignment with confidence and reasoning
    """
    # Step 1: Extract attributes
    attributes = extract_attributes(title, description)

    # Step 2: Find candidate categories
    candidates = find_candidate_categories(attributes)

    if not candidates:
        return {
            "category_id": None,
            "category_name": "Uncategorized",
            "confidence": 0.0,
            "error": "No matching categories in taxonomy",
        }

    # Step 3: Filter weak matches
    filtered_candidates = filter_weak_candidates(candidates, min_score=2)

    if not filtered_candidates:
        # All candidates were too weak - lower threshold
        filtered_candidates = candidates

    # Step 4: Score and rank
    ranked_candidates = score_categories(filtered_candidates)

    # Step 5: Resolve ambiguity and select final category
    result = resolve_ambiguity(ranked_candidates, title, description)

    return result
