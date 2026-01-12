#!/usr/bin/env python3
"""Example: Competitor Analysis RAG Pipeline with X-Ray observability.

This example demonstrates how to use the X-Ray SDK to instrument a
RAG (Retrieval-Augmented Generation) pipeline for competitor analysis.
Each step captures decision-making data including search queries,
filter criteria, ranking scores, and LLM reasoning.

Usage:
    # Start the X-Ray backend first
    docker-compose up -d

    # Install dependencies and run the example
    pip install -r requirements.txt
    python main.py
"""

import sys

from sdk import XRayConfig, init_xray, shutdown_xray

from .pipeline import run_competitor_analysis


def main() -> None:
    # Initialize X-Ray SDK
    config = XRayConfig(
        base_url="http://localhost:8000",
        buffer_size=100,
        flush_interval=2.0,
    )
    client = init_xray(config)

    print("X-Ray SDK initialized")
    print("=" * 60)

    try:
        # Run multiple analysis queries to generate data
        test_queries = [
            {"query": "AI analytics platform", "min_relevance": 0.7},
            {"query": "market observability growth", "min_relevance": 0.8},
            {"query": "competitor funding partnership", "min_relevance": 0.6},
        ]

        for i, params in enumerate(test_queries, 1):
            print(f"\n[Run {i}] Query: '{params['query']}' (min_relevance={params['min_relevance']})")
            print("-" * 60)

            # Create a run context for this pipeline execution
            with client.start_run(
                pipeline_name="competitor-analysis",
                input_data=params,
                metadata={
                    "request_id": f"analysis-{i}",
                    "user_id": "analyst-demo",
                    "environment": "development",
                },
            ):
                result = run_competitor_analysis(**params)

            # Display results
            if result.get("summary"):
                print(f"Summary: {result['summary']}")
                print(f"Sources: {', '.join(result.get('sources', []))}")
                print(f"Confidence: {result.get('confidence', 'N/A')}")
            else:
                print(f"No results: {result.get('error', 'unknown error')}")

        print("\n" + "=" * 60)
        print("Pipeline runs complete!")
    finally:
        print("Flushing data to X-Ray server...")
        # Graceful shutdown - flushes remaining events
        shutdown_xray(timeout=5.0)
        print("Done! Data captured in the database.")

    print("\nView captured data:")
    print("  - Query runs: GET http://localhost:8000/xray/runs?pipeline=competitor-analysis")
    print("  - Query steps: GET http://localhost:8000/xray/steps?step_type=filter")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted")
        shutdown_xray(timeout=2.0)
        sys.exit(1)
