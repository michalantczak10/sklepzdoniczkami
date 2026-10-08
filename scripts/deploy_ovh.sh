#!/usr/bin/env bash
set -Eeuo pipefail

PREPROD_MARKER_DIR="/etc/sklepzdoniczkami"
PREPROD_COMMIT_FILE="$PREPROD_MARKER_DIR/preprod-deployed-commit"

fail() {
    echo "Deployment blocked: $*" >&2
    exit 1
}

require_root_controlled_directory() {
    local directory="$1"
    local mode

    [[ -d "$directory" && ! -L "$directory" ]] ||
        fail "release-marker directory is missing or is a symlink."
    [[ "$(stat -c '%u' "$directory")" == "0" ]] ||
        fail "release-marker directory must be root-owned."
    mode="$(stat -c '%a' "$directory")"
    [[ "$mode" =~ ^[0-7]{3,4}$ ]] ||
        fail "could not read release-marker directory permissions."
    [[ ! "${mode: -2}" =~ [2367] ]] ||
        fail "release-marker directory must not be group- or world-writable."
}

[[ "$EUID" -eq 0 ]] || fail "run through sudo."
[[ "$#" -eq 2 ]] || fail "usage: deploy_ovh.sh development|preprod|production <full-commit-sha>."

TARGET_ENV="$1"
COMMIT="$2"
[[ "$COMMIT" =~ ^[0-9a-f]{40}$ ]] || fail "commit must be a full lowercase SHA."

case "$TARGET_ENV" in
    development)
        SOURCE_BRANCH="dev"
        APP_DIR="/opt/sklepzdoniczkami-development"
        APP_USER="sklepzdoniczkami-development"
        MIGRATION_USER="$APP_USER"
        APP_ENV_FILE="/etc/sklepzdoniczkami/development.env"
        MIGRATION_ENV_FILE="$APP_ENV_FILE"
        SERVICE="sklepzdoniczkami-development.service"
        STATE_DIR="/var/lib/sklepzdoniczkami-development"
        HEALTH_URL="https://localhost:8001/"
        CURL_INSECURE=1
        ;;
    preprod)
        SOURCE_BRANCH="main"
        APP_DIR="/opt/sklepzdoniczkami-preprod"
        APP_USER="sklepzdoniczkami-preprod"
        MIGRATION_USER="$APP_USER"
        APP_ENV_FILE="/etc/sklepzdoniczkami/preprod.env"
        MIGRATION_ENV_FILE="$APP_ENV_FILE"
        SERVICE="sklepzdoniczkami-preprod.service"
        STATE_DIR="/var/lib/sklepzdoniczkami-preprod"
        HEALTH_URL="https://localhost:8002/"
        CURL_INSECURE=1
        ;;
    production)
        SOURCE_BRANCH="main"
        APP_DIR="/opt/sklepzdoniczkami"
        APP_USER="sklepzdoniczkami-production"
        MIGRATION_USER="sklepzdoniczkami-migrator"
        APP_ENV_FILE="/etc/sklepzdoniczkami/app.env"
        MIGRATION_ENV_FILE="/etc/sklepzdoniczkami/migration.env"
        SERVICE="sklepzdoniczkami.service"
        STATE_DIR="/var/lib/sklepzdoniczkami-production"
        HEALTH_URL="https://sklepzdoniczkami.pl/"
        CURL_INSECURE=0
        ;;
    *)
        fail "unknown target '$TARGET_ENV'."
        ;;
esac

[[ -d "$APP_DIR/.git" ]] || fail "Git checkout not found at $APP_DIR."
[[ -x "$APP_DIR/.venv/bin/python" ]] || fail "Python environment not found at $APP_DIR/.venv."
[[ -r "$APP_ENV_FILE" && -r "$MIGRATION_ENV_FILE" ]] || fail "environment files are not readable."
[[ -d "$STATE_DIR" ]] || fail "systemd state directory not found at $STATE_DIR."

if [[ "$TARGET_ENV" == "production" ]]; then
    require_root_controlled_directory "$PREPROD_MARKER_DIR"
    BACKUP_MARKER="/etc/sklepzdoniczkami/production-backup-verified"
    [[ -f "$BACKUP_MARKER" && ! -L "$BACKUP_MARKER" ]] ||
        fail "verify an offsite database and media backup/restore before production deployment."
    [[ "$(stat -c '%u' "$BACKUP_MARKER")" == "0" ]] ||
        fail "the verified-backup marker must be root-owned."
    backup_marker_mode="$(stat -c '%a' "$BACKUP_MARKER")"
    [[ "$backup_marker_mode" =~ ^[0-7]{3,4}$ ]] ||
        fail "could not read verified-backup marker permissions."
    [[ ! "${backup_marker_mode: -2}" =~ [2367] ]] ||
        fail "the verified-backup marker must not be group- or world-writable."

    [[ -f "$PREPROD_COMMIT_FILE" && ! -L "$PREPROD_COMMIT_FILE" ]] ||
        fail "deploy and test this exact commit in preprod first."
    [[ "$(stat -c '%u' "$PREPROD_COMMIT_FILE")" == "0" ]] ||
        fail "the preprod deployment marker must be root-owned."
    preprod_marker_mode="$(stat -c '%a' "$PREPROD_COMMIT_FILE")"
    [[ "$preprod_marker_mode" =~ ^[0-7]{3,4}$ ]] ||
        fail "could not read preprod deployment marker permissions."
    [[ ! "${preprod_marker_mode: -2}" =~ [2367] ]] ||
        fail "the preprod deployment marker must not be group- or world-writable."
    [[ "$(cat "$PREPROD_COMMIT_FILE")" == "$COMMIT" ]] ||
        fail "production commit must match the successfully deployed preprod commit."
fi
if [[ "$TARGET_ENV" == "preprod" ]]; then
    require_root_controlled_directory "$PREPROD_MARKER_DIR"
fi

if [[ -n "$(git -C "$APP_DIR" status --porcelain --untracked-files=all)" ]]; then
    fail "the $TARGET_ENV checkout has local changes; inspect it before deploying."
fi

git -C "$APP_DIR" fetch --quiet origin \
    "refs/heads/$SOURCE_BRANCH:refs/remotes/origin/$SOURCE_BRANCH"
git -C "$APP_DIR" cat-file -e "${COMMIT}^{commit}" ||
    fail "commit $COMMIT is not present in the checkout."
git -C "$APP_DIR" merge-base --is-ancestor "$COMMIT" "refs/remotes/origin/$SOURCE_BRANCH" ||
    fail "commit $COMMIT is not reachable from origin/$SOURCE_BRANCH."

PREVIOUS_COMMIT="$(git -C "$APP_DIR" rev-parse HEAD)"
DEPLOYMENT_STARTED=0

restore_previous_release() {
    local exit_status="$?"
    trap - EXIT
    if [[ "$exit_status" -ne 0 && "$DEPLOYMENT_STARTED" -eq 1 ]]; then
        echo "Deployment failed; restoring code $PREVIOUS_COMMIT and restarting $SERVICE." >&2
        echo "Database migrations are not automatically reversed." >&2
        set +e
        systemctl stop "$SERVICE"
        git -C "$APP_DIR" switch --detach "$PREVIOUS_COMMIT"
        systemctl start "$SERVICE"
        set -e
    fi
    exit "$exit_status"
}
trap restore_previous_release EXIT

systemctl stop "$SERVICE"
DEPLOYMENT_STARTED=1
git -C "$APP_DIR" switch --detach "$COMMIT"
"$APP_DIR/.venv/bin/python" -m pip install --disable-pip-version-check \
    --requirement "$APP_DIR/requirements.txt"

runuser -u "$APP_USER" -- env DJANGO_ENV_FILE="$APP_ENV_FILE" PYTHONDONTWRITEBYTECODE=1 \
    "$APP_DIR/.venv/bin/python" "$APP_DIR/manage.py" check
runuser -u "$MIGRATION_USER" -- env DJANGO_ENV_FILE="$MIGRATION_ENV_FILE" \
    PYTHONDONTWRITEBYTECODE=1 \
    "$APP_DIR/.venv/bin/python" "$APP_DIR/manage.py" migrate --noinput
env DJANGO_ENV_FILE="$APP_ENV_FILE" \
    "$APP_DIR/.venv/bin/python" "$APP_DIR/manage.py" collectstatic --noinput

systemctl start "$SERVICE"
healthy=0
for attempt in {1..20}; do
    curl_options=(--fail --silent --show-error --max-time 5)
    if [[ "$CURL_INSECURE" -eq 1 ]]; then
        curl_options+=(--insecure)
    fi
    if systemctl is-active --quiet "$SERVICE" &&
        curl "${curl_options[@]}" "$HEALTH_URL" >/dev/null 2>&1; then
        healthy=1
        break
    fi
    sleep 1
done
[[ "$healthy" -eq 1 ]] || fail "the $TARGET_ENV service did not pass its HTTPS health check."

if [[ "$TARGET_ENV" == "preprod" ]]; then
    marker_path="$PREPROD_COMMIT_FILE"
    marker_tmp="$PREPROD_MARKER_DIR/.preprod-deployed-commit.$$"
else
    marker_path="$STATE_DIR/deployed-commit"
    marker_tmp="$STATE_DIR/.deployed-commit.$$"
fi
printf '%s\n' "$COMMIT" > "$marker_tmp"
chmod 0644 "$marker_tmp"
mv -- "$marker_tmp" "$marker_path"
DEPLOYMENT_STARTED=0
trap - EXIT

echo "Deployed $COMMIT to $TARGET_ENV and passed the health check."
