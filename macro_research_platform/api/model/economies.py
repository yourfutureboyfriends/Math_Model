"""
The economies the macro model runs on. The method (api/model/core.py) is the same for every economy — growth and
inflation diffusion factors → regime probabilities → regime-conditional expected returns → Black–Litterman portfolio →
walk-forward backtest; each economy supplies its own data:

    us     United States       FRED (17 series), US asset proxies, returns in USD over T-bills  (api/model/data.py)
    ea     Euro area           Eurostat + ECB, euro assets, returns in EUR over 3-month Euribor
    row    Rest of the world   OECD leading indicators and unemployment, BIS consumer prices for nine major
                               economies outside the US and the euro area; returns in USD over T-bills

Each loader returns (raw macro series by key, monthly asset excess returns). Series keys, their block (growth /
inflation), transform and publication lag in months follow the US convention in data.py: the panel at month t holds
only what had been published by the end of month t.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, List, Tuple

import pandas as pd

from api.model import sources as src

Spec = Dict[str, Tuple[str, str, int]]          # key -> (block, transform, publication lag in months)


@dataclass(frozen=True)
class Economy:
    """One economy's model configuration: its macro series, the assets it allocates across and where the data
    comes from."""
    id: str
    name: str
    currency: str
    cash_label: str
    series: Spec
    labels: Dict[str, str]                       # series key -> human label
    anchors: Tuple[str, str]                     # series each factor must load positively on (growth, inflation)
    assets: Dict[str, Tuple[str, str, str]]      # model asset -> (estimation proxy, tradeable instrument, environment)
    benchmark: Tuple[str, str]                   # (equity asset, bond asset) of the 60/40 benchmark
    sources: List[str]
    limitations: List[str]
    loader: Callable[[], Awaitable[Tuple[Dict[str, pd.Series], pd.DataFrame]]] = field(compare=False, repr=False)
    tradeable: bool = False                      # can stage orders for the fund's model sleeve (US only for now)

    def blocks(self) -> Dict[str, str]:
        """Series key → block ('growth' / 'inflation')."""
        return {k: v[0] for k, v in self.series.items()}

    def env(self) -> Dict[str, str]:
        """Model asset → environment class used by the environment-balanced prior."""
        return {k: v[2] for k, v in self.assets.items()}


def _excess(returns: Dict[str, pd.Series], cash_annual_pct: pd.Series) -> pd.DataFrame:
    """Monthly returns minus the cash rate (annual % / 12); the current, incomplete month is dropped."""
    r = pd.DataFrame(returns).sort_index()
    this_month = pd.Timestamp.today().to_period("M").to_timestamp()
    r = r[r.index < this_month]
    c = (cash_annual_pct.resample("MS").mean() / 1200).reindex(r.index).ffill()
    return r.sub(c, axis=0)


def _month_end(daily: pd.Series) -> pd.Series:
    """Last observation of each month, labelled by month start."""
    s = daily.dropna().sort_index()
    m = s.groupby(s.index.to_period("M")).last()
    m.index = m.index.to_timestamp()
    return m


# ── Euro area ────────────────────────────────────────────────────────────────
EA = "EA21"                                       # Bulgaria joined on 1 Jan 2026; EA20 series end in Dec 2025
EUROSTAT_SERIES: Dict[str, Tuple[str, Dict[str, str]]] = {
    "EA_IP": ("sts_inpr_m", {"geo": EA, "s_adj": "SCA", "unit": "I21", "nace_r2": "B-D", "indic_bt": "PRD"}),
    "EA_RETAIL": ("sts_trtu_m", {"geo": EA, "s_adj": "SCA", "unit": "I21", "nace_r2": "G47", "indic_bt": "VOL_SLS"}),
    "EA_CONSTR": ("sts_copr_m", {"geo": EA, "s_adj": "SCA", "unit": "I21", "nace_r2": "F", "indic_bt": "PRD"}),
    "EA_UNEMP": ("une_rt_m", {"geo": EA, "s_adj": "SA", "age": "TOTAL", "sex": "T", "unit": "PC_ACT"}),
    "EA_ESI": ("ei_bssi_m_r2", {"geo": EA, "s_adj": "SA", "indic": "BS-ESI-I"}),
    "EA_ICI": ("ei_bssi_m_r2", {"geo": EA, "s_adj": "SA", "indic": "BS-ICI-BAL"}),
    "EA_CCI": ("ei_bssi_m_r2", {"geo": EA, "s_adj": "SA", "indic": "BS-CSMCI-BAL"}),
    "EA_SCI": ("ei_bssi_m_r2", {"geo": EA, "s_adj": "SA", "indic": "BS-SCI-BAL"}),
    "EA_EEI": ("ei_bsee_m_r2", {"geo": EA, "s_adj": "SA", "indic": "BS-EEI-I", "unit": "INX"}),
    "EA_PPI": ("sts_inppd_m", {"geo": EA, "s_adj": "NSA", "unit": "I21", "nace_r2": "B-E36", "indic_bt": "PRC_PRR_DOM"}),
    "EA_SPE": ("ei_bsin_m_r2", {"geo": EA, "s_adj": "SA", "indic": "BS-ISPE"}),
}
ECB_SERIES = {
    "EA_HICP": "ECB/HICP/M.U2.N.000000.4D0.ANR",
    "EA_HICP_CORE": "ECB/HICP/M.U2.N.XEF000.4D0.ANR",
    "EA_HICP_SERV": "ECB/HICP/M.U2.N.SERV00.4D0.ANR",
    "EA_HICP_GOODS": "ECB/HICP/M.U2.N.GOODS0.4D0.ANR",
    "EA_EURIBOR3M": "ECB/FM/M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA",
    "DE_10Y": "ECB/IRS/M.DE.L.L40.CI.0000.EUR.N.Z",
    "IT_10Y": "ECB/IRS/M.IT.L.L40.CI.0000.EUR.N.Z",
}
EA_SPEC: Spec = {
    # Growth: hard activity data (published ~6 weeks after the month) and the European Commission surveys (end of
    # the same month)
    "EA_IP": ("growth", "yoy", 2), "EA_RETAIL": ("growth", "yoy", 2), "EA_CONSTR": ("growth", "yoy", 2),
    "EA_UNEMP": ("growth", "neg_diff12", 2), "EA_ESI": ("growth", "level", 0), "EA_ICI": ("growth", "level", 0),
    "EA_CCI": ("growth", "level", 0), "EA_SCI": ("growth", "level", 0), "EA_EEI": ("growth", "level", 0),
    # Inflation: HICP annual rates (final release mid next month), producer prices, firms' selling-price
    # expectations and oil in euros
    "EA_HICP": ("inflation", "level", 1), "EA_HICP_CORE": ("inflation", "level", 1),
    "EA_HICP_SERV": ("inflation", "level", 1), "EA_HICP_GOODS": ("inflation", "level", 1),
    "EA_PPI": ("inflation", "yoy", 2), "EA_SPE": ("inflation", "level", 0), "EA_BRENT_EUR": ("inflation", "yoy", 0),
}
EA_LABELS = {
    "EA_IP": "Industrial production", "EA_RETAIL": "Retail trade volume", "EA_CONSTR": "Construction output",
    "EA_UNEMP": "Unemployment rate (inverted)", "EA_ESI": "Economic sentiment indicator",
    "EA_ICI": "Industry confidence", "EA_CCI": "Consumer confidence", "EA_SCI": "Services confidence",
    "EA_EEI": "Employment expectations", "EA_HICP": "HICP inflation", "EA_HICP_CORE": "Core HICP (ex energy, food)",
    "EA_HICP_SERV": "Services inflation", "EA_HICP_GOODS": "Goods inflation", "EA_PPI": "Producer prices (domestic)",
    "EA_SPE": "Industry selling-price expectations", "EA_BRENT_EUR": "Brent crude in euros",
}
EA_ASSETS: Dict[str, Tuple[str, str, str]] = {
    "Euro-area equity": ("^GDAXI", "EXW1.DE", "Equity"),            # DAX: a total-return index, from 1987
    "Bunds (10y)": ("synthetic:DE_10Y", "IS0L.DE", "Nominal bonds"),
    "BTPs (10y)": ("synthetic:IT_10Y", "EUNH.DE", "Nominal bonds"),
    "Euro IG credit": ("IEAC.L", "IEAC.L", "Corporate credit"),
    "US equity (EUR)": ("usd:VFINX", "SXR8.DE", "Equity"),
    "EM equity (EUR)": ("usd:VEIEX", "IS3N.DE", "Equity"),
    "Gold (EUR)": ("usd:GC=F", "4GLD.DE", "Gold"),
    "Commodities (EUR)": ("usd:PCRIX", "CMOD.L", "Commodities"),
}


async def _load_ea() -> Tuple[Dict[str, pd.Series], pd.DataFrame]:
    import asyncio
    raw: Dict[str, pd.Series] = {}
    euro = await asyncio.gather(*[asyncio.to_thread(src.eurostat_series, ds, f) for ds, f in EUROSTAT_SERIES.values()],
                                return_exceptions=True)
    for k, s in zip(EUROSTAT_SERIES, euro):
        if isinstance(s, pd.Series) and not s.empty:
            raw[k] = s
    ecb = await asyncio.gather(*[asyncio.to_thread(src.dbnomics_series, c) for c in ECB_SERIES.values()],
                               return_exceptions=True)
    for k, s in zip(ECB_SERIES, ecb):
        if isinstance(s, pd.Series) and not s.empty:
            raw[k] = s
    fred = await src.fred_series(["DCOILBRENTEU", "DEXUSEU"])
    usd_per_eur_d = fred.get("DEXUSEU", pd.Series(dtype=float))
    if "DCOILBRENTEU" in fred and not usd_per_eur_d.empty:
        brent = fred["DCOILBRENTEU"].resample("MS").mean()
        raw["EA_BRENT_EUR"] = (brent / usd_per_eur_d.resample("MS").mean()).dropna()

    # Assets, in euros
    usd_per_eur = _month_end(usd_per_eur_d)
    tickers = sorted({p.split(":", 1)[-1] for p, _, _ in EA_ASSETS.values() if not p.startswith("synthetic:")})
    px = await asyncio.to_thread(src.yahoo_monthly, tickers, "ea_assets")
    rets: Dict[str, pd.Series] = {}
    for name, (proxy, _, _) in EA_ASSETS.items():
        if proxy.startswith("synthetic:"):
            y = raw.get(proxy.split(":", 1)[1])
            if y is not None:
                rets[name] = src.par_bond_returns(y, years=10, freq=1)
            continue
        t = proxy.split(":", 1)[-1]
        p = px.get(t)
        if p is None or p.empty:
            continue
        if proxy.startswith("usd:"):                       # a USD price seen by a euro investor (unhedged)
            p = (p / usd_per_eur.reindex(p.index)).dropna()
        rets[name] = p.sort_index().pct_change()
    cash = raw.get("EA_EURIBOR3M", pd.Series(dtype=float))
    return raw, _excess(rets, cash)


# ── Rest of the world ────────────────────────────────────────────────────────
ROW_ISO3 = ["GBR", "JPN", "CHN", "IND", "CAN", "KOR", "AUS", "BRA", "MEX"]
ROW_ISO2 = {"GBR": "GB", "JPN": "JP", "CHN": "CN", "IND": "IN", "CAN": "CA", "KOR": "KR", "AUS": "AU", "BRA": "BR", "MEX": "MX"}
ROW_UNEMP = ["GBR", "JPN", "CAN", "KOR", "AUS", "MEX"]       # monthly harmonised unemployment published by the OECD
COUNTRY = {"GBR": "UK", "JPN": "Japan", "CHN": "China", "IND": "India", "CAN": "Canada", "KOR": "Korea",
           "AUS": "Australia", "BRA": "Brazil", "MEX": "Mexico"}
ROW_SPEC: Spec = {
    **{f"CLI_{c}": ("growth", "level", 1) for c in ROW_ISO3},             # OECD CLI, amplitude adjusted (trend = 100)
    **{f"UNEMP_{c}": ("growth", "neg_diff12", 2) for c in ROW_UNEMP},
    **{f"CPI_{c}": ("inflation", "level", 2 if c == "AUS" else 1) for c in ROW_ISO3},   # BIS, annual % change
    "BRENT": ("inflation", "yoy", 0), "COMMODITIES": ("inflation", "yoy", 1),
}
ROW_LABELS = {
    **{f"CLI_{c}": f"{COUNTRY[c]} — OECD leading indicator" for c in ROW_ISO3},
    **{f"UNEMP_{c}": f"{COUNTRY[c]} — unemployment (inverted)" for c in ROW_UNEMP},
    **{f"CPI_{c}": f"{COUNTRY[c]} — CPI inflation" for c in ROW_ISO3},
    "BRENT": "Brent crude (USD)", "COMMODITIES": "IMF all-commodity price index",
}
ROW_ASSETS: Dict[str, Tuple[str, str, str]] = {
    "Japan equity": ("FJPNX", "EWJ", "Equity"),
    "UK equity": ("EWU", "EWU", "Equity"),
    "China & HK equity": ("FHKCX", "MCHI", "Equity"),
    "EM equity": ("VEIEX", "EEM", "Equity"),
    "International government bonds": ("RPIBX", "BWX", "Nominal bonds"),
    "EM bonds (USD)": ("PREMX", "EMB", "Corporate credit"),
    "Gold": ("GC=F", "GLD", "Gold"),
    "Commodities": ("PCRIX", "DBC", "Commodities"),
}


async def _load_row() -> Tuple[Dict[str, pd.Series], pd.DataFrame]:
    import asyncio
    raw: Dict[str, pd.Series] = {}
    cli, une, cpi = await asyncio.gather(
        asyncio.to_thread(src.oecd_by_country, "OECD.SDD.STES,DSD_STES@DF_CLI,",
                          f"{'+'.join(ROW_ISO3)}.M.LI...AA...H", "1985-01"),
        asyncio.to_thread(src.oecd_by_country, "OECD.SDD.TPS,DSD_LFS@DF_IALFS_UNE_M,",
                          f"{'+'.join(ROW_UNEMP)}.UNE_LF_M.PT_LF_SUB._Z.Y._T.Y_GE15._Z.M", "1985-01"),
        asyncio.to_thread(src.bis_cpi, [ROW_ISO2[c] for c in ROW_ISO3], "1985-01"),
        return_exceptions=True)
    if isinstance(cli, dict):
        raw.update({f"CLI_{c}": s for c, s in cli.items() if not s.empty})
    if isinstance(une, dict):
        raw.update({f"UNEMP_{c}": s for c, s in une.items() if not s.empty})
    if isinstance(cpi, dict):
        iso3 = {v: k for k, v in ROW_ISO2.items()}
        raw.update({f"CPI_{iso3[c]}": s for c, s in cpi.items() if c in iso3 and not s.empty})
    fred = await src.fred_series(["DCOILBRENTEU", "PALLFNFINDEXM", "TB3MS"])
    if "DCOILBRENTEU" in fred:
        raw["BRENT"] = fred["DCOILBRENTEU"].resample("MS").mean()
    if "PALLFNFINDEXM" in fred:
        raw["COMMODITIES"] = fred["PALLFNFINDEXM"]
    if "TB3MS" in fred:
        raw["TB3MS"] = fred["TB3MS"]

    px = await asyncio.to_thread(src.yahoo_monthly, sorted({p for p, _, _ in ROW_ASSETS.values()}), "row_assets")
    rets = {name: px[p].sort_index().pct_change() for name, (p, _, _) in ROW_ASSETS.items() if p in px and not px[p].empty}
    return raw, _excess(rets, raw.get("TB3MS", pd.Series(dtype=float)))


# ── US (the original model; data in api/model/data.py) ──────────────────────
async def _load_us() -> Tuple[Dict[str, pd.Series], pd.DataFrame]:
    import asyncio
    from api.model import data
    raw = await data.load_macro_raw()
    prices = await asyncio.to_thread(data.load_asset_prices)
    return raw, data.excess_returns(prices, raw.get(data.CASH_SERIES, pd.Series(dtype=float)))


def _us() -> Economy:
    from api.model import data
    return Economy(
        id="us", name="United States", currency="USD", cash_label="3-month T-bill",
        series=data.MACRO_SERIES, labels={k: k for k in data.MACRO_SERIES}, anchors=("INDPRO", "CPIAUCSL"),
        assets=data.ASSETS, benchmark=("US equity", "Intermediate Treasuries"),
        sources=["FRED (Federal Reserve Bank of St. Louis)", "Yahoo Finance (fund total returns)"],
        limitations=["FRED serves revised data, not first-release vintages (mild look-ahead in the macro inputs).",
                     "Regime probabilities assume growth and inflation directions are independent.",
                     "Estimation uses mutual-fund proxies; trading uses ETFs with shorter histories.",
                     "Gold history starts in 2000 and commodities in 2002."],
        loader=_load_us, tradeable=True)


ECONOMIES: Dict[str, Economy] = {
    "us": _us(),
    "ea": Economy(
        id="ea", name="Euro area", currency="EUR", cash_label="3-month Euribor",
        series=EA_SPEC, labels=EA_LABELS, anchors=("EA_IP", "EA_HICP"), assets=EA_ASSETS,
        benchmark=("Euro-area equity", "Bunds (10y)"),
        sources=["Eurostat (activity, unemployment, European Commission business and consumer surveys)",
                 "European Central Bank via DBnomics (HICP, Euribor, 10-year government yields)",
                 "FRED (Brent, EUR/USD)", "Yahoo Finance (DAX, euro credit ETF, USD fund prices)"],
        limitations=["Euro-area aggregates are the current 21-country composition back-cast by Eurostat / the ECB.",
                     "Euro-area equity uses the DAX (a German total-return index, the longest free euro equity "
                     "series) as its proxy; the tradeable instrument is the EURO STOXX 50.",
                     "Bund and BTP returns are rebuilt from 10-year yields (constant-maturity par bonds), not an index.",
                     "Euro IG credit starts in 2009 (the ETF's launch); USD assets start in 1999 (EUR/USD).",
                     "Revised data, not first-release vintages; growth and inflation directions treated as independent."],
        loader=_load_ea),
    "row": Economy(
        id="row", name="Rest of the world", currency="USD", cash_label="3-month T-bill",
        series=ROW_SPEC, labels=ROW_LABELS, anchors=("CLI_JPN", "CPI_GBR"), assets=ROW_ASSETS,
        benchmark=("EM equity", "International government bonds"),
        sources=["OECD (composite leading indicators, harmonised unemployment)",
                 "BIS (consumer prices)", "FRED (Brent, IMF commodity prices, T-bill)",
                 "Yahoo Finance (fund total returns)"],
        limitations=["One global ex-US, ex-euro cycle: the factors are the first principal component across nine "
                     "economies (UK, Japan, China, India, Canada, Korea, Australia, Brazil, Mexico) — not a model of "
                     "any single country.",
                     "OECD leading indicators are already smoothed and trend-adjusted, so the growth factor's direction "
                     "is persistent: its direction forecasts score well partly for that reason. Monthly unemployment is "
                     "published for six of the nine.",
                     "Returns are in US dollars (unhedged) over US T-bills.",
                     "Revised data, not first-release vintages; growth and inflation directions treated as independent."],
        loader=_load_row),
}


def get(economy: str) -> Economy:
    """The economy's configuration.

    Raises:
        LookupError: unknown economy id.
    """
    e = ECONOMIES.get((economy or "us").lower())
    if e is None:
        raise LookupError(f"Unknown economy '{economy}'. Use one of: {', '.join(ECONOMIES)}.")
    return e
