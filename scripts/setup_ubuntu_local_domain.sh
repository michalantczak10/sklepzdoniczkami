#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ "$#" -ne 0 ]]; then
    echo "Usage: sudo bash scripts/setup_ubuntu_local_domain.sh" >&2
    exit 2
fi
if [[ "$EUID" -ne 0 || -z "${SUDO_USER:-}" || "$SUDO_USER" == "root" ]]; then
    echo "Run with sudo from the non-root account that owns the checkout." >&2
    exit 1
fi

APP_USER="$SUDO_USER"
APP_GROUP="$(id -gn "$APP_USER")"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ENV_FILE="/etc/sklepzdoniczkami/production.env"
PROXY_TEMPLATE="$APP_DIR/deploy/sklepzdoniczkami-local-production-proxy.service"
CADDY_TEMPLATE="$APP_DIR/deploy/Caddyfile.local-wsl"
CADDY_CONFIG="/etc/caddy/Caddyfile"
PROXY_UNIT="/etc/systemd/system/sklepzdoniczkami-local-production-proxy.service"

if [[ "$APP_DIR" == *[[:space:]]* || "$APP_DIR" == /home/* ||
    ! -f "$APP_DIR/manage.py" || ! -f "$PROXY_TEMPLATE" || ! -f "$CADDY_TEMPLATE" ]]; then
    echo "Run this setup from the complete checkout at /opt/sklepzdoniczkami." >&2
    exit 1
fi
if [[ ! -f "$ENV_FILE" || ! -x "$APP_DIR/.venv/bin/gunicorn" ]] ||
    ! systemctl is-active --quiet sklepzdoniczkami-production.service; then
    echo "The local production profile must be configured and active first." >&2
    exit 1
fi
if [[ -e "$PROXY_UNIT" || -e "$CADDY_CONFIG" ]]; then
    echo "A local Caddy or production-proxy configuration already exists; inspect it before continuing." >&2
    exit 1
fi
if ! command -v systemctl >/dev/null 2>&1 ||
    ! command -v apt-get >/dev/null 2>&1 ||
    ! command -v curl >/dev/null 2>&1 ||
    ! command -v ss >/dev/null 2>&1; then
    echo "Ubuntu with systemd, apt, curl, and socket tools is required." >&2
    exit 1
fi
for port in 80 443 8003; do
    if ss -lntH | awk -v port=":$port" '$4 ~ port "$" { found = 1 } END { exit !found }'; then
        echo "Port $port is already in use; refusing to change the local domain route." >&2
        exit 1
    fi
done
for name in ALLOWED_HOSTS CSRF_TRUSTED_ORIGINS SITE_URL; do
    if ! grep -q "^${name}=" "$ENV_FILE"; then
        echo "Expected $name in $ENV_FILE; refusing to replace an incomplete profile." >&2
        exit 1
    fi
done

echo "Installing Caddy from its signed official Ubuntu package repository..."
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    ca-certificates \
    curl \
    gnupg
KEY_ASC="/usr/share/keyrings/caddy-stable-archive-keyring.asc"
KEY_GPG="/usr/share/keyrings/caddy-stable-archive-keyring.gpg"
SOURCE_LIST="/etc/apt/sources.list.d/caddy-stable.list"
if [[ -e "$SOURCE_LIST" || -e "$KEY_GPG" ]]; then
    if [[ ! -s "$SOURCE_LIST" || ! -s "$KEY_GPG" ]] ||
        ! grep -Fq 'https://dl.cloudsmith.io/public/caddy/stable/deb/debian' "$SOURCE_LIST" ||
        ! grep -Fq "signed-by=$KEY_GPG" "$SOURCE_LIST"; then
        echo "Existing Caddy package-source files do not match the official source; inspect them." >&2
        exit 1
    fi
else
    curl --fail --location --silent --show-error \
        https://dl.cloudsmith.io/public/caddy/stable/gpg.key --output "$KEY_ASC"
    gpg --dearmor --yes --output "$KEY_GPG" "$KEY_ASC"
    curl --fail --location --silent --show-error \
        https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt --output "$SOURCE_LIST"
    chmod 0644 "$KEY_GPG" "$SOURCE_LIST"
fi
apt-get -o Acquire::Retries=3 update
DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::Retries=3 install -y caddy

cp --preserve=mode,ownership "$ENV_FILE" "${ENV_FILE}.before-local-domain"
sed -i \
    -e 's|^ALLOWED_HOSTS=.*|ALLOWED_HOSTS=localhost,127.0.0.1,sklepzdoniczkami.pl,www.sklepzdoniczkami.pl|' \
    -e 's|^CSRF_TRUSTED_ORIGINS=.*|CSRF_TRUSTED_ORIGINS=https://localhost:8002,https://127.0.0.1:8002,https://sklepzdoniczkami.pl,https://www.sklepzdoniczkami.pl|' \
    -e 's|^SITE_URL=.*|SITE_URL=https://sklepzdoniczkami.pl|' \
    "$ENV_FILE"
chown root:"$APP_GROUP" "$ENV_FILE"
chmod 0640 "$ENV_FILE"

sed \
    -e "s|@APP_USER@|$APP_USER|g" \
    -e "s|@APP_GROUP@|$APP_GROUP|g" \
    -e "s|@APP_DIR@|$APP_DIR|g" \
    "$PROXY_TEMPLATE" > "$PROXY_UNIT"
chmod 0644 "$PROXY_UNIT"

install -d -o root -g caddy -m 0750 /etc/caddy
if [[ -e "$CADDY_CONFIG" ]]; then
    mv "$CADDY_CONFIG" "${CADDY_CONFIG}.before-sklep-local"
fi
install -o root -g caddy -m 0640 "$CADDY_TEMPLATE" "$CADDY_CONFIG"

systemctl daemon-reload
systemctl enable --now sklepzdoniczkami-local-production-proxy.service caddy.service
systemctl restart sklepzdoniczkami-production.service
systemctl restart caddy.service
caddy validate --config "$CADDY_CONFIG"

for attempt in $(seq 1 30); do
    if curl --insecure --silent --fail \
        --resolve sklepzdoniczkami.pl:443:127.0.0.1 \
        https://sklepzdoniczkami.pl/admin/login/ >/dev/null; then
        break
    fi
    if [[ "$attempt" -eq 30 ]]; then
        echo "The local HTTPS domain did not become healthy; inspect Caddy and Gunicorn logs." >&2
        exit 1
    fi
    sleep 1
done

echo "Local Caddy route is ready for sklepzdoniczkami.pl and www.sklepzdoniczkami.pl."
echo "Caddy's Windows-trustable local root certificate is at:"
find /var/lib/caddy -path '*/pki/authorities/local/root.crt' -type f -print -quit
echo "The Windows hosts override and CurrentUser certificate trust are separate steps."
echo "Public DNS is unchanged; the local production database remains empty until restored."
