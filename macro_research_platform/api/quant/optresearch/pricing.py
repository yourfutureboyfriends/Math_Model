"""
Vectorised option pricing for the research simulator: Black–Scholes–Merton value and Greeks (per share), strikes by
delta on a skewed smile, listed-style strike increments and expiry calendars.

European formulas are used for marks; American early exercise is handled as an event in the simulator (a short call
before an ex-dividend date, a deep in-the-money short put), not in the price.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy.special import ndtr, ndtri

SQRT_2PI = np.sqrt(2 * np.pi)


def _pdf(x):
    return np.exp(-0.5 * x * x) / SQRT_2PI


def bsm(S, K, T, r, q, vol, call) -> Dict[str, np.ndarray]:
    """Value and Greeks per share (vectorised; `call` may be an array of bools). At T ≤ 0: intrinsic value, delta 0/±1,
    other Greeks 0. Theta per calendar day, vega per 1 vol point (0.01)."""
    S, K, T, r, q, vol = (np.asarray(a, float) for a in (S, K, T, r, q, vol))
    call = np.asarray(call, bool)
    live = (T > 0) & (vol > 0) & (S > 0) & (K > 0)
    Ts = np.where(live, T, 1.0)
    vs = np.where(live, vol, 0.2)
    Sp, Kp = np.where(S > 0, S, 1.0), np.where(K > 0, K, 1.0)
    sq = vs * np.sqrt(Ts)
    d1 = (np.log(Sp / Kp) + (r - q + 0.5 * vs * vs) * Ts) / sq
    d2 = d1 - sq
    dq, dr = np.exp(-q * Ts), np.exp(-r * Ts)
    nd1 = _pdf(d1)
    c_val = Sp * dq * ndtr(d1) - Kp * dr * ndtr(d2)
    p_val = Kp * dr * ndtr(-d2) - Sp * dq * ndtr(-d1)
    val = np.where(call, c_val, p_val)
    delta = np.where(call, dq * ndtr(d1), -dq * ndtr(-d1))
    gamma = dq * nd1 / (Sp * sq)
    vega = Sp * dq * nd1 * np.sqrt(Ts) / 100.0
    common = -Sp * dq * nd1 * vs / (2 * np.sqrt(Ts))
    theta_c = common - r * Kp * dr * ndtr(d2) + q * Sp * dq * ndtr(d1)
    theta_p = common + r * Kp * dr * ndtr(-d2) - q * Sp * dq * ndtr(-d1)
    theta = np.where(call, theta_c, theta_p) / 365.0
    intr = np.where(call, np.maximum(S - K, 0.0), np.maximum(K - S, 0.0))
    idl = np.where(call, (S > K).astype(float), -(S < K).astype(float))
    z = np.zeros_like(val)
    return {"value": np.where(live, val, intr), "delta": np.where(live, delta, idl),
            "gamma": np.where(live, gamma, z), "theta": np.where(live, theta, z), "vega": np.where(live, vega, z)}


# ── Smile ────────────────────────────────────────────────────────────────────
# IV(K) = ATM × (1 − slope × ln(K/S) / √(T / 1 month)), floored at 30% of ATM. Puts (k < 0) use the put-side slope,
# calls the call-side slope. Index slopes are calibrated against CBOE's iron-condor (CNDR) and put-write (PUT)
# indices on 2011–2017 only (validate.calibrate_smile); single stocks use flatter published-typical slopes.
SMILE = {"index": (3.0, 1.0), "stock": (1.5, 0.3), "commodity": (1.2, 0.6), "bond": (1.0, 0.5)}


def smile_vol(atm, S, K, T, kind: str = "index", put_slope: float | None = None, call_slope: float | None = None):
    ps, cs = SMILE.get(kind, SMILE["stock"])
    ps = ps if put_slope is None else put_slope
    cs = cs if call_slope is None else call_slope
    k = np.log(np.asarray(K, float) / np.asarray(S, float))
    scale = np.sqrt(np.maximum(np.asarray(T, float), 1 / 365) / (1 / 12))
    v = np.asarray(atm, float) * (1 - np.where(k < 0, ps, cs) * k / scale)
    return np.maximum(v, 0.3 * np.asarray(atm, float))


def strike_increment(S):
    """Listed-style strike spacing by price (US equity/ETF options: $0.5 under $25, $1 under $200, $2.5 under $500,
    $5 above; weekly/penny classes have finer grids that are not modelled)."""
    S = np.asarray(S, float)
    return np.where(S < 25, 0.5, np.where(S < 200, 1.0, np.where(S < 500, 2.5, 5.0)))


def round_strike(K, S, up) -> np.ndarray:
    """Round to the listed grid: up (ceil) or down (floor) per element — always away from the money for short legs
    chosen by delta is the caller's choice."""
    inc = strike_increment(S)
    x = np.asarray(K, float) / inc
    return np.maximum(inc, np.where(np.asarray(up, bool), np.ceil(x), np.floor(x)) * inc)


def strike_for_delta(S, T, r, q, atm, target_delta, call: bool, kind: str = "index", iterations: int = 5,
                     put_slope: float | None = None, call_slope: float | None = None):
    """Strike whose |delta| equals target_delta on the smile (fixed-point iteration, vectorised); not yet rounded."""
    S, T, r, q, atm = (np.asarray(a, float) for a in (S, T, r, q, atm))
    tgt = np.clip(np.asarray(target_delta, float), 1e-4, 0.999) * np.exp(q * np.maximum(T, 1e-6))
    tgt = np.clip(tgt, 1e-4, 0.999)
    vol = atm.copy()
    Tm = np.maximum(T, 1 / 365)
    K = S.copy()
    z = ndtri(tgt) if call else -ndtri(tgt)
    for _ in range(iterations):
        K = S * np.exp(-z * vol * np.sqrt(Tm) + (r - q + 0.5 * vol * vol) * Tm)
        vol = smile_vol(atm, S, K, Tm, kind, put_slope, call_slope)
    return K


# ── Expiry calendars ─────────────────────────────────────────────────────────
def third_fridays(start: pd.Timestamp, end: pd.Timestamp) -> List[pd.Timestamp]:
    out = []
    for y in range(start.year, end.year + 2):
        for m in range(1, 13):
            d = pd.Timestamp(y, m, 1)
            out.append(d + pd.Timedelta(days=(4 - d.weekday()) % 7 + 14))
    return [d for d in out if start <= d <= end]


def fridays(start: pd.Timestamp, end: pd.Timestamp) -> List[pd.Timestamp]:
    first = start + pd.Timedelta(days=(4 - start.weekday()) % 7)
    return list(pd.date_range(first, end, freq="7D"))


def expiry_table(sessions: pd.DatetimeIndex, weeklies: bool) -> Tuple[np.ndarray, np.ndarray]:
    """(expiry dates as int64 days, session position of each expiry — the last session on or before it, holidays move
    earlier). Weekly Friday expiries for the index ETFs; monthly third Fridays for everything."""
    end = sessions[-1] + pd.Timedelta(days=200)
    days = sorted(set(third_fridays(sessions[0], end)) | (set(fridays(sessions[0], end)) if weeklies else set()))
    d = pd.DatetimeIndex(days)
    pos = sessions.searchsorted(d, side="right") - 1
    return d.values.astype("datetime64[D]").astype(np.int64), pos


def pick_expiry(entry_day: np.ndarray, target_dte: int, exp_days: np.ndarray, min_dte: int = 5) -> np.ndarray:
    """For each entry date (int days), the listed expiry closest to entry + target_dte calendar days, at least min_dte
    away. Returns an index into exp_days."""
    want = entry_day + target_dte
    i = np.searchsorted(exp_days, want)
    i = np.clip(i, 1, len(exp_days) - 1)
    lo, hi = exp_days[i - 1], exp_days[i]
    pick = np.where(np.abs(lo - want) <= np.abs(hi - want), i - 1, i)
    too_close = exp_days[pick] - entry_day < min_dte
    return np.where(too_close, np.minimum(pick + 1, len(exp_days) - 1), pick)
