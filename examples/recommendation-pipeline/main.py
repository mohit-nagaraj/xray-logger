#!/usr/bin/env python3
"""Example: Product Recommendation Pipeline with X-Ray observability.

This example demonstrates how to use the X-Ray SDK to instrument a
multi-step recommendation pipeline. Each step captures decision-making
data including filtering criteria, ranking scores, and reasoning.

Usage:
    # Start the X-Ray backend first
    docker-compose up -d

    # Install dependencies and run the example
    pip install -r requirements.txt
    python main.py
"""

import sys

from sdk import XRayConfig, init_xray, shutdown_xray

from pipeline import run_recommendation_pipeline


def main() -> None:
    # Initialize X-Ray SDK
    config = XRayConfig(
        base_url="http://localhost:8000",
        buffer_size=100,
        flush_interval=2.0,
    )
    client = init_xray(config)

    print("X-Ray SDK initialized")
    print("=" * 50)

    # Run multiple recommendation requests to generate data
    test_cases = [
        {"category": "electronics", "min_rating": 4.0, "limit": 3},
        {"category": "electronics", "min_rating": 3.5, "limit": 5},
        {"category": "books", "min_rating": 4.0, "limit": 3},
        {"category": "home", "min_rating": 3.5, "limit": 5},
    ]

    for i, params in enumerate(test_cases, 1):
        print(f"\n[Run {i}] Recommendations for '{params['category']}' (min_rating={params['min_rating']})")
        print("-" * 50)

        # Create a run context for this pipeline execution
        with client.start_run(
            pipeline_name="product-recommendations",
            input_data=params,
            metadata={"request_id": f"test-{i}", "user_id": "demo-user"},
        ):
            result = run_recommendation_pipeline(**params)

        # Display results
        if result["recommendations"]:
            print(f"Found {len(result['recommendations'])} recommendations:")
            for rec in result["recommendations"]:
                print(f"  - {rec['name']}: ${rec['price']} (rating: {rec['rating']}, score: {rec['score']})")
        else:
            print(f"  No recommendations: {result['metadata'].get('error', 'unknown')}")

    print("\n" + "=" * 50)
    print("Pipeline runs complete!")
    print("Flushing data to X-Ray server...")

    # Graceful shutdown - flushes remaining events
    shutdown_xray(timeout=5.0)

    print("Done! Data captured in PostgreSQL. View with:")
    print("  docker-compose exec postgres psql -U xray -d xray")
    print("  SELECT * FROM runs; SELECT * FROM steps;")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted")
        shutdown_xray(timeout=2.0)
        sys.exit(1)
