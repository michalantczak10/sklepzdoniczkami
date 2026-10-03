from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from sklepzdoniczkami.models import Category, Product
from sklepzdoniczkami.sample_catalog import SAMPLE_CATALOG


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
                product, product_created = Product.objects.get_or_create(
                    slug=product_data["slug"],
                    defaults={"category": category, **product_data, "is_active": True},
                )
                created_products += int(product_created)
                if not product_created and product.image != product_data["image"]:
                    product.image = product_data["image"]
                    product.save(update_fields=["image"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Preprod catalogue ready: {created_categories} categories and "
                f"{created_products} synthetic products created."
            )
        )
