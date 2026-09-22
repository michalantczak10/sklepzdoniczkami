"""One-time maintenance command to migrate internal Django bookkeeping from
the historical app label "shop" to "sklepzdoniczkami".

IMPORTANT: run this manually against production (e.g. via Render Shell)
BEFORE deploying the code change that flips AppConfig.label to
"sklepzdoniczkami". It must run under the code version where the app is
still registered under the "shop" label, because it only touches raw
bookkeeping tables (django_migrations, django_content_type) and does not
rely on the Django app registry at all.

The command is idempotent: running it more than once, or on a database
that has already been migrated, is a safe no-op.
"""

from django.core.management.base import BaseCommand
from django.db import connection, transaction


class Command(BaseCommand):
    help = (
        "Renames internal 'shop' bookkeeping (django_migrations.app, "
        "django_content_type.app_label) to 'sklepzdoniczkami'. Run once, "
        "manually, before deploying the AppConfig.label change."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without writing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT app, name FROM django_migrations WHERE app = %s ORDER BY id",
                ["shop"],
            )
            pending_migrations = cursor.fetchall()

            cursor.execute(
                "SELECT id, app_label, model FROM django_content_type WHERE app_label = %s",
                ["shop"],
            )
            pending_content_types = cursor.fetchall()

        if not pending_migrations and not pending_content_types:
            self.stdout.write(self.style.SUCCESS(
                "Nothing to do: no 'shop' rows found in django_migrations or "
                "django_content_type. The rename was already applied."
            ))
            return

        self.stdout.write(
            f"Found {len(pending_migrations)} django_migrations row(s) and "
            f"{len(pending_content_types)} django_content_type row(s) still "
            "labeled 'shop':"
        )
        for app, name in pending_migrations:
            self.stdout.write(f"  migration: {app}.{name}")
        for content_type_id, app_label, model in pending_content_types:
            self.stdout.write(f"  content type: {app_label}.{model} (id={content_type_id})")

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run: no changes written."))
            return

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE django_migrations SET app = %s WHERE app = %s",
                    ["sklepzdoniczkami", "shop"],
                )
                migrations_updated = cursor.rowcount

                cursor.execute(
                    "UPDATE django_content_type SET app_label = %s WHERE app_label = %s",
                    ["sklepzdoniczkami", "shop"],
                )
                content_types_updated = cursor.rowcount

        self.stdout.write(self.style.SUCCESS(
            f"Renamed {migrations_updated} django_migrations row(s) and "
            f"{content_types_updated} django_content_type row(s) from 'shop' "
            "to 'sklepzdoniczkami'."
        ))
        self.stdout.write(self.style.SUCCESS(
            "You can now deploy the code change that sets AppConfig.label = "
            "'sklepzdoniczkami'."
        ))
