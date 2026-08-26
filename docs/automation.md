# CrisisPulse automatic refresh

The local refresh workflow keeps CrisisPulse current without Docker, a cloud account, or a paid scheduler. Windows Task Scheduler can invoke the same tested script every 15 minutes.

## What one refresh does

1. Acquires an exclusive lock. If an earlier refresh still runs, the new invocation exits successfully without overlap.
2. Confirms which advertised GDELT GKG file is actually available, safely backtracking past temporary 404s when the index is ahead of storage, then downloads the newest eight-file window into `%USERPROFILE%\.crisispulse\raw` using checksums, temporary files, and idempotent destinations.
3. Starts at the first hour boundary inside that overlap, then processes the remaining files through cleaning, review sampling, regional/hourly features, and the anomaly scorer. This avoids treating a cut-off leading hour as complete.
4. Merges feature rows into compact history by hour and disaster type, replacing each refreshed hour as one partition so regional rows that disappear are not left stale.
5. Re-scores the accumulated history and atomically writes `%USERPROFILE%\.crisispulse\dashboard.json` for the Go API.
6. In the Docker production workflow, upserts all current flood-matched articles into a permanent compressed Parquet archive and verifies the new archive before continuing.
7. Applies checked-in, human-audited title overrides and checks a rotating batch of up to 12 archived articles that still lack a trustworthy publisher title. The safe reader reuses the same cache and robots/network protections, advances past blocked pages so they cannot starve the queue, and atomically saves successful titles back into the permanent archive. Overrides supply evidence without creating a crawler exception for a publisher that prohibits automation.
8. Builds the stable daily article-quality sample from permanent history so filtering can be reviewed even when no alerts fire.
9. Keeps raw ZIPs within a 10,000,000,000-byte (10 GB) budget and removes the oldest files first. The newest refresh window is always protected, and a failed archive verification prevents all pruning.
10. Atomically writes the outcome to `refresh-status.json`, including permanent-archive rows, bytes, title-backfill progress, a capped terminal-run ledger, and the active 48-hour reliability proof.

The two-hour overlap is deliberate: it lets a partial current hour be replaced by a complete hour on a later run without double-counting.

## Validate once manually

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-refresh.ps1
```

Inspect the local status:

```powershell
Get-Content "$env:USERPROFILE\.crisispulse\refresh-status.json"
```

A successful production status includes the first and last source filenames, the count of downloaded versus already-present files, the count processed from the first safe hour boundary, permanent article rows and bytes, title-backfill attempts/updates/remaining rows, retained raw-file count and bytes, the configured storage limit, any files pruned by retention, and bounded reliability evidence. The proof requires 48 observed hours and at least 95% schedule coverage. Failures, interrupted attempts, clock rollback, or gaps longer than 30 minutes restart it; sleep time never advances it.

## Enable the 15-minute task

After the manual run succeeds:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-refresh-task.ps1
```

The task runs only on this PC under Windows Task Scheduler. It does not create a Codex automation, cloud job, account, or paid resource. It uses the Windows Script Host launcher with a hidden window, so normal refreshes do not flash a terminal on the desktop. By default, Task Scheduler skips concurrent instances and starts a missed run when the PC becomes available.

## Disable automation

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall-refresh-task.ps1
```

Removing the task stops future scheduled runs but does not delete raw data, compact history, dashboard data, or status records.

## Linux production timer

The optional single-server package uses the same 15-minute overlap and retention rules through `pipelines.run_refresh`. It runs as a one-shot container with an advisory state lock and atomic status/dashboard writes. A systemd timer invokes the container every 15 minutes with `Persistent=true`, so a missed run is started after the server returns. See [the production deployment guide](production-deployment.md) for installation and backup timers.

## Storage and failure behavior

- Raw ZIPs live outside OneDrive by default and use a 10 GB oldest-first storage budget.
- Permanent article and compact feature Parquet history remain under `data/history`, are compressed, and are ignored by Git.
- Raw ZIPs, the live dashboard JSON, and refresh status remain under `%USERPROFILE%\.crisispulse`, outside OneDrive.
- Temporary two-hour input copies are removed whether the run succeeds or fails.
- Raw retention pruning occurs only after article archival is verified and the remaining processing and dashboard export succeed. It never removes the newest processing window.
- Failures remain visible in the status file, while `last_success_at` preserves the most recent successful cycle. Normal in-progress runs retain the last successful operational counts and do not trigger a false degraded alert.
