"""
Funds and index membership on free issuer / exchange data:

  index_members(code)   MEMB — constituents of major indices; weights from the issuer's full daily holdings file
                               (State Street for S&P 500 / Dow), Nasdaq's market caps for the Nasdaq-100, and
                               Wikipedia for European / Asian indices (membership only)
  etf_screener()        FSRC — ~200 liquid ETFs across asset classes with cost, size, yield, returns and risk
  etf_compare(a, b)     FSRC — two funds side by side: holdings overlap (full holdings where the issuer publishes
                               them, top holdings otherwise), sector overlap, costs and returns
"""
from __future__ import annotations

import concurrent.futures as cf
import io
import logging
import re
from typing import Any, Dict, List, Optional

import pandas as pd

from api.marketdata.core import NotFound, Upstream, _cached, _f, _info

logger = logging.getLogger(__name__)
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
      "Accept": "application/json, text/plain, */*"}
SSGA = "https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-{}.xlsx"
SSGA_FUNDS = {"SPY", "DIA", "MDY", "XLK", "XLF", "XLV", "XLE", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC", "SPLG", "SPYG", "SPYV",
              "SPSM", "SPMD", "KRE", "KBE", "XBI", "XME", "XOP", "XRT", "XHB", "GLD", "SDY", "SPDW", "SPEM", "SPYD", "RSP"}


def ssga_holdings(fund: str) -> pd.DataFrame:
    f = fund.upper()

    def fetch():
        import requests
        r = requests.get(SSGA.format(f.lower()), headers=UA, timeout=40)
        if r.status_code != 200 or "spreadsheet" not in (r.headers.get("content-type") or ""):
            raise NotFound(f"No full holdings file for {f}.")
        raw = pd.read_excel(io.BytesIO(r.content), header=None)
        hdr = next(i for i in range(min(15, len(raw))) if "Ticker" in [str(x) for x in raw.iloc[i].tolist()])
        df = pd.read_excel(io.BytesIO(r.content), skiprows=hdr)
        df = df[pd.to_numeric(df["Weight"], errors="coerce").notna()]
        df["Weight"] = df["Weight"].astype(float) / 100
        df["Ticker"] = df["Ticker"].astype(str).str.strip().str.replace(".", "-", regex=False)
        df = df[~df["Ticker"].isin(["-", "nan", "CASH_USD", "USD"])]
        return df[["Name", "Ticker", "Weight", "Sector"]].reset_index(drop=True)
    return _cached(f"ssga:{f}", 12 * 3600, fetch)


# ── MEMB ─────────────────────────────────────────────────────────────────────
WIKI = {"UKX": ("FTSE 100", "https://en.wikipedia.org/wiki/FTSE_100_Index", ".L"), "DAX": ("DAX 40", "https://en.wikipedia.org/wiki/DAX", ".DE"),
        "CAC": ("CAC 40", "https://en.wikipedia.org/wiki/CAC_40", ".PA"), "SX5E": ("Euro Stoxx 50", "https://en.wikipedia.org/wiki/EURO_STOXX_50", ""),
        "HSI": ("Hang Seng", "https://en.wikipedia.org/wiki/Hang_Seng_Index", ".HK")}
INDICES = {"SPX": "S&P 500", "INDU": "Dow Jones Industrial Average", "NDX": "Nasdaq-100", **{k: v[0] for k, v in WIKI.items()}}


def _wiki_members(code: str) -> List[Dict[str, Any]]:
    import requests
    name, url, suffix = WIKI[code]
    html = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (macro research terminal)"}, timeout=30).text
    best = None
    for t in pd.read_html(io.StringIO(html)):
        cols = [str(c) for c in t.columns]
        tick = next((c for c in cols if re.search(r"ticker|symbol|code|EPIC", c, re.I)), None)
        nm = next((c for c in cols if re.search(r"company|name|constituent", c, re.I)), None)
        if tick and nm and len(t) >= 20 and (best is None or len(t) > len(best[0])):
            best = (t, tick, nm, next((c for c in cols if re.search(r"sector|industry", c, re.I)), None))
    if best is None:
        raise Upstream(f"Couldn't read the {name} constituents table.")
    t, tick, nm, sec = best
    out = []
    for _, r in t.iterrows():
        raw = str(r[tick]).strip()
        if raw in ("nan", ""):
            continue
        if code == "HSI":
            n = re.sub(r"\D", "", raw)
            sym = f"{int(n):04d}.HK" if n else None
        elif code == "UKX":
            sym = raw.rstrip(".").replace(".", "-") + ".L"           # BT.A → BT-A.L (Yahoo's form)
        elif "." in raw:
            sym = raw                                                 # already exchange-qualified (AIR.PA, MT.AS)
        else:
            sym = raw.replace(" ", "") + suffix
        out.append({"symbol": sym, "name": str(r[nm]), "sector": str(r[sec]) if sec and str(r[sec]) != "nan" else None, "weight": None})
    return out


def index_members(code: str) -> Dict[str, Any]:
    code = code.strip().upper()
    if code not in INDICES:
        raise NotFound(f"Unknown index — try one of {', '.join(INDICES)}.")

    def build():
        note = None
        if code in ("SPX", "INDU"):
            df = ssga_holdings("SPY" if code == "SPX" else "DIA")
            rows = [{"symbol": r.Ticker, "name": str(r.Name).title(), "sector": None if r.Sector in ("-", None) else r.Sector, "weight": float(r.Weight)}
                    for r in df.itertuples()]
            src = f"State Street {'SPY' if code == 'SPX' else 'DIA'} full daily holdings (weights as held by the ETF)"
            if code == "INDU":
                note = "The Dow is price-weighted: a stock's weight is its share price over the sum of prices."
        elif code == "NDX":
            import requests
            j = requests.get("https://api.nasdaq.com/api/quote/list-type/nasdaq100", headers=UA, timeout=30).json()
            data = ((j.get("data") or {}).get("data") or {}).get("rows") or []
            rows = [{"symbol": r["symbol"], "name": re.sub(r" (Common Stock|Class [A-C].*|Ordinary Shares.*|American Depositary.*)$", "", r.get("companyName") or ""),
                     "sector": r.get("sector") or None, "mcap": _f(str(r.get("marketCap") or "").replace(",", ""))} for r in data]
            tot = sum(r["mcap"] or 0 for r in rows)
            for r in rows:
                r["weight"] = (r.pop("mcap") or 0) / tot if tot else None
            src = "Nasdaq (constituents and market caps)"
            note = "Weights approximated from total market cap; the official index caps the largest weights and uses free float."
        else:
            rows = _wiki_members(code)
            src = "Wikipedia constituents list (no weights published for free)"
        rows.sort(key=lambda r: -(r.get("weight") or 0))
        sectors: Dict[str, float] = {}
        for r in rows:
            if r.get("sector") and r.get("weight"):
                sectors[r["sector"]] = sectors.get(r["sector"], 0) + r["weight"]
        w = [r["weight"] for r in rows if r.get("weight")]
        return {"code": code, "name": INDICES[code], "count": len(rows), "members": rows,
                "sectors": sorted(({"sector": k, "weight": v} for k, v in sectors.items()), key=lambda x: -x["weight"]),
                "top10_weight": sum(sorted(w, reverse=True)[:10]) if w else None, "effective_n": 1 / sum(x * x for x in w) if w else None,
                "indices": [{"code": k, "name": v} for k, v in INDICES.items()], "note": note, "source": src}
    return _cached(f"memb:{code}", 12 * 3600, build)


# ── FSRC ─────────────────────────────────────────────────────────────────────
ETF_UNIVERSE = {
    "US equity": "SPY IVV VOO VTI QQQ DIA IWM IWB IJH IJR MDY RSP SPLG SCHB SCHX ITOT VV VO VB MGK VUG VTV IWF IWD SCHG SCHD VIG DGRO NOBL USMV MTUM QUAL VLUE SPHQ SPLV",
    "US sectors": "XLK XLF XLV XLE XLI XLY XLP XLU XLB XLRE XLC VGT SMH SOXX IBB XBI KRE KBE ITA ITB XHB XRT IYR VNQ IGV HACK CIBR SKYY ARKK TAN ICLN",
    "International": "EFA VEA IEFA EEM VWO IEMG VXUS ACWI VT EWJ EWG EWU EWQ EWC EWA EWZ EWW EWY EWT INDA MCHI FXI KWEB EZU VGK SCZ EWS EWH",
    "Bonds": "AGG BND BNDX TLT IEF SHY IEI GOVT TIP SCHP VTIP LQD VCIT VCSH IGSB HYG JNK USHY EMB PCY MUB VTEB BIL SGOV SHV FLOT MBB",
    "Commodities & alternatives": "GLD IAU SLV PPLT USO BNO UNG DBC PDBC GSG DBA CPER URA LIT REMX",
    "Income & options": "JEPI JEPQ QYLD XYLD DIVO SPYI PFF VYM HDV DVY",
    "Leveraged & inverse": "TQQQ SQQQ SPXL SPXS UPRO SSO SH PSQ SOXL SOXS TMF TBT UVXY SVXY",
    "Crypto": "IBIT FBTC GBTC ARKB BITB ETHA ETHE BITO",
}


def etf_screener() -> Dict[str, Any]:
    from api.marketdata.core import yahoo_call

    def build():
        items = [(cat, s) for cat, ss in ETF_UNIVERSE.items() for s in ss.split()]

        def one(item):
            cat, s = item
            try:
                i = yahoo_call(lambda: _info(s))
            except Exception:
                return None
            er = _f(i.get("netExpenseRatio"))
            return {"symbol": s, "name": i.get("longName") or i.get("shortName"), "group": cat, "category": i.get("category"),
                    "family": i.get("fundFamily"), "expense": er / 100 if er is not None else None, "aum": _f(i.get("totalAssets")),
                    "yield": _f(i.get("yield")) if i.get("yield") is not None else (_f(i.get("trailingAnnualDividendYield"))),
                    "ytd": (_f(i.get("ytdReturn")) or 0) / 100 if i.get("ytdReturn") is not None else None,
                    "r3y": _f(i.get("threeYearAverageReturn")), "r5y": _f(i.get("fiveYearAverageReturn")),
                    "beta3y": _f(i.get("beta3Year")), "price": _f(i.get("regularMarketPrice")) or _f(i.get("navPrice")),
                    "volume": _f(i.get("averageVolume")), "inception": i.get("fundInceptionDate"), "full_holdings": s in SSGA_FUNDS}
        with cf.ThreadPoolExecutor(5) as ex:
            rows = [r for r in ex.map(one, items) if r]
        if len(rows) < len(items) * 0.5:
            raise Upstream("Yahoo returned too few funds — try again in a minute.")
        return {"funds": rows, "groups": list(ETF_UNIVERSE), "count": len(rows),
                "note": "A curated universe of ~200 liquid US-listed ETFs. Returns are Yahoo's trailing averages; yield is the trailing distribution yield.",
                "source": "Yahoo Finance fund data"}
    return _cached("fsrc", 12 * 3600, build)


def _holdings_map(fund: str) -> (Dict[str, float], str, Dict[str, float]):
    """Holdings {symbol: weight}, coverage note, sector weights."""
    f = fund.upper()
    if f in SSGA_FUNDS:
        try:
            df = ssga_holdings(f)
            sec: Dict[str, float] = {}
            for r in df.itertuples():
                if r.Sector not in ("-", None) and str(r.Sector) != "nan":
                    sec[str(r.Sector)] = sec.get(str(r.Sector), 0) + float(r.Weight)
            return {r.Ticker: float(r.Weight) for r in df.itertuples()}, f"all {len(df)} holdings (issuer file)", sec
        except Exception:
            pass
    from api.marketdata.security import fund_holdings
    d = fund_holdings(f)
    hold = {h.get("symbol") or h.get("name"): (_f(h.get("weight")) or 0) for h in (d.get("holdings") or []) if h.get("symbol") or h.get("name")}
    sec = {s.get("sector") or s.get("name"): (_f(s.get("weight")) or 0) for s in (d.get("sectors") or [])}
    return hold, f"top {len(hold)} holdings (Yahoo)", sec


def etf_compare(a: str, b: str) -> Dict[str, Any]:
    A, B = a.strip().upper(), b.strip().upper()
    if A == B:
        raise NotFound("Pick two different funds.")

    def build():
        ha, ca, sa = _holdings_map(A)
        hb, cb, sb = _holdings_map(B)
        common = sorted(set(ha) & set(hb), key=lambda k: -min(ha[k], hb[k]))
        overlap = sum(min(ha[k], hb[k]) for k in common)
        sectors = sorted(set(sa) | set(sb))
        sec_overlap = sum(min(sa.get(k, 0), sb.get(k, 0)) for k in sectors) if sa and sb else None
        ia, ib = _info(A), _info(B)

        def facts(i):
            er = _f(i.get("netExpenseRatio"))
            return {"name": i.get("longName") or i.get("shortName"), "expense": er / 100 if er is not None else None, "aum": _f(i.get("totalAssets")),
                    "yield": _f(i.get("yield")), "ytd": (_f(i.get("ytdReturn")) or 0) / 100 if i.get("ytdReturn") is not None else None,
                    "r3y": _f(i.get("threeYearAverageReturn")), "r5y": _f(i.get("fiveYearAverageReturn")), "category": i.get("category")}
        return {"a": A, "b": B, "fa": facts(ia), "fb": facts(ib), "coverage_a": ca, "coverage_b": cb, "overlap_weight": overlap,
                "common_count": len(common), "count_a": len(ha), "count_b": len(hb),
                "common": [{"symbol": k, "weight_a": ha[k], "weight_b": hb[k]} for k in common[:40]],
                "only_a": sorted(((k, v) for k, v in ha.items() if k not in hb), key=lambda x: -x[1])[:15],
                "only_b": sorted(((k, v) for k, v in hb.items() if k not in ha), key=lambda x: -x[1])[:15],
                "sectors": [{"sector": k, "a": sa.get(k), "b": sb.get(k)} for k in sectors], "sector_overlap": sec_overlap,
                "note": "Overlap = sum over shared holdings of the smaller of the two weights (100% = identical portfolios). With only top "
                        "holdings available the true overlap is understated.", "source": "State Street holdings files; Yahoo Finance"}
    return _cached(f"etfcmp:{A}:{B}", 6 * 3600, build)
