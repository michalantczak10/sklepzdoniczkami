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
from unittest.mock import patch

from scripts import restore_github_production_backup
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
