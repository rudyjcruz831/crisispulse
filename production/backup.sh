#!/bin/sh
set -eu

umask 077
status_path="/backups/backup-status.json"
temporary=""
sidecar_temporary=""
listing=""
verbose_listing=""
verified=0
owns_backup_lock=0

write_status() {
    status="$1"
    verified_at="$2"
    archive_bytes="$3"
    checksum="$4"
    archive_name="$5"
    status_temporary="/backups/.backup-status.json.partial.$$"
    if [ "$status" = "verified" ]; then
        printf '{\n  "schema_version": 2,\n  "status": "verified",\n  "application_data_verified": true,\n  "verified_at": "%s",\n  "archive_name": "%s",\n  "archive_bytes": %s,\n  "checksum": "%s"\n}\n' \
            "$verified_at" "$archive_name" "$archive_bytes" "$checksum" > "$status_temporary"
    else
        printf '{\n  "schema_version": 2,\n  "status": "failed",\n  "application_data_verified": false,\n  "verified_at": null,\n  "archive_name": "",\n  "archive_bytes": 0,\n  "checksum": ""\n}\n' > "$status_temporary"
    fi
    chmod 0644 "$status_temporary"
    mv -f "$status_temporary" "$status_path"
}

cleanup() {
    exit_code="$?"
    [ -z "$temporary" ] || rm -f -- "$temporary"
    [ -z "$sidecar_temporary" ] || rm -f -- "$sidecar_temporary"
    [ -z "$listing" ] || rm -f -- "$listing"
    [ -z "$verbose_listing" ] || rm -f -- "$verbose_listing"
    if [ "$verified" -ne 1 ] && [ "$owns_backup_lock" -eq 1 ]; then
        write_status failed "" 0 "" "" || true
    fi
    exit "$exit_code"
}

trap cleanup EXIT
trap 'exit 130' HUP INT TERM

mkdir -p /backups
# Only one backup may publish status or clean partial files at a time.
exec 8> /backups/backup.lock
if ! flock -n 8; then
    echo "Another backup is already running." >&2
    exit 1
fi
owns_backup_lock=1
find /backups -maxdepth 1 -type f -name '*.partial*' -delete

retention_days="${CRISISPULSE_BACKUP_RETENTION_DAYS:-14}"
case "$retention_days" in
    ''|*[!0-9]*) echo "Backup retention must be a positive number of days." >&2; exit 2 ;;
esac
if [ "$retention_days" -lt 1 ]; then
    echo "Backup retention must be a positive number of days." >&2
    exit 2
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
temporary="/backups/crisispulse-${timestamp}.tar.gz.partial"
destination="/backups/crisispulse-${timestamp}.tar.gz"
sidecar_temporary="/backups/.crisispulse-${timestamp}.tar.gz.sha256.partial.$$"
sidecar_destination="${destination}.sha256"
listing="/tmp/crisispulse-backup-list.$$"
verbose_listing="/tmp/crisispulse-backup-verbose.$$"

if [ ! -f /state/refresh-status.lock ]; then
    echo "The refresh lock is unavailable." >&2
    exit 1
fi
# Refresh owns an exclusive lock; backup takes a shared lock and therefore
# waits for a coherent between-refresh snapshot.
exec 9< /state/refresh-status.lock
flock -s 9

for required_path in \
    /state/dashboard.json \
    /state/refresh-status.json \
    /work/history/hourly_region_features.parquet \
    /work/history/flood_articles_archive.parquet
do
    if [ ! -s "$required_path" ]; then
        echo "Backup refused: required application data is missing." >&2
        exit 1
    fi
done

# A nonempty file is not enough: only publish a backup whose application data
# can be parsed and satisfies the schemas the running service relies on.
if ! python3 /opt/crisispulse/validate_application_data.py \
    --state-root /state \
    --work-root /work
then
    echo "Backup refused: application data validation failed." >&2
    exit 1
fi

if [ -e "$destination" ]; then
    echo "A backup already exists for this timestamp." >&2
    exit 1
fi
tar \
    --exclude='state/raw' \
    --exclude='state/refresh-status.lock' \
    -C / -czf "$temporary" state work

# Listing failure is checked independently so a corrupt archive can never be
# published merely because the unsafe-path grep found no match.
if ! tar -tzf "$temporary" > "$listing"; then
    echo "Backup verification failed." >&2
    exit 1
fi
if grep -Eq '(^/|(^|/)\.\.(/|$))' "$listing"; then
    echo "Backup verification rejected an unsafe archive." >&2
    exit 1
fi
if grep -Ev '^(state|work)(/.*)?$' "$listing" | grep -q .; then
    echo "Backup verification rejected an unexpected archive entry." >&2
    exit 1
fi
if sort "$listing" | uniq -d | grep -q .; then
    echo "Backup verification rejected duplicate archive entries." >&2
    exit 1
fi
if grep -Eq '^state/raw(/|$)|^state/refresh-status\.lock$' "$listing"; then
    echo "Backup verification found excluded state." >&2
    exit 1
fi
for required in \
    state/dashboard.json \
    state/refresh-status.json \
    work/history/hourly_region_features.parquet \
    work/history/flood_articles_archive.parquet
do
    if ! grep -Fxq "$required" "$listing"; then
        echo "Backup verification failed to preserve required application data." >&2
        exit 1
    fi
done
if ! tar -tvzf "$temporary" > "$verbose_listing"; then
    echo "Backup verification failed." >&2
    exit 1
fi
if grep -Ev '^[-d]' "$verbose_listing" | grep -q .; then
    echo "Backup verification rejected a non-file archive entry." >&2
    exit 1
fi
for review_name in reviews.jsonl article-reviews.jsonl
do
    if [ -e "/state/${review_name}" ] && ! grep -Fxq "state/${review_name}" "$listing"; then
        echo "Backup verification failed to preserve a review log." >&2
        exit 1
    fi
done

archive_bytes="$(stat -c '%s' "$temporary")"
checksum="$(sha256sum "$temporary" | awk '{print $1}')"
verified_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf '%s  %s\n' "$checksum" "$(basename "$destination")" > "$sidecar_temporary"
chmod 0640 "$temporary" "$sidecar_temporary"
mv "$temporary" "$destination"
temporary=""
mv "$sidecar_temporary" "$sidecar_destination"
sidecar_temporary=""
find /backups -maxdepth 1 -type f -name 'crisispulse-*.tar.gz' -mtime "+${retention_days}" -print |
    while IFS= read -r expired_archive
    do
        rm -f -- "$expired_archive" "${expired_archive}.sha256"
    done
write_status verified "$verified_at" "$archive_bytes" "$checksum" "$(basename "$destination")"
verified=1
printf '%s\n' "$destination"
