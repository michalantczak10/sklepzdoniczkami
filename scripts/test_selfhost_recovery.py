import base64
import hashlib
import hmac
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import restore_github_production_backup
from scripts.restore_github_production_backup import (
    EXPECTED_DATABASE,
    EXPECTED_FILES,
    read_backup_package,
    verify_and_decrypt,
    verify_local_target,
)


class SelfHostRecoveryTests(unittest.TestCase):
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

            self.assertEqual({path.name for path in destination.iterdir()}, EXPECTED_FILES)

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
            with patch.object(restore_github_production_backup.subprocess, "run") as run:
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
                result = verify_and_decrypt(
                    directory, "encryption-key", encoded_hmac_key
                )

            self.assertEqual(result.read_bytes(), b"valid PostgreSQL dump")
            self.assertEqual(run.call_count, 2)


if __name__ == "__main__":
    unittest.main()
