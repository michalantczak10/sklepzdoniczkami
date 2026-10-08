#!/usr/bin/env python3
"""Verify and restore a GitHub Actions production database backup locally."""

import argparse
import base64
import getpass
import hashlib
import hmac
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from dotenv import dotenv_values

if __package__:
    from scripts.postgres_utils import connection_parts, postgres_environment
else:
    from postgres_utils import connection_parts, postgres_environment


EXPECTED_DATABASE = "sklepzdoniczkami_prod"
MIGRATION_DATABASE_USER = "sklepzdoniczkami_prod"
MIGRATION_SYSTEM_USER = "sklepzdoniczkami-migrator"
RUNTIME_DATABASE_USER = "sklepzdoniczkami_prod_web_limited"
EXPECTED_FILES = {
    "backup.dump.enc",
    "backup.dump.enc.hmac",
    "backup.hmac.keyid",
}
MIGRATION_CONFIG_FILE = Path("/etc/sklepzdoniczkami/migration.env")
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PRIVILEGE_SQL = f"""
REVOKE ALL PRIVILEGES ON DATABASE {EXPECTED_DATABASE} FROM PUBLIC;
REVOKE CREATE, TEMPORARY ON DATABASE {EXPECTED_DATABASE} FROM {RUNTIME_DATABASE_USER};
GRANT CONNECT ON DATABASE {EXPECTED_DATABASE} TO {RUNTIME_DATABASE_USER};
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM {RUNTIME_DATABASE_USER};
GRANT USAGE ON SCHEMA public TO {RUNTIME_DATABASE_USER};
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {RUNTIME_DATABASE_USER};
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public
    TO {RUNTIME_DATABASE_USER};
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {RUNTIME_DATABASE_USER};
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public
    TO {RUNTIME_DATABASE_USER};
ALTER DEFAULT PRIVILEGES FOR ROLE {MIGRATION_DATABASE_USER} IN SCHEMA public
    REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE {MIGRATION_DATABASE_USER} IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {RUNTIME_DATABASE_USER};
ALTER DEFAULT PRIVILEGES FOR ROLE {MIGRATION_DATABASE_USER} IN SCHEMA public
    REVOKE ALL ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE {MIGRATION_DATABASE_USER} IN SCHEMA public
    GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {RUNTIME_DATABASE_USER};
"""


def read_backup_package(package_path, destination):
    with tarfile.open(package_path, mode="r:gz") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        if len(members) != len(EXPECTED_FILES) or set(names) != EXPECTED_FILES:
            raise ValueError("Backup archive has an unexpected file set.")
        for member in members:
            if not member.isfile() or member.name not in EXPECTED_FILES:
                raise ValueError("Backup archive contains an unsafe file entry.")
            if member.name != "backup.dump.enc" and member.size > 128:
                raise ValueError("Backup integrity metadata is unexpectedly large.")
            source = archive.extractfile(member)
            if source is None:
                raise ValueError("Could not read a backup archive entry.")
            with source, (destination / member.name).open("wb") as output:
                shutil.copyfileobj(source, output)


def verify_and_decrypt(directory, encryption_key, hmac_key):
    try:
        hmac_key_bytes = base64.b64decode(hmac_key, validate=True)
    except ValueError as error:
        raise ValueError("The backup HMAC key must be valid base64.") from error
    if not encryption_key or not hmac_key_bytes:
        raise ValueError("Both backup keys must be non-empty.")

    key_id = hashlib.sha256(hmac_key_bytes).hexdigest()[:8]
    recorded_key_id = (directory / "backup.hmac.keyid").read_text(
        encoding="ascii"
    ).strip()
    if not hmac.compare_digest(key_id, recorded_key_id):
        raise ValueError("The backup HMAC key identifier does not match.")

    encrypted_dump = directory / "backup.dump.enc"
    mac = hmac.new(hmac_key_bytes, digestmod=hashlib.sha256)
    with encrypted_dump.open("rb") as backup_file:
        for chunk in iter(lambda: backup_file.read(1024 * 1024), b""):
            mac.update(chunk)
    expected_mac = mac.hexdigest()
    recorded_mac = (directory / "backup.dump.enc.hmac").read_text(
        encoding="ascii"
    ).strip()
    if not hmac.compare_digest(expected_mac, recorded_mac):
        raise ValueError("The backup HMAC verification failed.")

    decrypted_dump = directory / "backup.dump"
    environment = os.environ.copy()
    environment["BACKUP_ENCRYPTION_KEY"] = encryption_key
    subprocess.run(
        [
            "openssl",
            "enc",
            "-d",
            "-aes-256-cbc",
            "-pbkdf2",
            "-salt",
            "-in",
            str(encrypted_dump),
            "-out",
            str(decrypted_dump),
            "-pass",
            "env:BACKUP_ENCRYPTION_KEY",
        ],
        env=environment,
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        ["pg_restore", "--list", str(decrypted_dump)],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
    )
    return decrypted_dump


def verify_local_target(configuration):
    database_url = configuration.get("DATABASE_URL_PRODUCTION")
    if configuration.get("APP_ENV") != "production":
        raise ValueError("The local environment must be APP_ENV=production.")
    if configuration.get("DATABASE_NAME_PRODUCTION") != EXPECTED_DATABASE:
        raise ValueError("The configured target must be sklepzdoniczkami_prod.")
    if not database_url:
        raise ValueError("DATABASE_URL_PRODUCTION is missing from the private config.")
    connection = connection_parts(database_url)
    if (
        connection["dbname"] != EXPECTED_DATABASE
        or connection["host"] not in {"127.0.0.1", "localhost", "::1"}
        or connection["port"] != 5432
        or connection["user"] != MIGRATION_DATABASE_USER
    ):
        raise ValueError("Refusing to restore to a non-local or unexpected database.")
    return connection


def migration_command(
    repository_root=REPOSITORY_ROOT, config_file=MIGRATION_CONFIG_FILE
):
    return [
        "runuser",
        "-u",
        MIGRATION_SYSTEM_USER,
        "--",
        "env",
        f"DJANGO_ENV_FILE={config_file}",
        "DJANGO_SETTINGS_MODULE=config.settings",
        str(repository_root / ".venv/bin/python"),
        str(repository_root / "manage.py"),
        "migrate",
        "--noinput",
    ]


def grant_runtime_privileges(environment):
    subprocess.run(
        [
            "psql",
            "--set=ON_ERROR_STOP=1",
            f"--dbname={EXPECTED_DATABASE}",
            f"--command={RUNTIME_PRIVILEGE_SQL}",
        ],
        env=environment,
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
    )


def verify_restored_data(connection):
    try:
        import psycopg2
    except ImportError as error:
        raise RuntimeError("Install the project requirements before restoring.") from error
    try:
        with psycopg2.connect(**connection, connect_timeout=5) as database:
            with database.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM auth_user")
                row = cursor.fetchone()
                if row is None:
                    raise ValueError("Could not read the restored user count.")
                users = row[0]
                cursor.execute("SELECT COUNT(*) FROM sklepzdoniczkami_product")
                row = cursor.fetchone()
                if row is None:
                    raise ValueError("Could not read the restored product count.")
                products = row[0]
                cursor.execute("SELECT COUNT(*) FROM sklepzdoniczkami_order")
                row = cursor.fetchone()
                if row is None:
                    raise ValueError("Could not read the restored order count.")
                orders = row[0]
    except psycopg2.Error as error:
        raise RuntimeError("Could not verify restored PostgreSQL data.") from error
    return users, products, orders


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Verify the HMAC and decrypt a GitHub Actions database backup, then "
            "restore it to the isolated local production database."
        )
    )
    parser.add_argument(
        "package", type=Path, help="Path to the downloaded encrypted .tgz package"
    )
    arguments = parser.parse_args()

    if os.geteuid() != 0:
        parser.error("Run with sudo so the script can stop and start the systemd service.")
    if not MIGRATION_CONFIG_FILE.is_file():
        parser.error(f"Private migration config not found: {MIGRATION_CONFIG_FILE}")
    if not arguments.package.is_file():
        parser.error("The encrypted backup package does not exist.")

    configuration = dotenv_values(MIGRATION_CONFIG_FILE)
    try:
        connection = verify_local_target(configuration)
        encryption_key = getpass.getpass("Backup encryption key: ")
        hmac_key = getpass.getpass("Backup HMAC key (base64): ")
        with tempfile.TemporaryDirectory(prefix="sklep-backup-restore-") as temporary:
            working_directory = Path(temporary)
            read_backup_package(arguments.package, working_directory)
            decrypted_dump = verify_and_decrypt(
                working_directory, encryption_key, hmac_key
            )
            target = postgres_environment(connection)

            print("Backup integrity and PostgreSQL archive checks passed.")
            confirmation = input(
                f"Type RESTORE {EXPECTED_DATABASE} to replace the local database: "
            )
            if confirmation != f"RESTORE {EXPECTED_DATABASE}":
                raise ValueError("Restore cancelled; the local database was not changed.")

            subprocess.run(["systemctl", "stop", "sklepzdoniczkami.service"], check=True)
            try:
                subprocess.run(
                    [
                        "pg_restore",
                        "--clean",
                        "--if-exists",
                        "--no-owner",
                        "--no-privileges",
                        "--exit-on-error",
                        f"--dbname={EXPECTED_DATABASE}",
                        str(decrypted_dump),
                    ],
                    env=target,
                    check=True,
                    stdin=subprocess.DEVNULL,
                )
                grant_runtime_privileges(target)
                subprocess.run(
                    migration_command(),
                    cwd=REPOSITORY_ROOT,
                    check=True,
                    stdin=subprocess.DEVNULL,
                )
                users, products, orders = verify_restored_data(connection)
            except (
                OSError,
                RuntimeError,
                ValueError,
                subprocess.CalledProcessError,
            ):
                print(
                    "Restore did not finish successfully; the shop remains stopped. "
                    "Inspect the local database before starting it.",
                    file=sys.stderr,
                )
                raise

        subprocess.run(["systemctl", "start", "sklepzdoniczkami.service"], check=True)
        print(
            "Local production database restored — "
            f"users: {users}; products: {products}; orders: {orders}."
        )
        print("This backup contains no media files; restore media separately.")
    except (
        OSError,
        UnicodeError,
        ValueError,
        tarfile.TarError,
        RuntimeError,
        subprocess.CalledProcessError,
    ) as error:
        parser.exit(1, f"Restore failed: {error}\n")


if __name__ == "__main__":
    main()
