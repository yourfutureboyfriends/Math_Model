"""
Trade management — when to hold, tighten, trim, add to or exit a position, from technicals, fundamentals and news.
The entry side lives in stock_timing.py; this module answers "I'm in — what now?".

Each rule returns a signal {rule, action, evidence, source}; the position's action is the most severe one
(EXIT > TRIM > TIGHTEN > HOLD; ADD only when nothing argues against it).

Evidence for the defaults (exit_evidence below; the same price-only entry signals managed by each exit rule, 30
large caps, 10 years of daily data, 0.1% round-trip cost — Oct 2026):

    exit rule                                profit factor   return / year held   worst trade
    fixed 2.5×ATR stop + 2R target               1.64              17.7%             −31%
    chandelier 3×ATR(22) trailing stop           1.89              20.7%             −31%
    200-day trend break + initial stop           2.73              22.6%             −18%
    chandelier + trend + 60-session time stop    1.76              19.6%             −31%

The trend-break exit led in both halves of the decade (profit factor 2.75 / 2.29 vs the fixed target's 1.86 / 1.46);
wider chandelier stops (4–5×ATR) raised the profit factor but not the return per year held. So: exit on the trend,
let winners run (a target only tightens the stop), no time stop, and the chandelier is the tightened stop used when
a warning fires. Caveat: today's mega caps over a strong decade (survivorship) flatter any rule that holds longer.
Stop-losses add value when returns trend and cost money in a random walk (Kaminski & Lo, "When do stop-loss rules stop
losses?", J. Financial Markets, 2014) — trend-following entries are where they belong; a 10% stop on momentum winners
cut the worst monthly loss from about −50% to −11% in US data 1926–2011, before costs (Han, Zhou & Zhu, "Taming
momentum crashes", working paper).

Stops:
  initial      2.5 × ATR(14) from the entry — the entry model's stop, in force from day one.
  tightened    when a TIGHTEN warning fires: the chandelier level, highest close since entry − 3 × ATR(22) (LeBeau),
               or 2 ATRs from the price if that is closer — the stop only ever moves in the trade's favour.

Exit and trim rules:
  stop_hit         close through the stop in force → EXIT
  trend_break      close below the 200-day average (Faber, 2007) → EXIT (the best exit in the test above);
                   50-day below 200-day → TIGHTEN
  momentum         12-1 month return turns negative (Moskowitz, Ooi & Pedersen, 2012) → TRIM
  analyst_cuts     net downgrades or average price-target cuts in the last 30 days — revisions drift, analysts
                   update slowly (Chan, Jegadeesh & Lakonishok, J. Finance, 1996) → TRIM
  earnings_miss    a negative surprise in the last 60 days — post-earnings drift (Bernard & Thomas, 1989) → TIGHTEN
  news_tone        a run of negative headlines — negative media tone predicts lower returns, partly reversing
                   (Tetlock, J. Finance, 2007) → TIGHTEN (not an exit on its own)
  vol_spike        20-day volatility above twice its one-year median — scale exposure inversely to volatility
                   (Moreira & Muir, "Volatility-managed portfolios", J. Finance, 2017) → TRIM
  market_risk_off  home index below its 200-day average or VIX ≥ 30 — momentum crashes cluster in panics (Daniel &
                   Moskowitz, J. Financial Economics, 2016) → TIGHTEN
  target_reached   at or beyond the target → TIGHTEN, not sell: the fixed-target exit was the weakest rule tested
  earnings_ahead   a report within 5 days on a position up ≥ 1R → TRIM (gap risk on a gain)
Supportive:
  insider_buying   two or more insiders buying in the open market in 90 days — informed, "opportunistic" insider
                   trades predict returns (Cohen, Malloy & Pomorski, J. Finance, 2012); insider *sales* are mostly
                   liquidity-driven and carry little information (Lakonishok & Lee, 2001), so they are only noted.
  add              the entry model still says BUY, the price has pulled back, the trade is in profit and nothing
                   above argues against it → ADD (pyramid into strength, never into a loser).

All functions are pure (arrays in, dict out) and use only data up to the last bar.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

import numpy as np

from api.calculations.stock_timing import atr, sma

INITIAL_ATR, TRAIL_ATR, TRAIL_ATR_N = 2.5, 3.0, 22
TIME_STOP_SESSIONS, TIME_STOP_MIN_R = 60, 0.5        # only in the evidence test's "combined" rule (it did not help)
VOL_SPIKE = 2.0
SEVERITY = {"EXIT": 4, "TRIM": 3, "TIGHTEN": 2, "HOLD": 1, "ADD": 0}


def _sig(rule: str, action: str, evidence: str, source: str) -> Dict[str, str]:
    return {"rule": rule, "action": action, "evidence": evidence, "source": source}


def chandelier_stop(c: np.ndarray, h: np.ndarray, l: np.ndarray, entry_idx: int, side: int = 1,
                    mult: float = TRAIL_ATR, n: int = TRAIL_ATR_N) -> Optional[float]:
    """Trailing stop: the extreme close since entry minus (long) / plus (short) mult × ATR(n) as of today."""
    a = atr(h, l, c, n)
    if a is None or entry_idx >= len(c):
        return None
    seg = c[entry_idx:]
    return float(seg.max() - mult * a) if side > 0 else float(seg.min() + mult * a)


def realised_vol(c: np.ndarray, n: int) -> Optional[float]:
    """Annualised volatility of the last n daily returns."""
    if c.size < n + 1:
        return None
    r = np.diff(np.log(c[-(n + 1):]))
    return float(r.std(ddof=1) * np.sqrt(252))


def manage_position(c: np.ndarray, h: np.ndarray, l: np.ndarray, entry_idx: int, entry_price: float, side: int = 1,
                    *, today: Optional[date] = None, target: Optional[float] = None,
                    entry_verdict: Optional[str] = None, timing_state: Optional[str] = None,
                    momentum_score: Optional[float] = None, market_ok: Optional[bool] = None, vix: Optional[float] = None,
                    market_name: Optional[str] = None,
                    revisions: Optional[List[Dict[str, Any]]] = None, earnings: Optional[List[Dict[str, Any]]] = None,
                    news: Optional[List[Dict[str, Any]]] = None, insiders: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """What to do with an open position.

    Args:
        c, h, l: Daily closes, highs, lows (oldest first) up to today.
        entry_idx: Index of the entry bar in the arrays.
        entry_price: Average entry price.
        side: +1 long, −1 short.
        today: Date of the last bar (for the event windows).
        target: Price objective (consensus target or 2R projection), if any.
        entry_verdict: The entry model's current verdict code (BUY, WAIT, …) — for ADD.
        timing_state: Entry timing state (pullback / neutral / extended) — for ADD.
        momentum_score: The entry model's momentum component score (−1..+1).
        market_ok: Home index above its 200-day average and VIX calm.
        vix: Latest VIX.
        revisions: Analyst rating / target changes [{date, action, target_change}], newest first.
        earnings: Earnings [{date, surprise_pct, reported}].
        news: Recent headlines for the stock [{time, sentiment}].
        insiders: Insider activity {open_market_buys_6m, buyers_6m, buyers_90d?, sellers_6m}.

    Returns:
        {action, label, stop, stops, r_multiple, signals, ...}.
    """
    today = today or date.today()
    px = float(c[-1])
    a14 = atr(h, l, c, 14)
    if a14 is None or entry_idx < 0 or entry_idx >= len(c):
        return {"available": False, "reason": "not enough price history since the entry"}
    a_at_entry = atr(h[: entry_idx + 1], l[: entry_idx + 1], c[: entry_idx + 1], 14) or a14
    initial = entry_price - side * INITIAL_ATR * a_at_entry
    risk = abs(entry_price - initial)
    r_mult = side * (px - entry_price) / risk if risk > 0 else None
    trailing = chandelier_stop(c, h, l, entry_idx, side)
    stop = initial
    s50, s200 = sma(c, 50), sma(c, 200)
    held = len(c) - 1 - entry_idx
    signals: List[Dict[str, str]] = []

    # Price rules
    if (side > 0 and px <= stop) or (side < 0 and px >= stop):
        signals.append(_sig("stop_hit", "EXIT", f"Close {px:,.2f} is through the initial stop {stop:,.2f}.",
                            "Kaminski & Lo (2014)"))
    if s200 is not None:
        if side > 0 and px < s200:
            signals.append(_sig("trend_break", "EXIT", f"Close {px:,.2f} below the 200-day average {s200:,.2f}.", "Faber (2007)"))
        elif side < 0 and px > s200:
            signals.append(_sig("trend_break", "EXIT", f"Close {px:,.2f} above the 200-day average {s200:,.2f} (short).", "Faber (2007)"))
        elif s50 is not None and side > 0 and s50 < s200:
            signals.append(_sig("trend_weakening", "TIGHTEN", f"50-day average {s50:,.2f} below the 200-day {s200:,.2f}.", "Faber (2007)"))
    if momentum_score is not None and side * momentum_score < 0:
        signals.append(_sig("momentum", "TRIM", f"12-1 month momentum has turned {'negative' if side > 0 else 'positive'} (score {momentum_score:+.2f}).",
                            "Moskowitz, Ooi & Pedersen (2012)"))
    v20, v252 = realised_vol(c, 20), None
    if c.size >= 273:
        lr = np.diff(np.log(c[-273:]))
        roll = np.array([lr[i - 20:i].std(ddof=1) for i in range(20, len(lr) + 1)]) * np.sqrt(252)
        v252 = float(np.median(roll))
    if v20 is not None and v252 and v20 > VOL_SPIKE * v252:
        signals.append(_sig("vol_spike", "TRIM", f"20-day volatility {v20:.0%} is {v20 / v252:.1f}× its one-year median {v252:.0%}: cut size to keep risk constant.",
                            "Moreira & Muir (2017)"))
    if market_ok is False or (vix is not None and vix >= 30):
        # name the actual trigger: the stock's home index below its 200-day average, and / or VIX at 30 or above
        why = [f"{market_name or 'the home index'} below its 200-day average"] if market_ok is False else []
        if vix is not None and vix >= 30:
            why.append(f"VIX {vix:.0f}")
        signals.append(_sig("market_risk_off", "TIGHTEN", f"Market regime risk-off ({' and '.join(why)}): momentum positions crash in panics.",
                            "Daniel & Moskowitz (2016)"))
    if target and ((side > 0 and px >= target) or (side < 0 and px <= target)):
        signals.append(_sig("target_reached", "TIGHTEN", f"At the target {target:,.2f}: tighten the stop and let it run — the fixed-target "
                            "exit was the weakest rule in the platform's test.", "exit evidence (this module)"))

    # Fundamentals and news
    recent = [r for r in (revisions or []) if r.get("date") and (today - date.fromisoformat(r["date"][:10])).days <= 30]
    downs = sum(1 for r in recent if "down" in str(r.get("action", "")))
    ups = sum(1 for r in recent if "up" in str(r.get("action", "")))
    cuts = [r["target_change"] for r in recent if isinstance(r.get("target_change"), (int, float))]
    if side > 0 and (downs - ups >= 2 or (len(cuts) >= 2 and np.mean(cuts) < 0 and sum(1 for x in cuts if x < 0) >= 2)):
        signals.append(_sig("analyst_cuts", "TRIM", f"Last 30 days: {downs} downgrade(s), {ups} upgrade(s), {sum(1 for x in cuts if x < 0)} target cut(s).",
                            "Chan, Jegadeesh & Lakonishok (1996)"))
    past = sorted((e for e in (earnings or []) if e.get("reported") is not None and e.get("surprise_pct") is not None
                   and e.get("date") and e["date"] <= today.isoformat()), key=lambda e: e["date"], reverse=True)
    if past and (today - date.fromisoformat(past[0]["date"])).days <= 60 and side * past[0]["surprise_pct"] < -2:
        signals.append(_sig("earnings_miss", "TIGHTEN", f"Earnings {past[0]['date']}: surprise {past[0]['surprise_pct']:+.1f}% — negative drift risk.",
                            "Bernard & Thomas (1989)"))
    upcoming = sorted(e["date"] for e in (earnings or []) if e.get("date") and e["date"] > today.isoformat() and e.get("reported") is None)
    if upcoming and (date.fromisoformat(upcoming[0]) - today).days <= 5 and r_mult is not None and r_mult >= 1:
        signals.append(_sig("earnings_ahead", "TRIM", f"Reports {upcoming[0]} with the position up {r_mult:.1f}R: trim the gap risk on a gain.", "position management"))
    tones = [n["sentiment"] for n in (news or []) if isinstance(n.get("sentiment"), (int, float))]
    if len(tones) >= 3 and side * float(np.mean(tones)) <= -0.2:
        signals.append(_sig("news_tone", "TIGHTEN", f"{len(tones)} recent headlines, average tone {np.mean(tones):+.2f}.", "Tetlock (2007)"))
    buyers = (insiders or {}).get("buyers_6m") or 0
    supportive = []
    if side > 0 and buyers >= 2:
        supportive.append(_sig("insider_buying", "HOLD", f"{buyers} insiders bought in the open market in the last 6 months.",
                               "Cohen, Malloy & Pomorski (2012)"))

    worst = max((s["action"] for s in signals), key=lambda x: SEVERITY[x], default="HOLD")
    if (worst == "HOLD" and entry_verdict in ("BUY", "BUY_SMALL") and timing_state == "pullback"
            and r_mult is not None and r_mult > 0.5 and side > 0):
        worst = "ADD"
        signals.append(_sig("add", "ADD", "Entry model still a BUY, price pulled back, trade in profit: add to the winner.", "pyramiding into strength"))
    if worst in ("TIGHTEN", "TRIM"):
        # A warning while the price is already more than 3 ATRs off its best close since entry: the trail is breached
        # — trim rather than hold on.
        if trailing is not None and ((side > 0 and px <= trailing) or (side < 0 and px >= trailing)) and worst == "TIGHTEN":
            worst = "TRIM"
            signals.append(_sig("trail_breached", "TRIM", f"Already {abs(px - (c[entry_idx:].max() if side > 0 else c[entry_idx:].min())) / a14:.1f} ATRs "
                                "off the best close since entry, through the chandelier level, while a warning is active.", "LeBeau chandelier exit"))
        # Tighten: the chandelier level or 2 ATRs from the price, whichever is closer to the price but still on the
        # right side of it — and never looser than the stop already in force.
        levels_ = [x for x in (trailing, px - side * 2.0 * a14) if x is not None and (x < px if side > 0 else x > px)]
        if levels_:
            tight = max(levels_) if side > 0 else min(levels_)
            stop = max(stop, tight) if side > 0 else min(stop, tight)
    label = {"EXIT": "Exit", "TRIM": "Trim — reduce the position", "TIGHTEN": "Hold — tighten the stop",
             "HOLD": "Hold", "ADD": "Add"}[worst]
    return {"available": True, "action": worst, "label": label, "price": round(px, 4),
            "stop": round(stop, 4), "stop_distance_pct": round(side * (px - stop) / px, 4),
            "stop_basis": "initial 2.5×ATR" if stop == initial else "tightened (chandelier / 2×ATR)",
            "stops": {"initial": round(initial, 4), "trailing": None if trailing is None else round(trailing, 4),
                      "sma200": None if s200 is None else round(s200, 4)},
            "r_multiple": None if r_mult is None else round(r_mult, 2), "risk_per_share": round(risk, 4),
            "sessions_held": held, "vol_20d": None if v20 is None else round(v20, 4),
            "signals": sorted(signals, key=lambda s: -SEVERITY[s["action"]]) + supportive}


# ── Exit-rule evidence: the same entries, different exits (no look-ahead) ───────
EXIT_RULES = {
    "fixed": "Fixed: 2.5×ATR stop, 2R target (the entry model's levels)",
    "chandelier": "Chandelier: 3×ATR(22) trailing stop",
    "trend": "Trend: exit on a close below the 200-day average (with the 2.5×ATR initial stop)",
    "combined": "Combined: chandelier + trend break + 60-session time stop",
}


def simulate_exit(c: np.ndarray, h: np.ndarray, l: np.ndarray, i0: int, rule: str, max_hold: int = 252) -> Optional[Dict[str, float]]:
    """One long trade entered at the close of bar i0 and managed by `rule`; exits at the close that triggers it."""
    a0 = atr(h[: i0 + 1], l[: i0 + 1], c[: i0 + 1], 14)
    if a0 is None:
        return None
    e = float(c[i0])
    init = e - INITIAL_ATR * a0
    target = e + 2 * (e - init)
    peak = e
    for j in range(i0 + 1, min(len(c), i0 + 1 + max_hold)):
        px = float(c[j])
        peak = max(peak, px)
        if px <= init:
            return {"ret": px / e - 1, "r": (px - e) / (e - init), "days": j - i0}
        if rule == "fixed" and px >= target:
            return {"ret": px / e - 1, "r": (px - e) / (e - init), "days": j - i0}
        if rule in ("chandelier", "combined"):
            a = atr(h[: j + 1], l[: j + 1], c[: j + 1], TRAIL_ATR_N)
            if a is not None and px <= peak - TRAIL_ATR * a:
                return {"ret": px / e - 1, "r": (px - e) / (e - init), "days": j - i0}
        if rule in ("trend", "combined") and j >= 200 and px < float(np.mean(c[j - 199: j + 1])):
            return {"ret": px / e - 1, "r": (px - e) / (e - init), "days": j - i0}
        if rule == "combined" and j - i0 >= TIME_STOP_SESSIONS and (px - e) / (e - init) < TIME_STOP_MIN_R:
            return {"ret": px / e - 1, "r": (px - e) / (e - init), "days": j - i0}
    j = min(len(c), i0 + 1 + max_hold) - 1
    if j <= i0:
        return None
    return {"ret": float(c[j]) / e - 1, "r": (float(c[j]) - e) / (e - init), "days": j - i0, "open": True}


def summarise_trades(trades: List[Dict[str, float]], cost: float = 0.001) -> Dict[str, Any]:
    """Win rate, average return and R, profit factor and average holding period, net of a round-trip cost."""
    if not trades:
        return {"trades": 0}
    r = np.array([t["ret"] - cost for t in trades])
    rr = np.array([t["r"] for t in trades])
    gains, losses = r[r > 0].sum(), -r[r < 0].sum()
    return {"trades": int(len(r)), "win_rate": round(float((r > 0).mean()), 3), "avg_return": round(float(r.mean()), 4),
            "median_return": round(float(np.median(r)), 4), "avg_r": round(float(rr.mean()), 2),
            "profit_factor": round(float(gains / losses), 2) if losses > 0 else None,
            "worst": round(float(r.min()), 4), "avg_days": round(float(np.mean([t["days"] for t in trades])), 1),
            "return_per_year_held": round(float(r.sum() / (sum(t["days"] for t in trades) / 252)), 4) if trades else None}
