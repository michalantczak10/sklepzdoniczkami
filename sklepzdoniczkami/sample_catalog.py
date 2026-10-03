from decimal import Decimal


SAMPLE_CATALOG = (
    {
        "category": {"name": "Rośliny zielone", "slug": "preprod-rosliny-zielone"},
        "category_image": "sklepzdoniczkami/img/products/pot-terracotta-3.jpg",
        "products": (
            {
                "name": "Monstera deliciosa — test",
                "slug": "preprod-monstera-deliciosa",
                "description": "Syntetyczny produkt demonstracyjny środowiska preprod.",
                "price": Decimal("49.90"),
                "stock": 12,
                "image": "/static/sklepzdoniczkami/img/products/pot-ceramic.jpg",
            },
            {
                "name": "Epipremnum aureum — test",
                "slug": "preprod-epipremnum-aureum",
                "description": "Syntetyczny produkt demonstracyjny środowiska preprod.",
                "price": Decimal("29.90"),
                "stock": 8,
                "image": "/static/sklepzdoniczkami/img/products/pot-terracotta-3.jpg",
            },
        ),
    },
    {
        "category": {"name": "Doniczki — preprod", "slug": "preprod-doniczki"},
        "category_image": "sklepzdoniczkami/img/products/pot-terracotta-1.jpg",
        "products": (
            {
                "name": "Doniczka ceramiczna — test",
                "slug": "preprod-doniczka-ceramiczna",
                "description": "Syntetyczny produkt demonstracyjny środowiska preprod.",
                "price": Decimal("39.90"),
                "stock": 20,
                "image": "/static/sklepzdoniczkami/img/products/pot-ceramic.jpg",
            },
        ),
    },
)
