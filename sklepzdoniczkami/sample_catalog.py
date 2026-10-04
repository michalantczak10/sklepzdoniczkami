from decimal import Decimal


SAMPLE_CATALOG = (
    {
        "category": {
            "name": "Rośliny zielone",
            "slug": "rosliny-zielone",
            "legacy_slug": "preprod-rosliny-zielone",
            "description": "Zielone akcenty, które ożywiają domową przestrzeń.",
        },
        "category_image": "sklepzdoniczkami/img/products/pot-terracotta-3.jpg",
        "products": (
            {
                "name": "Monstera deliciosa",
                "slug": "monstera-deliciosa",
                "legacy_slug": "preprod-monstera-deliciosa",
                "description": (
                    "Monstera deliciosa o charakterystycznych, głęboko powcinanych "
                    "liściach. Wyrazisty akcent do jasnych i przestronnych wnętrz."
                ),
                "price": Decimal("49.90"),
                "stock": 12,
                "image": "/static/sklepzdoniczkami/img/products/pot-ceramic.jpg",
            },
            {
                "name": "Epipremnum złociste",
                "slug": "epipremnum-zlociste",
                "legacy_slug": "preprod-epipremnum-aureum",
                "description": (
                    "Pnąca roślina o sercowatych liściach, która wnosi do wnętrza "
                    "naturalną zieleń i dobrze prezentuje się na półce."
                ),
                "price": Decimal("29.90"),
                "stock": 8,
                "image": "/static/sklepzdoniczkami/img/products/pot-terracotta-3.jpg",
            },
        ),
    },
    {
        "category": {
            "name": "Doniczki",
            "slug": "doniczki",
            "legacy_slug": "preprod-doniczki",
            "description": "Formy i kolory, które dopełniają aranżację roślin.",
        },
        "category_image": "sklepzdoniczkami/img/products/pot-terracotta-1.jpg",
        "products": (
            {
                "name": "Doniczka ceramiczna",
                "slug": "doniczka-ceramiczna",
                "legacy_slug": "preprod-doniczka-ceramiczna",
                "description": (
                    "Ceramiczna doniczka o spokojnej, ponadczasowej formie. "
                    "Naturalny odcień dobrze komponuje się z zielenią roślin."
                ),
                "price": Decimal("39.90"),
                "stock": 20,
                "image": "/static/sklepzdoniczkami/img/products/pot-ceramic.jpg",
            },
        ),
    },
)
