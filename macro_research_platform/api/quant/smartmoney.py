"""
Institutional holdings (SEC 13F) as point-in-time strategy inputs.

The big quant and multi-manager firms (Renaissance, Two Sigma, D. E. Shaw, AQR, Citadel, Millennium,
Point72, Jane Street) and the concentrated fundamental funds (Berkshire, Viking, Lone Pine, Coatue,
Tiger, Baupost, Appaloosa, Pershing Square, Third Point, Duquesne, Elliott, Soros) must file their US
long positions every quarter, up to 45 days after quarter end. A position becomes usable only from
the day after its filing date — never from the quarter end it describes.

Research: Goldman Sachs' Hedge Fund VIP basket (the 50 stocks most often in fundamental funds' top 10)
beat the S&P 500 in ~60% of quarters since 2001 by ~52 bp a quarter on average; Cohen, Polk & Silli
(2010) "Best Ideas": managers' highest-conviction holdings beat the market by ~2.8–4.5% a year, the
rest of their portfolios do not. Quant funds turn over far faster than 45 days, so their filings say
little about their current book — a strategy here tests whether that is true.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
CACHE = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "quant" / "13f"
FIRST_PERIOD = "2014-03-31"          # XML information tables exist from mid-2013
TOP_N = 60                           # positions kept per filing (by value)

FUNDS: Dict[str, Dict[str, str]] = {
    # quantitative / multi-manager / market makers
    "1037389": {"name": "Renaissance Technologies", "style": "quant"},
    "1179392": {"name": "Two Sigma Investments", "style": "quant"},
    "1009207": {"name": "D. E. Shaw & Co.", "style": "quant"},
    "1167557": {"name": "AQR Capital Management", "style": "quant"},
    "1423053": {"name": "Citadel Advisors", "style": "multi"},
    "1273087": {"name": "Millennium Management", "style": "multi"},
    "1603466": {"name": "Point72 Asset Management", "style": "multi"},
    "1595888": {"name": "Jane Street Group", "style": "market_maker"},
    "1350694": {"name": "Bridgewater Associates", "style": "macro"},
    # concentrated fundamental funds
    "1067983": {"name": "Berkshire Hathaway", "style": "fundamental"},
    "1103804": {"name": "Viking Global", "style": "fundamental"},
    "1061165": {"name": "Lone Pine Capital", "style": "fundamental"},
    "1135730": {"name": "Coatue Management", "style": "fundamental"},
    "1167483": {"name": "Tiger Global", "style": "fundamental"},
    "1061768": {"name": "Baupost Group", "style": "fundamental"},
    "1656456": {"name": "Appaloosa", "style": "fundamental"},
    "1336528": {"name": "Pershing Square", "style": "fundamental"},
    "1040273": {"name": "Third Point", "style": "fundamental"},
    "1536411": {"name": "Duquesne Family Office", "style": "fundamental"},
    "1791786": {"name": "Elliott Investment Management", "style": "fundamental"},
    "1029160": {"name": "Soros Fund Management", "style": "fundamental"},
}
_ETF_WORDS = re.compile(r"\b(ETF|TRUST|FUND|SPDR|ISHARES|INVESCO QQQ|VANGUARD|PROSHARES|DIREXION|SELECT SECTOR|INDEX)\b", re.I)
_TICKER = re.compile(r"[A-Z]{1,5}(-[A-Z])?")
_lock = threading.Lock()
_status: Dict[str, Any] = {"state": "idle"}


def _sec_json(url: str):
    from api.marketdata.extras import _sec_get
    return _sec_get(url).json()


def filings(cik: str) -> List[Dict[str, str]]:
    """Original 13F-HR filings (amendments ignored), oldest first, from FIRST_PERIOD."""
    cik10 = f"{int(cik):010d}"
    sub = _sec_json(f"https://data.sec.gov/submissions/CIK{cik10}.json")
    blocks = [sub["filings"]["recent"]]
    for f in sub["filings"].get("files", []):
        try:
            blocks.append(_sec_json(f"https://data.sec.gov/submissions/{f['name']}"))
        except Exception:
            pass
    out = {}
    for r in blocks:
        for i, form in enumerate(r["form"]):
            if form == "13F-HR" and r["reportDate"][i] >= FIRST_PERIOD:
                p = r["reportDate"][i]
                # keep the first filing for each period (later 13F-HR for the same period are restatements)
                if p not in out or r["filingDate"][i] < out[p]["filed"]:
                    out[p] = {"acc": r["accessionNumber"][i], "period": p, "filed": r["filingDate"][i]}
    return sorted(out.values(), key=lambda x: x["period"])


def _holdings(cik: str, f: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Top positions of one filing (long stock only — options excluded), cached forever on disk."""
    p = CACHE / cik / f"{f['acc']}.json"
    try:
        return json.loads(p.read_text())
    except Exception:
        pass
    from api.marketdata.extras import _info_table
    try:
        rows = _info_table(f"{int(cik):010d}", f["acc"])
    except Exception as e:
        logger.info("[13f] %s %s: %s", cik, f["acc"], e)
        return None
    agg: Dict[str, Dict[str, Any]] = {}
    for x in rows:
        if x.get("put_call") or not x.get("cusip"):
            continue
        a = agg.setdefault(x["cusip"], {"cusip": x["cusip"], "issuer": x["issuer"], "value": 0.0})
        a["value"] += x.get("value") or 0.0
    total = sum(a["value"] for a in agg.values())
    top = sorted(agg.values(), key=lambda a: -a["value"])[:TOP_N]
    out = {**f, "total": total, "n_positions": len(agg),
           "top": [{**a, "weight": a["value"] / total if total else 0.0} for a in top]}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out))
    return out


RETRY_CACHE = CACHE / "figi_retry.json"


def _figi_retry(cusips: List[str]) -> Dict[str, Optional[str]]:
    """Second OpenFIGI pass without the US-exchange filter (ADRs, newly listed share classes); cached."""
    import requests
    try:
        cache = json.loads(RETRY_CACHE.read_text())
    except Exception:
        cache = {}
    todo = [c for c in cusips if c not in cache]
    for i in range(0, len(todo), 10):
        batch = todo[i:i + 10]
        try:
            r = requests.post("https://api.openfigi.com/v3/mapping", json=[{"idType": "ID_CUSIP", "idValue": c} for c in batch], timeout=20)
            if r.status_code == 429:
                time.sleep(6)
                continue
            if r.status_code != 200:
                break
            for c, res in zip(batch, r.json()):
                eq = [d for d in (res.get("data") or []) if d.get("marketSector") == "Equity"
                      and "Common" in str(d.get("securityType") or d.get("securityType2") or "")]
                data = [d for d in eq if d.get("exchCode") in ("US", "UN", "UW", "UQ", "UA", "UP")] or eq
                cache[c] = data[0].get("ticker") if data else None
        except Exception:
            break
        time.sleep(2.5)                                     # stay under the keyless rate limit
    RETRY_CACHE.parent.mkdir(parents=True, exist_ok=True)
    RETRY_CACHE.write_text(json.dumps(cache))
    return {c: cache.get(c) for c in cusips}


def _map_tickers(rows: List[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    from api.marketdata.extras import _cusip_tickers, _match_issuer, _sec_names
    cusips = list(dict.fromkeys(r["cusip"] for r in rows))
    tick = _cusip_tickers(cusips)
    missing = [c for c in cusips if not tick.get(c)]
    if missing:
        tick.update({c: t for c, t in _figi_retry(missing).items() if t})
    names = _sec_names()
    for r in rows:
        if not tick.get(r["cusip"]):
            tick[r["cusip"]] = _match_issuer(r["issuer"], names)
    return tick


def build(max_workers: int = 4) -> Dict[str, Any]:
    """Download (or read from cache) every tracked fund's filings; map the top holdings to tickers."""
    with _lock:
        _status.update(state="running", started=time.time(), done=0)
    all_rows: List[Dict[str, Any]] = []
    panel: List[Dict[str, Any]] = []
    for cik, meta in FUNDS.items():
        try:
            fl = filings(cik)
        except Exception as e:
            logger.warning("[13f] filings %s: %s", cik, e)
            continue
        with ThreadPoolExecutor(max_workers) as ex:
            hs = list(ex.map(lambda f: _holdings(cik, f), fl))
        for h in hs:
            if not h:
                continue
            panel.append({"cik": cik, **{k: h[k] for k in ("period", "filed", "total", "n_positions")}, "top": h["top"]})
            all_rows.extend(h["top"][:25])
        with _lock:
            _status["done"] = _status.get("done", 0) + 1
    tick = _map_tickers(all_rows)
    for f in panel:
        for r in f["top"]:
            t = tick.get(r["cusip"])
            t = t.replace("/", "-").replace(".", "-") if t else None
            valid = bool(t and _TICKER.fullmatch(t))                    # common shares only (no '*', bonds, warrants)
            r["ticker"] = t if valid and not _ETF_WORDS.search(r["issuer"] or "") else None
    out = {"filings": panel, "built": time.strftime("%Y-%m-%d %H:%M")}
    (CACHE / "panel.json").parent.mkdir(parents=True, exist_ok=True)
    (CACHE / "panel.json").write_text(json.dumps(out))
    with _lock:
        _status.update(state="ready", finished=time.time())
    return out


def panel(max_age_h: float = 24.0) -> Dict[str, Any]:
    p = CACHE / "panel.json"
    try:
        if time.time() - p.stat().st_mtime < max_age_h * 3600:
            return json.loads(p.read_text())
    except Exception:
        pass
    return build()


# ── Point-in-time signals ───────────────────────────────────────────────────
def _latest(filings_: List[Dict[str, Any]], date: str, styles: Tuple[str, ...]) -> Dict[str, Dict[str, Any]]:
    """For each fund of the given styles, its most recent filing *filed before* `date` (and no older
    than ~200 days, so a fund that stopped filing drops out)."""
    best: Dict[str, Dict[str, Any]] = {}
    cutoff = (pd.Timestamp(date) - pd.Timedelta(days=200)).strftime("%Y-%m-%d")
    for f in filings_:
        if FUNDS[f["cik"]]["style"] not in styles or f["filed"] >= date or f["filed"] < cutoff:
            continue
        cur = best.get(f["cik"])
        if cur is None or f["period"] > cur["period"]:
            best[f["cik"]] = f
    return best


def _prev(filings_: List[Dict[str, Any]], f: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    older = [g for g in filings_ if g["cik"] == f["cik"] and g["period"] < f["period"]]
    return max(older, key=lambda g: g["period"]) if older else None


def signal_dates(start: str = "2015-01-01") -> List[pd.Timestamp]:
    """Rebalance once a month, on the first trading day after the 15th (the 45-day filing deadline falls
    mid-Feb/May/Aug/Nov, so new information is picked up within weeks)."""
    days = pd.Series(pd.bdate_range(start, pd.Timestamp.today()))
    late = days[days.dt.day >= 16]
    return list(late.groupby(late.dt.to_period("M")).min())


def unmapped_share(kind: str, start: str = "2015-01-01") -> float:
    """Average share (by filed weight) of the candidate holdings that could not be priced — mostly companies
    since acquired (Anadarko, Time Warner, Celgene…) whose price history free sources no longer carry."""
    pn = panel()["filings"]
    styles = {"consensus": ("fundamental",), "best_ideas": ("fundamental",), "quant_adds": ("quant", "multi"), "rentech": ("quant",)}[kind]
    out = []
    for d in signal_dates(start):
        latest = _latest(pn, d.strftime("%Y-%m-%d"), styles)
        if kind == "rentech":
            latest = {k: v for k, v in latest.items() if k == "1037389"}
        rows = [r for f in latest.values() for r in f["top"][:20] if not _ETF_WORDS.search(r["issuer"] or "")]
        w = sum(r["weight"] for r in rows)
        if w:
            out.append(sum(r["weight"] for r in rows if not r.get("ticker")) / w)
    return round(float(np.mean(out)), 3) if out else 0.0


def portfolio(kind: str, n: int = 20, start: str = "2015-01-01") -> pd.DataFrame:
    """Target weights (rebalance dates × tickers) for one 13F strategy."""
    pn = panel()["filings"]
    rows = []
    for d in signal_dates(start):
        ds = d.strftime("%Y-%m-%d")
        w: Dict[str, float] = {}
        if kind == "consensus":                       # GS VIP style: most common top-10 holding of fundamental funds
            latest = _latest(pn, ds, ("fundamental",))
            score: Dict[str, List[float]] = {}
            for f in latest.values():
                for r in [r for r in f["top"] if r.get("ticker")][:10]:
                    score.setdefault(r["ticker"], []).append(r["weight"])
            ranked = sorted(score, key=lambda t: (-len(score[t]), -sum(score[t])))[:n]
            w = {t: 1.0 / len(ranked) for t in ranked} if ranked else {}
        elif kind == "best_ideas":                    # Cohen-Polk-Silli: each fund's highest-tilt position
            latest = _latest(pn, ds, ("fundamental",))
            avg: Dict[str, List[float]] = {}
            for f in latest.values():
                for r in f["top"]:
                    if r.get("ticker"):
                        avg.setdefault(r["ticker"], []).append(r["weight"])
            k = max(len(latest), 1)
            picks: Dict[str, float] = {}
            for f in latest.values():
                cand = [(r["weight"] - sum(avg[r["ticker"]]) / k, r["ticker"]) for r in f["top"] if r.get("ticker")]
                for tilt, t in sorted(cand, reverse=True)[:2]:             # each fund's two best ideas
                    picks[t] = picks.get(t, 0) + 1
            w = {t: 1.0 / len(picks) for t in picks} if picks else {}
        elif kind == "quant_adds":                    # what the quant giants bought most last quarter
            latest = _latest(pn, ds, ("quant", "multi"))
            chg: Dict[str, float] = {}
            for f in latest.values():
                p = _prev(pn, f)
                if not p:
                    continue
                pw = {r["ticker"]: r["weight"] for r in p["top"] if r.get("ticker")}
                for r in f["top"]:
                    if r.get("ticker"):
                        chg[r["ticker"]] = chg.get(r["ticker"], 0) + r["weight"] - pw.get(r["ticker"], 0.0)
            ranked = [t for t, v in sorted(chg.items(), key=lambda kv: -kv[1]) if v > 0][:n]
            w = {t: 1.0 / len(ranked) for t in ranked} if ranked else {}
        elif kind == "rentech":                       # Renaissance's largest disclosed positions
            latest = _latest(pn, ds, ("quant",))
            f = latest.get("1037389")
            if f:
                top = [r for r in f["top"] if r.get("ticker")][:n]
                tot = sum(r["weight"] for r in top)
                w = {r["ticker"]: r["weight"] / tot for r in top} if tot else {}
        rows.append(pd.Series(w, name=d))
    W = pd.DataFrame(rows).fillna(0.0)
    W.index = pd.DatetimeIndex(W.index)
    return W


def evaluate(kind: str, n: int = 20, start: str = "2015-01-01", costs: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """Backtest a 13F strategy with the Code Lab ledger engine (full costs), vs SPY. Decisions are taken only on
    the monthly signal dates; between them positions drift. A trusted server job, so the universe may exceed
    the user-code limit (it is named here, not silently raised)."""
    from api.quant import codelab, codeserver
    W = portfolio(kind, n, start)
    tickers = [t for t in W.columns if W[t].abs().sum() > 0]
    warm = (pd.Timestamp(start) - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
    d = None
    dropped: List[str] = []
    for _ in range(3):                                         # drop tickers Yahoo has no history for (reported)
        try:
            d = codeserver.load_data(tickers, warm, limit=None)
            break
        except ValueError as e:
            msg = str(e)
            if not msg.startswith("No price data for:"):
                raise
            bad = [t.strip() for t in msg.split(":", 1)[1].split("—")[0].split(",")]
            dropped += bad
            tickers = [t for t in tickers if t not in bad]
    if d is None:
        raise ValueError("Could not load prices for the 13F holdings.")
    cols = d.tickers
    idx = d.close.index
    Wd = pd.DataFrame(np.nan, index=idx, columns=cols)
    for dt, row in W[cols].iterrows():                         # a decision on the first session on/after each signal date
        pos = idx.searchsorted(dt)
        if pos >= len(idx):
            continue
        obs = d.observed.iloc[pos]
        live = row.where(obs, 0.0)
        tot = live.sum()
        Wd.iloc[pos] = (live / tot * row.sum()).to_numpy() if tot > 0 else 0.0
    res = codelab.backtest(Wd, d, costs, start)
    spy = codeserver._index_series("SPY", warm)
    ret = res["ret"]
    b = spy.reindex(ret.index).pct_change(fill_method=None).fillna(0.0) if spy is not None else None
    return {"metrics": codelab.metrics(ret, d.rf), "metrics_gross": codelab.metrics(res["gross"], d.rf),
            "costs": codelab.cost_summary(res), "optimisation": {"walk_forward": False, "params": {"n": n}},
            "weights_last": res["weights_last"], "holdings_last": res["holdings_last"], "ledger": res["ledger"],
            "execution": res["execution"], "events": res["events"][-50:],
            "dates": [x.strftime("%Y-%m-%d") for x in ret.index], "returns": [round(float(x), 8) for x in ret.values],
            "gross": [round(float(x), 8) for x in res["gross"].values],
            "benchmark": [round(float(x), 8) for x in b.values] if b is not None else None,
            "benchmark_metrics": codelab.metrics(b, d.rf) if b is not None else None,
            "provenance": {"engine_version": codelab.ENGINE_VERSION, "record_type": "rule-based, point-in-time from 13F "
                           "filing dates (no parameters fitted)", "tickers": len(cols), **d.provenance},
            "data_notes": {"tickers_used": len(cols), "tickers_without_prices": len(dropped), "missing": dropped[:20],
                           "unpriced_weight_share": unmapped_share(kind, start),
                           "note": "Holdings without a price (mostly companies since acquired) are skipped; the next-ranked "
                                   "name takes their place. Listings that end while held are settled at their last close."}}


def latest_view() -> Dict[str, Any]:
    """Current consensus, best ideas and quant adds, with the funds behind each name."""
    pn = panel()["filings"]
    today = pd.Timestamp.today().strftime("%Y-%m-%d")
    latest = _latest(pn, today, ("quant", "multi", "market_maker", "macro", "fundamental"))
    def dollars(f):
        # values are in thousands before 2023 (SEC rule change) — and some filers kept reporting thousands after
        t = f["total"]
        return t * 1000 if f["period"] < "2023-01-01" or (t < 2e8 and f["n_positions"] >= 5) else t
    funds = [{"cik": c, "name": FUNDS[c]["name"], "style": FUNDS[c]["style"], "period": f["period"], "filed": f["filed"],
              "positions": f["n_positions"], "value": dollars(f),
              "top": [{"ticker": r.get("ticker"), "issuer": r["issuer"], "weight": round(r["weight"], 4)} for r in f["top"][:10]]}
             for c, f in sorted(latest.items(), key=lambda kv: FUNDS[kv[0]]["style"])]
    return {"funds": funds, "as_of": today}
