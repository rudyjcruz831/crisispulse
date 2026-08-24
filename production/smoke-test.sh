#!/bin/sh
set -eu

cd "$(dirname "$0")/.."
set -a
. ./.env.production
set +a

origin="${CRISISPULSE_PUBLIC_ORIGIN:-http://localhost:8088}"
curl --fail --silent --show-error "${origin}/api/v1/health" >/dev/null

for protected_path in / /admin /api/v1/snapshot
do
    status_code="$(curl --silent --output /dev/null --write-out '%{http_code}' "${origin}${protected_path}")"
    if [ "$status_code" != "401" ]; then
        echo "Smoke test failed: ${protected_path} returned ${status_code} without authentication." >&2
        exit 1
    fi
done

# Set only this boolean to opt into the authenticated checks. curl prompts for
# the password on the terminal; the plaintext is not written to a file or env.
if [ "${CRISISPULSE_SMOKE_AUTH:-0}" = "1" ]; then
    curl \
        --user "${CRISISPULSE_ADMIN_USER:-admin}" \
        --fail --silent --show-error \
        "${origin}/" \
        "${origin}/admin" \
        "${origin}/api/v1/snapshot" \
        "${origin}/api/v1/admin/status" >/dev/null
    echo "Authenticated dashboard, admin, snapshot, and operations checks passed."
fi

docker compose --env-file .env.production -f compose.production.yml ps
echo "CrisisPulse health and unauthenticated protection checks passed at ${origin}."
