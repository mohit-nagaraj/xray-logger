"""Product categorization data - taxonomy and sample products."""

# Simplified e-commerce category taxonomy (in reality, could be 10,000+ categories)
CATEGORY_TAXONOMY = {
    "Electronics": {
        "id": "elec",
        "subcategories": {
            "Mobile Accessories": {
                "id": "elec-mobile-acc",
                "keywords": ["phone", "mobile", "cell", "smartphone", "iphone", "android"],
                "signals": ["charger", "case", "screen protector", "cable", "adapter", "holder"],
            },
            "Computer Accessories": {
                "id": "elec-comp-acc",
                "keywords": ["laptop", "computer", "desktop", "pc", "mac"],
                "signals": ["mouse", "keyboard", "monitor stand", "webcam", "hub", "dock"],
            },
            "Audio": {
                "id": "elec-audio",
                "keywords": ["audio", "sound", "music"],
                "signals": ["headphones", "earbuds", "speaker", "microphone", "amplifier"],
            },
        },
    },
    "Office Supplies": {
        "id": "office",
        "subcategories": {
            "Desk Organization": {
                "id": "office-desk",
                "keywords": ["desk", "office", "organization", "workspace"],
                "signals": ["organizer", "tray", "holder", "stand", "caddy", "divider"],
            },
            "Writing Supplies": {
                "id": "office-writing",
                "keywords": ["writing", "pen", "pencil", "marker"],
                "signals": ["notebook", "paper", "pad", "journal", "planner"],
            },
        },
    },
    "Home & Kitchen": {
        "id": "home",
        "subcategories": {
            "Kitchen Gadgets": {
                "id": "home-kitchen-gadget",
                "keywords": ["kitchen", "cooking", "food", "chef"],
                "signals": ["utensil", "tool", "gadget", "peeler", "grater", "slicer"],
            },
            "Storage": {
                "id": "home-storage",
                "keywords": ["storage", "container", "box", "bin"],
                "signals": ["organizer", "basket", "rack", "shelf", "drawer"],
            },
        },
    },
}


# Sample products for testing categorization
TEST_PRODUCTS = [
    {
        "title": "Wireless Phone Charger Stand with LED Light",
        "description": "Fast charging wireless stand for iPhone and Samsung smartphones. Sleek design with LED indicator light. Compatible with all Qi-enabled devices.",
        "expected_category": "elec-mobile-acc",
        "challenge": "Could be miscategorized as desk organization due to 'stand'",
    },
    {
        "title": "Bamboo Desktop Organizer with Phone Holder",
        "description": "Eco-friendly bamboo desk organizer with compartments for pens, paper clips, and a built-in phone stand. Perfect for home office.",
        "expected_category": "office-desk",
        "challenge": "Contains 'phone' keyword which could trigger mobile accessories",
    },
    {
        "title": "USB-C Hub 7-in-1 Adapter for MacBook",
        "description": "Multi-port USB-C hub with HDMI, USB 3.0, SD card reader. Perfect for MacBook Pro and other USB-C laptops.",
        "expected_category": "elec-comp-acc",
        "challenge": "Straightforward - strong computer signals",
    },
    {
        "title": "Adjustable Laptop Stand Aluminum Alloy",
        "description": "Ergonomic laptop riser for better posture. Fits all laptops 10-17 inches. Aluminum construction with ventilation holes.",
        "expected_category": "elec-comp-acc",
        "challenge": "Could be confused with desk organization 'stand'",
    },
    {
        "title": "Glass Food Storage Containers 10-Pack",
        "description": "Airtight glass meal prep containers with snap-lock lids. Microwave, oven, freezer safe. BPA-free.",
        "expected_category": "home-storage",
        "challenge": "Straightforward - kitchen storage signals",
    },
    {
        "title": "Bluetooth Wireless Earbuds with Charging Case",
        "description": "True wireless earbuds with noise cancellation. 24-hour battery life with charging case. Compatible with iPhone and Android.",
        "expected_category": "elec-audio",
        "challenge": "Phone compatibility might trigger mobile accessories",
    },
    {
        "title": "Stainless Steel Vegetable Peeler Set",
        "description": "Professional kitchen peeler set with 3 blade types. Ergonomic handle, dishwasher safe.",
        "expected_category": "home-kitchen-gadget",
        "challenge": "Straightforward - clear kitchen gadget",
    },
]
