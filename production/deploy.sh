#!/bin/sh
set -eu

cd "$(dirname "$0")/.."
if [ ! -f .env.production ]; then
    echo "Copy .env.production.example to .env.production and replace the password hash first." >&2
    exit 2
fi
if grep -q 'REPLACE_WITH_CADDY_BCRYPT_HASH' .env.production; then
    echo "Replace the example password hash before deployment." >&2
    exit 2
fi

docker compose --env-file .env.production -f compose.production.yml config >/dev/null
docker compose --env-file .env.production -f compose.production.yml build api dashboard refresh
docker compose --env-file .env.production -f compose.production.yml up -d caddy api dashboard monitor
docker compose --env-file .env.production -f compose.production.yml --profile maintenance run --rm refresh
docker compose --env-file .env.production -f compose.production.yml ps
