import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from sklepzdoniczkami.models import Category, Product


SAMPLE_PRODUCTS = (
    {
        "name": "Doniczka terakotowa na podstawce",
        "slug": "doniczka-terakotowa-na-podstawce",
        "description": "Klasyczna doniczka z naturalnej terakoty z dopasowaną podstawką.",
        "price": "39.90",
        "stock": 12,
        "image": "pot-terracotta-2.jpg",
    },
    {
        "name": "Zestaw doniczek z terakoty",
        "slug": "zestaw-doniczek-z-terakoty",
        "description": "Zestaw doniczek z terakoty w kilku praktycznych rozmiarach.",
        "price": "59.90",
        "stock": 8,
        "image": "pot-terracotta-1.jpg",
    },
    {
        "name": "Doniczka gliniana klasyczna",
        "slug": "doniczka-gliniana-klasyczna",
        "description": "Ponadczasowa doniczka z gliny do domu lub na zadaszony taras.",
        "price": "34.90",
        "stock": 10,
        "image": "pot-terracotta-3.jpg",
    },
    {
        "name": "Doniczka terakotowa szeroka",
        "slug": "doniczka-terakotowa-szeroka",
        "description": "Szeroka forma z terakoty, która dobrze prezentuje się na parapecie.",
        "price": "49.90",
        "stock": 6,
        "image": "pot-terracotta-2.jpg",
    },
    {
        "name": "Duża doniczka ogrodowa",
        "slug": "duza-doniczka-ogrodowa",
        "description": "Pojemna doniczka do aranżacji balkonu, tarasu lub ogrodu.",
        "price": "89.00",
        "stock": 4,
        "image": "pot-terracotta-3.jpg",
    },
)


class Command(BaseCommand):
    help = "Adds five sample pot products and copies their photos for local development."

    def handle(self, *args, **options):
        if settings.APP_ENV != "development":
            raise CommandError("Sample products can only be loaded when APP_ENV=development.")

        source_dir = Path(settings.BASE_DIR) / "docs" / "sample-images"
        media_dir = Path(settings.MEDIA_ROOT) / "products"
        media_dir.mkdir(parents=True, exist_ok=True)

        for filename in {product["image"] for product in SAMPLE_PRODUCTS}:
            source = source_dir / filename
            if not source.is_file():
                raise CommandError(f"Sample product image is missing: {source}")
            shutil.copyfile(source, media_dir / filename)

        category, _ = Category.objects.get_or_create(
            slug="doniczki",
            defaults={"name": "Doniczki"},
        )
        for sample in SAMPLE_PRODUCTS:
            product_data = sample.copy()
            image_name = product_data.pop("image")
            Product.objects.update_or_create(
                slug=product_data["slug"],
                defaults={
                    **product_data,
                    "category": category,
                    "image": f"{settings.MEDIA_URL}products/{image_name}",
                    "is_active": True,
                },
            )

        self.stdout.write(self.style.SUCCESS("Loaded five sample pot products."))
