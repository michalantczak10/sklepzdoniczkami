import os

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

    def add_arguments(self, parser):
        parser.add_argument("--confirm-production-preview", action="store_true")

    @staticmethod
    def validate_production_database():
        database = connections["default"]
        database_settings = database.settings_dict
        expected_host = os.environ.get("PRODUCTION_DATABASE_HOST", "").strip()
        connection_options = {
            str(option).lower() for option in database_settings.get("OPTIONS", {})
        }
        if (
            database_settings["ENGINE"] != "django.db.backends.postgresql"
            or database_settings["NAME"] != PRODUCTION_DATABASE_NAME
            or database_settings["USER"] != PRODUCTION_DATABASE_USER
            or not expected_host
            or database_settings["HOST"].lower() != expected_host.lower()
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
                can_create_objects,
                can_create_schemas,
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
        if can_create_objects or can_create_schemas or any(
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
                category, category_created = Category.objects.get_or_create(
                    slug=sample["category"]["slug"],
                    defaults={"name": sample["category"]["name"]},
                )
                if not category_created and category.name != sample["category"]["name"]:
                    raise CommandError(
                        f"Production category {category.slug} already has different data."
                    )
                created_categories += int(category_created)

                for product_data in sample["products"]:
                    preview_data = {
                        **product_data,
                        "category": category,
                        "stock": 0,
                        "is_active": True,
                    }
                    product, product_created = Product.objects.get_or_create(
                        slug=product_data["slug"],
                        defaults=preview_data,
                    )
                    if not product_created:
                        conflicts = (
                            field
                            for field, value in preview_data.items()
                            if getattr(product, field) != value
                        )
                        if next(conflicts, None) is not None or product.stock != 0:
                            raise CommandError(
                                f"Production product {product.slug} has conflicting data; "
                                "no existing product was changed."
                            )
                    created_products += int(product_created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Production preview catalogue ready: {created_categories} "
                f"categories and {created_products} products created with zero stock."
            )
        )
