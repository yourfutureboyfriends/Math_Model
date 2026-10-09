"""
Academic factor returns — Kenneth French Data Library (free, Dartmouth).

Daily US Fama–French five factors (Mkt-RF, SMB, HML, RMW, CMA), the risk-free rate and the
momentum factor (UMD), from CRSP. Updated monthly by the library (about a month's lag);
cached on disk for a week.

`attribution()` regresses a strategy's daily excess returns on these factors (OLS with
Newey–West standard errors): the intercept is the alpha left after known factor premia —
the question every quant allocator asks ("is this just value + momentum?").
"""
from __future__ import annotations

import io
import logging
import math
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

import numpy as np
import pandas as pd
import requests

logger = logging.getLogger(__name__)
CACHE = Path(__file__).resolve().parents[2] / "data" / "processed" / "factors"
BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
FILES = {"ff5": "F-F_Research_Data_5_Factors_2x3_daily_CSV.zip", "mom": "F-F_Momentum_Factor_daily_CSV.zip"}
TTL = 7 * 86400
NAMES = {"Mkt-RF": "Market", "SMB": "Size (small − big)", "HML": "Value (high − low B/M)",
         "RMW": "Profitability (robust − weak)", "CMA": "Investment (conservative − aggressive)", "Mom": "Momentum (UMD)"}
_mem: Dict[str, Any] = {"ts": 0.0, "df": None}


def _parse(raw: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        text = z.read(z.namelist()[0]).decode("latin-1")
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.strip().startswith(","))
    rows = []
    for l in lines[start + 1:]:
        parts = [p.strip() for p in l.split(",")]
        if len(parts) < 2 or not parts[0].isdigit() or len(parts[0]) != 8:
            break                                     # the daily table ends at the first non-date row
        rows.append(parts)
    cols = [c.strip() for c in lines[start].split(",")[1:]]
    df = pd.DataFrame([r[1:] for r in rows], index=pd.to_datetime([r[0] for r in rows], format="%Y%m%d"), columns=cols)
    df = df.apply(pd.to_numeric, errors="coerce")
    return df.where(df > -99) / 100.0                 # percent → decimal; -99.99 = missing


def factors() -> pd.DataFrame:
    """Daily factor returns (decimal), columns Mkt-RF, SMB, HML, RMW, CMA, RF, Mom."""
    if _mem["df"] is not None and time.time() - _mem["ts"] < 3600:
        return _mem["df"]
    path = CACHE / "ff_daily.pkl"
    df = None
    try:
        if time.time() - path.stat().st_mtime < TTL:
            df = pd.read_pickle(path)
    except Exception:
        pass
    if df is None:
        try:
            parts = []
            for f in FILES.values():
                r = requests.get(BASE + f, timeout=60)
                r.raise_for_status()
                parts.append(_parse(r.content))
            df = parts[0].join(parts[1], how="left")
            CACHE.mkdir(parents=True, exist_ok=True)
            df.to_pickle(path)
        except Exception as e:
            logger.warning("[factors] download failed: %s", e)
            try:
                df = pd.read_pickle(path)                 # stale beats nothing
            except Exception:
                raise RuntimeError("Factor library unavailable (no network and no cached copy).") from e
    _mem.update(ts=time.time(), df=df)
    return df


def _newey_west(X: np.ndarray, resid: np.ndarray, lags: int) -> np.ndarray:
    n = X.shape[0]
    XtX_inv = np.linalg.inv(X.T @ X)
    u = X * resid[:, None]
    S = u.T @ u
    for L in range(1, lags + 1):
        w = 1 - L / (lags + 1)
        G = u[L:].T @ u[:-L]
        S += w * (G + G.T)
    return XtX_inv @ S @ XtX_inv


def attribution(returns: Sequence[float], dates: Sequence[str], model: str = "ff5+mom") -> Dict[str, Any]:
    """Regress daily strategy returns minus the risk-free rate on the factors."""
    f = factors()
    r = pd.Series(np.asarray(returns, float), index=pd.to_datetime(list(dates)))
    cols = ["Mkt-RF", "SMB", "HML", "RMW", "CMA"] + (["Mom"] if "mom" in model else [])
    df = f[cols + ["RF"]].join(r.rename("r"), how="inner").dropna()
    if len(df) < 250:
        return {"available": False, "reason": "Less than a year of overlap with the factor data (it lags about a month)."}
    y = (df["r"] - df["RF"]).to_numpy()
    X = np.column_stack([np.ones(len(df)), df[cols].to_numpy()])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    lags = int(4 * (len(df) / 100) ** (2 / 9))           # Newey–West (1994) rule of thumb
    cov = _newey_west(X, resid, lags)
    se = np.sqrt(np.clip(np.diag(cov), 0, None))
    tstat = np.where(se > 0, beta / se, np.nan)
    r2 = 1 - resid.var() / y.var() if y.var() > 0 else None
    contrib = {c: float(beta[i + 1] * df[c].mean() * 252) for i, c in enumerate(cols)}
    return {"available": True, "model": "Fama–French 5 + momentum" if "mom" in model else "Fama–French 5",
            "start": df.index[0].strftime("%Y-%m-%d"), "end": df.index[-1].strftime("%Y-%m-%d"), "days": len(df),
            "alpha_annual": round(float(beta[0] * 252), 4), "alpha_t": round(float(tstat[0]), 2),
            "r2": round(float(r2), 3) if r2 is not None else None,
            "loadings": [{"factor": c, "name": NAMES.get(c, c), "beta": round(float(beta[i + 1]), 3),
                          "t": round(float(tstat[i + 1]), 2), "return_contribution": round(contrib[c], 4)}
                         for i, c in enumerate(cols)],
            "excess_return_annual": round(float(y.mean() * 252), 4),
            "note": "Alpha is the annual return not explained by the factors (Newey–West t-stats). US equity factors — "
                    "for multi-asset strategies a low R² is expected."}
