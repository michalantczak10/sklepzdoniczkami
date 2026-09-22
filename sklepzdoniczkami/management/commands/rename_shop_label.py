"""One-time maintenance command to migrate internal Django bookkeeping from
the historical app label "shop" to "sklepzdoniczkami".

This command is safe to run automatically as part of every deploy (it is
invoked from render.yaml's buildCommand, before `migrate`): it only touches
raw bookkeeping tables (django_migrations, django_content_type) via plain
SQL, is idempotent, and no-ops cleanly both when the rename was already
applied and on a brand-new database where these tables do not exist yet
(e.g. before the very first `migrate` has ever run).
"""

from django.core.management.base import BaseCommand
from django.db import DatabaseError, connection, transaction


def _table_exists(table_name):
    return table_name in connection.introspection.table_names()


class Command(BaseCommand):
    help = (
        "Renames internal 'shop' bookkeeping (django_migrations.app, "
        "django_content_type.app_label) to 'sklepzdoniczkami'. Safe to run "
        "repeatedly; no-ops once already applied or on a fresh database."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without writing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if not _table_exists("django_migrations") or not _table_exists("django_content_type"):
            self.stdout.write(self.style.SUCCESS(
                "Nothing to do: bookkeeping tables do not exist yet "
                "(fresh database, first migrate hasn't run)."
            ))
            return

        try:
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
        except DatabaseError:
            self.stdout.write(self.style.SUCCESS(
                "Nothing to do: bookkeeping tables are not queryable yet "
                "(fresh database)."
            ))
            return

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
