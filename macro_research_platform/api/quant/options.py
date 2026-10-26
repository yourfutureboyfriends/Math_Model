"""
Synthetic listed options for the Code Lab. Free data has no history of option quotes, so each option a strategy
declares (OPTIONS = [...]) becomes a tradable instrument priced every day by Black–Scholes–Merton from:

  underlying   its traded share price (split-adjusted, not dividend-adjusted) and continuous dividend yield
               (trailing 12 months of cash dividends ÷ price), in its own currency;
  rate         the underlying currency's short rate (api/quant/rates.py), as of each day;
  volatility   implied, where a CBOE volatility index exists — S&P 500 ETFs: the VIX term structure (VIX9D, VIX,
               VIX3M, VIX6M, interpolated in total variance to each contract's remaining life); Nasdaq-100: VXN;
               Dow: VXD; gold: GVZ; oil: OVX — scaled to at-the-money (a VIX-style index sits above ATM implied
               vol: ATM ≈ 0.92 × index). Elsewhere a model: blended realised volatility (EWMA, 1 and 6 months)
               × the market's current implied/realised ratio (VIX ÷ S&P realised), half passed through.
               A volatility skew by moneyness, steeper for puts and for short tenors (index: puts 3.0, calls
               1.0; single stocks: 1.5 and 0.3 — × ln(K/S) ÷ √(T / 1 month)), floored at 30% of ATM.

Contracts are European, cash-settled at intrinsic value at expiry (listed equity options are American; early
exercise is ignored), struck at the close of each roll date at a listed-style increment, and rolled at expiry:
  expiry   "monthly" (third Friday), "weekly" (Friday), "quarterly" (Mar/Jun/Sep/Dec third Friday), with
           "months": n for the n-th monthly expiry ahead; or "tenor_days": n calendar days;
  strike   "moneyness": K/S (default 1.0) or "delta": |Δ| (e.g. 0.25 → a 25-delta option).
The instrument's price is the live contract's value per share; on an expiry day the expiring contract settles
(the engine credits or debits intrinsic value) and the column continues as the new contract, struck at that
close. A standing target weight is re-established in the new contract at the next open (a roll).

Costs: half the quoted spread = max(half a tick — $0.01 under $3, $0.05 above, penny classes $0.01 — , 0.75% of
premium for index ETFs with a volatility index, 2.5% otherwise) plus $0.65 per contract commission, as
a spread floor; market impact against 2% of the underlying's traded value. One contract = 100 shares: board lots
apply. All of this is a model — tested against CBOE's PutWrite index (api/tests/test_options.py; docs).
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

MAX_OPTIONS = 12
MULTIPLIER = 100
ATM_SCALE = 0.92
# underlying → [(volatility index, tenor in days)] (several = a term structure)
VOL_INDEX: Dict[str, List[Tuple[str, int]]] = {
    **{u: [("^VIX9D", 9), ("^VIX", 30), ("^VIX3M", 93), ("^VIX6M", 182)] for u in ("SPY", "VOO", "IVV", "SPLG", "RSP")},
    "QQQ": [("^VXN", 30)], "QQQM": [("^VXN", 30)], "DIA": [("^VXD", 30)],
    "GLD": [("^GVZ", 30)], "IAU": [("^GVZ", 30)], "USO": [("^OVX", 30)],
}
INDEX_LIKE = set(VOL_INDEX) | {"IWM", "EFA", "EEM", "TLT", "XLF", "XLE", "XLK", "SMH", "HYG", "FXI", "EWZ", "SLV", "GDX"}
PENNY = {"SPY", "QQQ", "IWM", "DIA", "VOO", "IVV", "GLD", "SLV", "TLT", "EEM", "EFA", "XLF", "XLE", "USO", "AAPL",
         "MSFT", "AMZN", "NVDA", "TSLA", "META", "GOOGL", "AMD"}
KEYS = {"underlying", "type", "moneyness", "delta", "expiry", "months", "tenor_days", "name"}


# ── Specs ────────────────────────────────────────────────────────────────────
def parse(raw: Any) -> List[Dict[str, Any]]:
    """Validate an OPTIONS literal; returns normalised specs with unique instrument names."""
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)) or not 1 <= len(raw) <= MAX_OPTIONS:
        raise ValueError(f"OPTIONS must be a list of 1–{MAX_OPTIONS} option definitions.")
    out, names = [], set()
    for i, o in enumerate(raw):
        if not isinstance(o, dict) or set(o) - KEYS:
            raise ValueError(f"OPTIONS[{i}]: a dict with keys from {', '.join(sorted(KEYS))}.")
        u = str(o.get("underlying") or "").upper()
        kind = str(o.get("type") or "").lower()
        if not u or kind not in ("call", "put"):
            raise ValueError(f"OPTIONS[{i}]: needs 'underlying' and 'type' ('call' or 'put').")
        canonical = set(o) == KEYS and (o.get("delta") is None or float(o.get("moneyness", 1.0)) == 1.0)
        if "moneyness" in o and "delta" in o and not canonical:
            raise ValueError(f"OPTIONS[{i}]: give 'moneyness' or 'delta', not both.")
        m = float(o.get("moneyness", 1.0))
        d = o.get("delta")
        if not 0.5 <= m <= 1.5 or (d is not None and not 0.05 <= float(d) <= 0.95):
            raise ValueError(f"OPTIONS[{i}]: moneyness 0.5–1.5 (strike ÷ spot) or delta 0.05–0.95.")
        exp = str(o.get("expiry") or ("fixed" if "tenor_days" in o else "monthly")).lower()
        if exp not in ("monthly", "weekly", "quarterly", "fixed"):
            raise ValueError(f"OPTIONS[{i}]: expiry 'monthly', 'weekly' or 'quarterly' (or give tenor_days).")
        months = int(o.get("months", 1))
        tenor = int(o.get("tenor_days", 30))
        if not 1 <= months <= 12 or not 5 <= tenor <= 400:
            raise ValueError(f"OPTIONS[{i}]: months 1–12, tenor_days 5–400.")
        auto = (f"{u}_{'C' if kind == 'call' else 'P'}"
                + (f"D{round(float(d) * 100)}" if d is not None else f"{round(m * 100)}")
                + ("_W" if exp == "weekly" else "_Q" if exp == "quarterly" else f"_{tenor}D" if exp == "fixed"
                   else f"_{months}M"))
        name = str(o.get("name") or auto).upper().replace(" ", "_")
        if name in names:
            raise ValueError(f"OPTIONS: duplicate name {name} — give each a distinct 'name'.")
        names.add(name)
        out.append({"name": name, "underlying": u, "type": kind, "moneyness": m,
                    "delta": float(d) if d is not None else None, "expiry": exp, "months": months, "tenor_days": tenor})
    return out


def expand(raw: Any, universe: Sequence[str]) -> List[Dict[str, Any]]:
    """Expand '*' templates across every loaded underlying, never a sampled subset.

    The 12-definition limit remains a limit on user-authored templates, not on generated instruments.
    These are synthetic models; expansion does not verify that an exchange or broker lists the contracts.
    """
    templates = parse(raw)
    names = list(dict.fromkeys(str(u).upper() for u in universe))
    out, used = [], set()
    for template in templates:
        targets = names if template['underlying'] == '*' else [template['underlying']]
        for u in targets:
            item = dict(template, underlying=u)
            if template['underlying'] == '*':
                item['name'] = u + '__' + template['name'].replace('*', 'ALL')
            if item['name'] in used or item['name'] in names:
                raise ValueError(f"OPTIONS: instrument name collision {item['name']}.")
            used.add(item['name'])
            out.append(item)
    return out


# ── Pricing ──────────────────────────────────────────────────────────────────
def _ncdf(x):
    from scipy.special import ndtr
    return ndtr(x)


def bs(S, K, T, r, q, vol, call: bool):
    """Black–Scholes–Merton value and delta per share (vectorised); at T ≤ 0 the intrinsic value."""
    S, K, T, r, q, vol = (np.asarray(a, float) for a in (S, K, T, r, q, vol))
    live = (T > 0) & (vol > 0) & (S > 0) & (K > 0)
    Ts = np.where(live, T, 1.0)
    vs = np.where(live, vol, 0.2)
    d1 = (np.log(np.where(S > 0, S, 1.0) / np.where(K > 0, K, 1.0)) + (r - q + 0.5 * vs ** 2) * Ts) / (vs * np.sqrt(Ts))
    d2 = d1 - vs * np.sqrt(Ts)
    dq, dr = np.exp(-q * Ts), np.exp(-r * Ts)
    if call:
        v, dl = S * dq * _ncdf(d1) - K * dr * _ncdf(d2), dq * _ncdf(d1)
        intr, idl = np.maximum(S - K, 0.0), (S > K).astype(float)
    else:
        v, dl = K * dr * _ncdf(-d2) - S * dq * _ncdf(-d1), -dq * _ncdf(-d1)
        intr, idl = np.maximum(K - S, 0.0), -(S < K).astype(float)
    return np.where(live, v, intr), np.where(live, dl, idl)


def skewed_vol(atm, S, K, T, index_like: bool, call: bool):
    """Implied volatility at strike K from the at-the-money level (see module docstring)."""
    k = np.log(np.asarray(K, float) / np.asarray(S, float))
    scale = np.sqrt(np.maximum(np.asarray(T, float), 1 / 365) / (1 / 12))
    side = np.where(k < 0, 3.0 if index_like else 1.5, 1.0 if index_like else 0.3)
    v = atm * (1 - side * k / scale)
    return np.maximum(v, 0.3 * atm)


def strike_increment(S: float) -> float:
    return 0.5 if S < 25 else 1.0 if S < 250 else 5.0 if S < 1000 else 10.0


def _strike(S, T, r, q, atm, spec, index_like) -> float:
    call = spec["type"] == "call"
    if spec["delta"] is None:
        K = S * spec["moneyness"]
    else:
        from scipy.special import ndtri
        target = spec["delta"] * math.exp(q * T)
        vol = atm
        K = S
        for _ in range(4):                                      # strike ↔ skewed vol, a few fixed-point steps
            z = ndtri(target) if call else -ndtri(target)
            K = S * math.exp(-z * vol * math.sqrt(T) + (r - q + 0.5 * vol * vol) * T)
            vol = float(skewed_vol(atm, S, K, T, index_like, call))
    inc = strike_increment(S)
    return max(inc, round(K / inc) * inc)


# ── Expiry calendars ─────────────────────────────────────────────────────────
def _third_friday(y: int, m: int) -> pd.Timestamp:
    d = pd.Timestamp(y, m, 1)
    return d + pd.Timedelta(days=(4 - d.weekday()) % 7 + 14)


def _expiries(kind: str, start: pd.Timestamp, end: pd.Timestamp) -> List[pd.Timestamp]:
    if kind == "weekly":
        first = start + pd.Timedelta(days=(4 - start.weekday()) % 7)
        return list(pd.date_range(first, end + pd.Timedelta(days=14), freq="7D"))
    months = [(y, m) for y in range(start.year, end.year + 2) for m in range(1, 13)]
    if kind == "quarterly":
        months = [(y, m) for y, m in months if m in (3, 6, 9, 12)]
    return [_third_friday(y, m) for y, m in months]


def _schedule(spec, sessions: pd.DatetimeIndex) -> List[Tuple[int, int, pd.Timestamp]]:
    """[(strike position, last live position, expiry date)] over the underlying's sessions: each contract is struck
    at the close of the previous one's expiry. A listed expiry on a holiday moves to the previous session. The last
    contract may expire after the data ends: it stays live to the last session with its real (future) expiry date."""
    if len(sessions) < 2:
        return []
    last = len(sessions) - 1
    out, s = [], 0
    if spec["expiry"] == "fixed":
        while s < last:
            due = sessions[s] + pd.Timedelta(days=spec["tenor_days"])
            if due > sessions[-1]:
                out.append((s, last, due))
                break
            e = max(int(sessions.searchsorted(due)), s + 1)        # first session on or after the due date
            out.append((s, e, sessions[e]))
            s = e
        return out
    cal = _expiries(spec["expiry"], sessions[0], sessions[-1] + pd.Timedelta(days=400))
    listed = sorted({(int(sessions.searchsorted(d, side="right")) - 1, d) for d in cal if d <= sessions[-1]})
    pos = sorted({p for p, _ in listed if p >= 0})                 # holiday → previous session
    future = [d for d in cal if d > sessions[-1]]
    step = spec["months"] if spec["expiry"] == "monthly" else 1
    while s < last:
        ahead = [p for p in pos if p > s]
        if len(ahead) >= step:
            e = ahead[step - 1]
            out.append((s, e, sessions[e]))
            s = e
            continue
        k = step - len(ahead) - 1                                 # the expiry lies beyond the data
        out.append((s, last, future[k] if k < len(future) else sessions[-1] + pd.Timedelta(days=30 * step)))
        break
    return out


# ── Building instruments ─────────────────────────────────────────────────────
def _vol_index(u: str, idx: pd.DatetimeIndex, start: str) -> Optional[List[Tuple[pd.Series, int]]]:
    from api.quant import codeserver
    src = VOL_INDEX.get(u)
    if not src:
        return None
    out = []
    for sym, days in src:
        ser = codeserver._index_series(sym, start)
        if ser is not None:
            ser = ser[(ser > 1) & (ser < 300)] / 100.0
            out.append((ser.reindex(ser.index.union(idx)).ffill().reindex(idx), days))
    return out or None


def _atm_from_term(term: List[Tuple[pd.Series, int]], t: int, T_years: float) -> float:
    """At-the-money vol for a remaining life, interpolated in total variance across the index tenors."""
    pts = [(d / 365.0, float(s.iloc[t])) for s, d in term if np.isfinite(s.iloc[t])]
    if not pts:
        return float("nan")
    pts.sort()
    if T_years <= pts[0][0] or len(pts) == 1:
        v = pts[0][1] if T_years <= pts[0][0] else pts[-1][1]
    elif T_years >= pts[-1][0]:
        v = pts[-1][1]
    else:
        for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
            if t0 <= T_years <= t1:
                w = (T_years - t0) / (t1 - t0)
                v = math.sqrt(max(((1 - w) * v0 * v0 * t0 + w * v1 * v1 * t1) / T_years, 1e-8))
                break
    return ATM_SCALE * v


def build(specs: List[Dict[str, Any]], *, idx: pd.DatetimeIndex, observed: pd.DataFrame, share_close: pd.DataFrame,
          share_open: pd.DataFrame, div_yield: pd.DataFrame, conv: pd.DataFrame, volume: pd.DataFrame,
          inst: Dict[str, Dict[str, Any]], start: str, usd_per_unit: pd.Series) -> Dict[str, Any]:
    """Price each declared option on the trading days of its underlying. Inputs per underlying (columns): its
    observed mask, share price at the close and open in the quote currency (split-adjusted), ex-date dividend
    yields, account units per quote unit (as of each close), share volume. Returns the instrument columns
    (account currency), their settlement values, cost floors, lot values, analytics and metadata."""
    from api.quant import codeserver, rates
    spx = codeserver._index_series("^GSPC", start)
    vix = codeserver._index_series("^VIX", start)
    ratio = None
    if spx is not None and vix is not None:
        r = np.log(spx).diff()
        rv = r.ewm(halflife=21, min_periods=20).std() * math.sqrt(252)
        ratio = (vix / 100 / rv).clip(0.8, 2.5).reindex(idx, method="ffill")
    cols: Dict[str, Dict[str, pd.Series]] = {}
    meta: Dict[str, Dict[str, Any]] = {}
    for spec in specs:
        u = spec["underlying"]
        obs = observed[u] & share_close[u].notna()
        sess = idx[obs.to_numpy()]
        S = share_close[u][obs]
        So = share_open[u][obs]
        n = len(sess)
        i_u = inst[u]
        ccy = i_u["currency"]
        div = float(i_u.get("unit_divisor") or 1.0)
        rr = (rates.daily(sess, ccy) * 252).to_numpy() if rates.known(ccy) else np.zeros(n)
        rr_prev = np.r_[rr[0], rr[:-1]] if n else rr
        dy = div_yield[u].reindex(sess).fillna(0.0)
        q = (dy.rolling(252, min_periods=1).sum()).clip(0, 0.15).to_numpy()
        lr = np.log(S).diff()
        rv = (0.5 * lr.ewm(halflife=21, min_periods=10).std() + 0.5 * lr.ewm(halflife=126, min_periods=20).std()) * math.sqrt(252)
        mult = (1 + 0.5 * (ratio.reindex(sess) - 1)).fillna(1.1).to_numpy() if ratio is not None else np.full(n, 1.1)
        model_atm = (rv.to_numpy() * mult)
        term = _vol_index(u, sess, start)
        index_like = u in INDEX_LIKE
        call = spec["type"] == "call"
        V = np.full(n, np.nan)
        Vo = np.full(n, np.nan)
        settle = np.full(n, np.nan)
        delta = np.full(n, np.nan)
        iv = np.full(n, np.nan)
        strike = np.full(n, np.nan)
        dte = np.full(n, np.nan)
        roll = np.zeros(n, bool)
        Sv, Sov = S.to_numpy(float), So.to_numpy(float)
        for s, e, xd in _schedule(spec, sess):
            T_at = lambda t: max((xd - sess[t]).days, 0) / 365.0
            def atm(t, T):
                a = _atm_from_term(term, t, max(T, 1 / 365)) if term else float("nan")
                return a if np.isfinite(a) else model_atm[t]
            T0 = T_at(s)
            a0 = atm(s, T0)
            if not (np.isfinite(Sv[s]) and np.isfinite(a0) and a0 > 0):
                continue
            K = _strike(Sv[s], T0, rr[s], q[s], a0, spec, index_like)
            rng = np.arange(s, e + 1)
            Ts = np.array([T_at(t) for t in rng])
            atms = np.array([atm(t, max(T, 1 / 365)) for t, T in zip(rng, Ts)])
            vols = skewed_vol(atms, Sv[rng], K, Ts, index_like, call)
            val, dl = bs(Sv[rng], K, Ts, rr[rng], q[rng], vols, call)
            # the open trades on yesterday's volatility and rate (known before the open), today's opening price
            prev = np.maximum(rng - 1, 0)
            Ts_o = Ts + 0.25 / 365
            vols_o = skewed_vol(atms[np.maximum(np.arange(len(rng)) - 1, 0)], Sov[rng], K, Ts_o, index_like, call)
            val_o, _ = bs(Sov[rng], K, Ts_o, rr_prev[rng], q[prev], vols_o, call)
            # positions s+1..e belong to this contract (s's close belongs to it too: it is struck then)
            V[s], delta[s], iv[s], strike[s], dte[s] = val[0], dl[0], vols[0], K, (xd - sess[s]).days
            V[s + 1:e + 1], delta[s + 1:e + 1], iv[s + 1:e + 1] = val[1:], dl[1:], vols[1:]
            Vo[s + 1:e + 1] = val_o[1:]
            strike[s + 1:e + 1] = K
            dte[s + 1:e + 1] = [(xd - sess[t]).days for t in rng[1:]]
            settle[e] = val[-1] if Ts[-1] <= 0 else np.nan          # expiry: intrinsic (open-ended last one: none)
            if Ts[-1] <= 0:
                roll[e] = True
        # on an expiry day the close shows the NEW contract (written last above); `settle` keeps the old one's value
        Vf = np.maximum(V, 0.005 * div)                          # quotes do not go below half a tick
        c = conv[u].reindex(sess).ffill().to_numpy(float)          # account units per quote unit
        acct = lambda x: pd.Series(x * c, index=sess).reindex(idx)
        Vof = np.maximum(Vo, 0.005 * div)
        name = spec["name"]
        tick = np.where((Vf < 3 * div) | (u in PENNY), 0.01, 0.05) * div    # quote units
        base = 75.0 if u in VOL_INDEX else 250.0                   # half-spread, bp of premium
        usd = usd_per_unit.reindex(sess).ffill().bfill().to_numpy(float) * c   # USD per quote unit
        comm = 0.65 / (MULTIPLIER * Vf * usd) * 1e4                   # $0.65 per contract
        half = np.maximum(0.5 * tick / Vf * 1e4, base) + comm
        und_dv = (volume[u].reindex(sess) * Sv).to_numpy(float)
        cols[name] = {
            "close": acct(Vf), "open": acct(Vof), "settle": acct(settle),
            "volume": pd.Series(0.02 * und_dv / Vf, index=sess).reindex(idx),
            "observed": pd.Series(np.isfinite(V), index=sess).reindex(idx, fill_value=False),
            "tick_bps": pd.Series(np.minimum(half, 5000.0), index=sess).reindex(idx),
            "lot_value": acct(MULTIPLIER * Vf),
            "delta": pd.Series(delta, index=sess).reindex(idx), "iv": pd.Series(iv, index=sess).reindex(idx),
            "strike": pd.Series(strike / div, index=sess).reindex(idx), "dte": pd.Series(dte, index=sess).reindex(idx),
            "notional": pd.Series(Sv / Vf, index=sess).reindex(idx),
            "spot": acct(Sv), "spot_open": acct(Sov),
            "elasticity": pd.Series(delta * Sv / Vf, index=sess).reindex(idx),
            "roll": pd.Series(roll, index=sess).reindex(idx, fill_value=False),
        }
        meta[name] = {"country": i_u["country"], "quote_currency": i_u["quote_currency"], "currency": ccy,
                      "unit_divisor": div, "fx_ticker": i_u.get("fx_ticker"), "tax_buy_bps": 0.0, "tax_sell_bps": 0.0,
                      "tax_note": None, "sec_fee": i_u["country"] == "US", "wht": 0.0, "lot_size": MULTIPLIER,
                      "kind": "option", "underlying": u, "option_type": spec["type"], "expiry_rule": spec["expiry"],
                      "moneyness": spec["moneyness"], "target_delta": spec["delta"], "name": name,
                      "vol_source": (", ".join(s for s, _ in VOL_INDEX[u]) + " (implied)") if term else
                                    "model: realised vol × market implied/realised ratio",
                      "sector": "Option", "region": i_u.get("region"), "market_class": i_u.get("market_class")}
    return {"columns": cols, "instruments": meta}
