Security review: backup & restore workflows

Date: 2026-09-23

Summary
-------
A coordinated multi-agent review (reviewer, security, ci-tester) inspected the db-backup and restore-staging GitHub Actions workflows and recent runs. A small set of targeted, surgical hardening changes were applied and merged in PR #10 to address immediate risks and CI flakiness.

Immediate fixes applied
----------------------
- Safe artifact extraction: artifacts are unpacked into a temporary directory and validated to prevent zip-slip attacks.
- Fail-fast HTTP download: curl uses -fS to fail on HTTP errors.
- Decrypt checks: restore fails early if BACKUP_ENCRYPTION_KEY is missing; decrypted files are chmod 600.
- Docker env leakage: DATABASE_URL passed into containers only via env (-e) rather than in host command-lines.
- Host fallback: avoid installing docker on runner; if docker unavailable, use host's pg_restore as fallback.
- No secrets were committed.

Security findings and risk levels
--------------------------------
- 🟠 HIGH: Artifact authenticity/integrity not verified. Current backups are encrypted with openssl enc (AES-256-CBC + PBKDF2) but lack authenticated encryption or a signature/HMAC — corrupted or tampered ciphertext may decrypt to misleading data.
- 🟡 MEDIUM: Zip-slip risk during artifact extraction (mitigated now by extracting to temp dir and validating paths).
- 🟡 MEDIUM: Possibility of DATABASE_URL exposure via command-line in earlier workflow versions (mitigated by passing env to container).

Recommended migration: authenticated backups (priority)
------------------------------------------------------
Goal: Ensure backups are both confidential and authenticated so the restore job can verify integrity before attempting to decrypt and restore.

Options (preferred order):
1) AES-GCM (preferred) — use openssl enc -aes-256-gcm with a random IV, store IV with the ciphertext, and derive keys from BACKUP_ENCRYPTION_KEY; verify tag on decrypt. Pros: AEAD, built-in integrity. Cons: older openssl versions vary; careful handling of IV/tag required.

2) Encrypt-then-MAC — keep AES-CBC encryption but compute HMAC-SHA256 over ciphertext and store alongside; on restore verify HMAC before decrypt. Pros: compatible with current enc method. Cons: requires secure HMAC key (can be derived from same secret with KDF) and careful implementation to avoid timing leaks.

3) PGP/GPG signing — sign the dump or use symmetric encryption + detached signature. Pros: standard tooling, public-key rotation possible. Cons: more complex key management.

Suggested implementation plan (minimal, backward-compatible migration)
----------------------------------------------------------------------
- Phase 1 (short-term): Implement Encrypt-then-MAC on backups.
  - Backup workflow: after openssl enc -aes-256-cbc -pbkdf2, compute HMAC-SHA256 over backup.dump.enc and upload both backup.dump.enc and backup.dump.enc.hmac.
  - Store HMAC key in GitHub Secrets (e.g., BACKUP_HMAC_KEY) — can be derived from BACKUP_ENCRYPTION_KEY using HKDF if only one secret desired.
  - Restore workflow: download both files, verify HMAC before decrypting. If HMAC verification fails, abort early and alert.
  - Add automated test in CI: create a small test artifact, tamper with it, ensure restore fails on HMAC mismatch.

- Phase 2 (medium-term): Move to AES-GCM (or libsodium secretbox) for AEAD.
  - Update both backup and restore steps to use AES-GCM, ensure IV/tag handling and encode tag alongside ciphertext.
  - Run migration: for a period produce both formats (v1 HMAC, v2 AEAD) with version tag in artifact name.
  - Rotate keys and deprecate old format after all restores validated.

Operational recommendations
---------------------------
- Key rotation: define schedule and implement script to re-encrypt backups if needed; store keys in GitHub Secrets or a vault (HashiCorp Vault, cloud KMS) with restricted access.
- Retention: move long-term backups to S3/Backblaze with server-side encryption and lifecycle policies; keep short retention in GitHub artifacts for quick test restores.
- Alerts: add monitoring to ensure scheduled backups succeed and that restore runs pass sanity checks.

Next steps I can take (choose one):
- Implement Phase 1 (Encrypt-then-MAC) as a PR with minimal changes to db-backup.yml and restore-staging.yml, plus CI tests. (Recommended)
- Draft a Phase 2 PR plan for AES-GCM migration with backwards-compatibility strategy.
- Create a small CI test (in repo) that validates HMAC verification and tamper detection.
- Nothing — keep current state.

Contact
-------
Prepared by automated multi-agent review run on 2026-09-23.
Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
