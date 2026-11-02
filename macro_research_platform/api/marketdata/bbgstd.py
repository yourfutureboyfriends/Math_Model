"""More standard Bloomberg screens built from free data (the first set is in bbgplus.py):

    FWCV  forward curves      — forward rates implied by each government curve (1y1y, 2y1y, 5y5y, 10y10y …)
    ECFC  economic forecasts  — IMF growth, inflation, jobless and fiscal forecasts by country, against the latest CPI
    FOMC  Fed portal          — target range, decisions since 2008, the Fed's own projections (dots) vs market pricing
    EM    earnings matrix     — a company's EPS and revenue by fiscal quarter and year from its SEC filings, with growth
    EA    earnings analysis   — the season so far for an index: beat rates, surprises, price reactions, by sector
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from api.marketdata.core import NotFound, Upstream, _cached, _f

logger = logging.getLogger(__name__)


# ── FWCV ─────────────────────────────────────────────────────────────────────
FWD_PAIRS = [(1, 1), (2, 1), (3, 1), (4, 1), (5, 5), (10, 10), (2, 3), (5, 10)]   # (start, length) in years


def _interp(curve: List[Tuple[float, float]], t: float) -> Optional[float]:
    """Linear interpolation of a yield on tenor (no extrapolation)."""
    ts = [p[0] for p in curve]
    if not ts or t < ts[0] - 1e-9 or t > ts[-1] + 1e-9:
        return None
    return float(np.interp(t, ts, [p[1] for p in curve]))


def forward_rate(curve: List[Tuple[float, float]], start: float, length: float) -> Optional[float]:
    """Annually compounded forward rate (percent) from `start` for `length` years, treating the curve's yields as zero
    rates. For par curves (US Treasury, Canada, Australia) this is a close approximation, not an exact bootstrap."""
    y1, y2 = _interp(curve, start), _interp(curve, start + length)
    if y1 is None or y2 is None:
        return None
    g = (1 + y2 / 100) ** (start + length) / (1 + y1 / 100) ** start
    return (g ** (1 / length) - 1) * 100


def forward_curves() -> Dict[str, Any]:
    """Forward rates implied by each government curve today and a month ago, with the 1-year forward curve."""
    def build():
        from api.marketdata.curves import curves
        gc = curves()
        out = []
        for code in gc["order"]:
            c = gc["curves"][code]
            now = sorted((p["tenor"], p["yield"]) for p in c["points"])
            ago = sorted((p["tenor"], p["yield"]) for p in (c.get("month_ago") or {}).get("points", []))
            pairs = []
            for s, n in FWD_PAIRS:
                f, f0 = forward_rate(now, s, n), forward_rate(ago, s, n) if ago else None
                if f is not None:
                    pairs.append({"label": f"{s}y{n}y", "start": s, "length": n, "rate": f,
                                  "spot_end": _interp(now, s + n), "change_1m_bp": (f - f0) * 100 if f0 is not None else None})
            one_year = []                                       # the 1-year rate expected at each future date
            for s in range(0, 30):
                f = forward_rate(now, s, 1) if s else _interp(now, 1.0)
                if f is None:
                    break
                one_year.append({"start": s, "rate": f, "spot": _interp(now, s + 1)})
            spot1 = _interp(now, 1.0)
            out.append({"code": code, "name": c["name"], "date": c["date"], "source": c["source"], "pairs": pairs, "one_year": one_year,
                        "spot": [{"tenor": t, "yield": y} for t, y in now],
                        "priced_1y_change_bp": (forward_rate(now, 1, 1) - spot1) * 100 if spot1 is not None and forward_rate(now, 1, 1) is not None else None})
        if not out:
            raise Upstream("No government curves available for forwards.")
        return {"curves": out, "unavailable": gc.get("unavailable", {}),
                "note": "Forwards are what today's curve locks in: 5y5y is the 5-year rate five years from now. Yields are treated as "
                        "zero-coupon rates (exact for the Bundesbank, ECB and Bank of England curves; a close approximation for par curves).",
                "source": gc["source"]}
    return _cached("fwcv:v1", 3 * 3600, build)


# ── ECFC ─────────────────────────────────────────────────────────────────────
def economic_forecasts() -> Dict[str, Any]:
    """IMF World Economic Outlook forecasts for this year and next by country, with the latest actual CPI print and the
    policy rate beside them, plus regional medians."""
    def build():
        from api.marketdata import countries
        wd = countries.world_data()
        year = wd["year"]
        cpi: Dict[str, Tuple[float, str]] = {}
        try:
            from api.model.sources import bis_cpi
            start = (date.today() - timedelta(days=500)).strftime("%Y-%m")
            isos = sorted(i for i, c in wd["countries"].items() if c.get("gdp_growth") is not None and len(i) == 2)
            for i in range(0, len(isos), 40):                  # one request per 40 countries keeps the URL short
                for iso, sr in bis_cpi(isos[i:i + 40], start=start).items():
                    sr = sr.dropna()
                    if len(sr) and (pd.Timestamp(date.today()) - sr.index[-1]).days < 200:
                        cpi[iso] = (float(sr.iloc[-1]), sr.index[-1].strftime("%Y-%m"))
        except Exception as e:                                  # noqa: BLE001 — forecasts still show
            logger.info("ecfc cpi: %s", e)
        try:
            from api.marketdata.toolkit import central_banks
            cb = {b["code"]: b["rate"] for b in central_banks()["banks"]}
        except Exception as e:                                  # noqa: BLE001
            logger.info("ecfc policy: %s", e)
            cb = {}
        euro = {"AT", "BE", "CY", "DE", "EE", "ES", "FI", "FR", "GR", "HR", "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PT", "SI", "SK"}
        rows = []
        for iso, c in wd["countries"].items():
            if c.get("gdp_growth") is None and c.get("inflation") is None:
                continue
            pol = cb.get("XM" if iso in euro else iso)
            act = cpi.get(iso)
            rows.append({"iso": iso, "name": c["name"], "region": c.get("region"), "gdp_usd_bn": _f(c.get("gdp_usd_bn")),
                         "gdp_growth": _f(c.get("gdp_growth")), "gdp_growth_next": _f(c.get("gdp_growth_next")),
                         "inflation": _f(c.get("inflation")), "inflation_next": _f(c.get("inflation_next")),
                         "cpi_latest": act[0] if act else None, "cpi_month": act[1] if act else None,
                         "unemployment": _f(c.get("unemployment")), "current_account": _f(c.get("current_account")),
                         "gov_debt": _f(c.get("gov_debt")), "policy_rate": pol,
                         "real_policy_rate": pol - act[0] if pol is not None and act else None})
        if not rows:
            raise Upstream("IMF forecasts unavailable right now.")
        rows.sort(key=lambda r: -(r["gdp_usd_bn"] or 0))

        def med(rs, k):
            v = [r[k] for r in rs if r[k] is not None]
            return float(np.median(v)) if v else None
        regions = []
        for reg in ("americas", "europe", "apac", "mea"):
            rs = [r for r in rows if r["region"] == reg]
            if rs:
                regions.append({"region": reg, "count": len(rs), **{k: med(rs, k) for k in ("gdp_growth", "gdp_growth_next", "inflation", "inflation_next")}})
        weighted = [r for r in rows if r["gdp_usd_bn"] and r["gdp_growth"] is not None]
        world = (sum(r["gdp_usd_bn"] * r["gdp_growth"] for r in weighted) / sum(r["gdp_usd_bn"] for r in weighted)) if weighted else None
        return {"year": year, "rows": rows, "regions": regions, "world_growth_usd_weighted": world,
                "note": f"IMF forecasts for {year} and {year + 1}. 'Latest CPI' is the most recent actual year-on-year print (BIS); "
                        "the gap to the IMF's full-year figure shows whether inflation is running ahead of or behind the forecast. "
                        "World growth is weighted by GDP in US dollars (the IMF's own headline uses purchasing-power weights).",
                "source": "IMF World Economic Outlook; CPI and policy rates BIS."}
    return _cached("ecfc:v1", 6 * 3600, build)


# ── FOMC ─────────────────────────────────────────────────────────────────────
SEP_SERIES = {"fed_funds": ("FEDTARMD", "FEDTARRL", "FEDTARRH", "FEDTARMDLR"), "gdp": ("GDPC1MD", "GDPC1RL", "GDPC1RH", "GDPC1MDLR"),
              "unemployment": ("UNRATEMD", "UNRATERL", "UNRATERH", "UNRATEMDLR"), "pce": ("PCECTPIMD", "PCECTPIRL", "PCECTPIRH", "PCECTPIMDLR"),
              "core_pce": ("JCXFEMD", "JCXFERL", "JCXFERH", None)}
SEP_LABEL = {"fed_funds": "Fed funds rate (year end)", "gdp": "Real GDP growth (Q4/Q4)", "unemployment": "Unemployment rate (Q4)",
             "pce": "PCE inflation (Q4/Q4)", "core_pce": "Core PCE inflation (Q4/Q4)"}


def fomc() -> Dict[str, Any]:
    """The Fed in one screen: target range and effective rate, every decision since 2008, the latest Summary of Economic
    Projections (median and range), and the market's implied path from fed funds futures set against the dots."""
    def build():
        import concurrent.futures as cf
        from api.marketdata.insights import _fred
        ids = ["DFEDTARU", "DFEDTARL", "DFF"] + [s for v in SEP_SERIES.values() for s in v if s]

        def one(sid):
            try:
                return sid, _fred(sid, years=19)
            except Exception as e:                              # noqa: BLE001 — a missing series leaves a gap
                logger.info("fomc %s: %s", sid, e)
                return sid, {}
        with cf.ThreadPoolExecutor(6) as ex:
            got = dict(ex.map(one, ids))
        upper = pd.Series(got.get("DFEDTARU") or {}, dtype=float)
        if upper.empty:
            raise Upstream("Fed target data unavailable (FRED).")
        upper.index = pd.to_datetime(upper.index)
        upper = upper.sort_index()
        lower = pd.Series(got.get("DFEDTARL") or {}, dtype=float)
        lower.index = pd.to_datetime(lower.index)
        moves = upper[upper.diff().abs() > 1e-9]
        decisions = [{"date": str(d.date()), "change_bp": round(float(upper.diff()[d]) * 100), "upper": float(v),
                      "lower": float(lower[lower.index <= d].iloc[-1]) if (lower.index <= d).any() else None}
                     for d, v in moves.items()][::-1]
        effr = got.get("DFF") or {}
        last_effr = (max(effr), effr[max(effr)]) if effr else (None, None)
        sep: Dict[str, Any] = {}
        for k, (md, lo, hi, lr) in SEP_SERIES.items():
            m = got.get(md) or {}
            if not m:
                continue
            years = sorted(m)
            sep[k] = {"label": SEP_LABEL[k], "years": [{"year": int(y[:4]), "median": m[y], "low": (got.get(lo) or {}).get(y),
                                                        "high": (got.get(hi) or {}).get(y)} for y in years if int(y[:4]) >= date.today().year],
                      "longer_run": (lambda s: s[max(s)] if s else None)(got.get(lr) or {}) if lr else None}
        market = None
        try:
            from api.marketdata.extras import wirp
            w = wirp()
            meet = w.get("meetings") or []
            ye = [m for m in meet if m["meeting"][:4] == str(date.today().year)]
            ny = [m for m in meet if m["meeting"][:4] == str(date.today().year + 1)]
            market = {"next_meeting": meet[0] if meet else None, "path": meet,
                      "year_end": ye[-1]["implied_rate"] if ye else _f(w.get("effective_rate")),
                      "next_year_end": ny[-1]["implied_rate"] if ny else None, "as_of": w.get("as_of")}
        except Exception as e:                                  # noqa: BLE001
            logger.info("fomc wirp: %s", e)
        dots = {y["year"]: y["median"] for y in (sep.get("fed_funds") or {}).get("years", [])}
        gap = None
        if market:
            gap = [{"year": yr, "dots": dots.get(yr), "market": mk, "gap_bp": (mk - dots[yr]) * 100 if mk is not None and dots.get(yr) is not None else None}
                   for yr, mk in ((date.today().year, market["year_end"]), (date.today().year + 1, market["next_year_end"]))]
        hikes = sum(1 for d in decisions if d["change_bp"] > 0 and d["date"] >= str(date.today() - timedelta(days=730)))
        cuts = sum(1 for d in decisions if d["change_bp"] < 0 and d["date"] >= str(date.today() - timedelta(days=730)))
        return {"target_upper": float(upper.iloc[-1]), "target_lower": float(lower.iloc[-1]) if len(lower) else None,
                "target_date": str(upper.index[-1].date()), "effective": last_effr[1], "effective_date": last_effr[0],
                "last_move": decisions[0] if decisions else None, "hikes_2y": hikes, "cuts_2y": cuts,
                "decisions": decisions, "sep": sep, "market": market, "dots_vs_market": gap,
                "note": "Dots are the median of FOMC participants' year-end projections from the latest Summary of Economic Projections; "
                        "the market path is the fed funds futures-implied rate after each meeting (WIRP).",
                "source": "FRED (Federal Reserve target range, effective rate, Summary of Economic Projections); CME fed funds futures via Yahoo."}
    return _cached("fomc:v1", 3 * 3600, build)


# ── EM ───────────────────────────────────────────────────────────────────────
def earnings_matrix(symbol: str, years: int = 6) -> Dict[str, Any]:
    """Diluted EPS and revenue by fiscal year and quarter (Q4 derived from the 10-K where needed), each with growth on the
    same quarter a year earlier, as first filed."""
    from api.marketdata.extras import _company_only
    symbol = symbol.strip().upper()
    _company_only(symbol, "the earnings matrix")
    years = max(2, min(int(years), 12))

    def build():
        from api.providers import sec_edgar as se
        ent = se.resolve(symbol)
        facts = se.company_facts(ent["cik"]) if ent else None
        if not facts:
            raise NotFound(f"{symbol} doesn't file US GAAP statements with the SEC, so there is no quarterly history here.")
        out: Dict[str, Any] = {}
        for field in ("eps_diluted", "revenue"):
            _, pts = se._pick_tag(facts, se.DURATION[field])
            out[field] = (se.quarterly(pts), se.annual(pts)) if pts else ([], [])
        q_eps, a_eps = out["eps_diluted"]
        # EPS as first filed is on that day's share count: restate it for later splits so growth compares like with like
        try:
            from api.marketdata.corporate import actions
            splits = [(s["date"], float(s["ratio"])) for s in actions(symbol).get("splits", []) if s.get("ratio")]
        except Exception as e:                                 # noqa: BLE001 — no splits is the common case
            logger.info("em splits %s: %s", symbol, e)
            splits = []
        if splits:
            adj = lambda r: {**r, "val": r["val"] / float(np.prod([x for d, x in splits if d > r["filed"]] or [1.0]))}
            q_eps, a_eps = [adj(r) for r in q_eps], [adj(r) for r in a_eps]
        q_rev, a_rev = out["revenue"]
        ends = sorted({r["end"] for r in a_eps} | {r["end"] for r in a_rev})
        if not ends or not (q_eps or q_rev):
            raise NotFound(f"Not enough quarterly figures in {symbol}'s filings.")
        qe = {r["end"]: r["val"] for r in q_eps}
        qr = {r["end"]: r["val"] for r in q_rev}
        ae = {r["end"]: r["val"] for r in a_eps}
        ar = {r["end"]: r["val"] for r in a_rev}
        qends = sorted(set(qe) | set(qr))
        # fiscal years: the quarters that end after the previous 10-K year end, up to this one; then the open year
        bounds = [(ends[i - 1] if i else "0000-00-00", ends[i]) for i in range(len(ends))]
        last = ends[-1]
        open_q = [e for e in qends if e > last]
        if open_q:
            nxt = (pd.Timestamp(last) + pd.DateOffset(years=1)).strftime("%Y-%m-%d")
            bounds.append((last, nxt))
        rows = []
        for lo, hi in bounds[-years:]:
            qs = [e for e in qends if lo < e <= hi and (pd.Timestamp(hi) - pd.Timestamp(e)).days < 380]
            fy = pd.Timestamp(hi).year                           # named for the calendar year it ends in (Apple FY2025 = Sep 2025)
            closed = hi in ae or hi in ar
            rows.append({"fiscal_year": fy, "year_end": hi, "complete": closed,
                         "quarters": [{"q": i + 1, "end": e, "eps": qe.get(e), "revenue": qr.get(e)} for i, e in enumerate(qs[-4:])],
                         "eps": ae.get(hi), "revenue": ar.get(hi)})
        for i, r in enumerate(rows):                           # growth on the same quarter / year a year earlier
            prev = rows[i - 1] if i else None
            for q in r["quarters"]:
                pq = next((x for x in (prev or {}).get("quarters", []) if x["q"] == q["q"]), None)
                for k in ("eps", "revenue"):
                    a, b = q.get(k), (pq or {}).get(k)
                    q[f"{k}_yoy"] = (a / b - 1) if a is not None and b and b > 0 else None
            for k in ("eps", "revenue"):
                a, b = r.get(k), (prev or {}).get(k)
                r[f"{k}_yoy"] = (a / b - 1) if a is not None and b and b > 0 else None
        ttm_e = sum(qe[e] for e in qends[-4:] if e in qe) if len([e for e in qends[-4:] if e in qe]) == 4 else None
        ttm_r = sum(qr[e] for e in qends[-4:] if e in qr) if len([e for e in qends[-4:] if e in qr]) == 4 else None
        return {"symbol": symbol, "name": facts.get("entityName"), "rows": rows, "ttm_eps": ttm_e, "ttm_revenue": ttm_r,
                "last_quarter_end": qends[-1] if qends else None,
                "source": "SEC EDGAR XBRL, as first filed (EPS restated for later splits); Q4 derived as the 10-K year minus the first three quarters where it isn't reported."}
    return _cached(f"em:{symbol}:{years}", 6 * 3600, build)


# ── EA ───────────────────────────────────────────────────────────────────────
def _calendar_weeks(start: date, end: date, min_cap: float) -> List[Dict[str, Any]]:
    """Yahoo's earnings calendar a week at a time, 100 rows per page (larger windows silently truncate)."""
    import yfinance as yf
    from api.marketdata.core import yahoo_call
    rows: List[Dict[str, Any]] = []
    s = start
    while s < end:
        e = min(s + timedelta(days=7), end)
        for off in range(0, 1000, 100):
            df = yahoo_call(lambda: yf.Calendars().get_earnings_calendar(market_cap=min_cap, filter_most_active=False,
                                                                         start=s.isoformat(), end=e.isoformat(), limit=100, offset=off))
            if df is None or df.empty:
                break
            for sym, r in df.iterrows():
                t = r.get("Event Start Date")
                rows.append({"symbol": str(sym), "company": r.get("Company"), "datetime": t.isoformat() if hasattr(t, "isoformat") else str(t),
                             "timing": str(r.get("Timing")), "eps_estimate": _f(r.get("EPS Estimate")),
                             "eps_reported": _f(r.get("Reported EPS")), "surprise_pct": _f(r.get("Surprise(%)"))})
            if len(df) < 100:
                break
        s = e
    seen, out = set(), []
    for r in rows:                                              # one row per company per report
        k = (r["symbol"], r["datetime"][:10])
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def earnings_analysis(code: str = "SPX", days: int = 45) -> Dict[str, Any]:
    """The reporting season so far for an index's members: how many have reported, beat and missed, the size of the
    surprises, how the shares reacted (beats vs misses), and the same by sector."""
    code = code.strip().upper()
    if code not in ("SPX", "NDX", "INDU"):
        raise NotFound("Earnings analysis covers SPX, NDX and INDU.")
    days = max(14, min(int(days), 92))

    def build():
        from api.marketdata import funds
        memb = funds.index_members(code)
        members = {str(m["symbol"]).replace(".", "-"): m for m in memb["members"] if m.get("symbol")}
        end = date.today() + timedelta(days=1)
        cal = _calendar_weeks(end - timedelta(days=days), end + timedelta(days=14), 2e9)
        today = pd.Timestamp(date.today())
        rep = [r for r in cal if r["symbol"] in members and r["eps_reported"] is not None and r["eps_estimate"] is not None
               and pd.Timestamp(r["datetime"][:10]) <= today]
        upcoming = sorted((r for r in cal if r["symbol"] in members and r["eps_reported"] is None and pd.Timestamp(r["datetime"][:10]) >= today),
                          key=lambda r: r["datetime"])
        latest: Dict[str, Dict[str, Any]] = {}
        for r in sorted(rep, key=lambda r: r["datetime"]):
            latest[r["symbol"]] = r                             # the latest report per company
        rep = list(latest.values())
        if not rep:
            raise Upstream("No reports from index members in this window yet.")
        # price reaction: the close before the report to the first close that includes it (next day if after the close)
        closes = None
        try:
            from api.providers import massive
            closes = massive.panel(sorted(latest), days=days + 30)
            closes.index = pd.to_datetime(closes.index).normalize()
        except Exception as e:                                  # noqa: BLE001 — Yahoo instead
            logger.info("ea store: %s", e)
        if closes is None or closes.empty:
            from api.marketdata.bbgplus import _closes
            closes = _closes(sorted(latest), "6mo", adjusted=False)
        for r in rep:
            m = members[r["symbol"]]
            r.update({"name": m.get("name") or r["company"], "sector": m.get("sector") or "Other", "weight": _f(m.get("weight"))})
            est, act = r["eps_estimate"], r["eps_reported"]
            r["outcome"] = "beat" if act > est + 1e-9 else "miss" if act < est - 1e-9 else "in line"
            if r["surprise_pct"] is None and est:
                r["surprise_pct"] = (act / est - 1) * 100 * (1 if est > 0 else -1)
            r["reaction"] = None
            sr = closes[r["symbol"]].dropna() if r["symbol"] in closes else pd.Series(dtype=float)
            if len(sr) > 2:
                d = pd.Timestamp(r["datetime"][:10])
                after = r["timing"] == "AMC" or (r["timing"] not in ("BMO",) and pd.Timestamp(r["datetime"]).tz_localize(None).hour >= 20)
                k = sr.index.searchsorted(d)
                if k < len(sr) and sr.index[k] == d and after:
                    k += 1
                if 1 <= k < len(sr):
                    r["reaction"] = float(sr.iloc[k] / sr.iloc[k - 1] - 1)
        n = len(rep)
        beats = [r for r in rep if r["outcome"] == "beat"]
        misses = [r for r in rep if r["outcome"] == "miss"]
        surpr = [r["surprise_pct"] for r in rep if r["surprise_pct"] is not None]

        def avg(rs):
            v = [r["reaction"] for r in rs if r["reaction"] is not None]
            return float(np.mean(v)) if v else None
        sectors = []
        for sec in sorted({r["sector"] for r in rep}):
            rs = [r for r in rep if r["sector"] == sec]
            sp = [r["surprise_pct"] for r in rs if r["surprise_pct"] is not None]
            sectors.append({"sector": sec, "reported": len(rs), "members": sum(1 for m in members.values() if (m.get("sector") or "Other") == sec),
                            "beat_rate": sum(r["outcome"] == "beat" for r in rs) / len(rs), "median_surprise": float(np.median(sp)) if sp else None,
                            "avg_reaction": avg(rs)})
        sectors.sort(key=lambda s: -s["beat_rate"])
        keep = ("symbol", "name", "sector", "datetime", "eps_estimate", "eps_reported", "surprise_pct", "outcome", "reaction", "weight")
        trim = lambda rs: [{k: r.get(k) for k in keep} for r in rs]
        weighted = [r for r in rep if r["weight"]]
        return {
            "code": code, "name": memb["name"], "window_days": days, "as_of": str(date.today()),
            "reported": n, "members": len(members),
            "reported_weight": sum(r["weight"] for r in weighted) if weighted else None,
            "beat_rate": len(beats) / n, "miss_rate": len(misses) / n, "in_line_rate": (n - len(beats) - len(misses)) / n,
            "median_surprise": float(np.median(surpr)) if surpr else None,
            "avg_reaction": avg(rep), "avg_reaction_beat": avg(beats), "avg_reaction_miss": avg(misses),
            "beat_and_fell": sum(1 for r in beats if (r["reaction"] or 0) < 0), "missed_and_rose": sum(1 for r in misses if (r["reaction"] or 0) > 0),
            "sectors": sectors,
            "biggest_beats": trim(sorted([r for r in rep if r["surprise_pct"] is not None], key=lambda r: -r["surprise_pct"])[:12]),
            "biggest_misses": trim(sorted([r for r in rep if r["surprise_pct"] is not None], key=lambda r: r["surprise_pct"])[:12]),
            "biggest_reactions": trim(sorted([r for r in rep if r["reaction"] is not None], key=lambda r: -abs(r["reaction"]))[:12]),
            "reports": trim(sorted(rep, key=lambda r: r["datetime"], reverse=True)),
            "upcoming": [{k: r.get(k) for k in ("symbol", "datetime", "eps_estimate")} | {"name": members[r["symbol"]].get("name")} for r in upcoming[:30]],
            "note": f"Reports from index members over the last {days} days, against the analysts' consensus Yahoo shows. Reaction is "
                    "the close before the report to the first close after it (next day for reports after the bell); not adjusted for the market.",
            "source": f"Yahoo Finance earnings calendar; {memb['source']}; prices from the local daily-bars store (Massive) or Yahoo.",
        }
    return _cached(f"ea:{code}:{days}", 1800, build)
