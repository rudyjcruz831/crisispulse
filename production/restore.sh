#!/bin/sh
set -eu

if [ "${CONFIRM_RESTORE:-NO}" != "YES" ]; then
    echo "Restore refused: set CONFIRM_RESTORE=YES for a fresh-volume restore drill." >&2
    exit 2
fi

archive="${RESTORE_ARCHIVE:-}"
case "$archive" in
    /backups/*) archive_name="${archive#/backups/}" ;;
    *) echo "Restore archive directory must be exactly /backups." >&2; exit 2 ;;
esac
case "$archive_name" in
    */*|'') echo "Restore archive directory must be exactly /backups." >&2; exit 2 ;;
esac
if ! printf '%s\n' "$archive_name" | grep -Eq '^crisispulse-[0-9]{8}T[0-9]{6}Z\.tar\.gz$'; then
    echo "Restore archive name is invalid." >&2
    exit 2
fi
if [ ! -f "$archive" ]; then
    echo "Restore archive does not exist." >&2
    exit 2
fi
sidecar="${archive}.sha256"
if [ ! -f "$sidecar" ]; then
    echo "Restore refused: backup checksum sidecar is missing." >&2
    exit 2
fi
if ! awk 'NR != 1 || NF != 2 { exit 1 } END { if (NR != 1) exit 1 }' "$sidecar"; then
    echo "Restore refused: backup checksum sidecar is invalid." >&2
    exit 2
fi
expected_checksum="$(awk 'NR == 1 { print $1 }' "$sidecar")"
expected_name="$(awk 'NR == 1 { print $2 }' "$sidecar")"
case "$expected_checksum" in
    *[!0-9a-fA-F]*|'') echo "Restore refused: backup checksum sidecar is invalid." >&2; exit 2 ;;
esac
if [ "${#expected_checksum}" -ne 64 ] || [ "$expected_name" != "$(basename "$archive")" ]; then
    echo "Restore refused: backup checksum sidecar is invalid." >&2
    exit 2
fi
actual_checksum="$(sha256sum "$archive" | awk '{print $1}')"
if [ "$actual_checksum" != "$expected_checksum" ]; then
    echo "Restore refused: backup checksum verification failed." >&2
    exit 2
fi

listing="/tmp/crisispulse-restore-list.$$"
verbose_listing="/tmp/crisispulse-restore-verbose.$$"
cleanup() {
    rm -f -- "$listing" "$verbose_listing"
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM

# Archive integrity must succeed independently before any target-volume check
# or mutation. This prevents a failed tar listing from falling through a pipe.
if ! tar -tzf "$archive" > "$listing"; then
    echo "Restore refused: backup archive integrity check failed." >&2
    exit 2
fi
if grep -Eq '(^/|(^|/)\.\.(/|$))' "$listing"; then
    echo "Restore archive contains an unsafe path." >&2
    exit 2
fi
if grep -Ev '^(state|work)(/.*)?$' "$listing" | grep -q .; then
    echo "Restore archive contains an unexpected entry." >&2
    exit 2
fi
if sort "$listing" | uniq -d | grep -q .; then
    echo "Restore archive contains duplicate entries." >&2
    exit 2
fi
if grep -Eq '^state/raw(/|$)|^state/refresh-status\.lock$' "$listing"; then
    echo "Restore archive contains excluded runtime state." >&2
    exit 2
fi
if ! tar -tvzf "$archive" > "$verbose_listing"; then
    echo "Restore refused: backup archive integrity check failed." >&2
    exit 2
fi
if grep -Ev '^[-d]' "$verbose_listing" | grep -q .; then
    echo "Restore archive contains a non-file entry." >&2
    exit 2
fi

for required in \
    state/dashboard.json \
    state/refresh-status.json \
    work/history/hourly_region_features.parquet \
    work/history/flood_articles_archive.parquet
do
    if ! grep -Fxq "$required" "$listing"; then
        echo "Restore refused: backup is missing required application data." >&2
        exit 2
    fi
done

if wget -q -T 2 -O /dev/null http://api:8080/api/v1/health 2>/dev/null; then
    echo "Restore refused: the API is still reachable; stop the application first." >&2
    exit 2
fi

if [ ! -f /state/refresh-status.lock ]; then
    echo "Restore refused: the target refresh lock is unavailable." >&2
    exit 2
fi
exec 9<> /state/refresh-status.lock
if ! flock -xn 9; then
    echo "Restore refused: the target volume is in use." >&2
    exit 2
fi

# A restore is allowed only into fresh target volumes. The lock is created by
# init-volumes and is the sole permitted pre-existing entry.
if find /state -mindepth 1 -maxdepth 1 ! -name refresh-status.lock -print -quit | grep -q .; then
    echo "Restore refused: target state volume is not empty." >&2
    exit 2
fi
if find /work -mindepth 1 -maxdepth 1 -print -quit | grep -q .; then
    echo "Restore refused: target work volume is not empty." >&2
    exit 2
fi

tar -C / -xzf "$archive"

for required_path in \
    /state/dashboard.json \
    /state/refresh-status.json \
    /work/history/hourly_region_features.parquet \
    /work/history/flood_articles_archive.parquet
do
    if [ ! -s "$required_path" ]; then
        echo "Restore failed post-restore validation; discard these fresh target volumes." >&2
        exit 1
    fi
done
if ! python3 /opt/crisispulse/validate_application_data.py \
    --state-root /state \
    --work-root /work
then
    echo "Restore failed semantic validation; discard these fresh target volumes." >&2
    exit 1
fi
chown -R 10001:10001 /state /work
# Archive modes are untrusted input. Normalize the restored application data so
# the non-root API and refresh processes can read and update their own files.
find /state /work -type d -exec chmod 0750 {} +
find /state /work -type f -exec chmod 0640 {} +
chmod 0644 /state/refresh-status.lock
echo "Restore completed in fresh target volumes. Validate them before changing the live volume names."
