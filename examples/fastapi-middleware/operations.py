"""Business logic operations instrumented with X-Ray SDK @step decorators.

This module demonstrates how to use @step decorators to capture
function-level observability within API endpoints.
"""

from typing import List, Optional

from sdk import attach_candidates, attach_reasoning, step

from data import PRODUCTS, get_next_product_id


@step(step_type="retrieval")
def get_product_from_db(product_id: str) -> Optional[dict]:
    """Retrieve a single product by ID from the database.

    Simulates a database query with reasoning capture.
    """
    product = PRODUCTS.get(product_id)

    attach_reasoning({
        "query_type": "primary_key_lookup",
        "product_id": product_id,
        "found": product is not None,
    })

    return product.copy() if product else None


@step(step_type="retrieval")
def list_products_with_filters(
    category: Optional[str] = None,
    min_rating: Optional[float] = None,
) -> List[dict]:
    """List products with optional filtering.

    Args:
        category: Filter by category (electronics, books, home)
        min_rating: Minimum rating threshold

    Returns:
        List of products matching the filters
    """
    products = list(PRODUCTS.values())
    initial_count = len(products)

    # Apply category filter
    if category:
        products = [p for p in products if p["category"] == category]

    # Apply rating filter
    if min_rating is not None:
        products = [p for p in products if p["rating"] >= min_rating]

    # Attach candidates for observability
    attach_candidates(products, phase="output")

    # Attach reasoning explaining the filter results
    attach_reasoning({
        "filters_applied": {
            "category": category,
            "min_rating": min_rating,
        },
        "results": {
            "initial_count": initial_count,
            "after_category_filter": len([p for p in PRODUCTS.values() if not category or p["category"] == category]),
            "final_count": len(products),
            "removed_count": initial_count - len(products),
        },
    })

    return [p.copy() for p in products]


@step(step_type="filter")
def validate_product_data(product: dict) -> dict:
    """Validate product data before creating or updating.

    Args:
        product: Product data to validate

    Returns:
        Validated product data

    Raises:
        ValueError: If validation fails
    """
    validation_results = {
        "has_name": "name" in product and len(product.get("name", "")) > 0,
        "has_category": "category" in product and product["category"] in ["electronics", "books", "home"],
        "has_valid_price": "price" in product and product["price"] > 0,
        "has_valid_rating": "rating" in product and 0 <= product["rating"] <= 5,
    }

    all_passed = all(validation_results.values())

    attach_reasoning({
        "validation_rules": validation_results,
        "passed": all_passed,
        "product_preview": {
            "name": product.get("name", ""),
            "category": product.get("category", ""),
        },
    })

    if not all_passed:
        failed_rules = [k for k, v in validation_results.items() if not v]
        raise ValueError(f"Validation failed: {', '.join(failed_rules)}")

    return product


@step(step_type="transform")
def create_product_in_db(product: dict) -> dict:
    """Create a new product in the database.

    Args:
        product: Product data (without ID)

    Returns:
        Created product with ID assigned
    """
    # Generate new ID
    category = product["category"]
    product_id = get_next_product_id(category)

    # Create product
    new_product = {
        "id": product_id,
        **product,
        "in_stock": product.get("in_stock", True),
    }

    # Save to "database"
    PRODUCTS[product_id] = new_product

    attach_reasoning({
        "operation": "create",
        "generated_id": product_id,
        "category": category,
        "total_products_after": len(PRODUCTS),
    })

    return new_product.copy()


@step(step_type="transform")
def update_product_in_db(product_id: str, updates: dict) -> Optional[dict]:
    """Update an existing product in the database.

    Args:
        product_id: ID of product to update
        updates: Fields to update

    Returns:
        Updated product, or None if not found
    """
    if product_id not in PRODUCTS:
        attach_reasoning({
            "operation": "update",
            "product_id": product_id,
            "found": False,
        })
        return None

    # Update product
    product = PRODUCTS[product_id]
    updated_fields = []

    for key, value in updates.items():
        if key != "id" and key in product:  # Don't allow ID changes
            old_value = product[key]
            product[key] = value
            updated_fields.append({
                "field": key,
                "old_value": old_value,
                "new_value": value,
            })

    attach_reasoning({
        "operation": "update",
        "product_id": product_id,
        "found": True,
        "updated_fields": updated_fields,
    })

    return product.copy()


@step(step_type="transform")
def delete_product_from_db(product_id: str) -> bool:
    """Delete a product from the database.

    Args:
        product_id: ID of product to delete

    Returns:
        True if deleted, False if not found
    """
    if product_id in PRODUCTS:
        del PRODUCTS[product_id]

        attach_reasoning({
            "operation": "delete",
            "product_id": product_id,
            "deleted": True,
            "total_products_after": len(PRODUCTS),
        })

        return True

    attach_reasoning({
        "operation": "delete",
        "product_id": product_id,
        "deleted": False,
        "reason": "product_not_found",
    })

    return False


@step(step_type="transform")
def format_product_response(product: dict) -> dict:
    """Format product data for API response.

    Args:
        product: Raw product data

    Returns:
        Formatted product data
    """
    # Remove internal fields, format for API
    formatted = {
        "id": product["id"],
        "name": product["name"],
        "category": product["category"],
        "price": round(product["price"], 2),
        "rating": product["rating"],
        "in_stock": product["in_stock"],
    }

    attach_reasoning({
        "operation": "format_response",
        "product_id": product["id"],
    })

    return formatted
