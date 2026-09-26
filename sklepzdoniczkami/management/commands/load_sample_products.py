import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from sklepzdoniczkami.models import Category, Product


SAMPLE_PRODUCTS = (
    {
        "name": "Doniczka ceramiczna na podstawce",
        "slug": "doniczka-ceramiczna-na-podstawce",
        "legacy_slug": "doniczka-terakotowa-na-podstawce",
        "description": "Klasyczna doniczka ceramiczna z dopasowaną podstawką.",
        "price": "39.90",
        "stock": 12,
        "category": "ceramiczne",
        "image": "pot-terracotta-1.jpg",
    },
    {
        "name": "Kolorowy zestaw doniczek plastikowych",
        "slug": "zestaw-doniczek-plastikowych",
        "legacy_slug": "zestaw-doniczek-z-terakoty",
        "description": "Lekkie doniczki w żywych kolorach, idealne na parapet i balkon.",
        "price": "59.90",
        "stock": 8,
        "category": "plastikowe",
        "image": "pot-plastic.jpg",
    },
    {
        "name": "Doniczka cementowa klasyczna",
        "slug": "doniczka-cementowa-klasyczna",
        "legacy_slug": "doniczka-gliniana-klasyczna",
        "description": "Prosta, stabilna forma o surowym charakterze do nowoczesnych wnętrz.",
        "price": "34.90",
        "stock": 10,
        "category": "cementowe",
        "image": "pot-cement.jpg",
    },
    {
        "name": "Doniczka ceramiczna szeroka",
        "slug": "doniczka-ceramiczna-szeroka",
        "legacy_slug": "doniczka-terakotowa-szeroka",
        "description": "Szeroka, jasna forma ceramiczna, która dobrze prezentuje się na parapecie.",
        "price": "49.90",
        "stock": 6,
        "category": "ceramiczne",
        "image": "pot-ceramic.jpg",
    },
    {
        "name": "Duża doniczka plastikowa ogrodowa",
        "slug": "duza-doniczka-plastikowa-ogrodowa",
        "legacy_slug": "duza-doniczka-ogrodowa",
        "description": "Lekka i pojemna doniczka do aranżacji balkonu, tarasu lub ogrodu.",
        "price": "89.00",
        "stock": 4,
        "category": "plastikowe",
        "image": "pot-plastic.jpg",
    },
)

SAMPLE_CATEGORIES = {
    "ceramiczne": "Ceramiczne",
    "plastikowe": "Plastikowe",
    "cementowe": "Cementowe",
}


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

        categories = {
            slug: Category.objects.get_or_create(slug=slug, defaults={"name": name})[0]
            for slug, name in SAMPLE_CATEGORIES.items()
        }
        for sample in SAMPLE_PRODUCTS:
            product_data = sample.copy()
            image_name = product_data.pop("image")
            category_slug = product_data.pop("category")
            legacy_slug = product_data.pop("legacy_slug")
            if legacy_slug != product_data["slug"]:
                Product.objects.filter(slug=legacy_slug).update(slug=product_data["slug"])
            Product.objects.update_or_create(
                slug=product_data["slug"],
                defaults={
                    **product_data,
                    "category": categories[category_slug],
                    "image": f"{settings.MEDIA_URL}products/{image_name}",
                    "is_active": True,
                },
            )

        self.stdout.write(self.style.SUCCESS("Loaded five sample pot products in three material categories."))
