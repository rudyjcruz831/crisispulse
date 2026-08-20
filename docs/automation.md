# CrisisPulse automatic refresh

The local refresh workflow keeps CrisisPulse current without Docker, a cloud account, or a paid scheduler. Windows Task Scheduler can invoke the same tested script every 15 minutes.

## What one refresh does

1. Acquires an exclusive lock. If an earlier refresh still runs, the new invocation exits successfully without overlap.
2. Downloads the newest eight GDELT GKG files into `%USERPROFILE%\.crisispulse\raw` using checksums, temporary files, and idempotent destinations.
3. Starts at the first hour boundary inside that overlap, then processes the remaining files through cleaning, review sampling, regional/hourly features, and the anomaly scorer. This avoids treating a cut-off leading hour as complete.
4. Merges feature rows into compact history by hour and disaster type, replacing each refreshed hour as one partition so regional rows that disappear are not left stale.
5. Re-scores the accumulated history and atomically writes `%USERPROFILE%\.crisispulse\dashboard.json` for the Go API.
6. Keeps the newest 672 raw ZIPs and removes older ZIPs, capping normal retention at seven days.
7. Writes the outcome to `%USERPROFILE%\.crisispulse\refresh-status.json`.

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

A successful status includes the first and last source filenames, the count of downloaded versus already-present files, the count processed from the first safe hour boundary, retained raw-file count, and any files pruned by retention.

## Enable the 15-minute task

After the manual run succeeds:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-refresh-task.ps1
```

The task runs only on this PC under Windows Task Scheduler. It does not create a Codex automation, cloud job, account, or paid resource. By default, Task Scheduler skips concurrent instances and starts a missed run when the PC becomes available.

## Disable automation

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall-refresh-task.ps1
```

Removing the task stops future scheduled runs but does not delete raw data, compact history, dashboard data, or status records.

## Storage and failure behavior

- Raw ZIPs live outside OneDrive by default and are limited to 672 files.
- Compact Parquet history remains under `data/history` and is ignored by Git.
- Raw ZIPs, the live dashboard JSON, and refresh status remain under `%USERPROFILE%\.crisispulse`, outside OneDrive.
- Temporary two-hour input copies are removed whether the run succeeds or fails.
- Raw retention pruning occurs only after processing and dashboard export succeed.
- Failures remain visible in the status file, while `last_success_at` preserves the most recent successful cycle.
