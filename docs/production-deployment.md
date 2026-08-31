# CrisisPulse single-server production package

## Current status

The production package is built locally but **no paid server or cloud resource has been activated**. The current Windows dashboard and 15-minute task continue to cost $0. A server starts costing money only after an account is created and a billable machine is turned on.

The first paid-pilot architecture is intentionally small:

```text
Customer browser
      |
      v
Caddy: HTTPS + shared pilot login
      |------------------------|
      v                        v
React dashboard            Go API
                               |
                               v
                    persistent state volume
                               ^
                               |
                  15-minute Python refresh
                               |
                               v
                         free GDELT data
```

One server runs the dashboard, API, refresh worker, health monitor, and daily backup job. This is suitable for the first roughly 5–25 pilot users; it is not high availability.

## What the package provides

- Password protection for the entire pilot, including `/admin` and review writes.
- Automatic HTTPS when a real domain is supplied.
- Restart-on-crash and restart-after-reboot behavior.
- A Linux-native, locked 15-minute refresh with persistent state.
- Clear URL-headline mismatch filtering before an item can create an alert.
- A health monitor that logs stale refreshes and can call an optional webhook.
- Daily verified backups that wait for the refresh lock, preserve review logs and permanent history, and exclude only re-downloadable raw GDELT ZIP files and the runtime lock.
- A sanitized atomic backup-status record containing verification time, archive size, and SHA-256 checksum.
- A guarded fresh-volume restore that refuses corrupt or unsafe archives, a reachable API, a busy lock, and every nonempty target volume.
- A one-command build/update script after the server is prepared.

## Local no-cost validation

Copy `.env.production.example` to `.env.production`. Generate a Caddy password hash interactively so the password is not stored in shell history:

```sh
docker compose --env-file .env.production -f compose.production.yml run --rm --no-deps caddy hash-password
```

Put only the generated hash in `.env.production`, then run:

```sh
sh production/deploy.sh
sh production/smoke-test.sh
```

The default smoke test verifies that health is public while the dashboard,
admin page, and snapshot reject unauthenticated requests. To check the private
flows too, use `CRISISPULSE_SMOKE_AUTH=1 sh production/smoke-test.sh`. `curl`
prompts for the shared pilot password; the plaintext is not placed in the
repository, environment file, or command line.

The local production URL defaults to `http://localhost:8088`. This uses the existing computer and has no CrisisPulse hosting charge.

After the short soak test passes, install the permanent local production schedule:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-production-refresh-task.ps1
```

It repeats every 15 minutes until explicitly removed, starts a missed run when Windows becomes available, skips overlap, and attempts to launch Docker Desktop when the engine is stopped. The refresh container is capped at eight CPUs by default so the browser and desktop remain responsive; change `CRISISPULSE_REFRESH_CPUS` only after measuring the effect. The scheduled action uses the hidden Windows Script Host launcher, so it does not flash a PowerShell or Docker terminal during normal runs. Collection occurs only while the PC is on, the user is signed in, and internet access is available; after sleep or shutdown, the next available run catches up from the newest overlap. Remove only the schedule with `scripts/uninstall-production-refresh-task.ps1`; this does not remove raw data, permanent history, reviews, or backups.

Install the local verified daily backup schedule separately:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-encrypted-offsite-backup.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\install-production-backup-task.ps1
```

The one-time setup keeps plaintext archives under the current Windows user's
local application-data folder and sends only authenticated encrypted
`.cpbackup.p7m` copies to the registered OneDrive folder. It creates a
password-protected recovery bundle in OneDrive and a recovery-code file outside
OneDrive. Save both values from that recovery code in a password manager or on
paper; neither the repository nor OneDrive contains them. Setup performs a real
decrypt, authentication, and checksum test with the exported recovery bundle
before publishing its configuration.

The schedule default is 07:10 UTC—3:10 AM EDT or 2:10 AM EST—between the normal
15-minute refresh boundaries. The UTC boundary keeps the schedule stable through
daylight-saving and Windows time-zone changes. It starts the missed backup after
the next sign-in if the PC was off, waits for any refresh to finish, excludes
only re-downloadable raw ZIP files, encrypts and verifies the off-device copy,
and runs through the same hidden launcher. Remove only this schedule with
`scripts/uninstall-production-backup-task.ps1`; existing local and encrypted
backup archives are retained.

## First paid server

When the local package has passed a 48-hour soak test, create one Ubuntu 24.04 server with 2 GB RAM, 1 vCPU, and about 50 GB storage. Clone the repository to `/opt/crisispulse`, create `.env.production`, and change these values:

```dotenv
CRISISPULSE_SITE_ADDRESS=your-domain.example
CRISISPULSE_PUBLIC_ORIGIN=https://your-domain.example
CRISISPULSE_HTTP_PORT=80
CRISISPULSE_HTTPS_PORT=443
CRISISPULSE_STATE_VOLUME=crisispulse_crisis_state
CRISISPULSE_WORK_VOLUME=crisispulse_crisis_work
CRISISPULSE_REFRESH_CPUS=0.75
```

Point the domain to the server, allow inbound TCP ports 80 and 443, and run `sh production/deploy.sh`. Do not place card details, passwords, or the plaintext pilot password in the repository or this chat.

Do not expose the paid server to the internet until the host or edge has failed-login throttling (for example, a tested firewall/fail2ban rule or provider edge rate limit) in front of Caddy Basic Auth. Password hashing is deliberately CPU-intensive, so a strong password alone does not prevent a parallel login spray from exhausting a one-CPU pilot server. Before inviting a user, verify normal login, repeated `401` responses, the throttle/temporary block, recovery after its cooldown, and continued access to the public health endpoint. This is a paid-server deployment gate; it is not needed for the loopback-only no-cost soak.

Install the timers after the first successful refresh:

```sh
sudo cp production/systemd/crisispulse-*.service production/systemd/crisispulse-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now crisispulse-refresh.timer crisispulse-backup.timer
```

The unit files assume the repository is at `/opt/crisispulse`.

## Operations

- Public service health: `https://your-domain.example/api/v1/health`
- Private operations page: `https://your-domain.example/admin`
- Refresh logs: `sudo journalctl -u crisispulse-refresh.service`
- Application status: `docker compose --env-file .env.production -f compose.production.yml ps`
- Manual backup: `docker compose --env-file .env.production -f compose.production.yml --profile maintenance run --rm backup`
- Latest sanitized backup verification: read `backup-status.json` from the directory configured by `CRISISPULSE_BACKUP_DIR`.

Every successful backup is fully listed before publication, requires the core
dashboard/status/history files, rejects unsafe and non-file entries, writes an
adjacent `.sha256` sidecar for that exact archive, and updates
`backups/backup-status.json` atomically. A failed run records only `failed`; it
does not expose host paths or raw tool errors through the API. The archive
includes `reviews.jsonl` and `article-reviews.jsonl` whenever they exist. The
same-server copy is operational convenience, not disaster recovery. On the
Windows pilot, `run-production-backup.ps1` encrypts the exact archive named by
the verified status, decrypts it again to verify size and SHA-256, then publishes
it atomically in OneDrive. A file in the local OneDrive folder is not proof of a
completed upload; confirm the encrypted file and `Recovery` folder are visible
on OneDrive's website before accepting paid review work.

After total PC loss, clone this repository, download an encrypted `.cpbackup.p7m` file
and the password-protected PFX from OneDrive, then run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\restore-encrypted-offsite-backup.ps1 `
  -EncryptedBackupPath "C:\path\to\crisispulse-YYYYMMDDTHHMMSSZ.tar.gz.cpbackup.p7m" `
  -RecoveryBundlePath "C:\path\to\CrisisPulse-Backup-Recovery-v2.pfx"
```

The command prompts for the separately saved recovery password and
authentication key, decrypts without installing the private key, verifies the
authentication tag, size, and SHA-256, checks the tar archive, and refuses to
overwrite an existing restored file. Windows PowerShell caps this in-memory
format at 64 MiB per local archive; migrate to a streaming authenticated format
before backups approach that boundary.

## Restore drill with fresh volumes

Never point the restore service at the live volume names. It deliberately
refuses nonempty targets and never deletes files. Use an exact reviewed archive
name and new volume names:

```sh
sudo systemctl stop crisispulse-refresh.timer crisispulse-backup.timer
docker compose --env-file .env.production -f compose.production.yml stop caddy monitor api dashboard

export CRISISPULSE_STATE_VOLUME=crisispulse_restore_state_20260825
export CRISISPULSE_WORK_VOLUME=crisispulse_restore_work_20260825
export RESTORE_ARCHIVE=/backups/crisispulse-YYYYMMDDTHHMMSSZ.tar.gz
export CONFIRM_RESTORE=YES

docker compose --env-file .env.production -f compose.production.yml --profile maintenance run --rm restore
unset CONFIRM_RESTORE RESTORE_ARCHIVE
```

Restore verifies the selected archive against its own `.sha256` sidecar before
opening it. The init service creates the sole allowed pre-existing file,
`refresh-status.lock`. Restore first proves the archive is readable, safe, and
contains the dashboard, refresh status, feature history, and permanent article
archive. It then requires the API to be unreachable, takes the same lock
exclusively, extracts into the fresh volumes, and repeats required-file checks.

Validate the restored data before directing public traffic to it:

```sh
docker compose --env-file .env.production -f compose.production.yml up -d api dashboard local-preview
docker compose --env-file .env.production -f compose.production.yml exec -T api \
  wget -q -O - http://127.0.0.1:8080/api/v1/admin/status
```

Compare archived-article and review counts with the source installation. If the
drill passes, write the two tested volume names into `.env.production`, unset
the two exported volume variables so Compose reads the saved values, then start
the protected services, run both smoke-test modes, and resume the timers. The
old live volumes remain untouched and provide the immediate rollback target.
If validation fails, unset the two exported variables, retain the previous
volume names in `.env.production`, and restart the old installation; retain the
failed fresh volumes for diagnosis.

## Deployment and rollback

`production/deploy.sh` now detects existing data in the configured state or
work volume and refuses to update it unless a new pre-deploy backup completes
with `verified` status. It
builds Caddy, API, dashboard, monitor, and refresh images so an older auxiliary
image cannot survive an update.

Before deploying, record the current commit and image list. Keep that commit,
the old Docker volumes, and the verified pre-deploy archive until the release
has completed its observation window. Roll back immediately for any of these:

- authentication bypass, invalid HTTPS, or protected content available without a login;
- API, dashboard, or Caddy restart loops, or more than 5% request failures for five minutes;
- two consecutive refresh failures, no successful refresh for 30 minutes, or a refresh approaching the 14-minute timeout;
- an unexpected article-count decrease, missing or unwritable review logs, or invalid dashboard data;
- failed backup verification, a verified backup older than 26 hours, an OOM kill, or less than 20% disk space remaining.

For a code-only problem, stop the timers, capture logs, check out the recorded
last-known-good commit, rebuild all five images, and run the smoke test. Preserve
the live volumes when the data format is compatible. For suspected state or
schema corruption, keep the bad volumes untouched and promote a successfully
validated fresh-volume restore instead. Resume timers only after public health,
authentication, admin status, snapshot loading, record counts, and a new manual
backup all pass.

## Reliability and growth limits

This version has one compute failure domain: if the server fails, the service is
unavailable until restored. A verified encrypted off-server backup is required
before the paid pilot because the local backup directory shares the server's
disk. At roughly $3,000 monthly recurring revenue—or earlier if customers
require an SLA—revisit managed identity, a second server, and automated failover.
