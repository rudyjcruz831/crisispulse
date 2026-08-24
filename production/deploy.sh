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
docker compose --env-file .env.production -f compose.production.yml build backup restore

if docker compose --env-file .env.production -f compose.production.yml --profile maintenance \
    run --rm --no-deps --entrypoint /bin/sh backup -c \
    'if find /state -mindepth 1 ! -name refresh-status.lock -print -quit | grep -q . || find /work -mindepth 1 -print -quit | grep -q .; then exit 0; fi; exit 1'
then
    echo "Existing installation detected; creating a verified pre-deploy backup."
    docker compose --env-file .env.production -f compose.production.yml --profile maintenance run --rm backup
    if ! docker compose --env-file .env.production -f compose.production.yml --profile maintenance \
        run --rm --no-deps --entrypoint python3 backup -c \
        'import json; p=json.load(open("/backups/backup-status.json", encoding="utf-8")); raise SystemExit(0 if p.get("schema_version") == 2 and p.get("status") == "verified" and p.get("application_data_verified") is True else 1)'
    then
        echo "Deployment refused: pre-deploy backup was not verified." >&2
        exit 1
    fi
fi

docker compose --env-file .env.production -f compose.production.yml build caddy api dashboard monitor refresh
docker compose --env-file .env.production -f compose.production.yml up -d caddy api dashboard monitor
docker compose --env-file .env.production -f compose.production.yml --profile maintenance run --rm refresh
docker compose --env-file .env.production -f compose.production.yml ps
