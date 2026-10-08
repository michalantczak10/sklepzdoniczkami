#!/usr/bin/env bash
set -euo pipefail
umask 022

usage() {
    echo "Usage: sudo bash scripts/setup_ubuntu_selfhost.sh production" >&2
    exit 2
}

[[ "$#" -le 1 ]] || usage
[[ -z "${1:-}" || "$1" == "production" ]] || usage
APP_ENV="production"
DATABASE_NAME="sklepzdoniczkami_prod"
OWNER_ROLE="$DATABASE_NAME"
RUNTIME_ROLE="sklepzdoniczkami_prod_web_limited"
DEBUG="False"
ALLOWED_HOSTS="sklepzdoniczkami.pl,www.sklepzdoniczkami.pl"
CSRF_TRUSTED_ORIGINS="https://sklepzdoniczkami.pl,https://www.sklepzdoniczkami.pl"
SITE_URL="https://sklepzdoniczkami.pl"

if [[ "$EUID" -ne 0 ]]; then
    echo "Run with sudo, for example: sudo bash $0 production" >&2
    exit 1
fi
if [[ -z "${SUDO_USER:-}" || "$SUDO_USER" == "root" ]]; then
    echo "Run this script with sudo from the non-root account that owns the checkout." >&2
    exit 1
fi

APP_USER="sklepzdoniczkami-production"
APP_GROUP="$APP_USER"
MIGRATION_USER="sklepzdoniczkami-migrator"
MIGRATION_GROUP="$MIGRATION_USER"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ENV_DIR="/etc/sklepzdoniczkami"
ENV_FILE="$ENV_DIR/app.env"
MIGRATION_ENV_FILE="$ENV_DIR/migration.env"
UNIT_FILE="/etc/systemd/system/sklepzdoniczkami.service"
STATE_DIR="/var/lib/$APP_USER"
MEDIA_ROOT="$STATE_DIR/media"
SERVICE_TEMPLATE="$APP_DIR/deploy/sklepzdoniczkami.service"

if [[ "$APP_DIR" == *[[:space:]]* || "$APP_DIR" == *"|"* ]]; then
    echo "Move the checkout to a path without spaces or '|' (recommended: /opt/sklepzdoniczkami)." >&2
    exit 1
fi
if [[ "$APP_DIR" != "/opt/sklepzdoniczkami" ]]; then
    echo "Place the production checkout at /opt/sklepzdoniczkami before running this installer." >&2
    exit 1
fi
if [[ ! -f "$APP_DIR/manage.py" || ! -f "$SERVICE_TEMPLATE" ]]; then
    echo "Run this script from a complete repository checkout." >&2
    exit 1
fi
if [[ -L "$APP_DIR/.env" || ( -e "$APP_DIR/.env" && ! -f "$APP_DIR/.env" ) ]]; then
    echo "A checkout .env must be a regular file, not a symlink or directory." >&2
    exit 1
fi
if [[ -f "$APP_DIR/.env" ]]; then
    CHECKOUT_ENV_MODE="$(stat -c '%a' "$APP_DIR/.env")"
    if (( (8#$CHECKOUT_ENV_MODE & 044) != 0 )); then
        echo "The checkout .env is group/world-readable; refusing to expose its secrets." >&2
        exit 1
    fi
fi
if [[ -e "$ENV_FILE" || -L "$ENV_FILE" ||
    -e "$MIGRATION_ENV_FILE" || -L "$MIGRATION_ENV_FILE" ||
    -e "$UNIT_FILE" || -L "$UNIT_FILE" ]]; then
    echo "An existing self-hosting configuration was found; refusing to overwrite it." >&2
    exit 1
fi
if [[ -e "$STATE_DIR" || -L "$STATE_DIR" || -e "$MEDIA_ROOT" || -L "$MEDIA_ROOT" ]]; then
    echo "Existing production state was found at $STATE_DIR; refusing to modify it." >&2
    exit 1
fi
if [[ -e "$APP_DIR/.venv" || -L "$APP_DIR/.venv" ]]; then
    echo "An existing virtual environment was found at $APP_DIR/.venv; refusing to reuse it." >&2
    exit 1
fi
if getent passwd "$APP_USER" >/dev/null || getent group "$APP_GROUP" >/dev/null; then
    echo "The production service account or group already exists; inspect it before continuing." >&2
    exit 1
fi
if getent passwd "$MIGRATION_USER" >/dev/null || getent group "$MIGRATION_GROUP" >/dev/null; then
    echo "The production migration account or group already exists; inspect it before continuing." >&2
    exit 1
fi
if [[ -e "$ENV_DIR" || -L "$ENV_DIR" ]]; then
    if [[ ! -d "$ENV_DIR" || -L "$ENV_DIR" || "$(stat -c '%u' "$ENV_DIR")" != "0" ]]; then
        echo "$ENV_DIR must be an existing root-owned directory or absent." >&2
        exit 1
    fi
fi
if ! command -v apt-get >/dev/null 2>&1 || ! command -v systemctl >/dev/null 2>&1; then
    echo "This installer supports Ubuntu Server LTS with apt and systemd." >&2
    exit 1
fi
if [[ ! -r /etc/os-release ]]; then
    echo "Cannot identify this Linux distribution." >&2
    exit 1
fi
. /etc/os-release
OS_CODENAME="${VERSION_CODENAME:-}"
OS_ARCH="$(dpkg --print-architecture)"
if [[ "${ID:-}" != "ubuntu" || -z "$OS_CODENAME" ]]; then
    echo "This installer supports Ubuntu Server LTS only." >&2
    exit 1
fi
if [[ "$OS_ARCH" != "amd64" && "$OS_ARCH" != "arm64" ]]; then
    echo "This installer supports Ubuntu LTS on amd64 or arm64." >&2
    exit 1
fi
if systemctl is-active --quiet sklepzdoniczkami.service ||
    systemctl is-enabled --quiet sklepzdoniczkami.service; then
    echo "A production service already exists or is active; refusing to modify it." >&2
    exit 1
fi

APP_GROUP_CREATED=0
APP_USER_CREATED=0
MIGRATION_GROUP_CREATED=0
MIGRATION_USER_CREATED=0
OWNER_ROLE_CREATED=0
RUNTIME_ROLE_CREATED=0
DATABASE_CREATED=0
ENV_DIR_CREATED=0
APP_ENV_CREATED=0
MIGRATION_ENV_CREATED=0
STATE_DIR_CREATED=0
MEDIA_DIR_CREATED=0
VENV_CREATED=0
UNIT_CREATED=0
ROLLBACK_FAILED=0
CHECKOUT_PERMISSIONS_CHANGED=0
declare -a CHECKOUT_PATHS=()
declare -a CHECKOUT_UIDS=()
declare -a CHECKOUT_GIDS=()
declare -a CHECKOUT_MODES=()

cleanup_action() {
    local description="$1"
    shift
    if "$@"; then
        return 0
    fi
    echo "Rollback failed while attempting to $description." >&2
    ROLLBACK_FAILED=1
    return 0
}

remove_empty_directory() {
    local path="$1"
    [[ ! -d "$path" ]] || rmdir -- "$path"
}

snapshot_checkout_permissions() {
    local path metadata uid gid mode
    while IFS= read -r -d '' path; do
        metadata="$(stat -c '%u %g %a' -- "$path")" || return 1
        read -r uid gid mode <<< "$metadata"
        CHECKOUT_PATHS+=("$path")
        CHECKOUT_UIDS+=("$uid")
        CHECKOUT_GIDS+=("$gid")
        CHECKOUT_MODES+=("$mode")
    done < <(
        find "$APP_DIR" \
            -path "$APP_DIR/.env" -prune -o \
            -type l -prune -o \
            -print0
    )
}

restore_checkout_permissions() {
    local index failed=0 path
    for index in "${!CHECKOUT_PATHS[@]}"; do
        path="${CHECKOUT_PATHS[$index]}"
        if [[ ! -e "$path" ]]; then
            continue
        fi
        if ! chown "${CHECKOUT_UIDS[$index]}:${CHECKOUT_GIDS[$index]}" -- "$path"; then
            echo "Could not restore ownership for $path." >&2
            failed=1
        fi
        if ! chmod "${CHECKOUT_MODES[$index]}" -- "$path"; then
            echo "Could not restore permissions for $path." >&2
            failed=1
        fi
    done
    return "$failed"
}

rollback() {
    local original_status="$?"
    trap - EXIT INT TERM
    if (( original_status == 0 )); then
        return 0
    fi

    echo "Installation failed; rolling back resources created by this run." >&2
    set +e
    if (( UNIT_CREATED )); then
        if systemctl is-active --quiet sklepzdoniczkami.service; then
            cleanup_action "stop the new production service" \
                systemctl stop sklepzdoniczkami.service
        fi
        if systemctl is-enabled --quiet sklepzdoniczkami.service; then
            cleanup_action "disable the new production service" \
                systemctl disable sklepzdoniczkami.service
        fi
        if [[ -e "$UNIT_FILE" ]]; then
            cleanup_action "remove the new systemd unit" rm -f -- "$UNIT_FILE"
        fi
        cleanup_action "reload systemd after unit removal" systemctl daemon-reload
    fi
    if (( DATABASE_CREATED )); then
        cleanup_action "drop the production database created by this run" \
            runuser -u postgres -- dropdb --if-exists --port=5432 "$DATABASE_NAME"
    fi
    if (( RUNTIME_ROLE_CREATED )); then
        cleanup_action "drop the runtime database role created by this run" \
            runuser -u postgres -- psql --port=5432 --set=ON_ERROR_STOP=1 \
                --command="DROP ROLE IF EXISTS \"$RUNTIME_ROLE\""
    fi
    if (( OWNER_ROLE_CREATED )); then
        cleanup_action "drop the owner database role created by this run" \
            runuser -u postgres -- psql --port=5432 --set=ON_ERROR_STOP=1 \
                --command="DROP ROLE IF EXISTS \"$OWNER_ROLE\""
    fi
    if (( APP_ENV_CREATED )) && [[ -e "$ENV_FILE" ]]; then
        cleanup_action "remove the generated application environment file" \
            rm -f -- "$ENV_FILE"
    fi
    if (( MIGRATION_ENV_CREATED )) && [[ -e "$MIGRATION_ENV_FILE" ]]; then
        cleanup_action "remove the generated migration environment file" \
            rm -f -- "$MIGRATION_ENV_FILE"
    fi
    if (( MEDIA_DIR_CREATED )); then
        cleanup_action "remove the empty media directory" remove_empty_directory "$MEDIA_ROOT"
    fi
    if (( STATE_DIR_CREATED )); then
        cleanup_action "remove the empty service state directory" remove_empty_directory "$STATE_DIR"
    fi
    if (( VENV_CREATED )) && [[ -e "$APP_DIR/.venv" ]]; then
        cleanup_action "remove the virtual environment created by this run" \
            rm -rf -- "$APP_DIR/.venv"
    fi
    if (( CHECKOUT_PERMISSIONS_CHANGED )); then
        cleanup_action "restore checkout ownership and permissions" \
            restore_checkout_permissions
    fi
    if (( APP_USER_CREATED )) && getent passwd "$APP_USER" >/dev/null; then
        cleanup_action "remove the new service account" userdel "$APP_USER"
    fi
    if (( MIGRATION_USER_CREATED )) && getent passwd "$MIGRATION_USER" >/dev/null; then
        cleanup_action "remove the new migration account" userdel "$MIGRATION_USER"
    fi
    if (( APP_GROUP_CREATED )) && getent group "$APP_GROUP" >/dev/null; then
        cleanup_action "remove the new service group" groupdel "$APP_GROUP"
    fi
    if (( MIGRATION_GROUP_CREATED )) && getent group "$MIGRATION_GROUP" >/dev/null; then
        cleanup_action "remove the new migration group" groupdel "$MIGRATION_GROUP"
    fi
    if (( ENV_DIR_CREATED )); then
        cleanup_action "remove the empty configuration directory" \
            remove_empty_directory "$ENV_DIR"
    fi

    if (( ROLLBACK_FAILED )); then
        echo "Rollback was incomplete; inspect the resources listed above before retrying." >&2
    else
        echo "Rollback completed; pre-existing data was left untouched." >&2
    fi
    exit "$original_status"
}

trap rollback EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "Installing Python and PostgreSQL 18 packages..."
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    ca-certificates \
    curl \
    postgresql-common \
    python3 \
    python3-venv

PGDG_KEY="/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc"
PGDG_SOURCES="/etc/apt/sources.list.d/pgdg.sources"
install -d -m 0755 "$(dirname "$PGDG_KEY")"
if [[ ! -s "$PGDG_KEY" ]]; then
    curl --fail --location --silent --show-error \
        https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        --output "$PGDG_KEY"
fi
if [[ -e "$PGDG_SOURCES" ]]; then
    grep -Fxq "URIs: https://apt.postgresql.org/pub/repos/apt" "$PGDG_SOURCES" &&
        grep -Fxq "Suites: ${OS_CODENAME}-pgdg" "$PGDG_SOURCES" &&
        grep -Fxq "Architectures: $OS_ARCH" "$PGDG_SOURCES" &&
        grep -Fxq "Signed-By: $PGDG_KEY" "$PGDG_SOURCES" || {
        echo "An incompatible PGDG apt source already exists at $PGDG_SOURCES." >&2
        exit 1
    }
else
    cat > "$PGDG_SOURCES" <<EOF
Types: deb
URIs: https://apt.postgresql.org/pub/repos/apt
Suites: ${OS_CODENAME}-pgdg
Architectures: $OS_ARCH
Components: main
Signed-By: $PGDG_KEY
EOF
fi
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y postgresql-18 postgresql-client-18

PYTHON="$(command -v python3)"
PYTHON_VERSION="$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
if ! "$PYTHON" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))'; then
    echo "Python 3.11 or newer is required; installed version is $PYTHON_VERSION." >&2
    exit 1
fi
if ! systemctl is-active --quiet postgresql; then
    systemctl enable --now postgresql
fi
PG18_PORT="$(pg_lsclusters --no-header | awk '$1 == "18" && $2 == "main" { print $3 }')"
if [[ "$PG18_PORT" != "5432" ]]; then
    echo "Expected the PostgreSQL 18 main cluster on port 5432; found '${PG18_PORT:-none}'." >&2
    echo "Resolve existing PostgreSQL clusters before retrying." >&2
    exit 1
fi
if ! pg_isready --host=127.0.0.1 --port=5432 >/dev/null; then
    echo "PostgreSQL is not accepting local connections on 127.0.0.1:5432." >&2
    echo "Resolve the existing PostgreSQL cluster/port configuration before retrying." >&2
    exit 1
fi
PG18_VERSION="$(runuser -u postgres -- psql --port=5432 --tuples-only --no-align \
    --command='SHOW server_version_num')"
if [[ "$PG18_VERSION" -lt 180000 || "$PG18_VERSION" -ge 190000 ]]; then
    echo "Expected PostgreSQL 18 on port 5432; found server version $PG18_VERSION." >&2
    exit 1
fi

OWNER_PASSWORD="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
RUNTIME_PASSWORD="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
DJANGO_SECRET="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
ROLE_EXISTS="$(runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_roles WHERE rolname = '$OWNER_ROLE' OR rolname = '$RUNTIME_ROLE'")"
DATABASE_EXISTS="$(runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_database WHERE datname = '$DATABASE_NAME'")"
if [[ -n "$ROLE_EXISTS" || -n "$DATABASE_EXISTS" ]]; then
    echo "A production database role or database already exists; refusing to alter existing data." >&2
    exit 1
fi

groupadd --system "$APP_GROUP"
APP_GROUP_CREATED=1
useradd --system --gid "$APP_GROUP" --no-create-home --home-dir /nonexistent \
    --shell /usr/sbin/nologin "$APP_USER"
APP_USER_CREATED=1
groupadd --system "$MIGRATION_GROUP"
MIGRATION_GROUP_CREATED=1
useradd --system --gid "$MIGRATION_GROUP" --no-create-home --home-dir /nonexistent \
    --shell /usr/sbin/nologin "$MIGRATION_USER"
MIGRATION_USER_CREATED=1
usermod --append --groups "$APP_GROUP" "$MIGRATION_USER"

runuser -u postgres -- psql --port=5432 --set=ON_ERROR_STOP=1 <<SQL
CREATE ROLE "$OWNER_ROLE" LOGIN PASSWORD '$OWNER_PASSWORD';
SQL
OWNER_ROLE_CREATED=1
runuser -u postgres -- psql --port=5432 --set=ON_ERROR_STOP=1 <<SQL
CREATE ROLE "$RUNTIME_ROLE" LOGIN PASSWORD '$RUNTIME_PASSWORD';
SQL
RUNTIME_ROLE_CREATED=1
runuser -u postgres -- createdb --port=5432 --owner="$OWNER_ROLE" "$DATABASE_NAME"
DATABASE_CREATED=1

runuser -u postgres -- psql --port=5432 --dbname="$DATABASE_NAME" \
    --set=ON_ERROR_STOP=1 <<SQL
REVOKE ALL PRIVILEGES ON DATABASE "$DATABASE_NAME" FROM PUBLIC;
REVOKE CREATE, TEMPORARY ON DATABASE "$DATABASE_NAME" FROM "$RUNTIME_ROLE";
GRANT CONNECT ON DATABASE "$DATABASE_NAME" TO "$RUNTIME_ROLE";
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM "$RUNTIME_ROLE";
GRANT USAGE ON SCHEMA public TO "$RUNTIME_ROLE";
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "$RUNTIME_ROLE";
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO "$RUNTIME_ROLE";
ALTER DEFAULT PRIVILEGES FOR ROLE "$OWNER_ROLE" IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "$RUNTIME_ROLE";
ALTER DEFAULT PRIVILEGES FOR ROLE "$OWNER_ROLE" IN SCHEMA public
    GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO "$RUNTIME_ROLE";
SQL

if [[ ! -e "$ENV_DIR" ]]; then
    mkdir -m 0711 -- "$ENV_DIR"
    ENV_DIR_CREATED=1
    chown root:root "$ENV_DIR"
    chmod 0711 "$ENV_DIR"
fi

mkdir -- "$STATE_DIR"
STATE_DIR_CREATED=1
chown "$APP_USER":"$APP_GROUP" "$STATE_DIR"
chmod 0750 "$STATE_DIR"
mkdir -- "$MEDIA_ROOT"
MEDIA_DIR_CREATED=1
chown "$APP_USER":"$APP_GROUP" "$MEDIA_ROOT"
chmod 0750 "$MEDIA_ROOT"

create_environment_file() {
    local file="$1"
    local group="$2"
    local database_url="$3"
    (umask 077; set -o noclobber; : > "$file")
    if [[ "$file" == "$ENV_FILE" ]]; then
        APP_ENV_CREATED=1
    else
        MIGRATION_ENV_CREATED=1
    fi
    chown root:"$group" "$file"
    cat >> "$file" <<EOF
APP_ENV=$APP_ENV
DATABASE_NAME_${APP_ENV^^}=$DATABASE_NAME
DATABASE_URL_${APP_ENV^^}=$database_url
DJANGO_SECRET_KEY_${APP_ENV^^}=$DJANGO_SECRET
DEBUG=$DEBUG
ALLOWED_HOSTS=$ALLOWED_HOSTS
CSRF_TRUSTED_ORIGINS=$CSRF_TRUSTED_ORIGINS
SITE_NAME=Sklepzdoniczkami
SITE_URL=$SITE_URL
MEDIA_ROOT=$MEDIA_ROOT
EOF
    chmod 0640 "$file"
}

create_environment_file "$ENV_FILE" "$APP_GROUP" \
    "postgresql://${RUNTIME_ROLE}:${RUNTIME_PASSWORD}@127.0.0.1:5432/${DATABASE_NAME}"
create_environment_file "$MIGRATION_ENV_FILE" "$MIGRATION_GROUP" \
    "postgresql://${OWNER_ROLE}:${OWNER_PASSWORD}@127.0.0.1:5432/${DATABASE_NAME}"

if [[ -e "$APP_DIR/.venv" || -L "$APP_DIR/.venv" ]]; then
    echo "A virtual environment appeared at $APP_DIR/.venv; refusing to overwrite it." >&2
    exit 1
fi
snapshot_checkout_permissions
mkdir -- "$APP_DIR/.venv"
VENV_CREATED=1
"$PYTHON" -m venv "$APP_DIR/.venv"
CHECKOUT_PERMISSIONS_CHANGED=1
find "$APP_DIR" \
    -path "$APP_DIR/.env" -prune -o \
    -type l -prune -o \
    -exec chown root:"$APP_GROUP" -- {} +
find "$APP_DIR" \
    -path "$APP_DIR/.env" -prune -o \
    -type l -prune -o \
    -exec chmod u=rwX,g=rX,o= -- {} +
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"
chown -R root:"$APP_GROUP" "$APP_DIR/.venv"
chmod -R u=rwX,g=rX,o= "$APP_DIR/.venv"

runuser -u "$MIGRATION_USER" -- env DJANGO_ENV_FILE="$MIGRATION_ENV_FILE" \
    "$APP_DIR/.venv/bin/python" "$APP_DIR/manage.py" migrate --noinput
env DJANGO_ENV_FILE="$ENV_FILE" \
    "$APP_DIR/.venv/bin/python" "$APP_DIR/manage.py" collectstatic --noinput

(set -o noclobber; : > "$UNIT_FILE")
UNIT_CREATED=1
cat "$SERVICE_TEMPLATE" > "$UNIT_FILE"
chown root:root "$UNIT_FILE"
chmod 0644 "$UNIT_FILE"
systemctl daemon-reload
systemctl enable --now sklepzdoniczkami.service

echo
echo "Created the production database $DATABASE_NAME and started the production service."
echo "The app connects as $RUNTIME_ROLE; migrations connect as $OWNER_ROLE."
echo "The service listens on 127.0.0.1:8000; PostgreSQL is not exposed publicly."
echo "Configure payment/email secrets and the HTTPS reverse proxy separately."
echo "This installer is only for a new production VPS; existing data is never overwritten."
