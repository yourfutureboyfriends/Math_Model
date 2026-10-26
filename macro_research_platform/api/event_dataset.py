"""
Macro event dataset — the first building block of a macro-transmission research engine: what was published, when,
how unexpected it was (a labelled proxy), and how liquid markets moved afterwards.

Point-in-time by construction:
* Economic releases use ALFRED vintages: the value of each month AND the months before it as they stood on the
  release date (later revisions are never used). The release date is ALFRED's realtime_start; the time of day is the
  agency's fixed schedule (BLS 08:30 ET).
* The "surprise" is a PROXY — consensus forecasts are licensed, so: actual minus the mean of the previous six prints
  as known on the release date (CPI m/m, payroll change), or minus the previous print (unemployment rate). The
  standardised surprise divides by the standard deviation of the previous 24 surprises (only earlier events).
* FOMC decisions: the actual is the change in the target range's upper bound; the surprise proxy is the 2-year
  Treasury yield change on the decision day — a market measure that CONTAINS the reaction (fed funds futures, the
  standard measure, are not free); flagged on every row.
* Reactions: for each asset, the last close before the release time → the first close after it (h0), and five
  sessions later (h5). London listings close 11:30 ET, US listings and FRED yields 16:00 ET, Yahoo FX daily bars
  ~17:00 ET (their timing is approximate). Returns in % of the asset's own currency; yields in bp.

The dataset is versioned by a hash of its inputs and rows; summaries are descriptive and in-sample.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

VERSION = "events-1"
START = "2015-01-01"

RELEASES = {
    "us_cpi": {"label": "US CPI (headline, m/m %)", "series": "CPIAUCSL", "how": "pct_mom", "time": "08:30",
               "agency": "BLS", "proxy": "actual − mean of the previous 6 first-print m/m changes (as known then)"},
    "us_core_cpi": {"label": "US core CPI (m/m %)", "series": "CPILFESL", "how": "pct_mom", "time": "08:30",
                    "agency": "BLS", "proxy": "actual − mean of the previous 6 m/m changes (as known then)"},
    "us_payrolls": {"label": "US nonfarm payrolls (change, thousands)", "series": "PAYEMS", "how": "diff", "time": "08:30",
                    "agency": "BLS", "proxy": "actual − mean of the previous 6 monthly changes (as known then)"},
    "us_unemployment": {"label": "US unemployment rate (%)", "series": "UNRATE", "how": "level", "time": "08:30",
                        "agency": "BLS", "proxy": "actual − previous month (as known then)"},
}
FOMC = {"label": "FOMC decision (target upper bound change, bp)", "time": "14:00",
        "proxy": "2-year Treasury yield change on the decision day, bp (market-based; contains the reaction itself)"}

# asset → (source, close time ET as "HH:MM", unit)
ASSETS = {
    "USDJPY=X": ("yahoo", "17:00", "%"), "EURUSD=X": ("yahoo", "17:00", "%"), "GBPUSD=X": ("yahoo", "17:00", "%"),
    "CSPX.L": ("yahoo", "11:30", "%"), "SWDA.L": ("yahoo", "11:30", "%"), "SJPA.L": ("yahoo", "11:30", "%"),
    "IDTL.L": ("yahoo", "11:30", "%"), "IGLT.L": ("yahoo", "11:30", "%"), "SGLN.L": ("yahoo", "11:30", "%"),
    "CMOD.L": ("yahoo", "11:30", "%"), "DGS2": ("fred", "16:00", "bp"), "DGS10": ("fred", "16:00", "bp"),
}


def _vintages(series: str) -> List[Dict[str, Any]]:
    from api.providers import alfred
    obs = alfred._fetch({"series_id": series, "realtime_start": "1776-07-04", "realtime_end": "9999-12-31",
                         "output_type": 1, "observation_start": "2013-01-01"}, f"{series}_vint_2013-01-01")
    return [{"date": o["date"], "value": alfred._num(o["value"]), "rs": o["realtime_start"], "re": o["realtime_end"]}
            for o in obs]


def _as_of(vint: List[Dict[str, Any]], on: str) -> Dict[str, float]:
    """{observation month: value} as published on `on`."""
    out = {}
    for v in vint:
        if v["rs"] <= on <= v["re"] and v["value"] is not None:
            out[v["date"]] = v["value"]
    return out


def _metric(series: Dict[str, float], month: str, how: str) -> Optional[float]:
    months = sorted(series)
    if month not in series:
        return None
    i = months.index(month)
    if how == "level":
        return series[month]
    if i == 0:
        return None
    prev = series[months[i - 1]]
    if how == "diff":
        return series[month] - prev
    return (series[month] / prev - 1) * 100 if prev else None


def release_events(code: str) -> List[Dict[str, Any]]:
    """One row per release of `code` since START: value, prior and surprise proxy as known on the release date."""
    spec = RELEASES[code]
    vint = _vintages(spec["series"])
    firsts: Dict[str, str] = {}
    for v in vint:                                  # each month's first publication date
        if v["value"] is not None and (v["date"] not in firsts or v["rs"] < firsts[v["date"]]):
            firsts[v["date"]] = v["rs"]
    rows, past_surprises = [], []
    for month, rel in sorted(firsts.items(), key=lambda x: x[1]):
        if rel < START:
            continue
        known = _as_of(vint, rel)
        actual = _metric(known, month, spec["how"])
        if actual is None:
            continue
        earlier = [m for m in sorted(known) if m < month]
        hist = [x for x in (_metric(known, m, spec["how"]) for m in earlier[-6:]) if x is not None]
        prior = _metric(known, earlier[-1], spec["how"]) if earlier else None
        expect = prior if spec["how"] == "level" else (sum(hist) / len(hist) if len(hist) >= 3 else None)
        surprise = actual - expect if expect is not None else None
        z = None
        if surprise is not None and len(past_surprises) >= 12:
            w = past_surprises[-24:]
            mu = sum(w) / len(w)
            sd = math.sqrt(sum((x - mu) ** 2 for x in w) / (len(w) - 1))
            z = surprise / sd if sd else None
        if surprise is not None:
            past_surprises.append(surprise)
        rows.append({"event": code, "label": spec["label"], "date": rel, "time_et": spec["time"], "period": month[:7],
                     "actual": round(actual, 4), "prior": round(prior, 4) if prior is not None else None,
                     "expectation_proxy": round(expect, 4) if expect is not None else None,
                     "surprise": round(surprise, 4) if surprise is not None else None,
                     "surprise_z": round(z, 3) if z is not None else None, "proxy": spec["proxy"]})
    return rows


def fomc_events() -> List[Dict[str, Any]]:
    """FOMC decisions since 2013 with the target change and the 2-year yield reaction as the surprise proxy."""
    from api.macro_calendar import _fetch_fomc_meetings
    from api.providers import alfred
    tgt = {o["date"]: o["value"] for o in alfred.latest("DFEDTARU", "2013-01-01") if o["value"] is not None}
    y2 = {o["date"]: o["value"] for o in alfred.latest("DGS2", "2013-01-01") if o["value"] is not None}
    td, yd = sorted(tgt), sorted(y2)
    today = date.today().isoformat()
    rows, past = [], []

    def before(days, series, d):
        p = [x for x in days if x < d]
        return series[p[-1]] if p else None

    def on_or_after(days, series, d, lag=0):
        p = [x for x in days if x >= d]
        return series[p[lag]] if len(p) > lag else None
    for _, d in _fetch_fomc_meetings():
        if d < START or d >= today:
            continue
        t0, t1 = before(td, tgt, d), on_or_after(td, tgt, (date.fromisoformat(d) + timedelta(days=1)).isoformat())
        a, b = before(yd, y2, d), (y2.get(d))
        actual = (t1 - t0) * 100 if t0 is not None and t1 is not None else None
        surprise = (b - a) * 100 if a is not None and b is not None else None
        z = None
        if surprise is not None and len(past) >= 12:
            w = past[-24:]
            mu = sum(w) / len(w)
            sd = math.sqrt(sum((x - mu) ** 2 for x in w) / (len(w) - 1))
            z = surprise / sd if sd else None
        if surprise is not None:
            past.append(surprise)
        rows.append({"event": "fomc", "label": FOMC["label"], "date": d, "time_et": FOMC["time"], "period": d[:7],
                     "actual": round(actual, 1) if actual is not None else None, "prior": None, "expectation_proxy": None,
                     "surprise": round(surprise, 1) if surprise is not None else None,
                     "surprise_z": round(z, 3) if z is not None else None, "proxy": FOMC["proxy"]})
    return rows


def _closes(asset: str) -> Dict[str, float]:
    src = ASSETS[asset][0]
    if src == "fred":
        from api.providers import alfred
        return {o["date"]: o["value"] for o in alfred.latest(asset, "2014-06-01") if o["value"] is not None}
    from api.calculations import benchmark as bm
    s = bm._closes_local(asset)
    return {d.strftime("%Y-%m-%d"): float(v) for d, v in s.items()}


def _reaction(closes: Dict[str, float], days: List[str], d: str, t_event: str, t_close: str, unit: str
              ) -> Tuple[Optional[float], Optional[float]]:
    """(h0, h5): last close before the event → first close after it, and five sessions after that."""
    if not days:
        return None, None
    i_after = next((i for i, x in enumerate(days) if x > d or (x == d and t_close > t_event)), None)
    if i_after is None or i_after == 0:
        return None, None
    pre = closes[days[i_after - 1]]

    def chg(j):
        if j >= len(days) or pre in (None, 0):
            return None
        v = closes[days[j]]
        return round((v - pre) * 100, 1) if unit == "bp" else round((v / pre - 1) * 100, 3)
    return chg(i_after), chg(i_after + 5)


def build() -> Dict[str, Any]:
    """The full dataset (all event types, reactions of every asset) with its version hash."""
    events: List[Dict[str, Any]] = []
    errors = {}
    for code in RELEASES:
        try:
            events += release_events(code)
        except Exception as e:                                                 # noqa: BLE001 — reported per source
            errors[code] = f"{type(e).__name__}: {str(e)[:160]}"
    try:
        events += fomc_events()
    except Exception as e:                                                     # noqa: BLE001
        errors["fomc"] = f"{type(e).__name__}: {str(e)[:160]}"
    px = {}
    for a in ASSETS:
        try:
            px[a] = _closes(a)
        except Exception as e:                                                 # noqa: BLE001
            errors[a] = f"{type(e).__name__}: {str(e)[:160]}"
    days = {a: sorted(v) for a, v in px.items()}
    for ev in events:
        ev["reactions"] = {}
        for a, (_, tclose, unit) in ASSETS.items():
            if a not in px:
                continue
            h0, h5 = _reaction(px[a], days[a], ev["date"], ev["time_et"], tclose, unit)
            ev["reactions"][a] = {"h0": h0, "h5": h5, "unit": unit}
    events.sort(key=lambda e: (e["date"], e["event"]))
    body = json.dumps(events, sort_keys=True, default=str)
    return {"version": VERSION, "hash": hashlib.sha256(body.encode()).hexdigest()[:16], "built_at": datetime.now().isoformat(timespec="seconds"),
            "start": START, "events": events, "errors": errors, "event_types": {**{k: v["label"] for k, v in RELEASES.items()}, "fomc": FOMC["label"]},
            "assets": {a: {"source": s, "close_et": t, "unit": u} for a, (s, t, u) in ASSETS.items()},
            "method": __doc__.strip()}


_MEM: Dict[str, Any] = {}


def dataset(refresh: bool = False) -> Dict[str, Any]:
    """The dataset, rebuilt at most every 12 hours (or on request) and kept on disk with its hash, so a published
    result can name the exact version it used."""
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "data" / "processed" / f"event_dataset_{VERSION}.json"
    if not refresh and _MEM.get("d") and (datetime.now() - _MEM["t"]).total_seconds() < 12 * 3600:
        return _MEM["d"]
    if not refresh and path.exists() and (datetime.now().timestamp() - path.stat().st_mtime) < 12 * 3600:
        d = json.loads(path.read_text())
    else:
        d = build()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(d, default=str))
    _MEM.update(d=d, t=datetime.now())
    return d


def summary(ds: Dict[str, Any], event: str, horizon: str = "h0") -> Dict[str, Any]:
    """Per asset: slope of the reaction on the standardised surprise (OLS), its t-statistic, correlation and the
    number of events — descriptive and in-sample; a starting point for hypotheses, not evidence of a tradeable edge."""
    rows = [e for e in ds["events"] if e["event"] == event and e.get("surprise_z") is not None]
    out = {}
    for a in ds["assets"]:
        pts = [(e["surprise_z"], e["reactions"].get(a, {}).get(horizon)) for e in rows]
        pts = [(x, y) for x, y in pts if y is not None]
        n = len(pts)
        if n < 10:
            out[a] = {"n": n}
            continue
        mx, my = sum(x for x, _ in pts) / n, sum(y for _, y in pts) / n
        sxx = sum((x - mx) ** 2 for x, _ in pts)
        sxy = sum((x - mx) * (y - my) for x, y in pts)
        syy = sum((y - my) ** 2 for _, y in pts)
        beta = sxy / sxx if sxx else None
        resid = sum((y - my - beta * (x - mx)) ** 2 for x, y in pts) if beta is not None else None
        se = math.sqrt(resid / (n - 2) / sxx) if resid is not None and sxx and n > 2 else None
        if event == "fomc" and a == "DGS2" and horizon == "h0":
            out[a] = {"n": n, "mechanical": True, "note": "the FOMC surprise proxy is this series' change: not a result"}
            continue
        out[a] = {"n": n, "beta_per_1sd": round(beta, 4) if beta is not None else None,
                  "t_stat": round(beta / se, 2) if beta is not None and se else None,
                  "corr": round(sxy / math.sqrt(sxx * syy), 3) if sxx and syy else None,
                  "unit": ds["assets"][a]["unit"]}
    return {"event": event, "horizon": horizon, "events": len(rows), "by_asset": out,
            "caveat": "In-sample, descriptive, one test per asset (multiple testing not controlled); surprise is a "
                      "proxy. Treat a large t-statistic as a hypothesis for G0, not as evidence."}
