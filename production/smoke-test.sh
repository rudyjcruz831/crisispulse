#!/bin/sh
set -eu

cd "$(dirname "$0")/.."
set -a
. ./.env.production
set +a

origin="${CRISISPULSE_PUBLIC_ORIGIN:-http://localhost:8088}"
curl --fail --silent --show-error "${origin}/api/v1/health" >/dev/null
docker compose --env-file .env.production -f compose.production.yml ps
echo "CrisisPulse public health check passed at ${origin}."
