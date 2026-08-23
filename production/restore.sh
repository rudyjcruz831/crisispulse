#!/bin/sh
set -eu

if [ "${CONFIRM_RESTORE:-NO}" != "YES" ]; then
    echo "Restore refused: set CONFIRM_RESTORE=YES after stopping the application." >&2
    exit 2
fi

archive="${RESTORE_ARCHIVE:-}"
case "$archive" in
    /backups/crisispulse-*.tar.gz) ;;
    *) echo "Restore archive must be a CrisisPulse backup under /backups." >&2; exit 2 ;;
esac
if [ ! -f "$archive" ]; then
    echo "Restore archive does not exist." >&2
    exit 2
fi
if tar -tzf "$archive" | grep -Eq '(^/|(^|/)\.\.(/|$))'; then
    echo "Restore archive contains an unsafe path." >&2
    exit 2
fi

find /state -mindepth 1 -maxdepth 1 ! -name raw -exec rm -rf -- {} +
find /work -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
tar -C / -xzf "$archive"
chown -R 10001:10001 /state /work
echo "Restore complete. Start the application and run a health check."
