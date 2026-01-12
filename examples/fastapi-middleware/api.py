"""API route handlers demonstrating X-Ray middleware integration.

This module shows how middleware automatically creates Run contexts,
and how @step decorators work within route handlers for comprehensive
function-level observability.
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sdk import current_run

from operations import (
    create_product_in_db,
    delete_product_from_db,
    format_product_response,
    get_product_from_db,
    list_products_with_filters,
    update_product_in_db,
    validate_product_data,
)

router = APIRouter()


# Pydantic models for request/response validation
class ProductCreate(BaseModel):
    """Product creation request."""

    name: str = Field(..., min_length=1, max_length=200)
    category: str = Field(..., pattern="^(electronics|books|home)$")
    price: float = Field(..., gt=0)
    rating: float = Field(..., ge=0, le=5)
    in_stock: bool = True


class ProductUpdate(BaseModel):
    """Product update request."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    category: Optional[str] = Field(None, pattern="^(electronics|books|home)$")
    price: Optional[float] = Field(None, gt=0)
    rating: Optional[float] = Field(None, ge=0, le=5)
    in_stock: Optional[bool] = None


class ProductResponse(BaseModel):
    """Product response."""

    id: str
    name: str
    category: str
    price: float
    rating: float
    in_stock: bool


class BatchCreateRequest(BaseModel):
    """Batch product creation request."""

    products: List[ProductCreate] = Field(..., min_items=1, max_items=10)


class BatchCreateResponse(BaseModel):
    """Batch creation response."""

    created: List[ProductResponse]
    failed: List[dict]
    summary: dict


@router.get("/products", response_model=List[ProductResponse])
async def list_products(
    request: Request,
    category: Optional[str] = None,
    min_rating: Optional[float] = None,
):
    """List all products with optional filtering.

    Query Parameters:
        - category: Filter by category (electronics, books, home)
        - min_rating: Minimum rating threshold

    Demonstrates:
        - Query parameter capture by middleware
        - @step decorator for filtering logic
        - Custom metadata via current_run()
    """
    # Access current run created by middleware
    run = current_run()
    if run:
        run.metadata["operation"] = "list_products"
        run.metadata["filters"] = {
            "category": category,
            "min_rating": min_rating,
        }

    # Use @step decorated function for filtering
    products = list_products_with_filters(category=category, min_rating=min_rating)

    # Add result count to metadata
    if run:
        run.metadata["result_count"] = len(products)

    return [format_product_response(p) for p in products]


@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(product_id: str, request: Request):
    """Get a single product by ID.

    Path Parameters:
        - product_id: Product identifier

    Demonstrates:
        - Path parameter capture by middleware
        - Simple retrieval step
        - 404 error handling
    """
    # Access current run
    run = current_run()
    if run:
        run.metadata["operation"] = "get_product"
        run.metadata["product_id"] = product_id

    # Use @step decorated function
    product = get_product_from_db(product_id)

    if not product:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")

    return format_product_response(product)


@router.post("/products", response_model=ProductResponse, status_code=201)
async def create_product(product: ProductCreate, request: Request):
    """Create a new product.

    Request Body:
        - ProductCreate schema with validation

    Demonstrates:
        - Request body parsing
        - Validation step
        - Creation step
        - Custom metadata (client IP, operation type)
    """
    # Access current run created by middleware
    run = current_run()
    if run:
        run.metadata["operation"] = "create_product"
        run.metadata["category"] = product.category
        run.metadata["client_ip"] = request.client.host if request.client else None

    # Validate product data
    product_dict = product.model_dump()
    validated = validate_product_data(product_dict)

    # Create product
    created = create_product_in_db(validated)

    # Add creation metadata
    if run:
        run.metadata["created_product_id"] = created["id"]

    return format_product_response(created)


@router.put("/products/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: str,
    product: ProductUpdate,
    request: Request,
):
    """Update an existing product.

    Path Parameters:
        - product_id: Product identifier

    Request Body:
        - ProductUpdate schema (partial updates allowed)

    Demonstrates:
        - Path parameter + request body
        - Partial update handling
        - 404 error for non-existent product
    """
    # Access current run
    run = current_run()
    if run:
        run.metadata["operation"] = "update_product"
        run.metadata["product_id"] = product_id

    # Get only fields that were provided
    updates = product.model_dump(exclude_unset=True)

    # Validate updates if any
    if updates:
        validate_product_data(updates)

    # Update product
    updated = update_product_in_db(product_id, updates)

    if not updated:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")

    # Add metadata about updated fields
    if run:
        run.metadata["updated_fields"] = list(updates.keys())

    return format_product_response(updated)


@router.delete("/products/{product_id}/force-error")
async def force_error_endpoint(product_id: str):
    """Intentionally raise an error to demonstrate middleware error capture.

    Path Parameters:
        - product_id: Product identifier (not actually used)

    Demonstrates:
        - Exception capture by middleware
        - Run status set to "error" automatically
        - Custom error metadata

    Note: This endpoint always raises an exception for demonstration purposes.
    """
    # Access current run
    run = current_run()
    if run:
        run.metadata["testing"] = "error_handling"
        run.metadata["product_id"] = product_id

    # Intentionally raise an exception
    # The middleware will capture this and set run status to "error"
    raise ValueError(
        f"Intentional error for product {product_id} - demonstrating error capture"
    )


@router.post("/products/batch", response_model=BatchCreateResponse, status_code=201)
async def batch_create_products(batch: BatchCreateRequest, request: Request):
    """Create multiple products in a single request.

    Request Body:
        - BatchCreateRequest with list of products (max 10)

    Demonstrates:
        - Batch operations with partial success handling
        - Error collection without failing entire request
        - Custom metadata for batch operations

    Returns:
        Summary with created products and failed items
    """
    # Access current run
    run = current_run()
    if run:
        run.metadata["operation"] = "batch_create"
        run.metadata["batch_size"] = len(batch.products)

    created_products = []
    failed_items = []

    for idx, product in enumerate(batch.products):
        try:
            # Validate
            product_dict = product.model_dump()
            validated = validate_product_data(product_dict)

            # Create
            created = create_product_in_db(validated)
            created_products.append(format_product_response(created))

        except Exception as e:
            # Collect errors without failing entire batch
            failed_items.append({
                "index": idx,
                "product_name": product.name,
                "error": str(e),
            })

    # Add summary metadata
    if run:
        run.metadata["results"] = {
            "created_count": len(created_products),
            "failed_count": len(failed_items),
            "success_rate": len(created_products) / len(batch.products),
        }

    return BatchCreateResponse(
        created=created_products,
        failed=failed_items,
        summary={
            "total_requested": len(batch.products),
            "created": len(created_products),
            "failed": len(failed_items),
        },
    )
