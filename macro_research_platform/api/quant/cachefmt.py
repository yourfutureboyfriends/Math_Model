"""
Portable on-disk caches for DataFrames (and {name: DataFrame} dicts): Parquet via pyarrow, written
atomically. A legacy pickle at the same base path (written by this server) is read once and migrated;
an unreadable file — e.g. a pickle from another pandas version — is treated as absent, so the caller
re-downloads instead of half-using it.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

import pandas as pd

logger = logging.getLogger(__name__)


def _pq(path: Path) -> Path:
    return Path(path).with_suffix(".parquet")


def mtime(path: Path) -> Optional[float]:
    for p in (_pq(path), Path(path)):
        try:
            return p.stat().st_mtime
        except OSError:
            continue
    return None


def write(obj: Union[pd.DataFrame, Dict[str, pd.DataFrame]], path: Path) -> None:
    p = _pq(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(obj, dict):
        frame = pd.concat({str(k): v for k, v in obj.items()}, axis=1) if obj else pd.DataFrame()
        frame.attrs = {}
    else:
        frame = obj.copy()
        frame.columns = [str(c) for c in frame.columns] if not isinstance(frame.columns, pd.MultiIndex) else frame.columns
    tmp = p.with_suffix(".parquet.tmp")
    frame.to_parquet(tmp)
    os.replace(tmp, p)


def read(path: Path, as_dict: bool = False) -> Optional[Any]:
    p = _pq(path)
    if p.exists():
        try:
            df = pd.read_parquet(p)
            return _split(df) if as_dict else df
        except Exception as e:                               # noqa: BLE001
            logger.warning("[cache] unreadable %s: %s", p.name, e)
            return None
    legacy = Path(path)
    if legacy.exists() and legacy.suffix == ".pkl":
        try:
            obj = pd.read_pickle(legacy)
        except Exception as e:                               # noqa: BLE001
            logger.warning("[cache] legacy pickle %s unreadable (%s) — will refresh", legacy.name, e)
            return None
        try:
            write(obj, path)
            os.utime(_pq(path), (legacy.stat().st_atime, legacy.stat().st_mtime))   # keep its age
            legacy.unlink()
        except Exception as e:                               # noqa: BLE001
            logger.info("[cache] could not migrate %s: %s", legacy.name, e)
        return obj
    return None


def _split(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    if not isinstance(df.columns, pd.MultiIndex):
        return {}
    out = {}
    for k in df.columns.get_level_values(0).unique():
        out[str(k)] = df[k].dropna(how="all")
    return out
