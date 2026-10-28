"""
Official-statistics fetchers for the non-US macro models — each returns monthly pandas Series indexed by month start.

    eurostat_series(dataset, filters)   Eurostat dissemination API (JSON-stat 2.0), one series per call
    dbnomics_series(code)               DBnomics mirror (used for the ECB: HICP, interest rates, Euribor)
    oecd_by_country(flow, key)          OECD SDMX API, one request for many countries → {ISO3: Series}
    bis_cpi(countries)                  BIS long consumer-price series (annual % change) → {ISO2: Series}
    fred_series(ids)                    FRED, through the platform's rate-limited loader
    yahoo_monthly(tickers)              Yahoo Finance month-end total-return prices (adjusted closes)
    par_bond_returns(yields, years)     monthly total return of a constant-maturity par bond from its yield

Every fetch is cached on disk (12 hours; the last good copy is served if a refresh fails), so a model run costs
at most one request per dataset and the official APIs — some of which rate-limit — are not hammered.

Why these sources (checked October 2026): DBnomics' copy of Eurostat lags by months, so Eurostat is called
directly; the euro aggregate is EA21 since Bulgaria joined on 1 January 2026 (EA20 series end in December 2025);
HICP moved to the ECB's new HICP dataflow (ECOICOP 2) in 2026; the OECD's own CPI lags for Japan and Mexico, so
consumer prices come from the BIS.
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
import time
from typing import Dict, Iterable, List, Optional

import numpy as np
import pandas as pd
import requests

logger = logging.getLogger(__name__)

TTL = 12 * 3600
UA = {"User-Agent": "macro-research-platform/1.0 (research use)"}
EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
OECD = "https://sdmx.oecd.org/public/rest/data/"
BIS = "https://stats.bis.org/api/v1/data/"


def _cached(name: str, fetch) -> Dict[str, Dict[str, float]]:
    """{label: {YYYY-MM: value}} from the disk cache, refreshed after TTL; the last good copy if a refresh fails."""
    from api.handlers.macro_inputs import _disk_load, _disk_save
    hit = _disk_load(f"econ_{name}", max_age=TTL)
    if hit:
        return hit["data"]
    try:
        data = fetch()
        if data and any(data.values()):
            _disk_save(f"econ_{name}", {"data": data})
            return data
        raise ValueError("no observations")
    except Exception as e:
        stale = _disk_load(f"econ_{name}")
        logger.warning("[econ] %s refresh failed (%s)%s", name, str(e)[:120], " — using last good copy" if stale else "")
        return stale["data"] if stale else {}


def to_series(obs: Dict[str, float]) -> pd.Series:
    """{YYYY-MM or YYYY-MM-DD: value} → float Series on month starts (daily data averaged within the month)."""
    if not obs:
        return pd.Series(dtype=float)
    s = pd.Series(obs, dtype=float)
    s.index = pd.to_datetime([k[:7] + "-01" for k in s.index])
    return s.groupby(level=0).mean().sort_index()


# ── Eurostat ─────────────────────────────────────────────────────────────────
def _eurostat_fetch(dataset: str, filters: Dict[str, str]) -> Dict[str, Dict[str, float]]:
    r = requests.get(EUROSTAT + dataset, params={**filters, "format": "JSON", "lang": "EN"}, headers=UA, timeout=60)
    r.raise_for_status()
    j = r.json()
    if any(n != 1 for n in j["size"][:-1]):
        raise ValueError(f"{dataset}: filters select {j['size']} series, expected one")
    idx = j["dimension"]["time"]["category"]["index"]
    periods = sorted(idx, key=idx.get)
    vals = j.get("value", {})
    return {"v": {periods[int(k)]: float(v) for k, v in vals.items() if v is not None}}


def eurostat_series(dataset: str, filters: Dict[str, str]) -> pd.Series:
    """One Eurostat monthly series selected by dimension filters (every non-time dimension must be pinned)."""
    key = dataset + "_" + "_".join(f"{k}-{v}" for k, v in sorted(filters.items()))
    return to_series(_cached(key, lambda: _eurostat_fetch(dataset, filters)).get("v", {}))


# ── DBnomics (ECB) ───────────────────────────────────────────────────────────
def dbnomics_series(code: str) -> pd.Series:
    """A DBnomics series by provider/dataset/series code (the provider module caches it)."""
    from api.providers import dbnomics
    d = dbnomics.series(code)
    return to_series({o["period"]: o["value"] for o in d.get("observations", []) if o.get("value") is not None})


# ── OECD ─────────────────────────────────────────────────────────────────────
def _oecd_fetch(flow: str, key: str, start: str) -> Dict[str, Dict[str, float]]:
    r = requests.get(f"{OECD}{flow}/{key}", params={"startPeriod": start, "format": "csvfile"}, headers=UA, timeout=90)
    r.raise_for_status()
    out: Dict[str, Dict[str, float]] = {}
    for row in csv.DictReader(io.StringIO(r.text)):
        v = row.get("OBS_VALUE")
        if v not in (None, "", "NaN"):
            out.setdefault(row["REF_AREA"], {})[row["TIME_PERIOD"]] = float(v)
    return out


def oecd_by_country(flow: str, key: str, start: str = "1985-01") -> Dict[str, pd.Series]:
    """One OECD SDMX request for many countries → {ISO3 country: monthly Series}."""
    data = _cached(f"oecd_{flow}_{key}".replace(",", "_").replace("@", "_").replace("+", "-"),
                   lambda: _oecd_fetch(flow, key, start))
    return {c: to_series(v) for c, v in data.items()}


# ── BIS ──────────────────────────────────────────────────────────────────────
def _bis_fetch(countries: Iterable[str], start: str) -> Dict[str, Dict[str, float]]:
    url = f"{BIS}WS_LONG_CPI/M.{'+'.join(countries)}.771"
    r = requests.get(url, params={"startPeriod": start, "detail": "dataonly"},
                     headers={**UA, "Accept": "application/vnd.sdmx.data+csv;version=1.0.0"}, timeout=90)
    r.raise_for_status()
    out: Dict[str, Dict[str, float]] = {}
    for row in csv.DictReader(io.StringIO(r.text)):
        v = row.get("OBS_VALUE")
        if v not in (None, "", "NaN"):
            out.setdefault(row["REF_AREA"], {})[row["TIME_PERIOD"]] = float(v)
    return out


def bis_cpi(countries: List[str], start: str = "1985-01") -> Dict[str, pd.Series]:
    """BIS consumer prices, year-on-year % change (unit 771), monthly → {ISO2 country: Series}."""
    data = _cached("bis_cpi_" + "-".join(countries), lambda: _bis_fetch(countries, start))
    return {c: to_series(v) for c, v in data.items()}


# ── FRED ─────────────────────────────────────────────────────────────────────
async def fred_series(ids: List[str], years: int = 45) -> Dict[str, pd.Series]:
    """FRED series through the platform loader (rate-limited, cached), as daily-or-monthly Series."""
    from api.handlers.macro_inputs import load_fred_series
    got = await load_fred_series(ids, days=int(years * 365.25))
    return {sid: pd.Series(ds.values, index=pd.to_datetime(ds.dates)).astype(float)
            for sid, ds in got.items() if ds and ds.values}


# ── Yahoo ────────────────────────────────────────────────────────────────────
def _yahoo_fetch(tickers: List[str]) -> Dict[str, Dict[str, float]]:
    import yfinance as yf
    out: Dict[str, Dict[str, float]] = {}
    for t in tickers:
        try:
            h = yf.Ticker(t).history(period="max", interval="1mo", auto_adjust=True)
            if h is not None and not h.empty:
                out[t] = {str(i)[:7]: float(c) for i, c in zip(h.index, h["Close"]) if c == c}
        except Exception as e:                                                 # noqa: BLE001 — one ticker failing is reported, not fatal
            logger.warning("[econ] Yahoo history failed for %s: %s", t, e)
        time.sleep(0.2)
    return out


def yahoo_monthly(tickers: List[str], cache_name: str) -> Dict[str, pd.Series]:
    """Monthly adjusted closes (dividends reinvested) for each ticker, labelled by month start."""
    data = _cached(f"yahoo_{cache_name}", lambda: _yahoo_fetch(tickers))
    return {t: to_series(v) for t, v in data.items()}


# ── Synthetic bond returns ───────────────────────────────────────────────────
def par_bond_returns(yields_pct: pd.Series, years: int = 10, freq: int = 1) -> pd.Series:
    """Monthly total return of a constant-maturity government bond, rebuilt from its yield.

    Each month buys a new `years`-year par bond (coupon = that month's yield, `freq` coupons a year) and revalues it a
    month later at the next month's yield with 1/12 year less to maturity — the standard way to turn a yield history
    into a bond-index-like return series (e.g. Swinkels, 2019). Ignores the small roll-down and convexity of a real
    index's maturity spread; good for regime statistics, not for tracking a specific ETF.

    Args:
        yields_pct: Monthly yield in percent, indexed by month.
        years: Constant maturity.
        freq: Coupons per year (1 for Bunds and BTPs, 2 for Treasuries and gilts).

    Returns:
        Monthly simple returns indexed by the month they are earned in.
    """
    y = (yields_pct.dropna().astype(float) / 100.0).sort_index()
    out = {}
    n = years * freq
    for (t0, y0), (t1, y1) in zip(y.items(), list(y.items())[1:]):
        c = y0 / freq
        times = np.arange(1, n + 1) / freq - 1 / 12           # cash-flow times after one month has passed
        disc = (1 + y1 / freq) ** (-freq * times)
        price = c * disc.sum() + disc[-1]                      # per 1 of face; bought at par (1.0)
        out[t1] = price - 1.0
    return pd.Series(out, dtype=float)


def run_sync(fn, *args):
    """Run a blocking fetcher in a worker thread (for use from async loaders)."""
    return asyncio.to_thread(fn, *args)
