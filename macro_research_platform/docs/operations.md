# Operations runbook

How to run, watch, back up and restore the platform — written so that a second person can operate it. The Due
diligence tab (Fund Governance → Due diligence) checks this list against the live record.

## Run

| What | Command (from `macro_research_platform/`) | Port |
|---|---|---|
| Backend | `../.venv/bin/python -m uvicorn api.main:socket_app --host 127.0.0.1 --port 8000` | 8000 |
| Frontend (dev) | `cd frontend && npm run dev` | 5173 |
| Tests | `../.venv/bin/python -m pytest api/tests -q` · `cd frontend && npx vitest run` | — |

Only one backend may hold port 8000. If it is taken: `lsof -nP -iTCP:8000 -sTCP:LISTEN` shows who has it.

## Scheduled jobs (UTC, in the backend's scheduler)

| Job | When | What it leaves behind |
|---|---|---|
| `daily_backup` | 03:15 daily | `backups/auto/<date>/` + `manifest.json` |
| `governance_reconcile` | 06:30 Mon–Fri | reconciliation rows; a break halts execution |
| `governance_monthly_pack` | 07:00 on the 1st | `data/processed/reports/monthly/<fund>/<YYYY-MM>.json` (frozen, never overwritten) |
| `ops_feeds` | every 10 min | `data/processed/monitor/events.jsonl` (incident opened / resolved) |
| `ops_audit` | 22:30 Mon–Fri | `data/processed/audit/accuracy_*.json`; failures become critical events |
| `commodity_curve_snapshot` | 22:45 Mon–Fri | `commodity_curves` table (main db): each commodity's futures curve as of that day — the history commodity carry will be tested on. The Fed's EBP file is also kept per version (`data_vintages`) whenever it changes. Status: `GET /api/v1/ops/archive` |

The scheduler runs only while the backend runs. A job missed while the machine was off runs at the next start if it
is inside its grace period (backup 12 h, monthly pack 3 days).

## Watch

- **System Health** (Macro → System health): feed status, open data incidents, the last accuracy audit, recent events.
- In-app alerts: a feed going down raises a sticky alert; a failed audit raises one too.
- `GET /api/v1/ops/monitor` returns the same as JSON.

## Back up

- Automatic: every database (the main one — accounts, the fund registry, Moriah's ledger and governance record — and
  each fund's `api/funds/*.db`) is copied with SQLite's online-backup API, integrity-checked, and kept for 14 days.
- **Off this disk:** set `BACKUP_COPY_DIR` in `.env` to a folder on another disk or a synced drive (for example
  `~/Library/Mobile Documents/com~apple~CloudDocs/MoriahBackups`). Without it, a disk failure loses the backups too.
- Manual: Fund Governance → Due diligence → *Back up now*, or `POST /api/v1/governance/backup/run`.
- Secrets (`.env`) are not in the backup: keep a copy in a password manager.

## Restore

1. *Test restore* (Due diligence tab) opens the newest backup read-only and checks integrity and row counts — do it
   monthly; the result is recorded for the DDQ.
2. To actually restore: stop the backend; copy `backups/auto/<date>/main.db` over the file `DATABASE_URL` points to
   (default `api/macro_terminal.db`) and `fund_<id>.db` over `api/funds/<id>.db`; delete any `-wal` / `-shm` files
   beside the originals; start the backend; check Fund Governance → Overview and the NAV history.

## Moving to a server (when ready)

The platform is one Python process plus a static frontend; any small Linux VM works. Checklist:

1. Same Python version; `pip install -r requirements.txt`; `npm ci && npm run build` for the frontend.
2. Copy `.env` by hand (never through git) and the databases from the latest backup.
3. Run the backend under a process supervisor (systemd) so it restarts on failure, behind a TLS proxy.
4. Set `BACKUP_COPY_DIR` to storage outside the VM (object storage mount or a second disk).
5. Re-run the accuracy audit against the new host before anyone relies on it.

## Change control

- Work on a branch; the main branch receives only reviewed changes (pull request with the tests green).
- Model changes go through the G0–G5 gates in Fund Governance; the owner cannot sign off their own model.
