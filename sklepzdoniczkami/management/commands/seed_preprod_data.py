from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from sklepzdoniczkami.models import Category, Product


SAMPLE_CATALOG = (
    {
        "category": {"name": "Rośliny zielone", "slug": "preprod-rosliny-zielone"},
        "products": (
            {
                "name": "Monstera deliciosa — test",
                "slug": "preprod-monstera-deliciosa",
                "description": "Syntetyczny produkt demonstracyjny środowiska preprod.",
                "price": Decimal("49.90"),
                "stock": 12,
            },
            {
                "name": "Epipremnum aureum — test",
                "slug": "preprod-epipremnum-aureum",
                "description": "Syntetyczny produkt demonstracyjny środowiska preprod.",
                "price": Decimal("29.90"),
                "stock": 8,
            },
        ),
    },
    {
        "category": {"name": "Doniczki — preprod", "slug": "preprod-doniczki"},
        "products": (
            {
                "name": "Doniczka ceramiczna — test",
                "slug": "preprod-doniczka-ceramiczna",
                "description": "Syntetyczny produkt demonstracyjny środowiska preprod.",
                "price": Decimal("39.90"),
                "stock": 20,
            },
        ),
    },
)


class Command(BaseCommand):
    help = "Creates an idempotent synthetic product catalogue for preproduction."

    def handle(self, *args, **options):
        if settings.APP_ENV != "preprod":
            raise CommandError("This command only runs when APP_ENV=preprod.")

        created_categories = 0
        created_products = 0
        for sample in SAMPLE_CATALOG:
            category, category_created = Category.objects.get_or_create(
                slug=sample["category"]["slug"],
                defaults={"name": sample["category"]["name"]},
            )
            created_categories += int(category_created)

            for product_data in sample["products"]:
                _, product_created = Product.objects.get_or_create(
                    slug=product_data["slug"],
                    defaults={"category": category, **product_data},
                )
                created_products += int(product_created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Preprod catalogue ready: {created_categories} categories and "
                f"{created_products} synthetic products created."
            )
        )
