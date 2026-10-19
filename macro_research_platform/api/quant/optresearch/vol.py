"""
Implied volatility for the research simulator, and the observed CBOE series used to check it.

Observed (CBOE, free daily history from cdn.cboe.com):
  * at-the-money implied volatility proxies — VIX-method 30-day indices for 16 underlyings since 2011 (SPY: the whole
    term structure VIX9D / VIX / VIX3M / VIX6M);
  * strategy benchmark indices — PUT (S&P 500 put-write), CNDR (iron condor: short ~20-delta put and call, long
    ~5-delta wings, monthly, held to expiry), BFLY, BXM, BXMD, PPUT, CLL, WPUT, CMBO. CBOE back-calculated the early
    history of several of these before their launch dates; they are still CBOE's published series.

A VIX-method index measures a variance swap rate, which sits above at-the-money volatility because of the skew; ATM is
taken as 0.92 × the index for broad equity indices and 0.96 × for single stocks and commodity/bond ETFs (assumption,
tested for the index case against PUT and CNDR).

Modelled (single stocks without a CBOE index): log ATM-IV = a + b₁ log(blended realised vol) + b₂ log(VIX) +
b₃ log(S&P realised vol) + c·[single stock], fitted by OLS on the observed-IV names up to 2018-12-31 and evaluated on
2019 onward (`iv_model_report`). Term structure: the S&P 500's (VIX pillars, interpolated in total variance), applied as
a ratio — fully for ETFs, square-rooted for single stocks, whose term structures are flatter.
"""
from __future__ import annotations

import io
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
CACHE = Path(__file__).resolve().parents[3] / "data" / "processed" / "quant" / "research" / "cboe"
URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{sym}_History.csv"
TTL = 20 * 3600
TRAIN_END = "2018-12-31"

# underlying → (CBOE index, kind). SPY carries the full term structure separately.
OBSERVED_IV: Dict[str, Tuple[str, str]] = {
    "SPY": ("VIX", "index"), "QQQ": ("VXN", "index"), "DIA": ("VXD", "index"), "IWM": ("RVX", "index"),
    "AAPL": ("VXAPL", "stock"), "AMZN": ("VXAZN", "stock"), "GOOGL": ("VXGOG", "stock"), "GOOG": ("VXGOG", "stock"),
    "GS": ("VXGS", "stock"), "IBM": ("VXIBM", "stock"), "EEM": ("VXEEM", "index"), "EWZ": ("VXEWZ", "index"),
    "FXI": ("VXFXI", "index"), "SLV": ("VXSLV", "commodity"), "GLD": ("GVZ", "commodity"), "USO": ("OVX", "commodity"),
    "TLT": ("VXTLT", "bond"),
}
ATM_SCALE = {"index": 0.92, "stock": 0.96, "commodity": 0.96, "bond": 0.96}
SPY_TERM = [("VIX9D", 9), ("VIX", 30), ("VIX3M", 93), ("VIX6M", 182)]
STRATEGY_INDICES = {
    "PUT": "S&P 500 PutWrite: sells a monthly ATM put, fully collateralised in T-bills",
    "CNDR": "S&P 500 Iron Condor: short ~20-delta put & call, long ~5-delta wings, monthly, held to expiry",
    "BFLY": "S&P 500 Iron Butterfly: short ATM straddle, long ~5-delta wings, monthly",
    "BXM": "S&P 500 BuyWrite: long index, short monthly ATM call",
    "BXMD": "S&P 500 30-Delta BuyWrite",
    "PPUT": "S&P 500 5% Put Protection: long index, long monthly 5% OTM put",
    "CLL": "S&P 500 95-110 Collar",
    "WPUT": "S&P 500 One-Week PutWrite",
    "CMBO": "S&P 500 Covered Combo: long index, short ATM call and put",
}
ETF_KIND = {"SPY": "index", "QQQ": "index", "DIA": "index", "IWM": "index", "EEM": "index", "EFA": "index",
            "EWZ": "index", "FXI": "index", "XLF": "index", "XLE": "index", "XLK": "index", "SMH": "index",
            "GLD": "commodity", "SLV": "commodity", "USO": "commodity", "GDX": "commodity", "TLT": "bond", "HYG": "bond"}


def kind_of(sym: str, asset_type: str = "") -> str:
    if sym in ETF_KIND:
        return ETF_KIND[sym]
    return "index" if asset_type.upper() in ("ETF", "FUND") else "stock"


# ── CBOE data ────────────────────────────────────────────────────────────────
def cboe(sym: str, refresh: bool = True) -> Optional[pd.Series]:
    """Daily close of a CBOE index (cached; a stale copy if CBOE is unreachable)."""
    f = CACHE / f"{sym}.parquet"
    try:
        if not refresh or time.time() - f.stat().st_mtime < TTL:
            return pd.read_parquet(f).iloc[:, 0]
    except (OSError, ValueError):
        pass
    try:
        import requests
        r = requests.get(URL.format(sym=sym), timeout=30, headers={"User-Agent": "Mozilla/5.0 (macro research terminal)"})
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        col = "CLOSE" if "CLOSE" in df.columns else df.columns[-1]
        s = pd.Series(pd.to_numeric(df[col], errors="coerce").to_numpy(),
                      index=pd.to_datetime(df["DATE"], format="%m/%d/%Y"), name=sym).dropna()
        s = s[s > 0].sort_index()
        s = s[~s.index.duplicated(keep="last")]
        if len(s):
            CACHE.mkdir(parents=True, exist_ok=True)
            tmp = f.with_suffix(".tmp")
            s.to_frame().to_parquet(tmp)
            tmp.replace(f)
            return s
    except Exception as e:                                          # noqa: BLE001 — stale beats nothing
        logger.warning("[optresearch] CBOE %s unavailable: %s", sym, str(e)[:120])
    try:
        return pd.read_parquet(f).iloc[:, 0]
    except (OSError, ValueError):
        return None


def quality(s: pd.Series, sessions: pd.DatetimeIndex) -> Dict[str, Any]:
    """Coverage and staleness of an observed series over the research sessions (runs of an unchanged value ≥ 5
    sessions are flagged — a stopped feed, not a calm market)."""
    x = s.reindex(sessions)
    have = x.notna()
    runs, cur, worst = 0, 0, 0
    prev = None
    for v in x.dropna().to_numpy():
        cur = cur + 1 if prev is not None and v == prev else 0
        if cur == 4:
            runs += 1
        worst = max(worst, cur + 1)
        prev = v
    return {"first": str(s.index[0].date()) if len(s) else None, "last": str(s.index[-1].date()) if len(s) else None,
            "coverage": round(float(have.mean()), 3), "stale_runs": runs, "longest_unchanged": int(worst)}


# ── Realised volatility features ─────────────────────────────────────────────
def realised(close: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """Annualised close-to-close realised volatility: EWMA (half-life 10 sessions), 63 and 126 sessions, and the blend
    the IV model uses. Causal (uses returns up to and including each day)."""
    lr = np.log(close / close.shift(1)).replace([np.inf, -np.inf], np.nan)
    ew = np.sqrt((lr ** 2).ewm(halflife=10, min_periods=15).mean() * 252)
    r63 = lr.rolling(63, min_periods=40).std() * np.sqrt(252)
    r126 = lr.rolling(126, min_periods=80).std() * np.sqrt(252)
    r21 = lr.rolling(21, min_periods=15).std() * np.sqrt(252)
    blend = (0.5 * ew + 0.3 * r63 + 0.2 * r126.fillna(r63)).clip(lower=0.03)
    return {"rv21": r21, "ewma": ew, "rv63": r63, "rv126": r126, "blend": blend}


# ── ATM implied volatility ───────────────────────────────────────────────────
def observed_atm(tickers: List[str], sessions: pd.DatetimeIndex) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """30-day ATM IV for the underlyings with a CBOE index (NaN elsewhere) and a coverage report."""
    out, rep = {}, {}
    for t in tickers:
        if t not in OBSERVED_IV:
            continue
        idx, kind = OBSERVED_IV[t]
        s = cboe(idx)
        if s is None:
            rep[t] = {"index": idx, "error": "unavailable"}
            continue
        s = s[(s > 3) & (s < 300)] / 100.0 * ATM_SCALE[kind]
        out[t] = s.reindex(s.index.union(sessions)).ffill(limit=3).reindex(sessions)
        rep[t] = {"index": idx, "kind": kind, **quality(s, sessions)}
    return pd.DataFrame(out, index=sessions).reindex(columns=tickers), rep


def spy_term(sessions: pd.DatetimeIndex) -> Tuple[np.ndarray, np.ndarray]:
    """(pillar tenors in years, ATM vols [session × pillar]) of the S&P 500 term structure. A missing pillar takes the
    nearest available one (VIX9D starts in 2011)."""
    cols = []
    for sym, _ in SPY_TERM:
        s = cboe(sym)
        cols.append((s / 100.0 * ATM_SCALE["index"]).reindex(s.index.union(sessions)).ffill(limit=3).reindex(sessions)
                    if s is not None else pd.Series(np.nan, index=sessions))
    P = pd.concat(cols, axis=1).to_numpy(float)
    for j in range(P.shape[1]):                                      # fill a missing pillar from its neighbours
        for k in sorted(range(P.shape[1]), key=lambda k: abs(k - j)):
            P[:, j] = np.where(np.isfinite(P[:, j]), P[:, j], P[:, k])
    return np.array([d / 365.0 for _, d in SPY_TERM]), P


def term_ratio(pillars: np.ndarray, P: np.ndarray, t: np.ndarray, T: np.ndarray) -> np.ndarray:
    """S&P ATM vol at tenor T ÷ at 30 days, for session positions t (vectorised; total-variance interpolation, flat
    beyond the pillars)."""
    t = np.asarray(t, int)
    T = np.clip(np.asarray(T, float), pillars[0], pillars[-1])
    rows = P[t]
    i = np.clip(np.searchsorted(pillars, T), 1, len(pillars) - 1)
    t0, t1 = pillars[i - 1], pillars[i]
    v0 = np.take_along_axis(rows, (i - 1)[..., None], axis=-1)[..., 0]
    v1 = np.take_along_axis(rows, i[..., None], axis=-1)[..., 0]
    w = (T - t0) / (t1 - t0)
    var = ((1 - w) * v0 * v0 * t0 + w * v1 * v1 * t1) / T
    at30 = rows[..., 1]
    return np.sqrt(np.maximum(var, 1e-8)) / np.where(at30 > 0, at30, np.nan)


def _design(rv: Dict[str, pd.DataFrame], vix: pd.Series, spy_rv: pd.Series, stock: np.ndarray) -> np.ndarray:
    n, m = rv["blend"].shape
    X = np.stack([np.ones((n, m)), np.log(rv["blend"].to_numpy()),
                  np.repeat(np.log(vix.to_numpy())[:, None], m, axis=1),
                  np.repeat(np.log(spy_rv.to_numpy())[:, None], m, axis=1),
                  np.repeat(stock[None, :].astype(float), n, axis=0)], axis=-1)
    return X


def fit_iv_model(close: pd.DataFrame, observed: pd.DataFrame, kinds: Dict[str, str], vix: pd.Series,
                 train_end: str = TRAIN_END) -> Dict[str, Any]:
    """OLS of log observed ATM IV on realised-vol features, pooled over the observed-IV underlyings except SPY (whose IV
    is the market factor itself), on sessions up to train_end only."""
    names = [c for c in observed.columns if c != "SPY" and observed[c].notna().any()]
    rv = realised(close[names + ["SPY"]])
    spy_rv = rv["rv63"]["SPY"]
    sub = {k: v[names] for k, v in rv.items()}
    stock = np.array([kinds.get(c) == "stock" for c in names])
    X = _design(sub, vix, spy_rv, stock)
    y = np.log(observed[names].to_numpy())
    train = (close.index <= pd.Timestamp(train_end))[:, None] & np.ones((1, len(names)), bool)
    ok = train & np.isfinite(y) & np.isfinite(X).all(axis=-1)
    beta, *_ = np.linalg.lstsq(X[ok], y[ok], rcond=None)
    resid = y[ok] - X[ok] @ beta
    return {"beta": beta.tolist(), "names": names, "train_end": train_end, "n": int(ok.sum()),
            "resid_sd": float(resid.std()), "terms": ["const", "log_rv_blend", "log_vix", "log_spy_rv63", "single_stock"]}


def model_atm(close: pd.DataFrame, kinds: Dict[str, str], vix: pd.Series, model: Dict[str, Any]) -> pd.DataFrame:
    rv = realised(close)
    spy_rv = rv["rv63"]["SPY"] if "SPY" in close.columns else rv["rv63"].median(axis=1)
    stock = np.array([kinds.get(c, "stock") == "stock" for c in close.columns])
    X = _design(rv, vix, spy_rv, stock)
    iv = np.exp(X @ np.asarray(model["beta"]))
    return pd.DataFrame(iv, index=close.index, columns=close.columns).clip(0.05, 2.5)


def iv_model_report(observed: pd.DataFrame, modelled: pd.DataFrame, train_end: str = TRAIN_END) -> Dict[str, Any]:
    """Accuracy of the IV model against the observed CBOE indices: in-sample (≤ train_end) and out-of-sample."""
    rows = []
    for c in observed.columns:
        if c == "SPY" or c not in modelled.columns or observed[c].isna().all():
            continue
        o, m = observed[c], modelled[c]
        for seg, mask in (("in_sample", o.index <= train_end), ("out_of_sample", o.index > train_end)):
            ok = mask & o.notna().to_numpy() & m.notna().to_numpy()
            if ok.sum() < 60:
                continue
            e = (m[ok] - o[ok]).to_numpy()
            rows.append({"underlying": c, "segment": seg, "days": int(ok.sum()), "mae_vol_pts": round(float(np.abs(e).mean() * 100), 2),
                         "bias_vol_pts": round(float(e.mean() * 100), 2),
                         "corr": round(float(np.corrcoef(m[ok], o[ok])[0, 1]), 3),
                         "mean_observed": round(float(o[ok].mean() * 100), 1)})
    df = pd.DataFrame(rows)
    summ = {}
    if len(df):
        for seg, g in df.groupby("segment"):
            summ[seg] = {"mae_vol_pts": round(float(np.average(g.mae_vol_pts, weights=g.days)), 2),
                         "bias_vol_pts": round(float(np.average(g.bias_vol_pts, weights=g.days)), 2),
                         "median_corr": round(float(g["corr"].median()), 3), "underlyings": int(len(g))}
    return {"by_underlying": rows, "summary": summ}


# ── The surface for a research panel ─────────────────────────────────────────
OBSERVED, MODEL = 1, 2


def surface(panel, train_end: str = TRAIN_END) -> Dict[str, Any]:
    """ATM 30-day IV for every (session, underlying): observed where a CBOE index exists, else the fitted model; the
    class of each cell; the S&P term-structure pillars; and the IV model's fit and out-of-sample accuracy."""
    sess = panel.dates
    close = panel.frame("close")
    kinds = {t: (OBSERVED_IV[t][1] if t in OBSERVED_IV else kind_of(t, "ETF" if panel.info[t].get("kind") == "etf" else ""))
             for t in panel.tickers}
    obs, coverage = observed_atm(panel.tickers, sess)
    vix_raw = cboe("VIX")
    vix = (vix_raw / 100.0).reindex(vix_raw.index.union(sess)).ffill().reindex(sess) if vix_raw is not None else None
    if vix is None or "SPY" not in panel.tickers:
        raise ValueError("The S&P 500 volatility index (VIX) and SPY are required for the IV model.")
    model = fit_iv_model(close, obs, kinds, vix, train_end)
    mod = model_atm(close, kinds, vix, model)
    report = iv_model_report(obs, mod, train_end)
    atm = obs.where(obs.notna(), mod)
    cls = np.where(obs.notna().to_numpy(), OBSERVED, MODEL).astype(np.int8)
    pillars, P = spy_term(sess)
    return {"atm": atm.to_numpy(np.float32), "cls": cls, "kinds": kinds, "pillars": pillars, "P": P,
            "vix": vix.to_numpy(float), "model": model, "model_report": report, "coverage": coverage,
            "rv": {k: v.to_numpy(np.float32) for k, v in realised(close).items() if k in ("rv21", "blend")}}


def synthetic_surface(panel, iv: float = 0.2, vix: float = 0.2) -> Dict[str, Any]:
    """A flat surface for correctness tests (stage 1): constant ATM IV, flat term structure."""
    T, N = panel.a["close"].shape
    pillars = np.array([d / 365.0 for _, d in SPY_TERM])
    rv = realised(panel.frame("close"))
    return {"atm": np.full((T, N), iv, np.float32), "cls": np.full((T, N), MODEL, np.int8),
            "kinds": {t: ("index" if panel.info[t].get("kind") == "etf" else "stock") for t in panel.tickers},
            "pillars": pillars, "P": np.full((T, len(pillars)), iv), "vix": np.full(T, vix), "model": {},
            "model_report": {}, "coverage": {}, "rv": {k: v.to_numpy(np.float32) for k, v in rv.items() if k in ("rv21", "blend")}}
