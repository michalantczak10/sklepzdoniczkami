from decimal import Decimal


SAMPLE_CATALOG = (
    {
        "category": {
            "name": "Doniczki",
            "slug": "doniczki",
            "legacy_slug": "preprod-doniczki",
            "description": "Doniczki w różnych formach, kolorach i materiałach.",
        },
        "category_image": "sklepzdoniczkami/img/products/pot-terracotta-1.jpg",
        "products": (
            {
                "name": "Doniczka ceramiczna",
                "slug": "doniczka-ceramiczna",
                "legacy_slug": "preprod-doniczka-ceramiczna",
                "description": (
                    "Ceramiczna doniczka o ponadczasowej formie i naturalnym odcieniu."
                ),
                "price": Decimal("39.90"),
                "stock": 20,
                "image": "/static/sklepzdoniczkami/img/products/pot-ceramic.jpg",
            },
        ),
    },
)
