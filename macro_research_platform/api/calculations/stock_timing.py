"""
Stock entry timing — when the evidence says a stock is a buy, and where to enter.

Two questions, answered separately (as in Kolanovic & Wei, J.P. Morgan 2015, where trend
signals decide direction and mean-reversion filters decide the entry):

SETUP — is this a stock to own? (each component scored −1..+1)
  * Trend: price vs 50/200-day averages — Faber (2007); Hurst, Ooi & Pedersen (AQR, 2017).
  * Time-series momentum: 12-1 month return divided by realised volatility — Moskowitz,
    Ooi & Pedersen (2012); volatility scaling per Barroso & Santa-Clara (2015).
  * 52-week-high proximity — George & Hwang (2004).
  * Earnings drift: latest EPS surprise, decaying with time — Bernard & Thomas (1989).
  * Sell-side view: consensus rating, price-target upside and recent rating/target
    revisions by brokerage (the banks' published research).
  * Quality: profitability and leverage — Asness, Frazzini & Pedersen, "Quality Minus Junk".

ENTRY — is now a good moment?
  * Pullback: distance from the 20-day average in ATR units and RSI(14) — short-term
    reversal (Jegadeesh, 1990) used as an entry filter inside an up-trend.
  * Market regime: S&P 500 above its 200-day average and VIX below 25 (Faber, 2007).

Levels: entry zone, a 2.5×ATR(14) stop, target = consensus price target (or 52-week high),
reward:risk, and size = 0.5% of NAV at risk to the stop, capped at the single-name limit.

All functions are pure (arrays in, numbers out) and use only data up to the last bar.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

SETUP_WEIGHTS = {"trend": 0.25, "momentum": 0.25, "high_52w": 0.10, "earnings": 0.10,
                 "analysts": 0.15, "quality": 0.15}
BUY_SETUP = 0.35          # setup score needed to call a stock a buy candidate
EXTENDED_TIMING = -0.2    # timing score below this = extended, wait for a pullback
MIN_REWARD_RISK = 1.5     # a BUY needs at least this reward:risk to its target


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return float(max(lo, min(hi, x)))


def sma(c: np.ndarray, n: int) -> Optional[float]:
    return float(np.mean(c[-n:])) if c.size >= n else None


def rsi(c: np.ndarray, n: int = 14) -> Optional[float]:
    """Wilder's RSI on closes."""
    if c.size < n + 1:
        return None
    d = np.diff(c)
    up, dn = np.clip(d, 0, None), np.clip(-d, 0, None)
    au, ad = up[:n].mean(), dn[:n].mean()
    for u, v in zip(up[n:], dn[n:]):
        au = (au * (n - 1) + u) / n
        ad = (ad * (n - 1) + v) / n
    if ad == 0:
        return 100.0
    return float(100 - 100 / (1 + au / ad))


def atr(h: np.ndarray, l: np.ndarray, c: np.ndarray, n: int = 14) -> Optional[float]:
    """Average true range (simple mean of the last n true ranges)."""
    if c.size < n + 1:
        return None
    tr = np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
    return float(tr[-n:].mean())


# ── Setup components ─────────────────────────────────────────────────────────
def trend_component(c: np.ndarray) -> Optional[Dict[str, Any]]:
    s50, s200 = sma(c, 50), sma(c, 200)
    if s200 is None:
        return None
    p = float(c[-1])
    above200, golden = p > s200, s50 > s200
    score = 1.0 if above200 and golden else 0.5 if above200 else -0.25 if golden else -1.0
    return {"score": score, "sma50": round(s50, 2), "sma200": round(s200, 2),
            "evidence": f"Price {'above' if above200 else 'below'} its 200-day average ({s200:,.2f}); "
                        f"50-day {'above' if golden else 'below'} 200-day"}


def momentum_component(c: np.ndarray) -> Optional[Dict[str, Any]]:
    if c.size < 253:
        return None
    r12_1 = float(c[-22] / c[-253] - 1)
    rets = np.diff(np.log(c[-253:]))
    vol = float(rets.std(ddof=1) * math.sqrt(252))
    if vol <= 0:
        return None
    sharpe_like = r12_1 / vol
    return {"score": round(math.tanh(sharpe_like), 3), "return_12_1": round(r12_1, 4), "volatility": round(vol, 4),
            "evidence": f"12-1 month return {r12_1:+.1%} on {vol:.0%} volatility (risk-adjusted {sharpe_like:+.2f})"}


def high52_component(c: np.ndarray) -> Optional[Dict[str, Any]]:
    if c.size < 200:
        return None
    hi = float(np.max(c[-252:]))
    ratio = float(c[-1] / hi)
    return {"score": round(_clip((ratio - 0.85) / 0.15), 3), "ratio": round(ratio, 4), "high_52w": round(hi, 2),
            "evidence": f"{ratio:.0%} of the 52-week high ({hi:,.2f})"}


def earnings_component(earnings: List[Dict[str, Any]], today: date) -> Optional[Dict[str, Any]]:
    """earnings: [{'date': 'YYYY-MM-DD', 'surprise_pct': float|None, 'estimate': .., 'reported': ..}]"""
    reported = [e for e in earnings if e.get("surprise_pct") is not None and e.get("date")]
    if not reported:
        return None
    reported.sort(key=lambda e: e["date"], reverse=True)
    last = reported[0]
    age = (today - date.fromisoformat(last["date"][:10])).days
    decay = 1.0 if age <= 60 else 0.5 if age <= 90 else 0.0
    beats = sum(1 for e in reported[:4] if e["surprise_pct"] > 0)
    score = _clip(last["surprise_pct"] / 10.0) * decay
    nxt = min((e["date"] for e in earnings if e.get("surprise_pct") is None and e["date"][:10] >= today.isoformat()),
              default=None)
    return {"score": round(score, 3), "last_date": last["date"][:10], "surprise_pct": round(last["surprise_pct"], 2),
            "days_since": age, "beats_last_4": beats, "next_date": nxt[:10] if nxt else None,
            "evidence": f"Last EPS surprise {last['surprise_pct']:+.1f}% ({age} days ago; {beats} of last "
                        f"{min(4, len(reported))} beat){'' if decay else ' — drift window passed'}"}


def analyst_component(info: Dict[str, Any], revisions: List[Dict[str, Any]], price: float,
                      today: date, window_days: int = 90) -> Optional[Dict[str, Any]]:
    """Sell-side consensus (1 = strong buy … 5 = sell), price-target upside and the net
    direction of rating / target changes by brokerage over the last `window_days`."""
    rm = info.get("recommendationMean")
    tgt = info.get("targetMeanPrice")
    n = info.get("numberOfAnalystOpinions")
    parts, ev = [], []
    if isinstance(rm, (int, float)):
        parts.append(_clip((3.0 - rm) / 1.5))
        ev.append(f"consensus {rm:.2f} ({info.get('recommendationKey', '').replace('_', ' ')}, {n or '?'} analysts)")
    upside = None
    if isinstance(tgt, (int, float)) and price:
        upside = tgt / price - 1
        parts.append(_clip(upside / 0.25))
        ev.append(f"mean target {tgt:,.2f} ({upside:+.0%})")
    cutoff = (today - timedelta(days=window_days)).isoformat()
    recent = [r for r in revisions if r.get("date", "") >= cutoff]
    up = sum(1 for r in recent if r.get("action") == "up")
    down = sum(1 for r in recent if r.get("action") == "down")
    raise_ = sum(1 for r in recent if (r.get("target_change") or 0) > 0)
    cut = sum(1 for r in recent if (r.get("target_change") or 0) < 0)
    if recent:
        net = (up - down) + 0.5 * (raise_ - cut)
        parts.append(_clip(net / max(4.0, len(recent) / 2)))
        ev.append(f"{window_days}d: {up} upgrades / {down} downgrades, {raise_} target raises / {cut} cuts")
    if not parts:
        return None
    return {"score": round(float(np.mean(parts)), 3), "recommendation_mean": rm, "target_mean": tgt,
            "target_high": info.get("targetHighPrice"), "target_low": info.get("targetLowPrice"),
            "upside": round(upside, 4) if upside is not None else None, "analysts": n,
            "upgrades": up, "downgrades": down, "target_raises": raise_, "target_cuts": cut,
            "evidence": "; ".join(ev)}


def quality_component(info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    roe, pm, de = info.get("returnOnEquity"), info.get("profitMargins"), info.get("debtToEquity")
    parts, ev = [], []
    if isinstance(roe, (int, float)):
        parts.append(_clip((roe - 0.10) / 0.15))
        ev.append(f"ROE {roe:.0%}")
    if isinstance(pm, (int, float)):
        parts.append(_clip((pm - 0.08) / 0.12))
        ev.append(f"net margin {pm:.0%}")
    if isinstance(de, (int, float)):
        parts.append(_clip(1.0 - de / 100.0))          # Yahoo reports debt/equity in percent
        ev.append(f"debt/equity {de / 100:.2f}")
    if not parts:
        return None
    return {"score": round(float(np.mean(parts)), 3), "evidence": ", ".join(ev)}


# ── Entry timing ─────────────────────────────────────────────────────────────
def timing_component(c: np.ndarray, h: np.ndarray, l: np.ndarray) -> Optional[Dict[str, Any]]:
    s20, a, r = sma(c, 20), atr(h, l, c), rsi(c)
    if s20 is None or not a or r is None:
        return None
    dist = (float(c[-1]) - s20) / a                       # ATRs above/below the 20-day average
    d_score = _clip(-(dist - 0.75) / 1.75)                # ≤ −1 ATR → +1, ≥ +2.5 ATR → −1
    r_score = _clip((55 - r) / 20)                        # RSI 35 → +1, RSI 75 → −1
    score = (d_score + r_score) / 2
    state = "pullback" if score >= 0.5 else "extended" if score <= EXTENDED_TIMING else "neutral"
    return {"score": round(score, 3), "rsi14": round(r, 1), "atr14": round(a, 4), "sma20": round(s20, 2),
            "atr_from_sma20": round(dist, 2), "state": state,
            "evidence": f"{dist:+.1f} ATR from the 20-day average, RSI(14) {r:.0f} — {state}"}


def market_component(index: np.ndarray, vix_last: Optional[float], name: str = "S&P 500") -> Optional[Dict[str, Any]]:
    """Home-market trend (index vs its 200-day average) and global risk appetite (VIX < 25)."""
    s200 = sma(index, 200)
    if s200 is None:
        return None
    up = float(index[-1]) > s200
    calm = vix_last is None or vix_last < 25
    ok = up and calm
    return {"ok": ok, "spx_above_200d": up, "index_above_200d": up, "index": name, "vix": vix_last,
            "evidence": f"{name} {'above' if up else 'below'} its 200-day average; VIX "
                        f"{'n/a' if vix_last is None else f'{vix_last:.1f}'}"}


# ── Combine ──────────────────────────────────────────────────────────────────
def combine_setup(components: Dict[str, Optional[Dict[str, Any]]]) -> Optional[float]:
    avail = {k: w for k, w in SETUP_WEIGHTS.items() if components.get(k)}
    if not avail:
        return None
    tot = sum(avail.values())
    return round(sum(components[k]["score"] * w for k, w in avail.items()) / tot, 3)


def verdict(setup: Optional[float], timing: Optional[Dict], market: Optional[Dict],
            reward_risk: Optional[float] = None, target_is_consensus: bool = True) -> Dict[str, str]:
    """`reward_risk` gates a BUY only when the target is an external estimate (consensus);
    a 2R projection has reward:risk 2 by construction."""
    if setup is None:
        return {"code": "N/A", "label": "Insufficient data", "detail": ""}
    t = timing["score"] if timing else 0.0
    if setup >= BUY_SETUP:
        if market and not market["ok"]:
            return {"code": "BUY_SMALL", "label": "Buy candidate — market regime unfavourable",
                    "detail": "Stock set-up is strong but the broad market is risk-off; size down or wait."}
        if t <= EXTENDED_TIMING:
            return {"code": "WAIT", "label": "Buy candidate — wait for a pullback",
                    "detail": "Set-up is strong but the price is stretched; enter in the zone below."}
        if target_is_consensus and reward_risk is not None and reward_risk < MIN_REWARD_RISK:
            return {"code": "WAIT", "label": "Buy candidate — limited upside at this price",
                    "detail": f"Reward:risk to the target is {reward_risk:.1f} (< {MIN_REWARD_RISK}); wait for a "
                              "lower entry or a higher target."}
        return {"code": "BUY", "label": "Buy — set-up and entry aligned",
                "detail": "Trend, momentum and fundamentals support the stock and the entry is not stretched."}
    if setup >= 0:
        return {"code": "WATCH", "label": "Watch — mixed evidence", "detail": "No clear edge yet; wait for the set-up to strengthen."}
    return {"code": "AVOID", "label": "Avoid — evidence negative", "detail": "Trend and/or fundamentals point down."}


def levels(price: float, timing: Optional[Dict], high_52w: Optional[float], target_mean: Optional[float],
           nav: Optional[float], risk_per_trade: float = 0.005, max_position_pct: float = 0.10,
           px_to_usd: float = 1.0) -> Optional[Dict]:
    """Levels are in the stock's quote currency; `px_to_usd` converts one quote unit to USD
    (e.g. pence → USD for London) so the size is measured against the USD NAV."""
    if not timing:
        return None
    a, s20 = timing["atr14"], timing["sma20"]
    if timing["score"] <= EXTENDED_TIMING:
        lo, hi = s20 - 0.5 * a, s20 + 0.5 * a              # wait for the 20-day average
    else:
        lo, hi = max(s20, price - a), price
    lo, hi = min(lo, hi), max(lo, hi)
    entry = (lo + hi) / 2
    stop = entry - 2.5 * a
    if isinstance(target_mean, (int, float)) and target_mean > 0:
        target, basis = target_mean, "consensus price target"
    else:
        # No sell-side target (most stocks outside the US): a 2R projection — twice the risk
        # to the stop — the usual objective for a trend entry without an external estimate.
        target, basis = entry + 2 * (entry - stop), "2R projection (no consensus target)"
    rr = (target - entry) / (entry - stop) if entry > stop else None
    out = {"entry_low": round(lo, 2), "entry_high": round(hi, 2), "entry": round(entry, 2),
           "stop": round(stop, 2), "target": round(target, 2),
           "target_basis": basis, "high_52w": round(high_52w, 2) if high_52w else None,
           "reward_risk": round(rr, 2) if rr is not None else None,
           "stop_basis": "2.5 × ATR(14) below entry"}
    if nav and entry > stop and px_to_usd > 0:
        shares_risk = (risk_per_trade * nav) / ((entry - stop) * px_to_usd)
        shares_cap = (max_position_pct * nav) / (entry * px_to_usd)
        shares = int(max(0, min(shares_risk, shares_cap)))
        out.update({"shares": shares, "notional": round(shares * entry * px_to_usd, 2),
                    "notional_local": round(shares * entry, 2), "px_to_usd": px_to_usd,
                    "pct_nav": round(shares * entry * px_to_usd / nav, 4),
                    "risk_usd": round(shares * (entry - stop) * px_to_usd, 2),
                    "sizing_basis": f"{risk_per_trade:.1%} of NAV at risk to the stop, capped at {max_position_pct:.0%} of NAV"})
    return out


# ── Historical test of the price-based rules (no look-ahead) ─────────────────
def price_signal_history(c: np.ndarray, h: np.ndarray, l: np.ndarray) -> np.ndarray:
    """1 on days the price-only rules say BUY (trend+momentum+52w setup ≥ BUY_SETUP and the
    entry not extended), else 0. Each day uses only data up to that day."""
    n = c.size
    sig = np.zeros(n)
    if n < 260:
        return sig
    import pandas as pd
    s = pd.Series(c)
    s50, s200, s20 = s.rolling(50).mean(), s.rolling(200).mean(), s.rolling(20).mean()
    logr = np.log(s).diff()
    vol = logr.rolling(252).std() * math.sqrt(252)
    r12_1 = s.shift(21) / s.shift(252) - 1
    hi252 = s.rolling(252, min_periods=200).max()
    tr = np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
    atr14 = pd.Series(np.concatenate([[np.nan], tr])).rolling(14).mean()
    d = s.diff()
    up, dn = d.clip(lower=0), (-d).clip(lower=0)
    rs = up.ewm(alpha=1 / 14, adjust=False).mean() / dn.ewm(alpha=1 / 14, adjust=False).mean()
    rsi14 = 100 - 100 / (1 + rs)
    trend = np.where(s > s200, np.where(s50 > s200, 1.0, 0.5), np.where(s50 > s200, -0.25, -1.0))
    mom = np.tanh(r12_1 / vol)
    high = ((s / hi252 - 0.85) / 0.15).clip(-1, 1)
    w = SETUP_WEIGHTS
    setup = (w["trend"] * trend + w["momentum"] * mom + w["high_52w"] * high) / (w["trend"] + w["momentum"] + w["high_52w"])
    dist = (s - s20) / atr14
    timing = (((-(dist - 0.75) / 1.75).clip(-1, 1)) + ((55 - rsi14) / 20).clip(-1, 1)) / 2
    setup = pd.Series(setup)
    ok = (setup >= BUY_SETUP) & (timing > EXTENDED_TIMING) & setup.notna() & timing.notna()
    sig = ok.to_numpy().astype(float)
    sig[:260] = 0
    return sig


def evaluate_signal(c: np.ndarray, sig: np.ndarray, horizons=(21, 63)) -> Dict[str, Any]:
    """Forward returns after BUY days vs all days. Signals are thinned to one per horizon
    (non-overlapping) so the counts are independent observations."""
    out = {}
    n = c.size
    for hz in horizons:
        fwd = np.full(n, np.nan)
        fwd[:-hz] = c[hz:] / c[:-hz] - 1
        valid = ~np.isnan(fwd)
        base = fwd[valid & (np.arange(n) >= 260)]
        picks, last = [], -10 ** 9
        for i in np.where((sig == 1) & valid)[0]:
            if i - last >= hz:
                picks.append(i)
                last = i
        sel = fwd[picks] if picks else np.array([])
        out[f"{hz}d"] = {
            "signals": int(len(picks)),
            "avg_return": round(float(sel.mean()), 4) if sel.size else None,
            "hit_rate": round(float((sel > 0).mean()), 3) if sel.size else None,
            "base_avg_return": round(float(base.mean()), 4) if base.size else None,
            "base_hit_rate": round(float((base > 0).mean()), 3) if base.size else None,
        }
    return out
