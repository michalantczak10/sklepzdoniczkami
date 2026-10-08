from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction

from sklepzdoniczkami.models import Category, Product
from sklepzdoniczkami.sample_catalog import SAMPLE_CATALOG


ROUTING_OPTIONS = {
    "database",
    "dbname",
    "host",
    "hostaddr",
    "options",
    "password",
    "port",
    "service",
    "servicefile",
    "target_session_attrs",
    "load_balance_hosts",
    "user",
}
PRODUCTION_DATABASE_NAME = "sklepzdoniczkami_prod"
PRODUCTION_DATABASE_USER = "sklepzdoniczkami_prod_web_limited"
ELEVATED_ROLE_NAMES = {
    "neon_superuser",
    "pg_execute_server_program",
    "pg_read_all_data",
    "pg_read_server_files",
    "pg_signal_backend",
    "pg_write_all_data",
    "pg_write_server_files",
}


class Command(BaseCommand):
    help = "Adds the synthetic preview catalogue to production with zero stock."

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

    def add_arguments(self, parser):
        parser.add_argument("--confirm-production-preview", action="store_true")

    @staticmethod
    def validate_production_database():
        database = connections["default"]
        database_settings = database.settings_dict
        connection_options = {
            str(option).lower() for option in database_settings.get("OPTIONS", {})
        }
        if (
            database_settings["ENGINE"] != "django.db.backends.postgresql"
            or database_settings["NAME"] != PRODUCTION_DATABASE_NAME
            or database_settings["USER"] != PRODUCTION_DATABASE_USER
            or database_settings["HOST"] not in {"127.0.0.1", "localhost", "::1"}
            or database_settings.get("PORT") not in {None, "", 5432, "5432"}
            or connection_options.intersection(ROUTING_OPTIONS)
        ):
            raise CommandError(
                "Refusing to write outside the pinned production database."
            )

        with database.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_user, current_schema()")
            actual_database, actual_user, actual_schema = cursor.fetchone()
            cursor.execute(
                "SELECT EXISTS ("
                "SELECT 1 FROM pg_namespace AS namespace "
                "WHERE left(namespace.nspname, 3) <> 'pg_' "
                "AND namespace.nspname <> 'information_schema' "
                "AND has_schema_privilege(current_user, namespace.oid, 'CREATE')"
                "), "
                "has_database_privilege(current_user, current_database(), 'CREATE'), "
                "rolcreatedb, rolcreaterole, rolsuper, rolreplication, rolbypassrls, "
                "EXISTS ("
                "SELECT 1 FROM pg_roles AS granted_role "
                "WHERE granted_role.rolname <> current_user "
                "AND pg_has_role(current_user, granted_role.oid, 'MEMBER') "
                "AND (granted_role.rolsuper OR granted_role.rolcreatedb "
                "OR granted_role.rolcreaterole OR granted_role.rolreplication "
                "OR granted_role.rolbypassrls "
                "OR granted_role.rolname::text = ANY(%s))"
                ") FROM pg_roles WHERE rolname = current_user",
                [list(ELEVATED_ROLE_NAMES)],
            )
            (
                can_create_schema_objects,
                can_create_database,
                can_create_databases,
                can_create_roles,
                is_superuser,
                can_replicate,
                can_bypass_row_security,
                has_elevated_membership,
            ) = cursor.fetchone()
        if (
            actual_database != PRODUCTION_DATABASE_NAME
            or actual_user != PRODUCTION_DATABASE_USER
            or actual_schema != "public"
        ):
            raise CommandError(
                "The active database connection does not match the production target."
            )
        if can_create_schema_objects or can_create_database or any(
            (
                can_create_databases,
                can_create_roles,
                is_superuser,
                can_replicate,
                can_bypass_row_security,
                has_elevated_membership,
            )
        ):
            raise CommandError(
                "The production runtime role has excessive database privileges."
            )

    def handle(self, *args, **options):
        if settings.APP_ENV != "production":
            raise CommandError("This command only runs when APP_ENV=production.")
        if not options["confirm_production_preview"]:
            raise CommandError(
                "Pass --confirm-production-preview to add demo products to production."
            )

        self.validate_production_database()

        created_categories = 0
        created_products = 0
        with transaction.atomic():
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
                            f"Production category {category.slug} has conflicting data."
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
                            "Both canonical and legacy production products exist for "
                            f"{product_data['slug']}."
                        )
                    if product is None:
                        product = legacy_product
                    preview_data = {
                        key: value
                        for key, value in product_data.items()
                        if key != "legacy_slug"
                    }
                    preview_data.update({
                        "category": category,
                        "stock": 0,
                        "is_active": True,
                    })
                    if product is None:
                        Product.objects.create(**preview_data)
                        created_products += 1
                        continue

                    if (
                        product.slug != product_data["slug"]
                        and Product.objects.filter(slug=product_data["slug"]).exists()
                    ):
                        raise CommandError(
                            f"Production product slug {product_data['slug']} "
                            "already exists."
                        )
                    if product.stock != 0:
                        raise CommandError(
                            f"Production product {product.slug} has nonzero stock; "
                            "it was not changed."
                        )
                    expected = {
                        "category": category,
                        "name": product_data["name"],
                        "slug": product_data["slug"],
                        "description": product_data["description"],
                        "image": product_data["image"],
                        "is_active": True,
                        "stock": 0,
                    }
                    if product.slug == product_data["slug"] and any(
                        getattr(product, field) != value
                        for field, value in expected.items()
                    ):
                        raise CommandError(
                            f"Production product {product.slug} has conflicting data; "
                            "it was not changed."
                        )
                    for field, value in expected.items():
                        if getattr(product, field) != value:
                            setattr(product, field, value)
                    product.save(
                        update_fields=[
                            "category",
                            "name",
                            "slug",
                            "description",
                            "image",
                            "is_active",
                            "stock",
                        ]
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"Production preview catalogue ready: {created_categories} "
                f"categories and {created_products} products created with zero stock."
            )
        )
