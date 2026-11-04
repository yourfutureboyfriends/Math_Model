"""
Daily backups of every fund's database, kept for 14 days, with an optional second copy off this disk.

  what    the main application database (accounts, the fund registry, Moriah's ledger and governance record) and each
          fund's own database (api/funds/*.db), copied with SQLite's online-backup API, so a copy taken while the
          server is writing is still consistent; then each copy is opened and integrity-checked
  where   backups/auto/<YYYY-MM-DD>/  (gitignored); the 14 newest days are kept
  copy    BACKUP_COPY_DIR (e.g. an iCloud Drive or external-disk folder) receives the same files — a backup on the same
          disk as the server does not survive the disk
  restore stop the server, copy the .db file back over the original, start the server (docs/operations.md)

Each run is recorded in backups/auto/manifest.json — the evidence a due-diligence reviewer asks for (last backup, last
restore test).
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "backups" / "auto"
KEEP_DAYS = 14


def _sources() -> List[Path]:
    from api.core.app_db import app_db_path
    from api.funds import FUNDS_DIR
    out = [Path(app_db_path())]
    if FUNDS_DIR.exists():
        out += sorted(FUNDS_DIR.glob("*.db"))
    return [p for p in out if p.exists()]


def _copy(src: Path, dst: Path) -> Dict[str, Any]:
    with sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=30) as s, sqlite3.connect(dst) as d:
        s.backup(d)
    with sqlite3.connect(dst) as d:
        ok = d.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    return {"file": src.name, "bytes": dst.stat().st_size, "integrity_ok": ok}


def _manifest() -> Dict[str, Any]:
    try:
        return json.loads((DEST / "manifest.json").read_text())
    except Exception:
        return {"runs": []}


def run_backup(dest: Path = DEST) -> Dict[str, Any]:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    target = dest / day
    target.mkdir(parents=True, exist_ok=True)
    files, errors = [], []
    for src in _sources():
        name = "main.db" if src.parent.name != "funds" else f"fund_{src.name}"
        try:
            files.append({**_copy(src, target / name), "file": name})
        except Exception as e:                                                  # noqa: BLE001 — record, carry on
            errors.append(f"{src.name}: {e}")
    copied_to = None
    off = os.getenv("BACKUP_COPY_DIR")
    if off:
        try:
            shutil.copytree(target, Path(off).expanduser() / day, dirs_exist_ok=True)
            copied_to = str(Path(off).expanduser() / day)
        except Exception as e:                                                  # noqa: BLE001
            errors.append(f"off-disk copy: {e}")
    days = sorted(p for p in dest.iterdir() if p.is_dir())
    for old in days[:-KEEP_DAYS]:
        shutil.rmtree(old, ignore_errors=True)
    run = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "day": day, "files": files,
           "ok": bool(files) and not errors and all(f["integrity_ok"] for f in files), "errors": errors,
           "off_disk_copy": copied_to}
    m = _manifest() if dest == DEST else {"runs": []}
    m["runs"] = ([run] + m.get("runs", []))[:60]
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "manifest.json").write_text(json.dumps(m, indent=1))
    return run


def status() -> Dict[str, Any]:
    runs = _manifest().get("runs", [])
    last = runs[0] if runs else None
    return {"last": last, "kept_days": sorted((p.name for p in DEST.iterdir() if p.is_dir()), reverse=True) if DEST.exists() else [],
            "off_disk": bool(os.getenv("BACKUP_COPY_DIR")), "restore_tested": _manifest().get("restore_tested"),
            "note": "Daily at 03:15 UTC; 14 days kept in backups/auto. Set BACKUP_COPY_DIR in .env for a copy off this disk."}


def restore_test() -> Dict[str, Any]:
    """Prove the latest backup restores: open each copy read-only, run the integrity check and count the rows of the
    accounts and NAV tables. Nothing is written back over the live databases."""
    st = status()
    if not st["kept_days"]:
        return {"ok": False, "detail": "No backup to test."}
    day = DEST / st["kept_days"][0]
    checks = []
    for f in sorted(day.glob("*.db")):
        with sqlite3.connect(f"file:{f}?mode=ro", uri=True) as c:
            tabs = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            rows = {t: c.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in ("users", "nav_history", "trades") if t in tabs}
            checks.append({"file": f.name, "integrity_ok": c.execute("PRAGMA integrity_check").fetchone()[0] == "ok",
                           "tables": len(tabs), "rows": rows})
    out = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "day": day.name, "files": checks,
           "ok": bool(checks) and all(c["integrity_ok"] and c["tables"] for c in checks)}
    m = _manifest()
    m["restore_tested"] = out
    (DEST / "manifest.json").write_text(json.dumps(m, indent=1))
    return out
