from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from sklepzdoniczkami.models import Category, Product


SAMPLE_PRODUCTS = (
    {
        "name": "Doniczka betonowa Kamień",
        "slug": "doniczka-betonowa-kamien",
        "description": "Surowa, jasnoszara forma z delikatną fakturą inspirowaną naturalnym kamieniem.",
        "price": "49.90",
        "stock": 8,
        "category": "betonowe",
        "image": "products/doniczka-betonowa-kamien.svg",
    },
    {
        "name": "Doniczka betonowa Loft",
        "slug": "doniczka-betonowa-loft",
        "description": "Geometryczna doniczka w grafitowym odcieniu do nowoczesnych wnętrz.",
        "price": "34.90",
        "stock": 10,
        "category": "betonowe",
        "image": "products/doniczka-betonowa-loft.svg",
    },
    {
        "name": "Doniczka drewniana Dębowa",
        "slug": "doniczka-drewniana-debowa",
        "description": "Ciepły, dębowy wygląd i prosta forma pasująca do naturalnych aranżacji.",
        "price": "69.90",
        "stock": 6,
        "category": "drewniane",
        "image": "products/doniczka-drewniana-debowa.svg",
    },
    {
        "name": "Doniczka drewniana Natural",
        "slug": "doniczka-drewniana-natural",
        "description": "Jasne drewno i oszczędny kształt do domowych roślin ozdobnych.",
        "price": "44.90",
        "stock": 10,
        "category": "drewniane",
        "image": "products/doniczka-drewniana-natural.svg",
    },
    {
        "name": "Doniczka plastikowa balkonowa",
        "slug": "doniczka-plastikowa-balkonowa",
        "description": "Lekka skrzynka balkonowa w spokojnym, szałwiowym kolorze.",
        "price": "19.90",
        "stock": 15,
        "category": "plastikowe",
        "image": "products/doniczka-plastikowa-balkonowa.svg",
    },
    {
        "name": "Doniczka plastikowa samonawadniająca",
        "slug": "doniczka-plastikowa-samonawadniajaca",
        "description": "Praktyczna forma z osobnym zbiornikiem na wodę do codziennej pielęgnacji.",
        "price": "34.90",
        "stock": 7,
        "category": "plastikowe",
        "image": "products/doniczka-plastikowa-samonawadniajaca.svg",
    },
    {
        "name": "Duża doniczka plastikowa ogrodowa",
        "slug": "duza-doniczka-plastikowa-ogrodowa",
        "legacy_slugs": ("duza-doniczka-ogrodowa",),
        "description": "Lekka i pojemna doniczka do aranżacji balkonu, tarasu lub ogrodu.",
        "price": "89.00",
        "stock": 4,
        "category": "plastikowe",
        "image": "products/duza-doniczka-plastikowa-ogrodowa.svg",
    },
    {
        "name": "Kolorowy zestaw doniczek plastikowych",
        "slug": "zestaw-doniczek-plastikowych",
        "legacy_slugs": ("zestaw-doniczek-z-terakoty",),
        "description": "Lekkie doniczki w żywych kolorach, idealne na parapet i balkon.",
        "price": "59.90",
        "stock": 8,
        "category": "plastikowe",
        "image": "products/zestaw-doniczek-plastikowych.svg",
    },
)

SAMPLE_CATEGORIES = {
    "betonowe": "Betonowe",
    "drewniane": "Drewniane",
    "plastikowe": "Plastikowe",
}

RETIRED_SAMPLE_SLUGS = (
    "doniczka-terakotowa-na-podstawce",
    "doniczka-ceramiczna-na-podstawce",
    "doniczka-gliniana-klasyczna",
    "doniczka-cementowa-klasyczna",
    "doniczka-terakotowa-szeroka",
    "doniczka-ceramiczna-szeroka",
    "doniczka-ceramiczna-plytka",
    "doniczka-betonowa-mini",
    "doniczka-zewnetrzna-duza",
)


class Command(BaseCommand):
    help = "Loads eight sample pot products and their original SVG illustrations for development."

    def handle(self, *args, **options):
        if settings.APP_ENV != "development":
            raise CommandError("Sample products can only be loaded when APP_ENV=development.")

        static_dir = Path(settings.BASE_DIR) / "sklepzdoniczkami" / "static"
        for sample in SAMPLE_PRODUCTS:
            image_path = static_dir / "sklepzdoniczkami" / "img" / sample["image"]
            if not image_path.is_file():
                raise CommandError(f"Sample product illustration is missing: {image_path}")

        with transaction.atomic():
            categories = {
                slug: Category.objects.update_or_create(
                    slug=slug, defaults={"name": name}
                )[0]
                for slug, name in SAMPLE_CATEGORIES.items()
            }
            Product.objects.filter(slug__in=RETIRED_SAMPLE_SLUGS).update(
                is_active=False,
                stock=0,
            )
            for sample in SAMPLE_PRODUCTS:
                product_data = sample.copy()
                image_name = product_data.pop("image")
                category_slug = product_data.pop("category")
                legacy_slugs = product_data.pop("legacy_slugs", ())
                for legacy_slug in legacy_slugs:
                    legacy_product = Product.objects.filter(slug=legacy_slug).first()
                    if legacy_product:
                        slug_taken = Product.objects.filter(slug=product_data["slug"]).exists()
                        if slug_taken:
                            legacy_product.is_active = False
                            legacy_product.stock = 0
                            legacy_product.save(update_fields=["is_active", "stock"])
                        else:
                            legacy_product.slug = product_data["slug"]
                            legacy_product.save(update_fields=["slug"])
                Product.objects.update_or_create(
                    slug=product_data["slug"],
                    defaults={
                        **product_data,
                        "category": categories[category_slug],
                        "image": f"{settings.STATIC_URL}sklepzdoniczkami/img/{image_name}",
                        "is_active": True,
                    },
                )

        self.stdout.write(
            self.style.SUCCESS(
                "Loaded eight sample pot products across concrete, wood, and plastic categories."
            )
        )
