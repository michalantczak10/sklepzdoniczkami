import os

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import connections, transaction


class Command(BaseCommand):
    help = "Creates the first production superuser from a protected password secret."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--email", required=True)
        parser.add_argument("--confirm-production-database", required=True)

    def validate_production_database(self):
        database = connections["default"]
        database_settings = database.settings_dict
        expected_host = os.environ.get("PRODUCTION_DATABASE_HOST", "").strip()
        if (
            database_settings["ENGINE"] != "django.db.backends.postgresql"
            or database_settings["NAME"] != "sklepzdoniczkami_prod"
            or database_settings["USER"] != "sklepzdoniczkami_prod_web_limited"
            or not expected_host
            or database_settings["HOST"].lower() != expected_host.lower()
        ):
            raise CommandError(
                "Refusing to create an administrator outside the pinned production database."
            )

        with database.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_user")
            actual_database, actual_user = cursor.fetchone()
        if (
            actual_database != "sklepzdoniczkami_prod"
            or actual_user != "sklepzdoniczkami_prod_web_limited"
        ):
            raise CommandError(
                "The active database connection does not match the production target."
            )

    def handle(self, *args, **options):
        if settings.APP_ENV != "production":
            raise CommandError("This command only runs when APP_ENV=production.")
        if options["confirm_production_database"] != "sklepzdoniczkami_prod":
            raise CommandError("The production database confirmation did not match.")

        username = options["username"]
        email = options["email"]
        password = os.environ.get("INITIAL_ADMIN_PASSWORD", "")
        if not username.strip():
            raise CommandError("Administrator username must not be empty.")
        if not password or len(password) < 16:
            raise CommandError(
                "INITIAL_ADMIN_PASSWORD must be set and contain at least 16 characters."
            )

        candidate = User(username=username, email=email)
        try:
            if len(username) > 150:
                raise ValidationError("Username is too long.")
            UnicodeUsernameValidator()(username)
            validate_email(email)
            validate_password(password, user=candidate)
        except ValidationError as exc:
            raise CommandError(
                "Administrator details or password did not pass validation."
            ) from exc

        self.validate_production_database()

        with transaction.atomic():
            if User.objects.filter(is_superuser=True).exists():
                raise CommandError(
                    "A production superuser already exists; refusing to create another."
                )
            if User.objects.filter(username=username).exists():
                raise CommandError(
                    "That username already exists; refusing to modify the account."
                )
            User.objects.create_superuser(
                username=username,
                email=email,
                password=password,
            )

        self.stdout.write(self.style.SUCCESS("Initial production superuser created."))
