#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="/opt/sklepzdoniczkami"
BACKUP_ROOT="/opt/sklepzdoniczkami-backup"

fail() {
    echo "Backup tooling installation blocked: $*" >&2
    exit 1
}

[[ "$EUID" -eq 0 ]] || fail "run through sudo."
[[ "$#" -eq 1 ]] || fail "usage: install_ovh_backup.sh <full-commit-sha>."

COMMIT="$1"
[[ "$COMMIT" =~ ^[0-9a-f]{40}$ ]] || fail "commit must be a full lowercase SHA."
[[ -d "$APP_DIR/.git" ]] || fail "production Git checkout not found at $APP_DIR."
[[ -x "$APP_DIR/.venv/bin/python" ]] || fail "production Python environment not found."
[[ -f /etc/sklepzdoniczkami/app.env && ! -L /etc/sklepzdoniczkami/app.env ]] ||
    fail "production environment file is missing or unsafe."
[[ -f /etc/sklepzdoniczkami/migration.env && ! -L /etc/sklepzdoniczkami/migration.env ]] ||
    fail "migration environment file is missing or unsafe."
"$APP_DIR/.venv/bin/python" -c 'import dotenv, psycopg2' ||
    fail "required Python packages are missing from the production environment."

git -C "$APP_DIR" fetch --quiet origin \
    refs/heads/main:refs/remotes/origin/main
git -C "$APP_DIR" cat-file -e "${COMMIT}^{commit}" ||
    fail "commit $COMMIT is not present in the production checkout."
git -C "$APP_DIR" merge-base --is-ancestor "$COMMIT" refs/remotes/origin/main ||
    fail "commit $COMMIT is not reachable from origin/main."

RELEASE_DIR="$BACKUP_ROOT/releases/$COMMIT"
[[ ! -e "$RELEASE_DIR" && ! -L "$RELEASE_DIR" ]] ||
    fail "backup tooling release already exists at $RELEASE_DIR."

temporary="$(mktemp -d /var/tmp/sklepzdoniczkami-backup-install.XXXXXXXX)"
install -d -o root -g root -m 0755 "$BACKUP_ROOT/releases"
staging="$(mktemp -d "$BACKUP_ROOT/.release.XXXXXXXX")"
temporary_link="$BACKUP_ROOT/.current.$$"
installation_complete=0
cleanup() {
    rm -rf -- "$temporary" "$staging"
    if [[ "$installation_complete" -eq 0 ]]; then
        rm -rf -- "$RELEASE_DIR" "$temporary_link"
    fi
}
trap cleanup EXIT
chmod 0700 "$temporary"

git -C "$APP_DIR" archive --format=tar "$COMMIT" \
    scripts/__init__.py \
    scripts/backup_ovh.py \
    scripts/postgres_utils.py \
    scripts/restore_github_production_backup.py \
    deploy/backup.env.example \
    deploy/sklepzdoniczkami-backup.service \
    deploy/sklepzdoniczkami-backup.timer |
    tar -xf - -C "$temporary"

for required_file in \
    scripts/__init__.py \
    scripts/backup_ovh.py \
    scripts/postgres_utils.py \
    scripts/restore_github_production_backup.py \
    deploy/backup.env.example \
    deploy/sklepzdoniczkami-backup.service \
    deploy/sklepzdoniczkami-backup.timer; do
    [[ -f "$temporary/$required_file" && ! -L "$temporary/$required_file" ]] ||
        fail "release archive is missing a required regular file: $required_file."
done

install -d -o root -g root -m 0755 "$staging/scripts" "$staging/deploy"
for source in \
    scripts/__init__.py \
    scripts/backup_ovh.py \
    scripts/postgres_utils.py \
    scripts/restore_github_production_backup.py \
    deploy/backup.env.example \
    deploy/sklepzdoniczkami-backup.service \
    deploy/sklepzdoniczkami-backup.timer; do
    install -o root -g root -m 0644 \
        "$temporary/$source" "$staging/$source"
done

mv -- "$staging" "$RELEASE_DIR"

install -o root -g root -m 0644 \
    "$RELEASE_DIR/deploy/sklepzdoniczkami-backup.service" \
    /etc/systemd/system/sklepzdoniczkami-backup.service
install -o root -g root -m 0644 \
    "$RELEASE_DIR/deploy/sklepzdoniczkami-backup.timer" \
    /etc/systemd/system/sklepzdoniczkami-backup.timer
systemctl daemon-reload

ln -s "$RELEASE_DIR" "$temporary_link"
mv -Tf -- "$temporary_link" "$BACKUP_ROOT/current"
installation_complete=1

echo "Installed backup tooling from $COMMIT without changing or restarting the application."
echo "The backup service and timer remain disabled until explicitly configured."
