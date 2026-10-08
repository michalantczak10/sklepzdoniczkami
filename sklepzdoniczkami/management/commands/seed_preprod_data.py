from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from sklepzdoniczkami.models import Category, Product
from sklepzdoniczkami.sample_catalog import SAMPLE_CATALOG


class Command(BaseCommand):
    help = "Creates an idempotent synthetic product catalogue for preproduction."

    @staticmethod
    def validate_legacy_category(category, sample):
        sample_product_slugs = {
            slug
            for product in sample["products"]
            for slug in (product["slug"], product.get("legacy_slug"))
            if slug
        }
        if Product.objects.filter(category=category).exclude(
            slug__in=sample_product_slugs
        ).exists():
            raise CommandError(
                f"Legacy category {category.slug} contains unrelated products."
            )

    def handle(self, *args, **options):
        if settings.APP_ENV != "preprod":
            raise CommandError("This command only runs when APP_ENV=preprod.")

        created_categories = 0
        created_products = 0
        for sample in SAMPLE_CATALOG:
            category_data = sample["category"]
            category = Category.objects.filter(slug=category_data["slug"]).first()
            legacy_category = Category.objects.filter(
                slug=category_data.get("legacy_slug")
            ).first()
            if category is None:
                category = legacy_category
            if category is not None and category.slug == category_data["slug"]:
                if category.name != category_data["name"]:
                    raise CommandError(
                        f"Preprod category {category.slug} has conflicting data."
                    )
            elif category is not None:
                self.validate_legacy_category(category, sample)
            if (
                category is not None
                and legacy_category is not None
                and legacy_category.pk != category.pk
            ):
                self.validate_legacy_category(legacy_category, sample)
                sample_product_slugs = {
                    slug
                    for product in sample["products"]
                    for slug in (product["slug"], product.get("legacy_slug"))
                    if slug
                }
                Product.objects.filter(
                    category=legacy_category,
                    slug__in=sample_product_slugs,
                ).update(category=category)
                legacy_category.delete()
            if category is None:
                category = Category.objects.create(
                    name=category_data["name"],
                    slug=category_data["slug"],
                )
                created_categories += 1
            else:
                if (
                    category.slug != category_data["slug"]
                    and Category.objects.filter(slug=category_data["slug"]).exists()
                ):
                    raise CommandError(
                        f"Category slug {category_data['slug']} is already in use."
                    )
                category.name = category_data["name"]
                category.slug = category_data["slug"]
                category.save(update_fields=["name", "slug"])

            for product_data in sample["products"]:
                product = Product.objects.filter(slug=product_data["slug"]).first()
                legacy_product = Product.objects.filter(
                    slug=product_data.get("legacy_slug")
                ).first()
                if product is not None and legacy_product is not None:
                    raise CommandError(
                        f"Both canonical and legacy products exist for {product_data['slug']}."
                    )
                if product is None:
                    product = legacy_product
                if product is None:
                    Product.objects.create(
                        category=category,
                        **{
                            key: value
                            for key, value in product_data.items()
                            if key != "legacy_slug"
                        },
                        is_active=True,
                    )
                    created_products += 1
                    continue

                if (
                    product.slug != product_data["slug"]
                    and Product.objects.filter(slug=product_data["slug"]).exists()
                ):
                    raise CommandError(
                        f"Product slug {product_data['slug']} is already in use."
                    )
                product.category = category
                product.name = product_data["name"]
                product.slug = product_data["slug"]
                product.description = product_data["description"]
                product.image = product_data["image"]
                product.is_active = True
                product.save(
                    update_fields=[
                        "category",
                        "name",
                        "slug",
                        "description",
                        "image",
                        "is_active",
                    ]
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Preprod catalogue ready: {created_categories} categories and "
                f"{created_products} synthetic products created."
            )
        )
