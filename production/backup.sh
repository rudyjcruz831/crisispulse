#!/bin/sh
set -eu

umask 077
retention_days="${CRISISPULSE_BACKUP_RETENTION_DAYS:-14}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
temporary="/backups/crisispulse-${timestamp}.tar.gz.partial"
destination="/backups/crisispulse-${timestamp}.tar.gz"

mkdir -p /backups
tar --exclude='state/raw' -C / -czf "$temporary" state work
mv "$temporary" "$destination"
find /backups -maxdepth 1 -type f -name 'crisispulse-*.tar.gz' -mtime "+${retention_days}" -delete
printf '%s\n' "$destination"
