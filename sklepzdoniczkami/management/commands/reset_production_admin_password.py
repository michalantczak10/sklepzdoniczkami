import os

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from .bootstrap_first_admin import Command as BootstrapFirstAdminCommand


class Command(BaseCommand):
    help = "Resets the password of the only production superuser from a protected secret."

    def add_arguments(self, parser):
        parser.add_argument("--confirm-production-database", required=True)

    def handle(self, *args, **options):
        if settings.APP_ENV != "production":
            raise CommandError("This command only runs when APP_ENV=production.")
        if options["confirm_production_database"] != "sklepzdoniczkami_prod":
            raise CommandError("The production database confirmation did not match.")

        password = os.environ.get("RESET_ADMIN_PASSWORD", "")
        if not password or len(password) < 16:
            raise CommandError(
                "RESET_ADMIN_PASSWORD must be set and contain at least 16 characters."
            )

        BootstrapFirstAdminCommand().validate_production_database()

        administrators = User.objects.filter(is_superuser=True)
        if administrators.count() != 1:
            raise CommandError(
                "Password reset requires exactly one production superuser."
            )
        administrator = administrators.get()
        if not administrator.is_active:
            raise CommandError("The production superuser is inactive.")
        try:
            validate_password(password, user=administrator)
        except ValidationError as exc:
            raise CommandError(
                "The new administrator password did not pass validation."
            ) from exc

        with transaction.atomic():
            administrator.set_password(password)
            administrator.save(update_fields=["password"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Production administrator password reset for username: "
                f"{administrator.username}"
            )
        )
