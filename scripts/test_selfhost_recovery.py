import base64
import hashlib
import hmac
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts import backup_ovh, restore_github_production_backup
from scripts.postgres_utils import postgres_environment
from scripts.restore_github_production_backup import (
    EXPECTED_DATABASE,
    EXPECTED_FILES,
    MIGRATION_CONFIG_FILE,
    MIGRATION_DATABASE_USER,
    MIGRATION_SYSTEM_USER,
    RUNTIME_DATABASE_USER,
    grant_runtime_privileges,
    migration_command,
    read_backup_package,
    verify_and_decrypt,
    verify_local_target,
)


class SelfHostRecoveryTests(unittest.TestCase):
    def test_restic_backup_requires_https_s3_and_dedicated_credentials(self):
        configuration = {
            "RESTIC_REPOSITORY": "s3:https://s3.gra.io.cloud.ovh.net/private-bucket/prod",
            "RESTIC_PASSWORD": "long-random-backup-password",
            "AWS_ACCESS_KEY_ID": "dedicated-key",
            "AWS_SECRET_ACCESS_KEY": "dedicated-secret",
            "AWS_DEFAULT_REGION": "gra",
        }

        environment = backup_ovh.validate_restic_configuration(configuration)

        self.assertEqual(
            environment["RESTIC_REPOSITORY"], configuration["RESTIC_REPOSITORY"]
        )
        self.assertEqual(environment["AWS_DEFAULT_REGION"], "gra")
        self.assertEqual(
            environment["RESTIC_CACHE_DIR"], str(backup_ovh.RESTIC_CACHE_DIR)
        )

        for repository in (
            "file:///tmp/backup",
            "s3:http://s3.gra.io.cloud.ovh.net/private-bucket/prod",
            "s3:https:///private-bucket/prod",
            "s3:https://s3.gra.io.cloud.ovh.net/",
        ):
            invalid_configuration = configuration | {"RESTIC_REPOSITORY": repository}
            with self.subTest(repository=repository), self.assertRaisesRegex(
                ValueError, "HTTPS S3 URL"
            ):
                backup_ovh.validate_restic_configuration(invalid_configuration)

    def test_restic_backup_requires_every_storage_credential(self):
        with self.assertRaisesRegex(ValueError, "AWS_SECRET_ACCESS_KEY"):
            backup_ovh.validate_restic_configuration(
                {
                    "RESTIC_REPOSITORY": "s3:https://s3.gra.io.cloud.ovh.net/bucket/prod",
                    "RESTIC_PASSWORD": "long-random-backup-password",
                    "AWS_ACCESS_KEY_ID": "dedicated-key",
                }
            )

    def test_restic_backup_covers_database_and_media_with_bounded_retention(self):
        backup_script = Path(__file__).with_name("backup_ovh.py").read_text(
            encoding="utf-8"
        )

        self.assertIn('"pg_dump"', backup_script)
        self.assertIn('str(MEDIA_ROOT)', backup_script)
        self.assertIn('"restic",\n                "backup"', backup_script)
        self.assertIn('"--keep-daily",\n            "7"', backup_script)
        self.assertIn('"--keep-weekly",\n            "5"', backup_script)
        self.assertIn('"--keep-monthly",\n            "12"', backup_script)
        self.assertIn('"--prune"', backup_script)
        forget_command = backup_script.split('"restic",\n            "forget"', 1)[1]
        self.assertIn('"--tag",\n            "production"', forget_command)

    def test_backup_bootstrap_installs_isolated_tooling_without_app_deploy(self):
        installer = Path(__file__).with_name("install_ovh_backup.sh").read_text(
            encoding="utf-8"
        ).replace("\r\n", "\n")
        installer_wrapper = Path(__file__).with_name("install_ovh_backup.ps1").read_text(
            encoding="utf-8"
        )

        for source_file in (
            "scripts/backup_ovh.py",
            "scripts/postgres_utils.py",
            "scripts/restore_github_production_backup.py",
            "deploy/backup.env.example",
            "deploy/sklepzdoniczkami-backup.service",
            "deploy/sklepzdoniczkami-backup.timer",
        ):
            self.assertIn(source_file, installer)
        self.assertIn('archive --format=tar "$COMMIT"', installer)
        self.assertIn("BACKUP_ROOT=", installer)
        self.assertNotIn('git -C "$APP_DIR" switch', installer)
        self.assertNotIn("systemctl enable", installer)
        self.assertNotIn("systemctl start", installer)
        self.assertIn("Django tests", installer_wrapper)
        self.assertIn("End-to-end tests (Playwright)", installer_wrapper)
        self.assertIn("PostgreSQL tests", installer_wrapper)
        self.assertIn("git merge-base --is-ancestor", installer_wrapper)

    def test_backup_creates_dump_uploads_both_data_sets_and_checks_repository(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache_directory = root / "restic-cache"
            cache_directory.mkdir()
            temporary_directory = MagicMock()
            temporary_directory.__enter__.return_value = str(root)
            temporary_directory.__exit__.return_value = False
            commands = []

            def run(command, **kwargs):
                commands.append(command)
                if command[0] == "pg_dump":
                    dump_path = Path(
                        next(
                            argument.removeprefix("--file=")
                            for argument in command
                            if argument.startswith("--file=")
                        )
                    )
                    dump_path.write_bytes(b"postgres backup")
                if command[:2] == ["restic", "backup"]:
                    return subprocess.CompletedProcess(
                        command,
                        0,
                        stdout='{"message_type":"summary","snapshot_id":"verified"}\n',
                    )
                return subprocess.CompletedProcess(command, 0)

            with (
                patch(
                    "scripts.backup_ovh.os.geteuid", return_value=0, create=True
                ),
                patch(
                    "scripts.backup_ovh.private_configuration",
                    return_value=(
                        {"RESTIC_REPOSITORY": "s3:https://example.invalid/bucket"},
                        {
                            "host": "127.0.0.1",
                            "port": 5432,
                            "user": EXPECTED_DATABASE,
                            "password": "test-only",
                            "dbname": EXPECTED_DATABASE,
                            "sslmode": "prefer",
                            "channel_binding": "prefer",
                        },
                    ),
                ),
                patch(
                    "scripts.backup_ovh.validate_restic_configuration",
                    return_value={
                        "RESTIC_REPOSITORY": "s3:https://example.invalid/bucket"
                    },
                ),
                patch.object(backup_ovh, "RESTIC_CACHE_DIR", cache_directory),
                patch(
                    "scripts.backup_ovh.tempfile.TemporaryDirectory",
                    return_value=temporary_directory,
                ),
                patch("scripts.backup_ovh.subprocess.run", side_effect=run),
            ):
                backup_ovh.create_backup()

            self.assertEqual(
                [command[0] for command in commands],
                ["pg_dump", "restic", "restic", "restic"],
            )
            backup_command = commands[1]
            self.assertIn(str(backup_ovh.MEDIA_ROOT), backup_command)
            self.assertIn("production", backup_command)
            self.assertEqual(commands[2][1], "check")
            self.assertEqual(commands[3][1], "forget")
            self.assertIn("--tag", commands[3])
            self.assertIn("production", commands[3])

    def test_deploy_script_requires_every_mandatory_ci_check(self):
        deploy_script = Path(__file__).with_name("deploy_ovh.ps1").read_text(
            encoding="utf-8"
        )

        for required_check in (
            "Django tests",
            "End-to-end tests (Playwright)",
            "PostgreSQL tests",
        ):
            self.assertIn(f"'{required_check}'", deploy_script)

    def test_production_gate_uses_root_controlled_preprod_marker(self):
        deploy_script = Path(__file__).with_name("deploy_ovh.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            'PREPROD_COMMIT_FILE="$PREPROD_MARKER_DIR/preprod-deployed-commit"',
            deploy_script,
        )
        self.assertNotIn(
            'PREPROD_COMMIT_FILE="/var/lib/sklepzdoniczkami-preprod/deployed-commit"',
            deploy_script,
        )
        self.assertIn(
            'require_root_controlled_directory "$PREPROD_MARKER_DIR"', deploy_script
        )
        self.assertIn('stat -c \'%u\' "$PREPROD_COMMIT_FILE"', deploy_script)
        self.assertIn('[[ ! "${preprod_marker_mode: -2}" =~ [2367] ]]', deploy_script)
        self.assertIn('[[ ! "${backup_marker_mode: -2}" =~ [2367] ]]', deploy_script)
        self.assertIn('backup_verified_at="$(cat "$BACKUP_MARKER")"', deploy_script)
        self.assertIn('current_time - backup_verified_at <= 2592000', deploy_script)

    def test_backup_package_accepts_only_expected_regular_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "backup.tgz"
            source_dir = root / "source"
            source_dir.mkdir()
            for name in EXPECTED_FILES:
                (source_dir / name).write_bytes(b"backup data")
            with tarfile.open(package, "w:gz") as archive:
                for name in EXPECTED_FILES:
                    archive.add(source_dir / name, arcname=name)

            destination = root / "unpacked"
            destination.mkdir()
            read_backup_package(package, destination)

            self.assertEqual(
                {path.name for path in destination.iterdir()}, EXPECTED_FILES
            )

    def test_backup_package_rejects_unexpected_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "backup.tgz"
            unexpected = root / "outside.txt"
            unexpected.write_text("not a backup", encoding="ascii")
            with tarfile.open(package, "w:gz") as archive:
                archive.add(unexpected, arcname="../outside.txt")

            with self.assertRaises(ValueError):
                read_backup_package(package, root / "unpacked")

    def test_backup_integrity_is_checked_before_decryption(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            encrypted = b"encrypted database"
            hmac_key = b"integrity-test-key"
            (directory / "backup.dump.enc").write_bytes(encrypted)
            (directory / "backup.dump.enc.hmac").write_text(
                hmac.new(hmac_key, encrypted, hashlib.sha256).hexdigest(),
                encoding="ascii",
            )
            (directory / "backup.hmac.keyid").write_text(
                hashlib.sha256(hmac_key).hexdigest()[:8], encoding="ascii"
            )
            with patch.object(
                restore_github_production_backup.subprocess, "run"
            ) as run:
                with self.assertRaises(ValueError):
                    verify_and_decrypt(directory, "encryption-key", "wrong-key")
                run.assert_not_called()

    def test_local_target_guard_rejects_remote_database(self):
        configuration = {
            "APP_ENV": "production",
            "DATABASE_NAME_PRODUCTION": EXPECTED_DATABASE,
            "DATABASE_URL_PRODUCTION": (
                f"postgresql://{EXPECTED_DATABASE}:secret@example.invalid:5432/"
                f"{EXPECTED_DATABASE}"
            ),
        }

        with self.assertRaisesRegex(ValueError, "non-local"):
            verify_local_target(configuration)

    def test_local_target_requires_owner_credentials(self):
        configuration = {
            "APP_ENV": "production",
            "DATABASE_NAME_PRODUCTION": EXPECTED_DATABASE,
            "DATABASE_URL_PRODUCTION": (
                "postgresql://sklepzdoniczkami_prod_web_limited:secret@"
                f"127.0.0.1:5432/{EXPECTED_DATABASE}"
            ),
        }

        with self.assertRaisesRegex(ValueError, "non-local"):
            verify_local_target(configuration)

    def test_local_restore_environment_uses_database_owner_credentials(self):
        configuration = {
            "APP_ENV": "production",
            "DATABASE_NAME_PRODUCTION": EXPECTED_DATABASE,
            "DATABASE_URL_PRODUCTION": (
                f"postgresql://{MIGRATION_DATABASE_USER}:owner-secret@"
                f"127.0.0.1:5432/{EXPECTED_DATABASE}"
            ),
        }

        connection = verify_local_target(configuration)
        environment = postgres_environment(connection)

        self.assertEqual(connection["user"], MIGRATION_DATABASE_USER)
        self.assertEqual(environment["PGUSER"], MIGRATION_DATABASE_USER)
        self.assertEqual(environment["PGPASSWORD"], "owner-secret")

    def test_restore_migrations_use_private_migrator_configuration(self):
        command = migration_command()

        self.assertEqual(command[:4], ["runuser", "-u", MIGRATION_SYSTEM_USER, "--"])
        self.assertIn(f"DJANGO_ENV_FILE={MIGRATION_CONFIG_FILE}", command)
        self.assertIn("migrate", command)
        self.assertEqual(MIGRATION_DATABASE_USER, EXPECTED_DATABASE)

    def test_restore_reapplies_runtime_dml_privileges_without_ddl(self):
        with patch(
            "scripts.restore_github_production_backup.subprocess.run"
        ) as run:
            grant_runtime_privileges({"PGUSER": MIGRATION_DATABASE_USER})

        command = run.call_args.args[0]
        privilege_sql = command[-1]
        self.assertIn(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
            f"TO {RUNTIME_DATABASE_USER}",
            " ".join(privilege_sql.split()),
        )
        self.assertIn(
            f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public "
            f"TO {RUNTIME_DATABASE_USER}",
            " ".join(privilege_sql.split()),
        )
        self.assertIn("ALTER DEFAULT PRIVILEGES", privilege_sql)
        self.assertNotIn(f"GRANT CREATE ON SCHEMA public TO {RUNTIME_DATABASE_USER}", privilege_sql)
        run.assert_called_once()

    def test_integrity_verified_backup_is_decrypted_and_listed(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            encrypted = b"encrypted database"
            hmac_key = b"integrity-test-key"
            (directory / "backup.dump.enc").write_bytes(encrypted)
            (directory / "backup.dump.enc.hmac").write_text(
                hmac.new(hmac_key, encrypted, hashlib.sha256).hexdigest(),
                encoding="ascii",
            )
            (directory / "backup.hmac.keyid").write_text(
                hashlib.sha256(hmac_key).hexdigest()[:8], encoding="ascii"
            )

            def fake_run(command, **kwargs):
                if command[0] == "openssl":
                    output_path = Path(command[command.index("-out") + 1])
                    output_path.write_bytes(b"valid PostgreSQL dump")
                return subprocess.CompletedProcess(command, 0)

            encoded_hmac_key = base64.b64encode(hmac_key).decode("ascii")
            with patch(
                "scripts.restore_github_production_backup.subprocess.run",
                side_effect=fake_run,
            ) as run:
                result = verify_and_decrypt(directory, "encryption-key", encoded_hmac_key)

            self.assertEqual(result.read_bytes(), b"valid PostgreSQL dump")
            self.assertEqual(run.call_count, 2)

    def test_decryption_matches_the_github_backup_cipher(self):
        openssl = shutil.which("openssl")
        if openssl is None:
            self.skipTest("OpenSSL is not installed.")

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            plaintext = directory / "source.dump"
            encrypted = directory / "backup.dump.enc"
            backup_bytes = b"PostgreSQL archive test bytes"
            plaintext.write_bytes(backup_bytes)
            encryption_key = "integration-test-encryption-key"
            encryption_environment = os.environ.copy()
            encryption_environment["BACKUP_ENCRYPTION_KEY"] = encryption_key
            subprocess.run(
                [
                    openssl,
                    "enc",
                    "-aes-256-cbc",
                    "-pbkdf2",
                    "-salt",
                    "-in",
                    str(plaintext),
                    "-out",
                    str(encrypted),
                    "-pass",
                    "env:BACKUP_ENCRYPTION_KEY",
                ],
                env=encryption_environment,
                check=True,
            )

            hmac_key = b"integration-test-hmac-key"
            (directory / "backup.dump.enc.hmac").write_text(
                hmac.new(hmac_key, encrypted.read_bytes(), hashlib.sha256).hexdigest(),
                encoding="ascii",
            )
            (directory / "backup.hmac.keyid").write_text(
                hashlib.sha256(hmac_key).hexdigest()[:8], encoding="ascii"
            )
            encoded_hmac_key = base64.b64encode(hmac_key).decode("ascii")
            real_run = subprocess.run

            def skip_archive_listing(command, **kwargs):
                if command[0] == "pg_restore":
                    return subprocess.CompletedProcess(command, 0)
                return real_run(command, **kwargs)

            with patch(
                "scripts.restore_github_production_backup.subprocess.run",
                side_effect=skip_archive_listing,
            ):
                restored = verify_and_decrypt(
                    directory, encryption_key, encoded_hmac_key
                )

            self.assertEqual(restored.read_bytes(), backup_bytes)


if __name__ == "__main__":
    unittest.main()
