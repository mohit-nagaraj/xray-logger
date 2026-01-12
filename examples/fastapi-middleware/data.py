"""In-memory product data store for the FastAPI middleware example.

This module provides a simple in-memory database for CRUD operations.
In a real application, this would be replaced with actual database access.
"""

from typing import Dict

# In-memory product database (key: product_id, value: product dict)
PRODUCTS: Dict[str, dict] = {
    "E001": {
        "id": "E001",
        "name": "Wireless Headphones Pro",
        "category": "electronics",
        "price": 149.99,
        "rating": 4.7,
        "in_stock": True,
    },
    "E002": {
        "id": "E002",
        "name": "Budget Earbuds",
        "category": "electronics",
        "price": 29.99,
        "rating": 3.2,
        "in_stock": True,
    },
    "E003": {
        "id": "E003",
        "name": "Bluetooth Speaker Mini",
        "category": "electronics",
        "price": 49.99,
        "rating": 4.1,
        "in_stock": True,
    },
    "E004": {
        "id": "E004",
        "name": "Smart Home Hub",
        "category": "electronics",
        "price": 129.99,
        "rating": 4.3,
        "in_stock": True,
    },
    "E005": {
        "id": "E005",
        "name": "Noise Cancelling Buds",
        "category": "electronics",
        "price": 199.99,
        "rating": 4.5,
        "in_stock": True,
    },
    "B001": {
        "id": "B001",
        "name": "Python Mastery",
        "category": "books",
        "price": 49.99,
        "rating": 4.8,
        "in_stock": True,
    },
    "B002": {
        "id": "B002",
        "name": "Data Science Handbook",
        "category": "books",
        "price": 59.99,
        "rating": 4.5,
        "in_stock": True,
    },
    "B003": {
        "id": "B003",
        "name": "Machine Learning Intro",
        "category": "books",
        "price": 44.99,
        "rating": 4.6,
        "in_stock": True,
    },
    "H001": {
        "id": "H001",
        "name": "Ergonomic Desk Chair",
        "category": "home",
        "price": 299.99,
        "rating": 4.4,
        "in_stock": True,
    },
    "H002": {
        "id": "H002",
        "name": "LED Desk Lamp",
        "category": "home",
        "price": 39.99,
        "rating": 4.2,
        "in_stock": True,
    },
}


def get_next_product_id(category: str) -> str:
    """Generate next product ID for a category."""
    prefix = category[0].upper()
    existing_ids = [
        int(pid[1:]) for pid in PRODUCTS.keys() if pid.startswith(prefix)
    ]
    next_num = max(existing_ids) + 1 if existing_ids else 1
    return f"{prefix}{next_num:03d}"
