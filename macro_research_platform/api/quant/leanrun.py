"""
Run a QuantConnect algorithm on QuantConnect's own LEAN engine (the official `quantconnect/lean` Docker image), unmodified,
with the platform's free daily prices converted to LEAN's data format — US equities, crypto pairs (any venue LEAN knows:
Coinbase, Binance, Kraken, …) and FX pairs (Oanda, FXCM) — so the algorithm runs exactly as LEAN runs it.

Data written per run (api/quant/leanrun.prepare):
  equity/usa/daily/<ticker>.zip       <ticker>.csv rows "YYYYMMDD 00:00,open,high,low,close,volume", prices × 10,000
  equity/usa/map_files/<ticker>.csv   the ticker from before the data starts to 2050 (no renames)
  equity/usa/factor_files/<ticker>.csv  factors 1 — prices are already split- and dividend-adjusted (total return)
  equity/usa/fundamental/coarse/, universes/etf/spy/, fundamental/free/   (universes; see below)
LEAN's market-hours and symbol-properties databases come from the image.

Isolation: the container has no network, every capability dropped, no privilege escalation, memory / CPU / process
caps; only the algorithm, the run's data and a results folder are mounted.

Crypto: trade and quote bars per venue (a USD pair also stands in for its stablecoin pairs, 1 stablecoin = 1 USD); FX: bid
and ask bars. Free daily data has no spread, so bid = ask = the traded price.

Universes: add_universe(selector), universe.etf("SPY"), dollar-volume selectors and the universe-selection models run
natively on LEAN's own coarse and ETF-constituent files, written per session from the point-in-time S&P 500 membership
(security identifiers in LEAN's encoding). `Fundamental` objects carry free values through a fundamental-data provider
plugin (api/quant/lean_plugin, compiled in the image): has_fundamental_data, today's Morningstar sector code, and SEC
EDGAR filings point in time (market cap, shares, EPS, P/E, P/B, P/S, yields, ROE/ROA, margins, statement lines). Other
Morningstar fields read as LEAN's missing-value defaults, and the run lists the ones the algorithm uses.

Custom data: each PythonData class's own get_source is run in the sandbox to find its URLs; the platform fetches them
(public http/https hosts only) and LEAN reads the local copies with the algorithm's own reader.

Resolution: free data is daily. A wrapper subclass (zzQuantLabDaily, appended to main.py — LEAN's loader takes the last
QCAlgorithm subclass by name) serves tick / second / minute / hour requests as daily and lists each mapping in the run's
notes; LEAN itself is unmodified.

Not available on this path (free data): intraday bars, options and futures chains, Morningstar fields without a free
source, QuantConnect's alternative datasets.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

IMAGE = os.getenv("MACRO_LEAN_IMAGE", "quantconnect/lean:latest")
LEAN_DATA = "/Lean/Data"
_STATUS: Dict[str, Any] = {"at": 0.0}


class LeanError(RuntimeError):
    pass


# Morningstar / fine-fundamental fields: QuantConnect's licensed dataset (coarse fields — price, volume, dollar volume —
# are written from free data)
MORNINGSTAR = re.compile(r"\b(asset_classification|AssetClassification|valuation_ratios|ValuationRatios|market_cap|"
                         r"MarketCap|earning_reports|EarningReports|operation_ratios|OperationRatios|financial_statements|"
                         r"FinancialStatements|company_reference|CompanyReference|security_reference|SecurityReference|"
                         r"company_profile|CompanyProfile|earning_ratios|EarningRatios|MorningstarSectorCode|"
                         r"MorningstarIndustryGroupCode|MorningstarIndustryCode|QC500UniverseSelectionModel)\b")


def status(refresh: bool = False) -> Dict[str, Any]:
    """Whether real-LEAN runs are possible: docker, a running daemon and the LEAN image. Cached for a minute."""
    if not refresh and time.time() - _STATUS["at"] < 60:
        return {k: v for k, v in _STATUS.items() if k != "at"}
    ok, why, version = False, None, None
    if not shutil.which("docker"):
        why = "docker is not installed"
    else:
        try:
            r = subprocess.run(["docker", "image", "inspect", IMAGE, "--format", "{{.Id}} {{.Created}}"],
                               capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                ok, version = True, r.stdout.strip().split(" ", 1)[-1][:10]
            elif "daemon" in (r.stderr or "") or "Cannot connect" in (r.stderr or ""):
                why = "Docker is not running"
            else:
                why = f"the LEAN image {IMAGE} is not downloaded (docker pull {IMAGE})"
        except Exception as e:                                               # noqa: BLE001
            why = f"docker check failed ({type(e).__name__})"
    _STATUS.update(at=time.time(), available=ok, reason=why, image=IMAGE, image_date=version)
    return {"available": ok, "reason": why, "image": IMAGE, "image_date": version}


PLUGIN_SRC = Path(__file__).resolve().parent / "lean_plugin"
PLUGIN_DIR = Path(__file__).resolve().parents[2] / "data" / "processed" / "lean_plugin"        # gitignored
PROVIDER = "QuantConnect.FreeData.FreeFundamentalDataProvider"


def plugin() -> Dict[str, Path]:
    """The free-fundamentals provider (api/quant/lean_plugin) compiled against this LEAN image, and the image's
    config.json with it selected as LEAN's fundamental-data provider. Built once per image and source (in the LEAN image,
    no network), then cached."""
    import hashlib
    img = subprocess.run(["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"], capture_output=True, text=True,
                         timeout=20).stdout.strip()
    h = hashlib.sha256((img + "".join(p.read_text() for p in sorted(PLUGIN_SRC.glob("*")) if p.is_file())).encode()
                       ).hexdigest()[:16]
    out = PLUGIN_DIR / h
    dll, cfg = out / "QuantConnect.FreeData.dll", out / "config.json"
    if dll.exists() and cfg.exists():
        return {"dll": dll, "config": cfg}
    out.mkdir(parents=True, exist_ok=True)
    os.chmod(out, 0o777)
    r = subprocess.run(["docker", "run", "--rm", "--network", "none", "-v", f"{PLUGIN_SRC}:/src:ro", "-v", f"{out}:/out",
                        "--entrypoint", "bash", IMAGE, "-c",
                        "cp -r /src /tmp/b && cd /tmp/b && dotnet build -c Release -o /tmp/o -nologo -v q && "
                        "cp /tmp/o/QuantConnect.FreeData.dll /out/ && cp /Lean/Launcher/bin/Debug/config.json /out/config.orig.json"],
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or not dll.exists():
        raise LeanError("Could not build LEAN's free-fundamentals provider: " + (r.stdout + r.stderr)[-600:])
    orig = (out / "config.orig.json").read_text()
    i = orig.index("{") + 1
    cfg.write_text(orig[:i] + f'\n  "fundamental-data-provider": "{PROVIDER}",' + orig[i:])
    return {"dll": dll, "config": cfg}


# free values for LEAN's FundamentalProperty names (SEC EDGAR, point in time; ratios on the day's price)
def _fund_props(f: Dict[str, pd.DataFrame], px: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    sh = f["shares"]
    mcap = sh * px
    pos = lambda x: x.where(x > 0)
    eq = f["equity"]
    return {
        "CompanyProfile_SharesOutstanding": sh, "CompanyProfile_MarketCap": mcap,
        "EarningReports_BasicEPS_TwelveMonths": f["eps_ttm"], "EarningReports_DilutedEPS_TwelveMonths": f["eps_ttm"],
        "ValuationRatios_PERatio": px / pos(f["eps_ttm"]), "ValuationRatios_EarningYield": f["eps_ttm"] / px,
        "ValuationRatios_PBRatio": mcap / pos(eq), "ValuationRatios_BookValueYield": eq / mcap,
        "ValuationRatios_PSRatio": mcap / pos(f["sales_ttm"]), "ValuationRatios_SalesYield": f["sales_ttm"] / mcap,
        "ValuationRatios_FCFYield": f["fcf_ttm"] / mcap,
        "OperationRatios_ROE_OneYear": f["net_income_ttm"] / pos(eq),
        "OperationRatios_ROA_OneYear": f["net_income_ttm"] / pos(f["total_assets"]),
        "OperationRatios_GrossMargin_OneYear": f["gross_profit_ttm"] / pos(f["sales_ttm"]),
        "OperationRatios_NetMargin_OneYear": f["net_income_ttm"] / pos(f["sales_ttm"]),
        "OperationRatios_DebtToAssets_OneYear": f["total_liabilities"] / pos(f["total_assets"]),
        "FinancialStatements_IncomeStatement_TotalRevenue_TwelveMonths": f["sales_ttm"],
        "FinancialStatements_IncomeStatement_NetIncome_TwelveMonths": f["net_income_ttm"],
        "FinancialStatements_IncomeStatement_GrossProfit_TwelveMonths": f["gross_profit_ttm"],
        "FinancialStatements_BalanceSheet_TotalAssets_TwelveMonths": f["total_assets"],
        "FinancialStatements_BalanceSheet_TotalLiabilitiesNetMinorityInterest_TwelveMonths": f["total_liabilities"],
        "FinancialStatements_BalanceSheet_StockholdersEquity_TwelveMonths": eq,
        "FinancialStatements_BalanceSheet_TotalEquity_TwelveMonths": eq,
        "FinancialStatements_CashFlowStatement_FreeCashFlow_TwelveMonths": f["fcf_ttm"],
    }


# the Fundamental attribute names free data supplies (snake case); anything else under a Morningstar group reads as LEAN's
# missing-value default (0 / NaN) and is listed in the run's notes
GROUPS = {"valuation_ratios", "operation_ratios", "earning_reports", "earning_ratios", "financial_statements",
          "company_profile", "company_reference", "security_reference", "asset_classification"}
SUPPLIED = GROUPS | {
    "shares_outstanding", "market_cap", "basic_eps", "diluted_eps", "twelve_months", "one_year", "value", "pe_ratio",
    "earning_yield", "pb_ratio", "book_value_yield", "ps_ratio", "sales_yield", "fcf_yield", "roe", "roa", "gross_margin",
    "net_margin", "debt_to_assets", "income_statement", "balance_sheet", "cash_flow_statement", "total_revenue",
    "net_income", "gross_profit", "total_assets", "total_liabilities_net_minority_interest", "stockholders_equity",
    "total_equity", "free_cash_flow", "morningstar_sector_code"}


def _snk(n: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", n).lower()     # PERatio → pe_ratio


def fine_fields(code: str) -> Dict[str, List[str]]:
    """Morningstar attribute chains the algorithm reads: {'used': [...], 'unsupplied': [...]} (snake case)."""
    used, missing = set(), set()
    for m in re.finditer(r"\b(\w+)((?:\.\w+)+)", code):
        parts = [m.group(1)] + m.group(2).strip(".").split(".")
        snake = [_snk(x) for x in parts]
        for k, x in enumerate(snake):
            if x in GROUPS:
                chain = snake[k:]
                used.add(".".join(chain))
                missing |= {".".join(chain)} if any(c not in SUPPLIED for c in chain) else set()
                break
    return {"used": sorted(used), "unsupplied": sorted(missing)}


def write_fundamentals(root: Path, frames: Dict[str, pd.DataFrame], instruments: Dict[str, Any],
                       members: pd.DataFrame, start: str, sec: bool) -> Dict[str, Any]:
    """equity/usa/fundamental/free/YYYYMMDD.csv for the provider: every member has fundamental data, today's sector as a
    Morningstar code, and — sec=True — SEC EDGAR fundamentals (as first filed, from the session after filing)."""
    from api.quant.qcalgo import morningstar_sector
    tick = {t: lean_ticker(t) for t in frames if lean_ticker(t)}
    ids = {t: sid(lt, first_date(frames[t].index)) for t, lt in tick.items()}
    close = pd.DataFrame({t: frames[t]["close"] for t in tick})
    idx = close.index
    props: Dict[str, pd.DataFrame] = {}
    info: Dict[str, Any] = {"sector": "today's sector for every date (sector history is not free)"}
    if sec:
        from api.providers import sec_edgar
        try:
            f = sec_edgar.pit_frame(list(tick), idx)
            props = _fund_props(f, close)
            info["sec"] = "SEC EDGAR company facts, as first filed, from the session after filing"
        except Exception as e:                                                # noqa: BLE001
            info["sec"] = f"SEC EDGAR unavailable ({str(e)[:120]}): only sector and has_fundamental_data"
    sector = pd.Series({t: morningstar_sector((instruments.get(t) or {}).get("sector")) for t in tick})
    out = root / "equity" / "usa" / "fundamental" / "free"
    out.mkdir(parents=True, exist_ok=True)
    names = list(props)
    head = "sid,AssetClassification_MorningstarSectorCode," + ",".join(names) + "\n"
    arrs = {n: props[n].reindex(index=idx, columns=list(tick)).to_numpy(float) for n in names}
    mem = members.reindex(index=idx, columns=list(tick)).fillna(False).to_numpy(bool)
    cols = list(tick)
    sect = [sector[t] for t in cols]
    days = 0
    for k, d in enumerate(idx):
        if d < pd.Timestamp(start) - pd.Timedelta(days=10):
            continue
        lines = []
        for j, t in enumerate(cols):
            if not mem[k, j]:
                continue
            vals = [("" if not np.isfinite(sect[j]) else f"{int(sect[j])}")] + [
                ("" if not np.isfinite(arrs[n][k, j]) else f"{arrs[n][k, j]:.10g}") for n in names]
            lines.append(ids[t] + "," + ",".join(vals))
        if lines:
            (out / f"{d:%Y%m%d}.csv").write_text(head + "\n".join(lines) + "\n")
            days += 1
    info["days"] = days
    info["fields"] = ["has_fundamental_data", "AssetClassification_MorningstarSectorCode"] + names
    return info


def lean_ticker(t: str) -> Optional[str]:
    """Platform ticker → LEAN's US-equity ticker (lower case; BRK-B → brk.b). None for non-US listings."""
    t = str(t).upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9]{0,5}([-.][A-Z])?", t):
        return None
    return t.replace("-", ".").lower()


def write_daily(root: Path, ticker: str, frame: pd.DataFrame) -> int:
    """One ticker's daily bars in LEAN's equity format. `frame` has open, high, low, close, volume (index = dates)."""
    f = frame.dropna(subset=["close"]).copy()
    if f.empty:
        return 0
    for c in ("open", "high", "low"):
        f[c] = f[c].fillna(f["close"])
    f["volume"] = f["volume"].fillna(0)
    rows = [f"{d.strftime('%Y%m%d')} 00:00,{int(round(o * 10000))},{int(round(h * 10000))},{int(round(l * 10000))},"
            f"{int(round(c * 10000))},{int(v)}"
            for d, o, h, l, c, v in zip(f.index, f["open"], f["high"], f["low"], f["close"], f["volume"])]
    daily = root / "equity" / "usa" / "daily"
    daily.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(daily / f"{ticker}.zip", "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{ticker}.csv", "\n".join(rows) + "\n")
    first = first_date(f.index)
    for sub, body in (("map_files", f"{first:%Y%m%d},{ticker}\n20501231,{ticker}\n"),
                      ("factor_files", f"{first:%Y%m%d},1,1,1\n20501231,1,1,0\n")):
        d = root / "equity" / "usa" / sub
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{ticker}.csv").write_text(body)
    return len(rows)


def first_date(index) -> pd.Timestamp:
    """The listing date LEAN sees (first row of the map file; also the date inside the security identifier)."""
    return pd.Timestamp(index[0]) - pd.Timedelta(days=10)


_B36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def sid(ticker: str, first: pd.Timestamp) -> str:
    """LEAN's SecurityIdentifier for a US equity: '<TICKER> <base36(days since 1899-12-30 × 10^14 + market usa (1) × 100
    + security type equity (1))>' — e.g. AAPL R735QTJ8XC9X (first traded 1998-01-02)."""
    n = (pd.Timestamp(first).normalize() - pd.Timestamp("1899-12-30")).days * 10 ** 14 + 101
    out = ""
    while n:
        n, r = divmod(n, 36)
        out = _B36[r] + out
    return f"{ticker.upper()} {out}"


def write_universe(root: Path, frames: Dict[str, pd.DataFrame], members: pd.DataFrame, start: str) -> Dict[str, Any]:
    """LEAN's own universe files from point-in-time S&P 500 membership, so add_universe / universe.etf("SPY") /
    dollar-volume selectors run natively:
      equity/usa/fundamental/coarse/YYYYMMDD.csv  SID,ticker,close,volume,dollar volume,has fundamentals,price factor,split factor
      equity/usa/universes/etf/spy/YYYYMMDD.csv   ticker,SID,date,weight,shares,
    Prices are already adjusted (factors 1). ETF weights are each member's share of 63-day traded value (free data has no
    market cap)."""
    coarse_dir = root / "equity" / "usa" / "fundamental" / "coarse"
    etf_dir = root / "equity" / "usa" / "universes" / "etf" / "spy"
    coarse_dir.mkdir(parents=True, exist_ok=True)
    etf_dir.mkdir(parents=True, exist_ok=True)
    tick = {t: lean_ticker(t) for t in frames if lean_ticker(t)}
    ids = {t: sid(lt, first_date(frames[t].index)) for t, lt in tick.items()}
    close = pd.DataFrame({t: frames[t]["close"] for t in tick})
    vol = pd.DataFrame({t: frames[t]["volume"] for t in tick}).reindex(close.index)
    dv = close * vol
    adv = dv.rolling(63, min_periods=1).mean()
    mem = members.reindex(index=close.index, columns=list(tick)).fillna(False).astype(bool)
    days = close.index[close.index >= pd.Timestamp(start) - pd.Timedelta(days=10)]
    n = 0
    for d in days:
        row_c, row_v, row_dv, row_m = close.loc[d], vol.loc[d], dv.loc[d], mem.loc[d]
        live = [t for t in tick if row_m[t] and np.isfinite(row_c[t])]
        if not live:
            continue
        stamp = d.strftime("%Y%m%d")
        (coarse_dir / f"{stamp}.csv").write_text("".join(
            f"{ids[t]},{tick[t].upper()},{row_c[t]:.6g},{int(row_v[t] or 0)},{int(row_dv[t] or 0)},True,1,1\n"
            for t in live))
        w = adv.loc[d, live].fillna(0)
        w = w / w.sum() if w.sum() > 0 else w * 0 + 1.0 / len(live)
        (etf_dir / f"{stamp}.csv").write_text("".join(
            f"{tick[t].upper()},{ids[t]},{stamp},{w[t]:.8f},{int((w[t] * 1e9) / row_c[t]) if row_c[t] else 0},\n"
            for t in live))
        n += 1
    return {"days": n, "names": len(live) if days.size else 0}


CRYPTO_VENUES = ("coinbase", "binance", "binanceus", "kraken", "bitfinex", "bybit")
FX_VENUES = ("oanda", "fxcm")


def _bars_csv(f: pd.DataFrame, quote: bool) -> str:
    """Unscaled daily rows; quote=True writes bid and ask bars (both at the traded price — free data has no spread)."""
    out = []
    for d, o, h, l, c, v in zip(f.index, f["open"], f["high"], f["low"], f["close"], f["volume"]):
        px = f"{o:.10g},{h:.10g},{l:.10g},{c:.10g}"
        out.append(f"{d:%Y%m%d} 00:00,{px},0,{px},0" if quote else f"{d:%Y%m%d} 00:00,{px},{float(v or 0):.10g}")
    return "\n".join(out) + "\n"


def _write_zip(path: Path, inner: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(inner, body)


def write_crypto(root: Path, base: str, quote: str, frame: pd.DataFrame) -> List[str]:
    """A crypto pair's daily trade and quote bars for every venue LEAN might ask (Market.COINBASE, BINANCE, …); a USD
    pair also stands in for its stablecoin pairs (USDT, USDC, BUSD)."""
    f = frame.dropna(subset=["close"]).fillna({"volume": 0})
    for c in ("open", "high", "low"):
        f[c] = f[c].fillna(f["close"])
    pairs = [f"{base}{quote}".lower()] + ([f"{base}{s}".lower() for s in ("usdt", "usdc", "busd", "fdusd")]
                                          if quote == "USD" else [])
    trade, quotes = _bars_csv(f, False), _bars_csv(f, True)
    for venue in CRYPTO_VENUES:
        for pair in pairs:
            d = root / "crypto" / venue / "daily"
            _write_zip(d / f"{pair}_trade.zip", f"{pair}.csv", trade)
            _write_zip(d / f"{pair}_quote.zip", f"{pair}.csv", quotes)
    return pairs


def write_forex(root: Path, pair: str, frame: pd.DataFrame) -> None:
    f = frame.dropna(subset=["close"]).fillna({"volume": 0})
    for c in ("open", "high", "low"):
        f[c] = f[c].fillna(f["close"])
    for venue in FX_VENUES:
        _write_zip(root / "forex" / venue / "daily" / f"{pair.lower()}.zip", f"{pair.lower()}.csv", _bars_csv(f, True))


def classify(ticker: str):
    """('equity', lean ticker) | ('crypto', (base, quote)) | ('forex', pair) | (None, None)."""
    t = str(ticker).upper()
    m = re.fullmatch(r"([A-Z]{6})=X", t)
    if m:
        return "forex", m.group(1)
    if re.fullmatch(r"[A-Z0-9]{2,10}-(USD|USDT|USDC|EUR|GBP|JPY|BTC|ETH)", t):
        b, q = t.split("-")
        return "crypto", (b, q)
    lt = lean_ticker(t)
    return ("equity", lt) if lt else (None, None)


def prepare(tickers: List[str], start: str, root: Path, say=lambda m: None, universe: bool = False,
            sec: bool = False) -> Dict[str, Any]:
    """Convert the platform's daily prices for `tickers` (+ SPY, LEAN's default benchmark) into LEAN's format.
    universe=True also writes every point-in-time S&P 500 member since `start` and LEAN's coarse / SPY-constituent
    universe files for each session."""
    from api.quant import codeserver
    names, minfo = [], None
    if universe:
        from api.quant import membership
        names, minfo = membership.universe_since(start)
    want = list(dict.fromkeys([t.upper() for t in tickers] + ["SPY"] + names))
    kinds = {t: classify(t) for t in want}
    skipped = [t for t, (k, _) in kinds.items() if k is None]
    usable = [t for t, (k, _) in kinds.items() if k is not None]
    if not usable:
        raise LeanError("No tickers LEAN can take (US equities, crypto pairs, FX pairs).")
    say(f"Converting daily prices for {len(usable)} instruments to LEAN's format…")
    warm = (pd.Timestamp(start) - pd.Timedelta(days=500)).strftime("%Y-%m-%d")    # history before the start for warm-up
    from api.quant import codelab
    d = codeserver.load_data(usable, warm, allow_missing=True, limit=codelab.LARGE_UNIVERSE_LIMIT)
    rows, notes, eq_frames = {}, [], {}
    for t in usable:
        if t not in d.close.columns:
            skipped.append(t)
            continue
        obs = d.observed[t]
        fr = pd.DataFrame({"open": d.open[t], "high": d.high[t], "low": d.low[t], "close": d.close[t],
                           "volume": d.volume[t]})[obs]
        kind, key = kinds[t]
        if kind == "equity":
            rows[t] = write_daily(root, key, fr)
            if rows[t]:
                eq_frames[t] = fr
        elif kind == "crypto":
            pairs = write_crypto(root, key[0], key[1], fr)
            rows[t] = int(len(fr))
            if len(pairs) > 1:
                notes.append(f"{t} also stands in for {', '.join(p.upper() for p in pairs[1:])} (stablecoin = 1 USD)")
        else:
            write_forex(root, key, fr)
            rows[t] = int(len(fr))
    uni = None
    if universe:
        from api.quant import membership
        say(f"Writing LEAN universe files (point-in-time S&P 500, {len(names)} past and present members)…")
        members = membership.members_frame(d.close.index, list(eq_frames))
        uni = write_universe(root, eq_frames, members, start)
        if sec:
            say("Loading point-in-time SEC fundamentals for the members (first run downloads them)…")
        uni["fundamentals"] = write_fundamentals(root, eq_frames, d.instruments or {}, members, start, sec)
        missing = [n for n in names if n not in eq_frames]
        notes.append(f"universe: point-in-time S&P 500 members in LEAN's coarse and SPY-constituent files "
                     f"({uni['days']} sessions); {len(missing)} former members have no free price history; ETF weights "
                     "are shares of 63-day traded value (no free index weights); fundamentals: has_fundamental_data, today's "
                     "Morningstar sector code" + (", SEC EDGAR filings point in time (market cap, EPS, ratios, statements)"
                                                   if sec else ""))
    if any(kinds[t][0] in ("crypto", "forex") for t in rows):
        notes.append("crypto and FX bid/ask are both the traded price (free daily data has no spread)")
    if universe:                                   # hundreds of members: report a count, not every row count
        skipped = [t for t in skipped if t not in names]
    return {"tickers": rows if not universe else {t: rows[t] for t in rows if t not in names or t in tickers},
            "instruments": len(rows), "skipped": skipped, "notes": notes, "universe": uni, "membership": minfo,
            "data_start": str(d.close.index[0].date()), "data_end": str(d.close.index[-1].date())}


# ── custom data: the URLs an algorithm's own get_source returns are fetched here (the container has no network) and
# served to LEAN as local files; LEAN runs the algorithm's own reader on them ─────────────────────────────────────
CUSTOM_CACHE = Path(__file__).resolve().parents[2] / "data" / "processed" / "lean_custom"          # gitignored
CUSTOM_MAX_BYTES = 50_000_000
CUSTOM_MAX_FILES = 40
CUSTOM_TTL_S = 24 * 3600


def _public_host(host: str) -> None:
    """Refuse hosts that resolve to private, loopback, link-local, reserved or multicast addresses (no SSRF into the
    platform's own network)."""
    import ipaddress
    import socket
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as e:
        raise LeanError(f"custom data: cannot resolve {host} ({e})")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise LeanError(f"custom data: {host} resolves to a non-public address ({ip}) — refused")


def fetch_source(url: str) -> Path:
    """Download one get_source URL (http/https, public hosts only, every redirect re-checked, ≤ 50 MB, 30 s) into the
    cache (a day). Returns the cached file."""
    import hashlib
    import urllib.error
    import urllib.parse
    import urllib.request
    base = url.split("#", 1)[0]
    path = urllib.parse.urlparse(base).path
    ext = os.path.splitext(path)[1].lower()
    ext = ext if ext in (".csv", ".zip", ".json", ".txt", ".tsv", ".xml", ".gz") else ".dat"
    CUSTOM_CACHE.mkdir(parents=True, exist_ok=True)
    out = CUSTOM_CACHE / (hashlib.sha256(base.encode()).hexdigest()[:24] + ext)
    if out.exists() and time.time() - out.stat().st_mtime < CUSTOM_TTL_S:
        return out

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    cur = base
    for _ in range(6):
        u = urllib.parse.urlparse(cur)
        if u.scheme not in ("http", "https") or not u.hostname:
            raise LeanError(f"custom data: only http(s) URLs can be fetched ({cur[:120]})")
        _public_host(u.hostname)
        req = urllib.request.Request(cur, headers={"User-Agent": "QuantLab-LEAN-data-fetch/1"})
        try:
            resp = opener.open(req, timeout=30)
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
                cur = urllib.parse.urljoin(cur, e.headers["Location"])
                continue
            raise LeanError(f"custom data: {cur[:120]} answered HTTP {e.code}")
        except Exception as e:                                                # noqa: BLE001
            raise LeanError(f"custom data: could not fetch {cur[:120]} ({type(e).__name__}: {str(e)[:120]})")
        body = resp.read(CUSTOM_MAX_BYTES + 1)
        if len(body) > CUSTOM_MAX_BYTES:
            raise LeanError(f"custom data: {cur[:120]} is larger than {CUSTOM_MAX_BYTES // 1_000_000} MB")
        tmp = out.with_suffix(out.suffix + ".part")
        tmp.write_bytes(body)
        tmp.replace(out)
        return out
    raise LeanError(f"custom data: too many redirects for {base[:120]}")


def custom_sources(code: str) -> List[Dict[str, Any]]:
    """The get_source URLs of every custom-data class the algorithm adds (found by running initialize() in the
    sandbox). Raises with the reason when a source cannot be served to LEAN."""
    from api.quant import sandbox
    found = sandbox.discover(code)
    recs = found.get("custom_sources") or []
    urls = []
    for r in recs:
        who = f"custom data '{r['ticker']}' ({r.get('class') or 'no class'})"
        if r.get("error") == "no get_source" or (not r.get("sources") and not r.get("error")):
            raise LeanError(f"{who}: the class has no get_source — LEAN needs one. On the built-in layer, add_data reads "
                            f"the CSV uploaded as '{r['ticker']}' (Quant Lab → Custom data).")
        if r.get("error"):
            raise LeanError(f"{who}: {r['error']}")
        for src in r["sources"]:
            t = (src.get("transport") or "").lower()
            if "local" in t or "object" in t:
                raise LeanError(f"{who}: get_source reads a local file / the object store ({src['url'][:100]}), which "
                                "only exists on QuantConnect's servers")
            urls.append(src["url"])
    urls = list(dict.fromkeys(urls))
    if len(urls) > CUSTOM_MAX_FILES:
        raise LeanError(f"custom data needs {len(urls)} files (over {CUSTOM_MAX_FILES})")
    return [{"url": u} for u in urls]


def custom_prelude(mapping: Dict[str, str]) -> str:
    """Python placed before the algorithm in main.py: SubscriptionDataSource(url, …) for a fetched URL becomes the local
    copy (transport LocalFile), before `from AlgorithmImports import *` copies the name into the algorithm."""
    return f'''# ── Quant Lab: get_source URLs fetched by the platform (LEAN's container has no network) ──
import AlgorithmImports as _ql_a0
_ql_urls = {mapping!r}
_ql_real_sds = _ql_a0.SubscriptionDataSource


def _ql_sds(source, *a, **k):
    s = str(source)
    loc = _ql_urls.get(s) or _ql_urls.get(s.split("#", 1)[0])
    if loc is None:
        return _ql_real_sds(source, *a, **k)
    if "#" in s:
        loc = loc + "#" + s.split("#", 1)[1]
    a = list(a)
    if a:
        a[0] = _ql_a0.SubscriptionTransportMedium.LocalFile
    for key in ("transport_medium", "transportMedium"):
        if key in k:
            k[key] = _ql_a0.SubscriptionTransportMedium.LocalFile
    return _ql_real_sds(loc, *a, **k)


_ql_a0.SubscriptionDataSource = _ql_sds
# ── end of Quant Lab prelude ──

'''


# Methods that take a Resolution (both spellings are generated below). Free data is daily: a finer request is mapped to
# daily (otherwise LEAN subscribes to minute files that do not exist and the algorithm silently never trades).
_RES_METHODS = ("add_equity", "add_crypto", "add_forex", "add_cfd", "add_index", "add_data", "add_security",
                "add_universe", "history", "set_warm_up", "consolidate", "register_indicator", "warm_up_indicator",
                "indicator_history", "sma", "ema", "rsi", "atr", "bb", "macd", "roc", "rocp", "momp", "mom", "max", "min",
                "std", "adx", "wma", "lwma", "hma", "dema", "tema", "kama", "trix", "apo", "ppo", "cmo", "logr", "cci",
                "sto", "willr", "aroon", "dch", "kch", "obv", "vwap", "mfi", "psar", "natr", "tr", "beta", "identity",
                "delay", "sar", "lsma", "alma", "t3", "frama", "vwma", "zlema", "ichimoku", "uo", "ao", "ad", "adosc",
                "rdv", "rvi", "sharpe_ratio", "sortino_ratio", "variance", "correlation", "regression", "hurst_exponent")


def daily_wrapper(cls: str) -> str:
    """Python appended to main.py: a subclass of the algorithm that maps tick / second / minute / hour requests to daily
    (the only free resolution) and records each mapping in /Results/quantlab-notes.txt. LEAN itself is unmodified."""
    names = sorted({n for m in _RES_METHODS for n in (m, "".join(w.upper() if w in ("sma", "ema", "rsi", "atr", "bb", "macd", "roc", "rocp", "momp", "mom", "max", "min", "std", "adx", "wma", "lwma", "hma", "dema", "tema", "kama", "trix", "apo", "ppo", "cmo", "logr", "cci", "sto", "willr", "dch", "kch", "obv", "vwap", "mfi", "psar", "natr", "tr", "sar", "lsma", "alma", "t3", "frama", "vwma", "zlema", "uo", "ao", "ad", "adosc", "rdv", "rvi") else w.capitalize() for w in m.split("_")))})
    return f'''

# ── Quant Lab: free data is daily — finer resolutions requested by the algorithm are served as daily ─────────────────
import AlgorithmImports as _ql_ai
_QL_FINE = ("Tick", "Second", "Minute", "Hour")
_QL_SEEN = set()


def _ql_note(what):
    if what not in _QL_SEEN:
        _QL_SEEN.add(what)
        try:
            with open("/Results/quantlab-notes.txt", "a") as _f:
                _f.write(what + "\\n")
        except Exception:
            pass


def _ql_res(x, where):
    if type(x).__name__ == "Resolution" and str(x).split(".")[-1].capitalize() in _QL_FINE:
        _ql_note(f"{{where}}: Resolution.{{str(x).split('.')[-1].upper()}} served as daily (free data is daily)")
        return _ql_ai.Resolution.DAILY
    return x


def _ql_wrap(name):
    def call(self, *a, **k):
        a = tuple(_ql_res(x, name) for x in a)
        for key in ("resolution", "Resolution"):
            if key in k:
                k[key] = _ql_res(k[key], name)
        if name.lower().replace("_", "") in ("addequity", "addcrypto", "addforex", "addcfd", "addindex") and \\
                not any(type(x).__name__ == "Resolution" for x in a) and "resolution" not in k:
            _ql_note(f"{{name}}: no resolution given (LEAN's default is minute) — served as daily")
            k["resolution"] = _ql_ai.Resolution.DAILY
        return getattr(super(zzQuantLabDaily, self), name)(*a, **k)
    call.__name__ = name
    return call


# (LEAN's Python loader ignores --algorithm-type-name: it takes the last QCAlgorithm subclass of main.py in name order,
# so this wrapper's name sorts after every other class name)
class zzQuantLabDaily({cls}):
    def initialize(self):
        self.UniverseSettings.Resolution = _ql_ai.Resolution.Daily
        for _k in type(self).__mro__[1:]:                 # the algorithm's own initialize / Initialize (not LEAN's base)
            _f = _k.__dict__.get("initialize") or _k.__dict__.get("Initialize")
            if _f is not None and _k.__module__ != "QuantConnect.Algorithm":
                _f(self)
                break
        if str(self.UniverseSettings.Resolution).split(".")[-1].capitalize() in _QL_FINE:
            _ql_note(f"universe_settings.resolution {{self.UniverseSettings.Resolution}} served as daily")
            self.UniverseSettings.Resolution = _ql_ai.Resolution.Daily

    Initialize = initialize
''' + "".join(f"    {n} = _ql_wrap({n!r})\n" for n in names)


def _docker_cmd(name: str, algo_dir: Path, data_dir: Path, results: Path, cls: str, cpu: int,
                plug: Optional[Dict[str, Path]] = None, custom_dir: Optional[Path] = None) -> List[str]:
    mounts = ["-v", f"{custom_dir}:/Lean/Data/qlcustom:ro"] if custom_dir else []
    if plug:                                                  # the free-fundamentals provider, selected in config.json
        mounts += ["-v", f"{plug['dll']}:/Lean/Launcher/bin/Debug/QuantConnect.FreeData.dll:ro",
                   "-v", f"{plug['config']}:/Lean/Launcher/bin/Debug/config.json:ro"]
    for sub in ("daily", "map_files", "factor_files", "fundamental/coarse", "fundamental/free", "universes/etf/spy"):
        p = data_dir / "equity" / "usa" / sub
        if p.exists():
            mounts += ["-v", f"{p}:{LEAN_DATA}/equity/usa/{sub}:ro"]
    for cls_dir in ("crypto", "forex"):
        for venue in sorted((data_dir / cls_dir).glob("*/daily")) if (data_dir / cls_dir).exists() else []:
            mounts += ["-v", f"{venue}:{LEAN_DATA}/{cls_dir}/{venue.parent.name}/daily:ro"]
    return ["docker", "run", "--rm", "--name", name, "--network", "none", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--memory", "6g", "--memory-swap", "6g", "--cpus", "2",
            "--pids-limit", "512", "--ulimit", f"cpu={cpu}:{cpu}",
            "-v", f"{algo_dir}:/Algorithm:ro", "-v", f"{results}:/Results:rw", *mounts,
            "-w", "/Lean/Launcher/bin/Debug", IMAGE,                   # the image's entrypoint is the LEAN launcher
            "--environment", "backtesting", "--algorithm-language", "Python",
            "--algorithm-type-name", "zzQuantLabDaily", "--algorithm-location", "/Algorithm/main.py",
            "--data-folder", LEAN_DATA, "--results-destination-folder", "/Results",
            "--close-automatically", "true"]


def _series(chart: Dict[str, Any], name: str) -> List[List[float]]:
    s = ((chart or {}).get("series") or (chart or {}).get("Series") or {}).get(name) or {}
    vals = s.get("values") or s.get("Values") or []
    out = []
    for v in vals:
        if isinstance(v, dict):
            out.append([float(v.get("x")), float(v.get("y"))])
        elif isinstance(v, (list, tuple)) and len(v) >= 2:
            out.append([float(v[0]), float(v[-1] if len(v) == 5 else v[1])])     # candles: [t, o, h, l, c]
    return out


def parse_results(results: Path) -> Dict[str, Any]:
    """LEAN's result JSON → statistics, equity curve, orders, logs."""
    main = results / "zzQuantLabDaily.json"
    if not main.exists():
        files = sorted(p for p in results.glob("*.json") if not re.search(
            r"-(summary|order-events|log|alpha|insights)\.json$|^data-monitor-report", p.name))
        main = files[0] if files else None
    if main is None:
        raise LeanError("LEAN wrote no result file.")
    r = json.loads(main.read_text())
    stats = r.get("statistics") or r.get("Statistics") or {}
    rt = r.get("runtimeStatistics") or r.get("RuntimeStatistics") or {}
    charts = r.get("charts") or r.get("Charts") or {}
    eq = _series(charts.get("Strategy Equity") or {}, "Equity")
    bm = _series(charts.get("Benchmark") or {}, "Benchmark")
    orders = r.get("orders") or r.get("Orders") or {}
    order_list = list(orders.values()) if isinstance(orders, dict) else list(orders)
    log = ""
    for p in results.glob("*log*.txt"):
        log += p.read_text(errors="replace")[-8000:]
    curve = [{"date": time.strftime("%Y-%m-%d", time.gmtime(x)), "equity": y} for x, y in eq]
    return {"statistics": stats, "runtime_statistics": rt, "equity_curve": curve,
            "benchmark_curve": [{"date": time.strftime("%Y-%m-%d", time.gmtime(x)), "value": y} for x, y in bm],
            "orders": [{k: o.get(k) for k in ("Id", "Symbol", "Time", "Type", "Status", "Quantity", "Price", "Tag",
                                              "id", "symbol", "time", "type", "status", "quantity", "price", "tag")
                        if k in o} for o in order_list[:500]],
            "order_count": len(order_list), "log_tail": log[-4000:]}


def run(code: str, job: Optional[Any] = None, timeout: int = 1800) -> Dict[str, Any]:
    """Backtest a QuantConnect algorithm on real LEAN. Returns LEAN's statistics, equity curve and orders."""
    from api.quant import qcalgo, sandbox
    say = (lambda m: job.progress(m)) if job is not None else (lambda m: None)
    st = status(refresh=True)
    if not st["available"]:
        raise LeanError(f"Real-LEAN runs are unavailable: {st['reason']}.")
    head = sandbox.check(code, uploads_required=False)     # same static and discovery checks as every server run
    qc = head.get("qc")
    if not qc:
        raise LeanError("Real-LEAN runs take a QuantConnect algorithm (a class deriving from QCAlgorithm).")
    fine = fine_fields(code)
    custom = []
    if head.get("custom") or qc.get("custom"):
        say("Finding the custom data the algorithm reads (its own get_source, run in the sandbox)…")
        custom = custom_sources(code)
    tmp = Path(tempfile.mkdtemp(prefix="qlean_")).resolve()
    name = f"qlean-{uuid.uuid4().hex[:12]}"
    try:
        algo_dir, data_dir, results = tmp / "algo", tmp / "data", tmp / "results"
        for p in (algo_dir, data_dir, results):
            p.mkdir()
        os.chmod(results, 0o777)
        from api.quant.codelab import split_project
        main, files = split_project(code)
        mapping = {}
        if custom:
            cdir = tmp / "custom"
            cdir.mkdir()
            say(f"Fetching {len(custom)} custom data file(s) for LEAN…")
            for c in custom:
                f = fetch_source(c["url"])
                shutil.copy(f, cdir / f.name)
                mapping[c["url"].split("#", 1)[0]] = f"/Lean/Data/qlcustom/{f.name}"
        (algo_dir / "main.py").write_text((custom_prelude(mapping) if mapping else "") + main + daily_wrapper(qc["class"]))
        for mod, src in files.items():                     # the project's other files, as real modules for LEAN
            path = algo_dir / (mod.replace(".", "/") + ".py")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(src)
            for parent in path.relative_to(algo_dir).parents:
                if str(parent) != ".":
                    (algo_dir / parent / "__init__.py").touch()
        uni = bool(qc.get("dynamic_universe")) or bool(MORNINGSTAR.search(code))
        prep = prepare(head["universe"], qc.get("start") or head["start"], data_dir, say, universe=uni,
                       sec=bool(fine["used"]) or bool(re.search(r"market_cap|MarketCap", code)))
        if fine["unsupplied"]:
            prep["notes"].append("Morningstar fields with no free source read as LEAN's missing-value defaults (0 / NaN): "
                                 + ", ".join(fine["unsupplied"][:12]))
        plug = plugin() if uni else None
        say(f"Running on LEAN ({IMAGE}) — {len(prep['tickers'])} tickers…")
        log_f = open(tmp / "lean.log", "w")
        p = subprocess.Popen(_docker_cmd(name, algo_dir, data_dir, results, qc["class"], timeout, plug,
                                         tmp / "custom" if mapping else None), stdout=log_f,
                             stderr=subprocess.STDOUT)
        t0 = time.time()
        while p.poll() is None:
            if job is not None and getattr(job, "cancelled", False):
                subprocess.run(["docker", "kill", name], capture_output=True, timeout=30)
                raise LeanError("Cancelled.")
            if time.time() - t0 > timeout:
                subprocess.run(["docker", "kill", name], capture_output=True, timeout=30)
                raise LeanError(f"LEAN ran longer than {timeout} s and was stopped.")
            time.sleep(0.5)
        log_f.close()
        console = (tmp / "lean.log").read_text(errors="replace")
        try:
            out = parse_results(results)
        except LeanError:
            err = [l for l in console.splitlines() if re.search(r"ERROR|Error|Exception|Traceback|Runtime Error", l)]
            raise LeanError("LEAN did not finish: " + (" | ".join(err[-4:]) or console[-800:]))
        rt_err = [l for l in console.splitlines() if "Runtime Error" in l or "PythonException" in l]
        qn = results / "quantlab-notes.txt"
        if qn.exists():
            prep["notes"] += [l for l in qn.read_text().splitlines() if l][:20]
        out.update({"engine": "QuantConnect LEAN (unmodified)", "image": IMAGE, "image_date": st.get("image_date"),
                    "data": {**prep, "source": "platform daily prices (split- and dividend-adjusted) in LEAN format"},
                    "runtime_errors": rt_err[-5:], "console_tail": console[-3000:],
                    "isolation": "docker: no network, capabilities dropped, no privilege escalation, memory/CPU caps"})
        return out
    finally:
        try:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=20)
        except Exception:                                                     # noqa: BLE001
            pass
        if os.getenv("MACRO_LEAN_KEEP"):                     # debugging: keep the run's folder (data, results, console)
            print(f"[leanrun] kept {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)
