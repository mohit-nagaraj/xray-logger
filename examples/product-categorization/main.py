#!/usr/bin/env python3
"""Example: Product Categorization with X-Ray observability.

This example demonstrates using X-Ray to instrument a product categorization
pipeline. The pipeline automatically assigns products to categories from a
taxonomy, capturing decision-making at each step.

Usage:
    # Start X-Ray backend (using published Docker image)
    docker run -d -p 8000:8000 \\
      -v /tmp/xray-data:/app/data \\
      -e XRAY_DATABASE_URL=sqlite+aiosqlite:////app/data/xray.db \\
      ghcr.io/mohit-nagaraj/xray-logger:latest

    # Install SDK from PyPI
    pip install 'xray-logger[sdk]'

    # Run this example
    python main.py
"""

import sys

from sdk import XRayConfig, init_xray, shutdown_xray

from data import TEST_PRODUCTS
from pipeline import categorize_product


def main() -> None:
    # Initialize X-Ray SDK
    print("Initializing X-Ray SDK...")
    print("Connecting to: http://localhost:8000")

    client = init_xray(XRayConfig(
        base_url="http://localhost:8000",
        buffer_size=1000,
        flush_interval=5.0,
    ))

    print("X-Ray SDK initialized")
    print("=" * 80)

    try:
        # Run categorization for each test product
        results = []

        for i, product in enumerate(TEST_PRODUCTS, 1):
            print(f"\n[{i}/{len(TEST_PRODUCTS)}] Categorizing: {product['title'][:50]}...")
            print("-" * 80)

            # Create a run for this categorization
            with client.start_run(
                pipeline_name="product-categorization",
                input_data={
                    "title": product["title"],
                    "description": product["description"][:100],
                },
                metadata={
                    "product_index": i,
                    "expected_category": product["expected_category"],
                    "challenge": product["challenge"],
                },
            ):
                result = categorize_product(
                    product["title"],
                    product["description"]
                )

                results.append({
                    "product": product["title"],
                    "assigned_category": result.get("category_id"),
                    "expected_category": product["expected_category"],
                    "confidence": result.get("confidence", 0.0),
                    "correct": result.get("category_id") == product["expected_category"],
                })

                # Display result
                print(f"  Category: {result.get('category_name', 'None')}")
                print(f"  Category ID: {result.get('category_id', 'None')}")
                print(f"  Confidence: {result.get('confidence', 0.0):.0%}")
                print(f"  Expected: {product['expected_category']}")
                print(f"  Match: {'✓' if results[-1]['correct'] else '✗'}")

        print("\n" + "=" * 80)
        print("Categorization Complete!")
        print("-" * 80)

        # Summary statistics
        correct_count = sum(1 for r in results if r["correct"])
        accuracy = (correct_count / len(results)) * 100

        print(f"Accuracy: {correct_count}/{len(results)} ({accuracy:.1f}%)")
        print(f"Average Confidence: {sum(r['confidence'] for r in results) / len(results):.0%}")

        # Show misclassifications
        errors = [r for r in results if not r["correct"]]
        if errors:
            print(f"\nMisclassifications ({len(errors)}):")
            for err in errors:
                print(f"  • {err['product'][:50]}")
                print(f"    Got: {err['assigned_category']}, Expected: {err['expected_category']}")

    finally:
        print("\n" + "=" * 80)
        print("Flushing data to X-Ray server...")
        shutdown_xray(timeout=5.0)
        # Give async tasks time to complete
        import time
        time.sleep(1)
        print("Done!")

    print("\nView captured data:")
    print("  • All runs: http://localhost:8000/docs#/default/list_runs_xray_runs_get")
    print("  • API docs: http://localhost:8000/docs")
    print("\nQuery examples:")
    print('  curl "http://localhost:8000/xray/runs?pipeline=product-categorization"')
    print('  curl "http://localhost:8000/xray/steps?step_type=filter"')


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted")
        shutdown_xray(timeout=2.0)
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        shutdown_xray(timeout=2.0)
        raise
