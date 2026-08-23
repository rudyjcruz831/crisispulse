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
- Daily compressed backups that preserve the permanent article/feature history and exclude only re-downloadable raw GDELT ZIP files.
- A guarded restore job that refuses to run without explicit confirmation.
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

The local production URL defaults to `http://localhost:8088`. This uses the existing computer and has no CrisisPulse hosting charge.

After the short soak test passes, install the permanent local production schedule:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-production-refresh-task.ps1
```

It repeats every 15 minutes until explicitly removed, starts a missed run when Windows becomes available, skips overlap, and attempts to launch Docker Desktop when the engine is stopped. Collection occurs only while the PC is on, the user is signed in, and internet access is available; after sleep or shutdown, the next available run catches up from the newest overlap. Remove only the schedule with `scripts/uninstall-production-refresh-task.ps1`; this does not remove raw data, permanent history, reviews, or backups.

## First paid server

When the local package has passed a 48-hour soak test, create one Ubuntu 24.04 server with 2 GB RAM, 1 vCPU, and about 50 GB storage. Clone the repository to `/opt/crisispulse`, create `.env.production`, and change these values:

```dotenv
CRISISPULSE_SITE_ADDRESS=your-domain.example
CRISISPULSE_PUBLIC_ORIGIN=https://your-domain.example
CRISISPULSE_HTTP_PORT=80
CRISISPULSE_HTTPS_PORT=443
```

Point the domain to the server, allow inbound TCP ports 80 and 443, and run `sh production/deploy.sh`. Do not place card details, passwords, or the plaintext pilot password in the repository or this chat.

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

To restore, stop the application first, set `RESTORE_ARCHIVE` to a file under `/backups`, set `CONFIRM_RESTORE=YES` for that command only, run the restore service, and start the application again. Restore should be tested on a disposable server before relying on it.

## Reliability and growth limits

This version has one failure domain: if the server or its disk fails, the service is unavailable until restored. The daily backup is stored on the same server by default, so a later paid milestone should copy encrypted backups off-server. At roughly $3,000 monthly recurring revenue—or earlier if customers require an SLA—revisit managed identity, a second server, off-server backups, and automated failover.
