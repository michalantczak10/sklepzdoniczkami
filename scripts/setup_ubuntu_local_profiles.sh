#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ "$#" -ne 0 ]]; then
    echo "Usage: sudo bash scripts/setup_ubuntu_local_profiles.sh" >&2
    exit 2
fi
if [[ "$EUID" -ne 0 ]]; then
    echo "Run with sudo from the non-root account that owns the checkout." >&2
    exit 1
fi
if [[ -z "${SUDO_USER:-}" || "$SUDO_USER" == "root" ]]; then
    echo "Run this script with sudo from the non-root account that owns the checkout." >&2
    exit 1
fi

APP_USER="$SUDO_USER"
APP_GROUP="$(id -gn "$APP_USER")"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ENV_DIR="/etc/sklepzdoniczkami"
TLS_DIR="$ENV_DIR/tls"
CERT_FILE="$TLS_DIR/localhost.crt"
KEY_FILE="$TLS_DIR/localhost.key"
UNIT_TEMPLATE="$APP_DIR/deploy/sklepzdoniczkami-local-profile.service"
CREDENTIALS_DIR="$(getent passwd "$APP_USER" | cut -d: -f6)/.local/share/sklepzdoniczkami"
CREDENTIALS_FILE="$CREDENTIALS_DIR/local-profiles-credentials.txt"

if [[ "$APP_DIR" == *[[:space:]]* || "$APP_DIR" == *"|"* || "$APP_DIR" == /home/* ]]; then
    echo "Keep the checkout outside /home in a path without spaces or '|'; use /opt/sklepzdoniczkami." >&2
    exit 1
fi
if [[ ! -f "$APP_DIR/manage.py" || ! -f "$UNIT_TEMPLATE" || ! -x "$APP_DIR/.venv/bin/python" ]]; then
    echo "A configured checkout with its existing development virtualenv is required." >&2
    exit 1
fi
if [[ ! -f "$ENV_DIR/app.env" || ! -f /etc/systemd/system/sklepzdoniczkami.service ]] ||
    ! systemctl is-active --quiet sklepzdoniczkami.service; then
    echo "The existing development profile and service must be configured and active first." >&2
    exit 1
fi
if [[ ! -r /etc/os-release ]]; then
    echo "Cannot identify this Linux distribution." >&2
    exit 1
fi
. /etc/os-release
if [[ "${ID:-}" != "ubuntu" ]]; then
    echo "This setup supports Ubuntu with systemd only." >&2
    exit 1
fi
if ! command -v systemctl >/dev/null 2>&1 ||
    ! command -v openssl >/dev/null 2>&1 ||
    ! command -v curl >/dev/null 2>&1 ||
    ! command -v pg_isready >/dev/null 2>&1 ||
    ! command -v ss >/dev/null 2>&1; then
    echo "Required systemd, OpenSSL, curl, PostgreSQL, and socket tools are missing." >&2
    exit 1
fi
if ! pg_isready --host=127.0.0.1 --port=5432 >/dev/null; then
    echo "PostgreSQL is not accepting local connections on 127.0.0.1:5432." >&2
    exit 1
fi
if [[ -e "$CREDENTIALS_FILE" ]]; then
    echo "Refusing to overwrite existing credentials at $CREDENTIALS_FILE." >&2
    exit 1
fi

declare -A DATABASES=(
    [preprod]=sklepzdoniczkami_preprod
    [production]=sklepzdoniczkami_prod
)
declare -A PORTS=(
    [preprod]=8001
    [production]=8002
)

for profile in preprod production; do
    database="${DATABASES[$profile]}"
    role="$database"
    port="${PORTS[$profile]}"
    env_file="$ENV_DIR/$profile.env"
    unit_file="/etc/systemd/system/sklepzdoniczkami-$profile.service"
    if [[ -e "$env_file" || -e "$unit_file" ]]; then
        echo "A $profile profile configuration already exists; refusing to overwrite it." >&2
        exit 1
    fi
    if runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_roles WHERE rolname = '$role'" | grep -q 1 ||
        runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_database WHERE datname = '$database'" | grep -q 1; then
        echo "Role or database $database already exists; refusing to alter existing data." >&2
        exit 1
    fi
    if ss -lntH | awk -v port=":$port" '$4 ~ port "$" { found = 1 } END { exit !found }'; then
        echo "Port $port is already in use; refusing to start the $profile profile." >&2
        exit 1
    fi
done

install -d -o root -g "$APP_GROUP" -m 0750 "$ENV_DIR" "$TLS_DIR"
if [[ ! -e "$CERT_FILE" && ! -e "$KEY_FILE" ]]; then
    openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
        -keyout "$KEY_FILE" -out "$CERT_FILE" \
        -subj "/CN=localhost" \
        -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" \
        -addext "basicConstraints=critical,CA:FALSE"
    chown root:"$APP_GROUP" "$CERT_FILE" "$KEY_FILE"
    chmod 0644 "$CERT_FILE"
    chmod 0640 "$KEY_FILE"
elif [[ ! -s "$CERT_FILE" || ! -s "$KEY_FILE" ]]; then
    echo "An incomplete localhost TLS certificate already exists; inspect $TLS_DIR." >&2
    exit 1
fi
if ! openssl x509 -in "$CERT_FILE" -noout -checkhost localhost >/dev/null 2>&1 ||
    ! openssl x509 -in "$CERT_FILE" -noout -checkip 127.0.0.1 >/dev/null 2>&1 ||
    ! openssl pkey -in "$KEY_FILE" -noout >/dev/null 2>&1 ||
    ! cmp -s <(openssl x509 -in "$CERT_FILE" -pubkey -noout) \
        <(openssl pkey -in "$KEY_FILE" -pubout); then
    echo "The localhost TLS certificate and private key are invalid or do not match." >&2
    exit 1
fi

install -d -o "$APP_USER" -g "$APP_GROUP" -m 0750 \
    /var/lib/sklepzdoniczkami/preprod/media \
    /var/lib/sklepzdoniczkami/production/media
install -d -o "$APP_USER" -g "$APP_GROUP" -m 0700 "$CREDENTIALS_DIR"
if [[ -e "$CREDENTIALS_FILE" ]]; then
    echo "Credentials file appeared during setup; refusing to overwrite it." >&2
    exit 1
fi

for profile in preprod production; do
    database="${DATABASES[$profile]}"
    port="${PORTS[$profile]}"
    env_file="$ENV_DIR/$profile.env"
    unit_name="sklepzdoniczkami-$profile"
    admin_password="$(openssl rand -hex 24)"
    database_password="$(openssl rand -hex 32)"
    django_secret="$(openssl rand -hex 48)"

    runuser -u postgres -- psql -v ON_ERROR_STOP=1 \
        -v app_role="$database" \
        -v app_password="$database_password" <<'SQL'
CREATE ROLE :"app_role" LOGIN PASSWORD :'app_password';
SQL
    runuser -u postgres -- createdb --owner="$database" "$database"

    cat > "$env_file" <<EOF
APP_ENV=$profile
DATABASE_NAME_${profile^^}=$database
DATABASE_URL_${profile^^}=postgresql://${database}:${database_password}@127.0.0.1:5432/${database}
DJANGO_SECRET_KEY_${profile^^}=${django_secret}
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://localhost:${port},https://127.0.0.1:${port}
SITE_NAME=Sklepzdoniczkami-${profile}
SITE_URL=https://localhost:${port}
SECURE_SSL_REDIRECT=True
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
MEDIA_ROOT=/var/lib/sklepzdoniczkami/${profile}/media
EOF
    chown root:"$APP_GROUP" "$env_file"
    chmod 0640 "$env_file"

    runuser -u "$APP_USER" -- env DJANGO_ENV_FILE="$env_file" \
        "$APP_DIR/.venv/bin/python" "$APP_DIR/manage.py" migrate --noinput
    runuser -u "$APP_USER" -- env DJANGO_ENV_FILE="$env_file" \
        DJANGO_SUPERUSER_USERNAME=admin \
        DJANGO_SUPERUSER_EMAIL="admin-${profile}@localhost" \
        DJANGO_SUPERUSER_PASSWORD="$admin_password" \
        "$APP_DIR/.venv/bin/python" "$APP_DIR/manage.py" createsuperuser --noinput

    sed \
        -e "s|@APP_USER@|$APP_USER|g" \
        -e "s|@APP_GROUP@|$APP_GROUP|g" \
        -e "s|@APP_DIR@|$APP_DIR|g" \
        -e "s|@PROFILE@|$profile|g" \
        -e "s|@PORT@|$port|g" \
        "$UNIT_TEMPLATE" > "/etc/systemd/system/$unit_name.service"
    chmod 0644 "/etc/systemd/system/$unit_name.service"

    printf '%s\n' \
        "Profile: $profile" \
        "URL: https://localhost:$port/" \
        "Admin username: admin" \
        "Admin password: $admin_password" \
        "" >> "$CREDENTIALS_FILE"
    chown "$APP_USER":"$APP_GROUP" "$CREDENTIALS_FILE"
    chmod 0600 "$CREDENTIALS_FILE"
    unset admin_password database_password django_secret
done

runuser -u "$APP_USER" -- env DJANGO_ENV_FILE="$ENV_DIR/preprod.env" \
    "$APP_DIR/.venv/bin/python" "$APP_DIR/manage.py" seed_preprod_data

systemctl daemon-reload
systemctl enable --now sklepzdoniczkami-preprod.service sklepzdoniczkami-production.service

for port in 8001 8002; do
    for attempt in $(seq 1 30); do
        if curl --insecure --silent --show-error --fail \
            "https://127.0.0.1:$port/admin/login/" >/dev/null; then
            break
        fi
        if [[ "$attempt" -eq 30 ]]; then
            echo "The local HTTPS service on port $port did not become healthy." >&2
            exit 1
        fi
        sleep 1
    done
done

echo "Created isolated local preprod and production databases and services."
echo "Preprod:    https://localhost:8001/ (synthetic catalogue)"
echo "Production: https://localhost:8002/ (empty local database)"
echo "Admin credentials: $CREDENTIALS_FILE (mode 0600)"
echo "The localhost TLS certificate is self-signed; browsers will show a warning."
echo "Both services and PostgreSQL listen only on loopback; no remote data or payment keys were copied."
