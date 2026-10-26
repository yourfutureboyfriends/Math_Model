"""
Custom data for Quant Lab strategies: a CSV the user uploads once (a date column and numeric columns), used by name:

    CUSTOM_DATA = ["fed_sentiment"]                       # plain strategies: data.custom["fed_sentiment"]["value"]
    self.add_data(MyData, "fed_sentiment")                # QuantConnect-style: slice[symbol].value, history(symbol)

Strategy code never reads files or URLs (the sandbox has no file or network access); the platform aligns the series to
the backtest's trading days as of each row's date — a value dated d is known from d's close, carried forward until the
next row, never visible earlier. The `_new` column marks sessions with a fresh row.
"""
from __future__ import annotations

import io
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence

import numpy as np
import pandas as pd

DIR = Path(__file__).resolve().parents[2] / "data" / "processed" / "quant_custom_data"      # gitignored
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
MAX_BYTES = 200_000_000
MAX_ROWS = 20_000_000
MAX_COLS = 2_000


def _path(name: str) -> Path:
    return DIR / f"{name}.csv"


def parse(text: str) -> pd.DataFrame:
    """A CSV with a date column (the first column, or one named date / time / timestamp) and numeric columns."""
    if not text or len(text.encode()) > MAX_BYTES:
        raise ValueError(f"The CSV must be non-empty and under {MAX_BYTES // 1_000_000} MB.")
    df = pd.read_csv(io.StringIO(text))
    if df.empty or len(df.columns) < 2:
        raise ValueError("Need a date column and at least one numeric column.")
    dcol = next((c for c in df.columns if str(c).strip().lower() in ("date", "time", "timestamp", "datetime")), df.columns[0])
    dates = pd.to_datetime(df[dcol], errors="coerce", utc=False)
    if dates.isna().mean() > 0.05:
        raise ValueError(f"Column '{dcol}' is not readable as dates (over 5% of rows failed).")
    out = df.drop(columns=[dcol]).apply(pd.to_numeric, errors="coerce")
    out = out.loc[:, out.notna().any()]
    if out.empty:
        raise ValueError("No numeric columns found.")
    out.columns = [re.sub(r"[^a-z0-9_]", "_", str(c).strip().lower())[:40] or f"col{i}" for i, c in enumerate(out.columns)]
    if len(out.columns) > MAX_COLS or len(out) > MAX_ROWS:
        raise ValueError(f"At most {MAX_COLS} columns and {MAX_ROWS:,} rows.")
    out.index = pd.DatetimeIndex(dates).tz_localize(None).normalize()
    out = out[out.index.notna()].sort_index()
    return out[~out.index.duplicated(keep="last")]


def save(name: str, text: str, owner: str) -> Dict[str, Any]:
    name = (name or "").strip().lower()
    if not NAME_RE.match(name):
        raise ValueError("Name: 1–40 characters, lowercase letters, digits and _, starting with a letter.")
    df = parse(text)
    DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(_path(name), index_label="date")
    meta = {"name": name, "owner": owner, "rows": int(len(df)), "columns": list(df.columns),
            "first": str(df.index[0].date()), "last": str(df.index[-1].date()), "uploaded_at": datetime.now().isoformat(timespec="seconds")}
    (DIR / f"{name}.json").write_text(json.dumps(meta))
    return meta


def catalog() -> List[Dict[str, Any]]:
    if not DIR.exists():
        return []
    out = []
    for p in sorted(DIR.glob("*.json")):
        try:
            out.append(json.loads(p.read_text()))
        except Exception:                                                  # noqa: BLE001
            continue
    return out


def delete(name: str, owner: str, is_admin: bool = False) -> bool:
    meta_p = DIR / f"{name}.json"
    if not NAME_RE.match(name or "") or not meta_p.exists():
        raise LookupError("No such dataset.")
    if not is_admin and json.loads(meta_p.read_text()).get("owner") != owner:
        raise PermissionError("Only the uploader (or an admin) can delete it.")
    meta_p.unlink()
    _path(name).unlink(missing_ok=True)
    return True


def load(name: str) -> pd.DataFrame:
    if not NAME_RE.match(name or "") or not _path(name).exists():
        raise ValueError(f"Custom data '{name}' has not been uploaded (Quant Lab → Custom data).")
    df = pd.read_csv(_path(name), index_col=0, parse_dates=True)
    return df.astype(float)


def align(df: pd.DataFrame, index: pd.DatetimeIndex) -> pd.DataFrame:
    """As-of alignment to trading days: each session sees the latest row dated on or before it; `_new` = 1 on sessions
    that received a row since the previous session."""
    idx = pd.DatetimeIndex(index).normalize()
    pos = idx.searchsorted(df.index, side="left")                      # the first session on/after each row's date
    pos = pos[pos < len(idx)]
    out = df.reindex(idx, method="ffill")
    new = np.zeros(len(idx))
    new[np.unique(pos)] = 1.0
    out["_new"] = new
    out.index = index
    return out


def frames(names: Sequence[str], index: pd.DatetimeIndex) -> Dict[str, pd.DataFrame]:
    return {n: align(load(n), index) for n in dict.fromkeys(names or [])}


def spec(value: Any) -> List[str]:
    if value in (None, False, "", []):
        return []
    vals = [value] if isinstance(value, str) else list(value)
    names = [str(v).strip().lower() for v in vals]
    bad = [n for n in names if not NAME_RE.match(n)]
    if bad:
        raise ValueError(f"CUSTOM_DATA names must be lowercase identifiers (not {bad[0]!r}).")
    return names
