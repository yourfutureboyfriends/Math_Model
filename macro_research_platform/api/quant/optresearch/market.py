"""
The research panel: one aligned, cached set of daily arrays for the options universe, built once per data day and
reused by every stage and experiment (no re-reading of per-symbol caches).

Universe ("US+PIT" by default): today's US-listed stocks in the tradable universe (US listing, USD quote), the
optionable ETFs below, and every past S&P 500 member since 2010 with free price history (so delisted / removed names
are present where the data permits). `members` marks S&P 500 membership as of each date (point in time). Listed
options exist for US listings; non-US stocks in the GLOBAL universe have no US-listed options and are not simulated.

Arrays (sessions × tickers, float32): close (split- and dividend-adjusted: returns and signals), px (traded share
price: strikes and option marks), high, low (adjusted), volume, observed, exdiv (cash dividend ÷ previous close on
ex-dates), adv (63-session median traded value, USD), members. Series: rf (annualised cash rate, decimal), dates.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
CACHE = Path(__file__).resolve().parents[3] / "data" / "processed" / "quant" / "research" / "panel"
START = "2010-01-04"
ETFS = ["SPY", "QQQ", "IWM", "DIA", "EEM", "EFA", "EWZ", "FXI", "GLD", "SLV", "USO", "TLT", "HYG", "XLF", "XLE",
        "XLK", "SMH", "GDX"]
FIELDS = ("close", "px", "high", "low", "volume", "exdiv", "adv")


@dataclass
class Panel:
    dates: pd.DatetimeIndex
    tickers: List[str]
    a: Dict[str, np.ndarray]                     # field → [T, N] float32 (observed / members: bool)
    rf: np.ndarray                               # cash rate per session, annualised decimal (÷252 for a day)
    info: Dict[str, Dict[str, Any]]              # ticker → {sector, name, kind, today_listed, …}
    meta: Dict[str, Any] = field(default_factory=dict)

    def col(self, t: str) -> int:
        return self.tickers.index(t)

    def frame(self, f: str) -> pd.DataFrame:
        return pd.DataFrame(self.a[f], index=self.dates, columns=self.tickers)

    def subset(self, tickers: List[str]) -> "Panel":
        ix = [self.tickers.index(t) for t in tickers]
        return Panel(self.dates, list(tickers), {k: v[:, ix] for k, v in self.a.items()}, self.rf,
                     {t: self.info[t] for t in tickers}, dict(self.meta, subset=len(tickers)))


def _key(spec: str) -> str:
    return hashlib.sha256(f"{spec}|{START}|v1".encode()).hexdigest()[:12]


def universe_names(spec: str = "US+PIT") -> Dict[str, Any]:
    from api.quant import codeserver, membership
    toks = spec.upper().split("+")
    names: List[str] = []
    today: List[str] = []
    if "US" in toks:
        today = codeserver.tradable_universe("US")
        names += today
    pit: List[str] = []
    if "PIT" in toks:
        pit, _ = membership.universe_since(START)
        names += pit
    if "SMALL" in toks:                                              # stage 2: the liquid index ETFs only
        names += ["SPY", "QQQ", "IWM", "DIA"]
    names = list(dict.fromkeys(ETFS + names)) if "SMALL" not in toks else list(dict.fromkeys(names))
    return {"names": names, "today_us": set(today), "pit": set(pit)}


def build(spec: str = "US+PIT", say=lambda m: None) -> Panel:
    """Load (or reuse today's cached) research panel."""
    from api.quant import codelab, codeserver, membership, rates
    key = _key(spec)
    f = CACHE / f"{key}.npz"
    mf = CACHE / f"{key}.json"
    day = time.strftime("%Y-%m-%d")
    try:
        meta = json.loads(mf.read_text())
        if meta.get("built_day") == day or meta.get("pinned"):
            return load(key)
    except (OSError, ValueError):
        pass
    u = universe_names(spec)
    say(f"Preparing the research panel: {len(u['names'])} underlyings (first build of the day reads the price caches)…")
    t0 = time.time()
    d = codeserver.load_data(u["names"], START, limit=codelab.LARGE_UNIVERSE_LIMIT, allow_missing=True)
    tick = [c for c in d.tickers if c in u["names"]]
    idx = d.close.index
    spy = d.observed["SPY"].to_numpy(bool) if "SPY" in d.tickers else np.ones(len(idx), bool)
    keep = spy                                                       # US sessions (the S&P calendar)
    sess = idx[keep]
    take = lambda fr: fr[tick].to_numpy(np.float32)[keep]
    close = take(d.close)
    px = d.share_px[tick].to_numpy(np.float32)[keep] if d.share_px is not None else close.copy()
    px = np.where(np.isfinite(px), px, close)
    vol = take(d.volume)
    trad = pd.DataFrame(np.where(d.observed[tick].to_numpy()[keep], px * vol, np.nan), index=sess)
    adv = trad.rolling(63, min_periods=20).median().to_numpy(np.float32)
    exdiv = d.div_yield[tick].to_numpy(np.float32)[keep] if d.div_yield is not None else np.zeros_like(close)
    members = membership.members_frame(sess, tick).to_numpy(bool)
    inst = d.instruments
    info = {}
    for c in tick:
        i = inst.get(c, {})
        info[c] = {"name": i.get("name"), "sector": i.get("sector") or ("ETF" if c in ETFS else "Unknown"),
                   "kind": "etf" if c in ETFS else "stock", "today_listed": c in u["today_us"] or c in ETFS,
                   "pit_member_ever": c in u["pit"]}
    rf = (rates.daily(sess, "USD") * 252) if rates.known("USD") else pd.Series(0.0, index=sess)   # annual decimal
    a = {"close": close, "px": px.astype(np.float32), "high": take(d.high), "low": take(d.low), "volume": vol,
         "exdiv": np.nan_to_num(exdiv).astype(np.float32), "adv": adv, "observed": d.observed[tick].to_numpy(bool)[keep],
         "members": members}
    meta = {"spec": spec, "key": key, "built_day": day, "built_seconds": round(time.time() - t0, 1),
            "sessions": len(sess), "tickers": len(tick), "first": str(sess[0].date()), "last": str(sess[-1].date()),
            "requested": len(u["names"]), "missing": sorted(set(u["names"]) - set(tick)),
            "former_members_with_data": sum(1 for c in tick if c in u["pit"] and c not in u["today_us"]),
            "survivorship": "today's US listings plus past S&P 500 members with free price history; removed names "
                            "without free history are absent (counted in 'missing')",
            "provenance": {k: d.provenance.get(k) for k in ("adjustment", "dropped_no_data", "bad_bars_removed")}}
    CACHE.mkdir(parents=True, exist_ok=True)
    np.savez(f.with_suffix(".tmp.npz"), dates=sess.values.astype("datetime64[ns]").astype(np.int64),
             rf=rf.to_numpy(np.float64), **a)
    f.with_suffix(".tmp.npz").replace(f)
    (CACHE / f"{key}.info.json").write_text(json.dumps({"tickers": tick, "info": info}))
    mf.write_text(json.dumps(meta, default=str))
    return load(key)


def load(key: str) -> Panel:
    z = np.load(CACHE / f"{key}.npz")
    ti = json.loads((CACHE / f"{key}.info.json").read_text())
    meta = json.loads((CACHE / f"{key}.json").read_text())
    dates = pd.DatetimeIndex(z["dates"].astype("datetime64[ns]"))
    a = {k: z[k] for k in z.files if k not in ("dates", "rf")}
    return Panel(dates, ti["tickers"], a, z["rf"], ti["info"], meta)


def synthetic(n_days: int = 900, tickers: Optional[List[str]] = None, seed: int = 3, drift: float = 0.08,
              vol: float = 0.2) -> Panel:
    """A small synthetic panel (geometric Brownian motion) for correctness tests — stage 1."""
    tickers = tickers or ["SPY", "AAA", "BBB", "CCC"]
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2015-01-02", periods=n_days)
    n = len(tickers)
    r = rng.normal((drift - 0.5 * vol * vol) / 252, vol / np.sqrt(252), (n_days, n))
    close = (100 * np.exp(np.cumsum(r, axis=0))).astype(np.float32)
    a = {"close": close, "px": close.copy(), "high": close * 1.005, "low": close * 0.995,
         "volume": np.full((n_days, n), 5e6, np.float32), "exdiv": np.zeros((n_days, n), np.float32),
         "adv": np.full((n_days, n), 5e8, np.float32), "observed": np.ones((n_days, n), bool),
         "members": np.ones((n_days, n), bool)}
    info = {t: {"sector": "ETF" if t == "SPY" else f"S{i % 2}", "kind": "etf" if t == "SPY" else "stock",
                "today_listed": True, "pit_member_ever": True} for i, t in enumerate(tickers)}
    return Panel(dates, tickers, a, np.full(n_days, 0.02), info, {"spec": "synthetic", "synthetic": True})
