#!/usr/bin/env python3
"""Create and retain encrypted production database and media backups in S3."""

import argparse
import json
import os
import socket
import stat
import subprocess
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

from scripts.postgres_utils import postgres_environment
from scripts.restore_github_production_backup import (
    EXPECTED_DATABASE,
    MIGRATION_CONFIG_FILE,
    verify_local_target,
)

BACKUP_CONFIG_FILE = Path(
    os.environ.get(
        "SKLEP_BACKUP_ENV_FILE", "/etc/sklepzdoniczkami/backup.env"
    )
)
PRODUCTION_CONFIG_FILE = Path("/etc/sklepzdoniczkami/app.env")
MEDIA_ROOT = Path("/var/lib/sklepzdoniczkami-production/media")
RESTIC_CACHE_DIR = Path("/var/cache/sklepzdoniczkami-restic")


def require_root_owned_file(path, *, allow_group_read=False):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Required private configuration is missing or unsafe: {path}")

    metadata = path.stat()
    mode = stat.S_IMODE(metadata.st_mode)
    disallowed_bits = 0o027 if allow_group_read else 0o077
    if metadata.st_uid != 0 or mode & disallowed_bits:
        raise ValueError(f"Private configuration has unsafe owner or permissions: {path}")


def load_private_environment(path, *, allow_group_read=False):
    require_root_owned_file(path, allow_group_read=allow_group_read)
    return {
        key: value
        for key, value in dotenv_values(path).items()
        if value is not None
    }


def validate_restic_configuration(configuration):
    required = (
        "RESTIC_REPOSITORY",
        "RESTIC_PASSWORD",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_DEFAULT_REGION",
    )
    missing = [key for key in required if not configuration.get(key)]
    if missing:
        raise ValueError(
            "Backup configuration is missing required values: " + ", ".join(missing)
        )

    repository = configuration["RESTIC_REPOSITORY"]
    parsed = urlsplit(repository.removeprefix("s3:"))
    if (
        not repository.startswith("s3:https://")
        or not parsed.hostname
        or not parsed.path.strip("/")
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "RESTIC_REPOSITORY must be an HTTPS S3 URL with a bucket path and no embedded credentials."
        )

    environment = os.environ.copy()
    environment.update(configuration)
    environment["RESTIC_REPOSITORY"] = repository
    environment["RESTIC_PASSWORD"] = configuration["RESTIC_PASSWORD"]
    environment["AWS_ACCESS_KEY_ID"] = configuration["AWS_ACCESS_KEY_ID"]
    environment["AWS_SECRET_ACCESS_KEY"] = configuration["AWS_SECRET_ACCESS_KEY"]
    environment["RESTIC_CACHE_DIR"] = str(RESTIC_CACHE_DIR)
    return environment


def private_configuration():
    backup_configuration = load_private_environment(BACKUP_CONFIG_FILE)
    migration_configuration = load_private_environment(
        MIGRATION_CONFIG_FILE, allow_group_read=True
    )
    production_configuration = load_private_environment(
        PRODUCTION_CONFIG_FILE, allow_group_read=True
    )
    database = verify_local_target(migration_configuration)
    if database["dbname"] != EXPECTED_DATABASE or not database["password"]:
        raise ValueError(
            "The private migration config is not a valid production database connection."
        )

    configured_media_root = Path(
        production_configuration.get("MEDIA_ROOT", str(MEDIA_ROOT))
    )
    if (
        not configured_media_root.is_absolute()
        or configured_media_root.resolve(strict=True) != MEDIA_ROOT
        or MEDIA_ROOT.is_symlink()
        or not MEDIA_ROOT.is_dir()
    ):
        raise ValueError(
            f"Production MEDIA_ROOT must be the existing directory {MEDIA_ROOT}."
        )
    return backup_configuration, database


def restic_snapshot_id(restic_environment):
    result = subprocess.run(
        ["restic", "snapshots", "--latest", "1", "--json", "--tag", "production"],
        env=restic_environment,
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        text=True,
    )
    snapshots = json.loads(result.stdout)
    if not snapshots or not snapshots[0].get("id"):
        raise RuntimeError("No production backup snapshot is available in the repository.")
    return snapshots[0]["id"]


def verify_restore(restic_environment, database):
    snapshot_id = restic_snapshot_id(restic_environment)
    database_environment = postgres_environment(database)
    verification_database = f"sklep_backup_verify_{uuid.uuid4().hex[:16]}"

    with tempfile.TemporaryDirectory(
        prefix="sklepzdoniczkami-restore-check-", dir="/var/tmp"
    ) as temporary:
        restore_root = Path(temporary)
        subprocess.run(
            ["restic", "restore", snapshot_id, "--target", str(restore_root)],
            env=restic_environment,
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
        )
        dump_paths = list(restore_root.rglob(f"{EXPECTED_DATABASE}.dump"))
        restored_media = restore_root / str(MEDIA_ROOT).lstrip("/")
        if (
            len(dump_paths) != 1
            or not dump_paths[0].is_file()
            or restored_media.is_symlink()
            or not restored_media.is_dir()
        ):
            raise RuntimeError(
                "The snapshot did not restore exactly one database dump and the production media directory."
            )
        subprocess.run(
            ["pg_restore", "--list", str(dump_paths[0])],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            [
                "runuser",
                "-u",
                "postgres",
                "--",
                "createdb",
                "--port=5432",
                f"--owner={EXPECTED_DATABASE}",
                verification_database,
            ],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
        )
        try:
            verification_environment = database_environment.copy()
            verification_environment["PGDATABASE"] = verification_database
            subprocess.run(
                [
                    "pg_restore",
                    "--no-owner",
                    "--no-privileges",
                    "--exit-on-error",
                    f"--dbname={verification_database}",
                    str(dump_paths[0]),
                ],
                env=verification_environment,
                check=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
            )
            import psycopg2
            verification_connection = database.copy()
            verification_connection["dbname"] = verification_database
            with psycopg2.connect(**verification_connection) as restored:
                with restored.cursor() as cursor:
                    for table in (
                        "auth_user",
                        "sklepzdoniczkami_product",
                        "sklepzdoniczkami_order",
                    ):
                        cursor.execute(f"SELECT COUNT(*) FROM {table}")
                        cursor.fetchone()
        finally:
            subprocess.run(
                [
                    "runuser",
                    "-u",
                    "postgres",
                    "--",
                    "dropdb",
                    "--if-exists",
                    "--port=5432",
                    verification_database,
                ],
                check=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
            )

    print(f"Restore verification succeeded for snapshot {snapshot_id}.")


def create_backup():
    if os.geteuid() != 0:
        raise PermissionError("Run the production backup service as root.")
    os.umask(0o077)

    backup_configuration, database = private_configuration()
    restic_environment = validate_restic_configuration(backup_configuration)
    if RESTIC_CACHE_DIR.is_symlink():
        raise ValueError("The Restic cache directory must not be a symlink.")
    RESTIC_CACHE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(RESTIC_CACHE_DIR, 0o700)
    database_environment = postgres_environment(database)

    with tempfile.TemporaryDirectory(
        prefix="sklepzdoniczkami-backup-", dir="/var/tmp"
    ) as temporary:
        dump_path = Path(temporary) / f"{EXPECTED_DATABASE}.dump"
        subprocess.run(
            [
                "pg_dump",
                "--format=custom",
                "--no-owner",
                "--no-acl",
                "--no-password",
                f"--file={dump_path}",
                f"--dbname={EXPECTED_DATABASE}",
            ],
            env=database_environment,
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
        )
        result = subprocess.run(
            [
                "restic",
                "backup",
                "--host",
                socket.getfqdn(),
                "--tag",
                "production",
                "--tag",
                "postgresql-and-media",
                "--json",
                str(dump_path),
                str(MEDIA_ROOT),
            ],
            env=restic_environment,
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            text=True,
        )

    try:
        events = [json.loads(line) for line in result.stdout.splitlines()]
    except json.JSONDecodeError as error:
        raise RuntimeError("Restic returned invalid backup status output.") from error
    summaries = [
        event
        for event in events
        if event.get("message_type") == "summary" and event.get("snapshot_id")
    ]
    if len(summaries) != 1:
        raise RuntimeError("Restic did not report a completed backup snapshot.")
    snapshot_id = summaries[-1]["snapshot_id"]

    subprocess.run(
        ["restic", "check"],
        env=restic_environment,
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        [
            "restic",
            "forget",
            "--keep-daily",
            "7",
            "--keep-weekly",
            "5",
            "--keep-monthly",
            "12",
            "--tag",
            "production",
            "--prune",
        ],
        env=restic_environment,
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
    )
    print(f"Offsite backup snapshot {snapshot_id} completed; repository check passed.")


def initialize_repository(restic_environment):
    if os.geteuid() != 0:
        raise PermissionError("Initialize the backup repository as root.")
    subprocess.run(
        ["restic", "init"],
        env=restic_environment,
        check=True,
        stdin=subprocess.DEVNULL,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument(
        "--verify-restore",
        action="store_true",
        help="Restore the latest snapshot into a temporary database and verify media.",
    )
    operation.add_argument(
        "--init-repository",
        action="store_true",
        help="Initialize the configured, empty Restic repository.",
    )
    arguments = parser.parse_args()
    if (arguments.verify_restore or arguments.init_repository) and os.geteuid() != 0:
        parser.error("Run backup administration operations as root.")
    if arguments.verify_restore or arguments.init_repository:
        os.umask(0o077)
        backup_configuration, database = private_configuration()
        environment = validate_restic_configuration(backup_configuration)
        if arguments.init_repository:
            initialize_repository(environment)
        else:
            verify_restore(environment, database)
    else:
        create_backup()
