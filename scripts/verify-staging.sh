#!/usr/bin/env bash
# Simple helper to run sanity SELECTs against DATABASE_URL_STAGING
# Usage: DATABASE_URL_STAGING="postgres://..." ./scripts/verify-staging.sh
set -euo pipefail
if [ -z "${DATABASE_URL_STAGING:-}" ]; then
  echo "Please set DATABASE_URL_STAGING env var"
  exit 2
fi
echo "Running sanity checks against $DATABASE_URL_STAGING"
# Run queries using postgres:18 docker image so psql binary versions match
docker run --rm -e DATABASE_URL="$DATABASE_URL_STAGING" postgres:18 sh -c '\
  psql "$DATABASE_URL_STAGING" -c "SELECT 'product_count' as metric, count(*) FROM sklepzdoniczkami_product;" -c "SELECT 'order_count' as metric, count(*) FROM sklepzdoniczkami_order;" -c "SELECT 'orderitem_count' as metric, count(*) FROM sklepzdoniczkami_orderitem;" -c "SELECT 'user_count' as metric, count(*) FROM auth_user;" -c "SELECT 'now' as metric, now();" -c "SELECT 'pg_version' as metric, version();"'
