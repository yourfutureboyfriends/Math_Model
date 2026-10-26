"""
Implementations of Bridgewater Associates' published research frameworks, on free data.

  environments()      ENVR — "The All Weather Story" (Bridgewater, 2012): every asset class is driven by the
                             two big surprises, growth and inflation. Classifies each month since 1950 into the four
                             environments and measures how each asset class actually did in each one.
  all_weather(...)    AWP  — the All Weather construction: put equal RISK into each of the four environments
                             (each environment gets the assets that do well in it, risk-balanced), optionally levered
                             to a target volatility; backtested against 60/40, stocks and naive risk parity.
  debt_cycles()       DCYC — "Big Debt Crises" / "How the Economic Machine Works" (Dalio): where ~40 economies are
                             in the short and long-term debt cycle (BIS credit, credit gaps, debt service), plus the
                             US monetary-policy stage (MP1 rates → MP2 QE → MP3 fiscal + monetary coordination).
  holy_grail(syms)    HGRL — Dalio's "Holy Grail": 15+ good, uncorrelated return streams cut risk ~80% without
                             cutting return. The theoretical curve, and your own instruments' effective number of bets.
  world_order()       WPWR — "Principles for Dealing with the Changing World Order" (Dalio, 2021): the eight measures
                             of national power, scored for the major economies from World Bank / IMF data.

These follow the frameworks as Bridgewater describes them publicly; the data, proxies and thresholds are this
terminal's own and are stated with each result.
"""
from __future__ import annotations
from api.market_dates import weekly_last

import concurrent.futures as cf
import io
import logging
import math
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from api.marketdata.core import NotFound, Upstream, _cached, yahoo_download

logger = logging.getLogger(__name__)
UA = {"User-Agent": "Mozilla/5.0 (macro research terminal)"}


def _fred_monthly(sid: str, years: int = 90) -> pd.Series:
    from api.marketdata.insights import _fred
    d = _fred(sid, years=years)
    s = pd.Series(d, dtype=float)
    s.index = pd.to_datetime(s.index)
    return s.sort_index().dropna().resample("ME").last().dropna()


def _monthly_close(sym: str, start: str = "1990-01-01") -> pd.Series:
    df = yahoo_download([sym], start=start, auto_adjust=True)
    c = df["Close"]
    if isinstance(c, pd.DataFrame):
        c = c.iloc[:, 0]
    c = c.dropna()
    c.index = pd.to_datetime(c.index).tz_localize(None)
    return c.resample("ME").last()


# ── ENVR: the four environments and asset behaviour in each ─────────────────
QUADS = {(1, 1): "Rising growth, rising inflation", (1, -1): "Rising growth, falling inflation",
         (-1, 1): "Falling growth, rising inflation", (-1, -1): "Falling growth, falling inflation"}
SHORT = {(1, 1): "Reflation / overheating", (1, -1): "Goldilocks", (-1, 1): "Stagflation", (-1, -1): "Deflationary bust"}


def _shiller() -> pd.DataFrame:
    def fetch():
        import requests
        r = requests.get("http://www.econ.yale.edu/~shiller/data/ie_data.xls", headers=UA, timeout=60)
        r.raise_for_status()
        x = pd.read_excel(io.BytesIO(r.content), sheet_name="Data", skiprows=7)
        x = x[pd.to_numeric(x["Date"], errors="coerce").notna() & pd.to_numeric(x["P"], errors="coerce").notna()]
        yr = x["Date"].astype(float)
        months = ((yr - yr.astype(int)) * 100).round().astype(int)
        idx = pd.to_datetime({"year": yr.astype(int), "month": months.clip(1, 12), "day": 1}) + pd.offsets.MonthEnd(0)
        return pd.DataFrame({"P": x["P"].astype(float).values, "D": pd.to_numeric(x["D"], errors="coerce").values,
                             "GS10": pd.to_numeric(x["Rate GS10"], errors="coerce").values}, index=idx)
    return _cached("shiller", 7 * 86400, fetch)


def _asset_returns() -> pd.DataFrame:
    """Monthly total returns since 1950: US equities (Shiller, then SPY), 10-year Treasuries (from yields, duration
    approximation), corporate Baa bonds (same), commodities (PPI all commodities), gold (from 2000), TIPS (from 2004),
    and cash (3-month T-bills)."""
    def build():
        sh = _shiller()
        eq = ((sh["P"] + sh["D"].ffill() / 12) / sh["P"].shift() - 1).dropna()
        spy = _monthly_close("SPY", "1993-01-01").pct_change().dropna()
        eq = pd.concat([eq[eq.index < spy.index[0]], spy]).sort_index()
        eq = eq[~eq.index.duplicated(keep="last")]

        def bond_tr(y: pd.Series, dur: float) -> pd.Series:
            y = y / 100
            return (y.shift() / 12 - dur * (y - y.shift())).dropna()
        gs10 = _fred_monthly("GS10")
        tsy = bond_tr(gs10, 7.5)
        baa = bond_tr(_fred_monthly("BAA"), 8.0)
        cash = (_fred_monthly("TB3MS") / 100 / 12).shift().dropna()
        comm = _fred_monthly("PPIACO").pct_change().dropna()
        gold = _monthly_close("GC=F", "2000-01-01").pct_change().dropna()
        tips = _monthly_close("TIP", "2004-01-01").pct_change().dropna()
        df = pd.DataFrame({"Equities": eq, "10y Treasuries": tsy, "Corporate bonds (Baa)": baa, "Commodities": comm,
                           "Gold": gold, "Inflation-linked bonds": tips, "Cash": cash})
        return df[df.index >= "1950-01-01"]
    return _cached("bw:assets", 24 * 3600, build)


def _quadrants(lookback: int = 6) -> pd.DataFrame:
    """Each month's environment: is growth (industrial production y/y) and inflation (CPI y/y) higher than six
    months earlier? Acceleration against the recent trend stands in for 'better/worse than expected'."""
    def build():
        ip = _fred_monthly("INDPRO")
        cpi = _fred_monthly("CPIAUCSL")
        g = ip.pct_change(12) * 100
        i = cpi.pct_change(12) * 100
        dg, di = g - g.shift(lookback), i - i.shift(lookback)
        q = pd.DataFrame({"growth_yoy": g, "inflation_yoy": i, "growth_chg": dg, "inflation_chg": di}).dropna()
        q["g"] = np.sign(q["growth_chg"]).replace(0, 1).astype(int)
        q["i"] = np.sign(q["inflation_chg"]).replace(0, 1).astype(int)
        return q
    return _cached(f"bw:quads:{lookback}", 24 * 3600, build)


def environments() -> Dict[str, Any]:
    def build():
        R = _asset_returns()
        Q = _quadrants()
        df = R.join(Q[["g", "i"]], how="inner")
        cash = df["Cash"]
        assets = [c for c in R.columns if c != "Cash"]
        table = []
        for (g, i), name in QUADS.items():
            sub = df[(df["g"] == g) & (df["i"] == i)]
            row = {"quadrant": name, "nickname": SHORT[(g, i)], "growth": "rising" if g > 0 else "falling",
                   "inflation": "rising" if i > 0 else "falling", "months": int(len(sub)), "share": len(sub) / len(df), "assets": {}}
            for a in assets:
                x = (sub[a] - sub["Cash"]).dropna()
                if len(x) < 12:
                    row["assets"][a] = None
                    continue
                row["assets"][a] = {"excess_annual": float(x.mean() * 12), "hit": float((x > 0).mean()), "months": int(len(x)),
                                    "t": float(x.mean() / (x.std() / math.sqrt(len(x)))) if x.std() > 0 else None}
            table.append(row)
        # average over all months (the unconditional baseline)
        base = {a: float((df[a] - cash).dropna().mean() * 12) for a in assets}
        # sensitivity: each asset's excess return in rising minus falling growth (and inflation)
        sens = {}
        for a in assets:
            x = (df[a] - cash)
            sens[a] = {"growth": float(x[df["g"] > 0].mean() * 12 - x[df["g"] < 0].mean() * 12) if x.notna().sum() > 24 else None,
                       "inflation": float(x[df["i"] > 0].mean() * 12 - x[df["i"] < 0].mean() * 12) if x.notna().sum() > 24 else None}
        Qr = _quadrants()
        now = Qr.iloc[-1]
        cur = (int(now["g"]), int(now["i"]))
        hist = [{"date": d.strftime("%Y-%m"), "growth_yoy": round(float(r["growth_yoy"]), 2), "inflation_yoy": round(float(r["inflation_yoy"]), 2),
                 "q": SHORT[(int(r["g"]), int(r["i"]))]} for d, r in Qr.iloc[-240:].iterrows()]
        runs = []                                                   # recent regime spells
        last = None
        for d, r in Qr.iloc[-120:].iterrows():
            k = (int(r["g"]), int(r["i"]))
            if k != last:
                runs.append({"start": d.strftime("%Y-%m"), "q": SHORT[k]})
                last = k
        return {"current": {"quadrant": QUADS[cur], "nickname": SHORT[cur], "as_of": Qr.index[-1].strftime("%Y-%m"),
                            "growth_yoy": float(now["growth_yoy"]), "growth_chg": float(now["growth_chg"]),
                            "inflation_yoy": float(now["inflation_yoy"]), "inflation_chg": float(now["inflation_chg"])},
                "table": table, "baseline": base, "sensitivity": sens, "assets": assets, "history": hist, "spells": runs[-12:],
                "start": df.index[0].strftime("%Y-%m"), "months": int(len(df)),
                "method": "Environment = whether US industrial-production growth and CPI inflation (both y/y) are higher or lower than six "
                          "months earlier. Returns are monthly excess returns over T-bills in the same month (contemporaneous — this shows "
                          "what each asset is exposed to, not a timing signal). Equities: Shiller total return to 1993, SPY after; bonds "
                          "from yields with a duration approximation; commodities: PPI all commodities; gold from 2000; TIPS from 2004.",
                "reference": "Bridgewater Associates, “The All Weather Story” (2012) and “Engineering Targeted Returns and Risks”.",
                "source": "Robert Shiller (Yale) long-run data; FRED; Yahoo Finance"}
    return _cached("bw:envr", 12 * 3600, build)


# ── AWP: the All Weather construction ────────────────────────────────────────
AW_ASSETS = {"SPY": "US equities", "EFA": "Developed ex-US equities", "EEM": "Emerging equities", "TLT": "Long Treasuries",
             "IEF": "Intermediate Treasuries", "TIP": "Inflation-linked bonds", "LQD": "IG corporate bonds", "EMB": "EM sovereign bonds",
             "DBC": "Commodities", "GLD": "Gold"}
AW_BUCKETS = {"Rising growth": ["SPY", "EFA", "EEM", "LQD", "EMB", "DBC"], "Falling growth": ["TLT", "IEF", "TIP"],
              "Rising inflation": ["TIP", "DBC", "GLD", "EMB"], "Falling inflation": ["SPY", "EFA", "TLT", "IEF"]}


def _inv_vol(cov: pd.DataFrame, names: List[str]) -> pd.Series:
    v = np.sqrt(np.diag(cov.loc[names, names].values))
    w = (1 / v) / (1 / v).sum()
    return pd.Series(w, index=names)


def _port_vol(w: pd.Series, cov: pd.DataFrame) -> float:
    n = list(w.index)
    return float(math.sqrt(max(0.0, w.values @ cov.loc[n, n].values @ w.values)))


def all_weather(target_vol: float = 0.10, max_leverage: float = 2.0) -> Dict[str, Any]:
    def build():
        syms = list(AW_ASSETS)
        df = yahoo_download(syms + ["^IRX"], start="2005-01-01", auto_adjust=True, group_by="ticker", threads=True)
        px = {}
        for s in syms + ["^IRX"]:
            try:
                px[s] = (df[s] if isinstance(df.columns, pd.MultiIndex) else df)["Close"].dropna()
            except Exception:
                pass
        P = pd.DataFrame(px).dropna(how="all")
        P.index = pd.to_datetime(P.index).tz_localize(None)
        irx = P.pop("^IRX").ffill() / 100 if "^IRX" in P else pd.Series(0.02, index=P.index)
        P = P.dropna()
        if len(P) < 500:
            raise Upstream("Not enough ETF history for the All Weather backtest.")
        rd = P.pct_change().dropna()
        cash_d = (irx.reindex(rd.index).ffill().fillna(0.02) / 252)
        months = rd.resample("ME").last().index
        out = {k: [] for k in ("aw", "aw_lev", "rp", "6040", "spy")}
        weights_hist, lev_hist = [], []
        W = None
        for k in range(12, len(months) - 1):
            end, nxt = months[k], months[k + 1]
            hist = rd[(rd.index > end - pd.Timedelta(days=365)) & (rd.index <= end)]
            cov = hist.cov() * 252
            # equal risk to each environment: inverse-vol inside each bucket, buckets scaled to the same volatility
            comb = pd.Series(0.0, index=syms)
            for b, names in AW_BUCKETS.items():
                wb = _inv_vol(cov, names)
                wb = wb / _port_vol(wb, cov)                       # one unit of risk per environment
                comb[names] += wb.values
            comb = comb / comb.sum()
            vol = _port_vol(comb, cov)
            lev = min(max_leverage, target_vol / vol) if vol > 0 else 1.0
            rp = _inv_vol(cov, syms)
            W = comb
            weights_hist.append({"date": end.strftime("%Y-%m"), **{s: round(float(comb[s]), 4) for s in syms}})
            lev_hist.append(lev)
            fwd = rd[(rd.index > end) & (rd.index <= nxt)]
            if fwd.empty:
                continue
            cd = cash_d.reindex(fwd.index).fillna(0)
            for name, w, L in (("aw", comb, 1.0), ("aw_lev", comb, lev), ("rp", rp, 1.0)):
                day = fwd[w.index] @ w.values
                out[name].append(L * day + (1 - L) * cd)               # leverage borrowed at the T-bill rate
            out["6040"].append(0.6 * fwd["SPY"] + 0.4 * fwd["IEF"])
            out["spy"].append(fwd["SPY"])
        series = {k: pd.concat(v) for k, v in out.items() if v}
        labels = {"aw": "All Weather (unlevered)", "aw_lev": f"All Weather at {target_vol:.0%} vol", "rp": "Naive risk parity (inverse vol)",
                  "6040": "60/40 (SPY / IEF)", "spy": "S&P 500 (SPY)"}

        def stats(r: pd.Series) -> Dict[str, Any]:
            eq = (1 + r).cumprod()
            yrs = len(r) / 252
            cagr = eq.iloc[-1] ** (1 / yrs) - 1
            vol = r.std() * math.sqrt(252)
            ex = r - cash_d.reindex(r.index).fillna(0)
            annual = (1 + r).groupby(r.index.year).prod() - 1
            return {"cagr": float(cagr), "vol": float(vol), "sharpe": float(ex.mean() / ex.std() * math.sqrt(252)) if ex.std() > 0 else None,
                    "max_drawdown": float((eq / eq.cummax() - 1).min()), "worst_year": float(annual.min()), "best_year": float(annual.max()),
                    "worst_year_label": int(annual.idxmin())}
        perf = [{"key": k, "label": labels[k], **stats(v)} for k, v in series.items()]
        curves = pd.DataFrame({k: (1 + v).cumprod() * 100 for k, v in series.items()})
        wk = weekly_last(curves)
        rows = [{"date": d.strftime("%Y-%m-%d"), **{k: round(float(x), 2) for k, x in r.items() if pd.notna(x)}} for d, r in wk.iterrows()]
        # balance check: monthly returns in each growth/inflation environment
        Q = _quadrants()
        mret = {k: (1 + v).resample("ME").prod() - 1 for k, v in series.items()}
        by_q = []
        for (g, i), name in QUADS.items():
            idx = Q[(Q["g"] == g) & (Q["i"] == i)].index
            row = {"quadrant": SHORT[(g, i)]}
            for k, m in mret.items():
                x = m[m.index.isin(idx)]
                row[k] = float(x.mean() * 12) if len(x) >= 6 else None
            by_q.append(row)
        cov = rd.iloc[-252:].cov() * 252
        rc = (W * (cov.loc[W.index, W.index].values @ W.values)) / (_port_vol(W, cov) ** 2)
        env_risk = {}
        for b, names in AW_BUCKETS.items():
            env_risk[b] = float(sum(rc[n] / sum(1 for bb in AW_BUCKETS.values() if n in bb) for n in names))
        return {"weights": [{"symbol": s, "name": AW_ASSETS[s], "weight": float(W[s]), "risk_share": float(rc[s]),
                             "environments": [b for b, n in AW_BUCKETS.items() if s in n]} for s in syms],
                "environment_risk": env_risk, "leverage_now": lev_hist[-1] if lev_hist else None, "vol_unlevered": _port_vol(W, cov),
                "performance": perf, "curves": rows, "by_quadrant": by_q, "labels": labels, "weights_history": weights_hist[-60:],
                "start": rows[0]["date"] if rows else None, "target_vol": target_vol, "buckets": AW_BUCKETS,
                "method": "Each environment (rising/falling growth, rising/falling inflation) gets the assets that tend to do well in it, "
                          "weighted by inverse volatility; each environment's mini-portfolio is scaled to the same risk, and the four are "
                          "added up. Re-estimated monthly from the trailing year of daily returns (no look-ahead). The levered version "
                          "borrows at the T-bill rate to reach the target volatility (capped at 2×). Before costs and taxes.",
                "reference": "Bridgewater Associates, “The All Weather Story” (2012); Dalio, “Engineering Targeted Returns and Risks”.",
                "source": "Yahoo Finance ETF prices (from 2005, start set by the youngest fund)"}
    return _cached(f"bw:awp:{target_vol}:{max_leverage}", 12 * 3600, build)


# ── DCYC: debt cycles ────────────────────────────────────────────────────────
BIS_NAMES = {"US": "United States", "XM": "Euro area", "CN": "China", "JP": "Japan", "GB": "United Kingdom", "DE": "Germany", "FR": "France",
             "IT": "Italy", "ES": "Spain", "CA": "Canada", "AU": "Australia", "KR": "South Korea", "IN": "India", "BR": "Brazil", "MX": "Mexico",
             "RU": "Russia", "TR": "Türkiye", "ZA": "South Africa", "ID": "Indonesia", "SA": "Saudi Arabia", "CH": "Switzerland", "SE": "Sweden",
             "NO": "Norway", "DK": "Denmark", "NL": "Netherlands", "BE": "Belgium", "AT": "Austria", "FI": "Finland", "PT": "Portugal", "GR": "Greece",
             "IE": "Ireland", "PL": "Poland", "CZ": "Czechia", "HU": "Hungary", "IL": "Israel", "HK": "Hong Kong", "SG": "Singapore", "TH": "Thailand",
             "MY": "Malaysia", "CL": "Chile", "CO": "Colombia", "AR": "Argentina", "NZ": "New Zealand"}


def _bis(flow: str, start: str = "2000-01-01") -> pd.DataFrame:
    def fetch():
        import requests
        r = requests.get(f"https://stats.bis.org/api/v1/data/{flow}/all", params={"startPeriod": start, "detail": "dataonly"},
                         headers={**UA, "Accept": "application/vnd.sdmx.data+csv;version=1.0.0"}, timeout=120)
        if r.status_code != 200:
            raise Upstream(f"BIS {flow} unavailable (HTTP {r.status_code}).")
        return pd.read_csv(io.StringIO(r.text))
    return _cached(f"bis:{flow}:{start}", 24 * 3600, fetch)


def _q(s: str) -> pd.Timestamp:
    y, q = s.split("-Q")
    return pd.Timestamp(year=int(y), month=int(q) * 3, day=1) + pd.offsets.MonthEnd(0)


def debt_cycles() -> Dict[str, Any]:
    def build():
        tc, gap, dsr = _bis("WS_TC"), _bis("WS_CREDIT_GAP"), _bis("WS_DSR")
        # total credit, % of GDP, market value, adjusted for breaks: private (P), households (H), corporates (N), government (G)
        tc = tc[(tc["UNIT_TYPE"].astype(str) == "770") & (tc["TC_ADJUST"].astype(str) == "A") & (tc["TC_LENDERS"].astype(str) == "A")]
        # private sectors at market value; government debt is published at nominal value
        tc = tc[((tc["TC_BORROWERS"] != "G") & (tc["VALUATION"] == "M")) | ((tc["TC_BORROWERS"] == "G") & (tc["VALUATION"] == "N"))]
        gp = gap[(gap["CG_DTYPE"] == "C") & (gap["TC_BORROWERS"] == "P")]       # credit-to-GDP gap
        dp = dsr[dsr["DSR_BORROWERS"] == "P"]
        try:
            from api.marketdata.toolkit import central_banks
            rates = {b["code"]: b for b in central_banks()["banks"]}
        except Exception:
            rates = {}

        def series(df, cty, extra=None):
            d = df[df["BORROWERS_CTY"] == cty]
            if extra:
                for k, v in extra.items():
                    d = d[d[k] == v]
            if d.empty:
                return pd.Series(dtype=float)
            s = pd.Series(d["OBS_VALUE"].astype(float).values, index=[_q(x) for x in d["TIME_PERIOD"]]).sort_index()
            return s[~s.index.duplicated(keep="last")]
        rows = []
        for cty, name in BIS_NAMES.items():
            priv = series(tc, cty, {"TC_BORROWERS": "P"})
            if priv.empty:
                continue
            hh, nfc, gov = series(tc, cty, {"TC_BORROWERS": "H"}), series(tc, cty, {"TC_BORROWERS": "N"}), series(tc, cty, {"TC_BORROWERS": "G"})
            g, d = series(gp, cty), series(dp, cty)
            last = lambda s: float(s.iloc[-1]) if len(s) else None
            chg = lambda s, n=12: float(s.iloc[-1] - s.iloc[-1 - n]) if len(s) > n else None     # 3 years of quarters
            d_avg = float(d.mean()) if len(d) >= 20 else None
            rate = (rates.get(cty) or {}).get("rate")
            gap_now, gap_chg = last(g), (float(g.iloc[-1] - g.iloc[-5]) if len(g) > 5 else None)
            dsr_now = last(d)
            dsr_dev = (dsr_now - d_avg) if dsr_now is not None and d_avg is not None else None
            # Dalio's archetypal short/long debt-cycle phases, with explicit, simple rules
            if rate is not None and rate <= 0.5 and (chg(priv) or 0) <= 0:
                phase, why = "Deleveraging", "policy rate at the floor while private debt/GDP is falling"
            elif gap_now is not None and gap_now > 8 and dsr_dev is not None and dsr_dev > 1:
                phase, why = "Bubble / top", "credit far above its trend and debt service above its average"
            elif gap_now is not None and gap_now > 4:
                phase, why = "Late upswing", "credit growing faster than its trend"
            elif gap_now is not None and gap_now < -8 and (gap_chg or 0) < 0:
                phase, why = "Deleveraging", "credit well below trend and still contracting relative to GDP"
            elif gap_now is not None and gap_now < -2:
                phase, why = "Early / recovery", "credit below trend — room to borrow"
            else:
                phase, why = "Mid-cycle", "credit close to its long-run trend"
            total = (last(priv) or 0) + (last(gov) or 0) if last(gov) is not None else None
            tot_hist = (priv + gov.reindex(priv.index)).dropna() if len(gov) else pd.Series(dtype=float)
            tot_pct = float((tot_hist < tot_hist.iloc[-1]).mean()) if len(tot_hist) > 20 else None
            if total is not None and total > 250 and (last(gov) or 0) > 90:
                lt, lt_why = "Late", "total debt above 250% of GDP with heavy government borrowing — the long-term cycle's late stage"
            elif total is not None and total > 180:
                lt, lt_why = "Mature", "high total debt; further leverage depends on low rates"
            else:
                lt, lt_why = "Early / moderate", "debt levels leave room"
            rows.append({"code": cty, "country": name, "long_term": lt, "long_term_why": lt_why, "total_percentile": tot_pct,
                         "private_debt": last(priv), "private_3y": chg(priv), "household": last(hh),
                         "corporate": last(nfc), "government": last(gov), "government_3y": chg(gov),
                         "total": total,
                         "credit_gap": gap_now, "credit_gap_1y": gap_chg, "dsr": dsr_now, "dsr_vs_avg": dsr_dev, "policy_rate": rate,
                         "as_of": priv.index[-1].strftime("%Y-Q") + str((priv.index[-1].month - 1) // 3 + 1), "phase": phase, "why": why})
        if not rows:
            raise Upstream("No BIS credit data.")
        rows.sort(key=lambda r: -(r["total"] or 0))
        us = _us_policy_stage()
        hist = {}
        for cty in ("US", "CN", "JP", "XM", "GB"):
            s = series(tc, cty, {"TC_BORROWERS": "P"})
            gv = series(tc, cty, {"TC_BORROWERS": "G"})
            hist[cty] = (s + gv.reindex(s.index)) if len(gv) else s
        H = pd.DataFrame(hist)
        h_rows = [{"date": d.strftime("%Y-%m-%d"), **{k: (round(float(v), 1) if pd.notna(v) else None) for k, v in r.items()}} for d, r in H.iterrows()]
        return {"countries": rows, "us": us, "history": h_rows,
                "method": "Credit-to-GDP gap = private credit/GDP minus its long-run (one-sided HP) trend — the BIS's early-warning "
                          "indicator (above ~10 points has preceded most banking crises). Debt service ratio = interest + principal as a "
                          "share of income. Phases are this terminal's simple rules on those measures, mapped to Dalio's archetypal debt "
                          "cycle; read them as a screen, not a forecast.",
                "reference": "Ray Dalio, “Principles for Navigating Big Debt Crises” (Bridgewater, 2018); “How the Economic Machine Works” (2013); "
                             "Bridgewater, “It's Time to Look More Carefully at ‘Monetary Policy 3’” (2019).",
                "source": "BIS total credit, credit-to-GDP gaps and debt service ratios; BIS policy rates; FRED"}
    return _cached("bw:dcyc", 12 * 3600, build)


def _us_policy_stage() -> Dict[str, Any]:
    """Where the US is in Dalio's monetary-policy sequence: MP1 (move short rates), MP2 (QE — buy bonds when rates are
    at zero), MP3 (fiscal deficits financed by the central bank)."""
    try:
        ff = _fred_monthly("FEDFUNDS", 30)
        bs = _fred_monthly("WALCL", 25)
        deficit = _fred_monthly("FYFSGDA188S", 40)                 # federal surplus/deficit, % of GDP (annual)
        debt = _fred_monthly("GFDEGDQ188S", 40)                    # federal debt, % of GDP
        interest = _fred_monthly("A091RC1Q027SBEA", 40)            # federal interest payments
        receipts = _fred_monthly("W006RC1Q027SBEA", 40)            # federal current tax receipts
        gdp = _fred_monthly("GDP", 40)
        y10 = _fred_monthly("GS10", 40)
    except Exception as e:
        return {"available": False, "reason": str(e)[:120]}
    rate = float(ff.iloc[-1])
    bs_yoy = float(bs.iloc[-1] / bs.iloc[-13] - 1) if len(bs) > 13 else None
    dfc = float(deficit.iloc[-1])
    ngdp_g = float(gdp.iloc[-1] / gdp[gdp.index <= gdp.index[-1] - pd.Timedelta(days=360)].iloc[-1] - 1) * 100 if len(gdp) > 5 else None
    r_minus_g = float(y10.iloc[-1]) - ngdp_g if ngdp_g is not None else None
    int_share = float(interest.iloc[-1] / receipts.iloc[-1]) if len(interest) and len(receipts) else None
    if rate > 0.5:
        stage, text = "MP1", "The Fed is steering with interest rates — conventional policy still works."
        if dfc < -5 and (bs_yoy or 0) > 0.05:
            stage, text = "MP1 → MP3 risk", "Rates are positive, but large deficits are being met with a growing Fed balance sheet."
    elif (bs_yoy or 0) > 0.05:
        stage, text = "MP2", "Rates are at the floor and the Fed is buying bonds (quantitative easing)."
        if dfc < -5:
            stage, text = "MP3", "Rates at the floor, QE, and large fiscal deficits — monetary and fiscal policy working together."
    else:
        stage, text = "MP1 (at the floor)", "Rates near zero without active QE."
    return {"available": True, "stage": stage, "explanation": text, "fed_funds": rate, "fed_balance_sheet_yoy": bs_yoy,
            "deficit_pct_gdp": dfc, "federal_debt_pct_gdp": float(debt.iloc[-1]), "interest_share_of_receipts": int_share,
            "nominal_gdp_growth": ngdp_g, "ten_year": float(y10.iloc[-1]), "r_minus_g": r_minus_g,
            "debt_dynamics": (None if r_minus_g is None or r_minus_g != r_minus_g else
                              "Debt/GDP drifts up even with a balanced primary budget (r > g)" if r_minus_g > 0
                              else "Nominal growth above the borrowing rate helps stabilise debt/GDP (r < g)"),
            "series": {"fed_funds": [{"date": d.strftime("%Y-%m"), "v": round(float(v), 2)} for d, v in ff.iloc[-240:].items()],
                       "balance_sheet": [{"date": d.strftime("%Y-%m"), "v": round(float(v) / 1e6, 3)} for d, v in bs.iloc[-240:].items()]}}


# ── HGRL: the Holy Grail ─────────────────────────────────────────────────────
def holy_grail(symbols: List[str], years: int = 3) -> Dict[str, Any]:
    syms = [s.strip().upper() for s in symbols if s.strip()][:40]
    curve = [{"n": n, **{f"rho{int(r * 100)}": math.sqrt(1 / n + (1 - 1 / n) * r) for r in (0.0, 0.1, 0.2, 0.4, 0.6)}} for n in range(1, 21)]
    out: Dict[str, Any] = {"curve": curve,
                           "note": "Risk of an equal-weight mix of N streams of equal volatility, as a share of one stream’s risk: "
                                   "√(1/N + (1 − 1/N)·ρ). With ρ = 0, 15 streams cut risk by ~75%; with ρ = 0.6 diversification barely helps.",
                           "reference": "Ray Dalio, “Principles” (2017) — the “Holy Grail of investing”."}
    if len(syms) < 2:
        return out
    df = yahoo_download(syms, period=f"{years}y", auto_adjust=True, group_by="ticker", threads=True)
    cols = {}
    for s in syms:
        try:
            cols[s] = (df[s] if isinstance(df.columns, pd.MultiIndex) else df)["Close"].dropna()
        except Exception:
            continue
    P = weekly_last(pd.DataFrame(cols)).dropna(how="all")
    R = P.pct_change().dropna(how="all")
    R = R.loc[:, R.notna().sum() > 52]
    if R.shape[1] < 2:
        raise NotFound("Not enough overlapping history.")
    C = R.corr()
    ev = np.clip(np.linalg.eigvalsh(C.values), 0, None)
    n = C.shape[0]
    eff = float(ev.sum() ** 2 / (ev ** 2).sum())                       # participation ratio of the correlation matrix
    p = ev / ev.sum()
    ent = float(math.exp(-(p[p > 0] * np.log(p[p > 0])).sum()))
    off = C.values[np.triu_indices(n, 1)]
    avg = float(np.nanmean(off))
    vols = R.std() * math.sqrt(52)
    w = (1 / vols) / (1 / vols).sum()
    cov = R.cov() * 52
    pv = float(math.sqrt(w.values @ cov.values @ w.values))
    avg_vol = float((w * vols).sum())
    pairs = sorted(((C.columns[i], C.columns[j], float(C.values[i, j])) for i in range(n) for j in range(i + 1, n)), key=lambda x: -x[2])
    out.update({"symbols": list(C.columns), "correlation": C.round(2).values.tolist(), "average_correlation": avg,
                "effective_bets": eff, "effective_bets_entropy": ent, "n": n,
                "risk_reduction": 1 - pv / avg_vol if avg_vol else None, "portfolio_vol": pv, "average_vol": avg_vol,
                "most_correlated": [{"a": a, "b": b, "rho": r} for a, b, r in pairs[:6]],
                "least_correlated": [{"a": a, "b": b, "rho": r} for a, b, r in pairs[-6:][::-1]],
                "missing": [s for s in syms if s not in C.columns],
                "verdict": (f"{n} holdings behave like about {eff:.1f} independent bets (average correlation {avg:.2f}). "
                            + ("Well diversified." if eff >= 0.6 * n else "Much of the risk is the same bet repeated — add genuinely different return streams."))})
    return out


# ── WPWR: the changing world order ───────────────────────────────────────────
WO_COUNTRIES = {"USA": "United States", "CHN": "China", "EMU": "Euro area", "JPN": "Japan", "GBR": "United Kingdom", "IND": "India",
                "DEU": "Germany", "FRA": "France", "RUS": "Russia", "KOR": "South Korea", "BRA": "Brazil", "CAN": "Canada",
                "AUS": "Australia", "SAU": "Saudi Arabia", "TUR": "Türkiye", "IDN": "Indonesia"}
WO_INDICATORS = {
    "Education": ("SE.TER.ENRR", "rate", "tertiary enrolment rate"),
    "Innovation & technology": ("GB.XPD.RSDV.GD.ZS", "rd", "R&D spending (share of world, from % of GDP × GDP)"),
    "Competitiveness": ("TX.VAL.TECH.CD", "share", "high-technology exports"),
    "Economic output": ("NY.GDP.MKTP.PP.CD", "share", "GDP at purchasing-power parity"),
    "Share of world trade": ("NE.EXP.GNFS.CD", "share", "exports of goods and services"),
    "Military strength": ("MS.MIL.XPND.CD", "share", "military spending"),
    "Financial center": ("CM.MKT.LCAP.CD", "share", "stock market capitalisation"),
}
COFER_CCY = {"USD": "USA", "EUR": "EMU", "JPY": "JPN", "GBP": "GBR", "CNY": "CHN", "CAD": "CAN", "AUD": "AUS"}


def _wb(indicator: str) -> Dict[str, Dict[int, float]]:
    import requests
    codes = ";".join(WO_COUNTRIES)
    r = requests.get(f"https://api.worldbank.org/v2/country/{codes}/indicator/{indicator}",
                     params={"format": "json", "date": "2000:2025", "per_page": 2000}, headers=UA, timeout=60)
    j = r.json()
    out: Dict[str, Dict[int, float]] = {}
    for x in (j[1] if isinstance(j, list) and len(j) > 1 and j[1] else []):
        if x.get("value") is not None:
            out.setdefault(x["countryiso3code"], {})[int(x["date"])] = float(x["value"])
    return out


COFER_CODES = {"USD": "USD", "EURO": "EUR", "JPY": "JPY", "GBP": "GBP", "CNY": "CNY", "CAD": "CAD", "AUD": "AUD"}


def _cofer() -> Dict[str, float]:
    """Shares of allocated FX reserves by currency (IMF COFER, latest year, %) via DBnomics."""
    import requests
    out = {}
    for code, ccy in COFER_CODES.items():
        try:
            j = requests.get(f"https://api.db.nomics.world/v22/series/IMF/COFER/A.W00.RAXGFXAR{code}RT_PT",
                             params={"observations": 1}, headers=UA, timeout=30).json()
            docs = (j.get("series") or {}).get("docs") or []
            vals = [v for v in (docs[0].get("value", []) if docs else []) if isinstance(v, (int, float))]
            if vals:
                out[COFER_CCY[ccy]] = float(vals[-1]) / 100
        except Exception:
            continue
    return out


def world_order() -> Dict[str, Any]:
    def build():
        with cf.ThreadPoolExecutor(4) as ex:
            futs = {name: ex.submit(_wb, ind) for name, (ind, _, _) in WO_INDICATORS.items()}
            gdp_f = ex.submit(_wb, "NY.GDP.MKTP.CD")
            res = cf.wait(list(futs.values()) + [gdp_f])
        data = {k: f.result() for k, f in futs.items()}
        gdp = gdp_f.result()
        latest = lambda d, c: (max(d.get(c, {}).items())[1] if d.get(c) else None)
        year_of = lambda d, c: (max(d.get(c, {}).items())[0] if d.get(c) else None)
        comp: Dict[str, Dict[str, Optional[float]]] = {}
        detail = {}
        for name, (ind, kind, label) in WO_INDICATORS.items():
            d = data[name]
            vals = {}
            for c in WO_COUNTRIES:
                v = latest(d, c)
                if v is None:
                    continue
                if kind == "rd":
                    g = latest(gdp, c)
                    v = v / 100 * g if g else None
                if v is not None:
                    vals[c] = v
            if kind in ("share", "rd"):
                members = {c: v for c, v in vals.items() if c != "EMU"}
                tot = sum(members.values()) or 1
                share = {c: v / tot for c, v in vals.items()}
            else:
                share = vals
            mx = max(share.values()) if share else 1
            comp[name] = {c: share.get(c, None) / mx if share.get(c) is not None and mx else None for c in WO_COUNTRIES}
            detail[name] = {"label": label, "values": {c: share.get(c) for c in WO_COUNTRIES}, "years": {c: year_of(d, c) for c in WO_COUNTRIES}}
        res_shares = _cofer()
        if res_shares:
            mx = max(res_shares.values())
            comp["Reserve currency"] = {c: (res_shares.get(c, 0.0) / mx) for c in WO_COUNTRIES}
            detail["Reserve currency"] = {"label": "share of world FX reserves (IMF COFER)", "values": {c: res_shares.get(c, 0.0) for c in WO_COUNTRIES}, "years": {}}
        rows = []
        for c, nm in WO_COUNTRIES.items():
            scores = {k: comp[k].get(c) for k in comp}
            have = [v for v in scores.values() if v is not None]
            rows.append({"code": c, "country": nm, "scores": scores, "index": float(np.mean(have)) if len(have) >= 5 else None, "measures": len(have)})
        rows.sort(key=lambda r: -(r["index"] or 0))
        return {"countries": rows, "measures": list(comp), "detail": detail,
                "note": "Each measure is the country’s share of the group total (or its rate, for education), scaled so the leader scores 1; "
                        "the index is the average. The euro area is shown alongside Germany and France (it isn’t counted twice in the shares). "
                        "Dalio’s full index also uses history, cost competitiveness, internal order and more — this is the data-available core.",
                "reference": "Ray Dalio, “Principles for Dealing with the Changing World Order” (2021).",
                "source": "World Bank World Development Indicators; IMF COFER via DBnomics"}
    return _cached("bw:wpwr", 24 * 3600, build)


# ── Targets for the macro trader: All Weather, optionally tilted to the current environment ──
TRADER_BUCKETS = {"Rising growth": ["SPY", "EFA", "EEM", "HYG", "LQD", "DBC"], "Falling growth": ["TLT", "IEF", "TIP"],
                  "Rising inflation": ["TIP", "DBC", "GLD"], "Falling inflation": ["SPY", "EFA", "TLT", "IEF"]}
TILTS = {"Reflation / overheating": {"Rising growth": 1.5, "Rising inflation": 1.5, "Falling growth": 0.6, "Falling inflation": 0.6},
         "Goldilocks": {"Rising growth": 1.5, "Falling inflation": 1.5, "Falling growth": 0.6, "Rising inflation": 0.6},
         "Stagflation": {"Falling growth": 1.5, "Rising inflation": 1.5, "Rising growth": 0.6, "Falling inflation": 0.6},
         "Deflationary bust": {"Falling growth": 1.5, "Falling inflation": 1.5, "Rising growth": 0.6, "Rising inflation": 0.6}}


def all_weather_targets(tilt: bool = False, target_vol: float = 0.10, closes: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Current All Weather weights over the macro trader's ETF universe (unlevered — the trader holds cash, it doesn't
    borrow): equal risk per environment, or with each environment's risk budget scaled by the current quadrant
    (favoured environments ×1.5, the opposite ones ×0.6). If the mix is more volatile than `target_vol`, the
    remainder is held in cash."""
    syms = sorted({s for v in TRADER_BUCKETS.values() for s in v})
    if closes:
        P = pd.DataFrame({s: closes[s]["Close"] for s in syms if s in closes}).dropna()
    else:
        df = yahoo_download(syms, period="2y", auto_adjust=True, group_by="ticker", threads=True)
        P = pd.DataFrame({s: (df[s] if isinstance(df.columns, pd.MultiIndex) else df)["Close"] for s in syms}).dropna()
    missing = [s for s in syms if s not in P]
    if missing:
        raise Upstream(f"No prices for {', '.join(missing)}.")
    rd = P.pct_change().dropna().iloc[-252:]
    cov = rd.cov() * 252
    quad = None
    budgets = {b: 1.0 for b in TRADER_BUCKETS}
    if tilt:
        try:
            quad = environments()["current"]["nickname"]
            budgets = TILTS.get(quad, budgets)
        except Exception as e:
            logger.info("[aw] quadrant unavailable, no tilt: %s", e)
    comb = pd.Series(0.0, index=syms)
    for b, names in TRADER_BUCKETS.items():
        wb = _inv_vol(cov, names)
        wb = wb / _port_vol(wb, cov) * budgets[b]
        comb[names] += wb.values
    comb = comb / comb.sum()
    vol = _port_vol(comb, cov)
    invest = min(1.0, target_vol / vol) if vol > 0 else 1.0
    w = comb * invest
    return {"weights": {s: float(v) for s, v in w.items()}, "cash": float(1 - invest), "regime": quad or "All Weather (no tilt)",
            "expected_vol": vol * invest, "expected_excess_return": None, "budgets": budgets,
            "as_of": rd.index[-1].strftime("%Y-%m-%d")}
