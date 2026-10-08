#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: sudo bash scripts/setup_ubuntu_selfhost.sh production" >&2
    exit 2
}

[[ "$#" -le 1 ]] || usage
[[ -z "${1:-}" || "$1" == "production" ]] || usage
APP_ENV="production"
DATABASE_NAME="sklepzdoniczkami_prod"
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
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ENV_DIR="/etc/sklepzdoniczkami"
ENV_FILE="$ENV_DIR/app.env"
UNIT_FILE="/etc/systemd/system/sklepzdoniczkami.service"
MEDIA_ROOT="/var/lib/sklepzdoniczkami-production/media"
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
if [[ -e "$ENV_FILE" || -e "$UNIT_FILE" ]]; then
    echo "An existing self-hosting configuration was found; refusing to overwrite it." >&2
    exit 1
fi
if getent passwd "$APP_USER" >/dev/null; then
    echo "The dedicated service account $APP_USER already exists; inspect it before continuing." >&2
    exit 1
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

APP_PASSWORD="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
DJANGO_SECRET="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
ROLE_EXISTS="$(runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_roles WHERE rolname = '$DATABASE_NAME'")"
DATABASE_EXISTS="$(runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_database WHERE datname = '$DATABASE_NAME'")"
if [[ -n "$ROLE_EXISTS" || -n "$DATABASE_EXISTS" ]]; then
    echo "Role or database $DATABASE_NAME already exists; refusing to alter existing data." >&2
    exit 1
fi

useradd --system --user-group --no-create-home --home-dir /nonexistent \
    --shell /usr/sbin/nologin "$APP_USER"
runuser -u postgres -- psql -v ON_ERROR_STOP=1 \
    -v app_role="$DATABASE_NAME" \
    -v app_password="$APP_PASSWORD" <<'SQL'
CREATE ROLE :"app_role" LOGIN PASSWORD :'app_password';
SQL
runuser -u postgres -- createdb --owner="$DATABASE_NAME" "$DATABASE_NAME"

install -d -o root -g root -m 0711 "$ENV_DIR"
install -d -o "$APP_USER" -g "$APP_GROUP" -m 0750 "$MEDIA_ROOT"
cat > "$ENV_FILE" <<EOF
APP_ENV=$APP_ENV
DATABASE_NAME_${APP_ENV^^}=$DATABASE_NAME
DATABASE_URL_${APP_ENV^^}=postgresql://${DATABASE_NAME}:${APP_PASSWORD}@127.0.0.1:5432/${DATABASE_NAME}
DJANGO_SECRET_KEY_${APP_ENV^^}=${DJANGO_SECRET}
DEBUG=$DEBUG
ALLOWED_HOSTS=$ALLOWED_HOSTS
CSRF_TRUSTED_ORIGINS=$CSRF_TRUSTED_ORIGINS
SITE_NAME=Sklepzdoniczkami
SITE_URL=$SITE_URL
MEDIA_ROOT=$MEDIA_ROOT
EOF
chown root:"$APP_GROUP" "$ENV_FILE"
chmod 0640 "$ENV_FILE"

if [[ -e "$APP_DIR/.venv" && ! -x "$APP_DIR/.venv/bin/python" ]]; then
    echo "An incomplete virtual environment exists at $APP_DIR/.venv; inspect it before continuing." >&2
    exit 1
fi
if [[ ! -x "$APP_DIR/.venv/bin/python" ]]; then
    "$PYTHON" -m venv "$APP_DIR/.venv"
fi
chown -R root:"$APP_GROUP" "$APP_DIR"
chmod -R u=rwX,g=rX,o= "$APP_DIR"
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"
runuser -u "$APP_USER" -- env DJANGO_ENV_FILE="$ENV_FILE" \
    "$APP_DIR/.venv/bin/python" "$APP_DIR/manage.py" migrate --noinput
env DJANGO_ENV_FILE="$ENV_FILE" \
    "$APP_DIR/.venv/bin/python" "$APP_DIR/manage.py" collectstatic --noinput

install -o root -g root -m 0644 "$SERVICE_TEMPLATE" "$UNIT_FILE"
systemctl daemon-reload
systemctl enable --now sklepzdoniczkami.service

echo
echo "Created the production database $DATABASE_NAME and started the production service."
echo "The service listens on 127.0.0.1:8000; PostgreSQL is not exposed publicly."
echo "Configure payment/email secrets and the HTTPS reverse proxy separately."
echo "This installer is only for a new VPS; do not use it to modify existing environments."
