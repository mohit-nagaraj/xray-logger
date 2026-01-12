"""Product recommendation pipeline instrumented with X-Ray SDK.

Demonstrates:
- @step decorator for function instrumentation
- attach_reasoning() for decision explanation
- attach_candidates() for capturing ranked results
- Different step types: retrieval, filter, rank, transform
"""

from sdk import attach_candidates, attach_reasoning, step

from data import PRODUCTS


@step(step_type="retrieval")
def get_candidates(category: str) -> list[dict]:
    """Retrieve all products in the requested category."""
    candidates = [p.copy() for p in PRODUCTS if p["category"] == category]
    return candidates


@step(step_type="filter")
def filter_products(
    products: list[dict],
    min_rating: float = 3.5,
    in_stock_only: bool = True,
) -> list[dict]:
    """Filter out low-rated and out-of-stock products."""
    initial_count = len(products)

    # Track removal reasons
    low_rating_ids = []
    out_of_stock_ids = []

    filtered = []
    for p in products:
        if p["rating"] < min_rating:
            low_rating_ids.append(p["id"])
        elif in_stock_only and not p["in_stock"]:
            out_of_stock_ids.append(p["id"])
        else:
            filtered.append(p)

    # Attach reasoning explaining WHY items were filtered
    attach_reasoning({
        "filter_criteria": {
            "min_rating": min_rating,
            "in_stock_only": in_stock_only,
        },
        "removal_summary": {
            "total_removed": initial_count - len(filtered),
            "low_rating": {"count": len(low_rating_ids), "ids": low_rating_ids},
            "out_of_stock": {"count": len(out_of_stock_ids), "ids": out_of_stock_ids},
        },
    })

    return filtered


@step(step_type="rank")
def rank_products(
    products: list[dict],
    rating_weight: float = 0.7,
    price_weight: float = 0.3,
) -> list[dict]:
    """Score and rank products by composite score."""
    # Find max price for normalization (use 1 if all products are free to avoid division by zero)
    max_price = max((p["price"] for p in products), default=1) or 1

    # Calculate scores
    for p in products:
        # Higher rating = higher score
        rating_score = p["rating"] / 5.0

        # Lower price = higher score (inverse normalized)
        price_score = 1 - (p["price"] / max_price) if max_price > 0 else 1.0

        # Composite score
        p["score"] = round(rating_score * rating_weight + price_score * price_weight, 3)
        p["score_breakdown"] = {
            "rating_contribution": round(rating_score * rating_weight, 3),
            "price_contribution": round(price_score * price_weight, 3),
        }

    # Sort by score descending
    ranked = sorted(products, key=lambda x: x["score"], reverse=True)

    # Attach candidates with their scores
    attach_candidates(ranked, phase="output")

    # Attach reasoning explaining the ranking formula
    attach_reasoning({
        "ranking_formula": f"score = (rating/5) * {rating_weight} + (1 - price/max_price) * {price_weight}",
        "weights": {"rating": rating_weight, "price": price_weight},
        "max_price_in_set": max_price,
        "top_3_results": [
            {"id": p["id"], "name": p["name"], "score": p["score"]}
            for p in ranked[:3]
        ],
    })

    return ranked


@step(step_type="transform")
def format_response(products: list[dict], limit: int = 5) -> dict:
    """Format the final API response."""
    recommendations = [
        {
            "id": p["id"],
            "name": p["name"],
            "price": p["price"],
            "rating": p["rating"],
            "score": p["score"],
        }
        for p in products[:limit]
    ]

    return {
        "recommendations": recommendations,
        "metadata": {
            "total_candidates_after_ranking": len(products),
            "returned_count": len(recommendations),
        },
    }


def run_recommendation_pipeline(
    category: str,
    min_rating: float = 3.5,
    limit: int = 5,
) -> dict:
    """Execute the full recommendation pipeline."""
    # Step 1: Retrieve candidates
    candidates = get_candidates(category)

    if not candidates:
        return {"recommendations": [], "metadata": {"error": f"No products in category: {category}"}}

    # Step 2: Filter
    filtered = filter_products(candidates, min_rating=min_rating)

    if not filtered:
        return {"recommendations": [], "metadata": {"error": "All candidates filtered out"}}

    # Step 3: Rank
    ranked = rank_products(filtered)

    # Step 4: Format response
    response = format_response(ranked, limit=limit)

    return response
