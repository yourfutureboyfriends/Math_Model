"""
Data-rich panel for the ML engine: ~75 monthly US series across the groups of the St. Louis Fed's FRED-MD database
(McCracken & Ng, "FRED-MD: A Monthly Database for Macroeconomic Research", JBES 2016), built from the FRED API with
FRED-MD's standard transformations so every series is stationary:
    1 level · 2 change · 4 log · 5 change of log (growth) · 6 second difference of log (acceleration, prices/money)
Each value is the one known at the month: data through the previous month (one-month publication lag). Series are
the latest revised data (not first releases) — the panel's caveat, carried with the results.

Why: in the research on machine learning for macro forecasting, the gains come from non-linear models on rich
datasets with strong regularisation — factors extracted from a FRED-MD-style panel being the best regulariser
(Goulet Coulombe, Leroux, Stevanovic & Surprenant, J. Applied Econometrics 2022), random forests on FRED-MD beating
inflation benchmarks (Medeiros, Vasconcelos, Veiga & Zilberman, JBES 2021), and diffusion-index factors
(Stock & Watson 2002). The FRED-MD file itself is served behind an access check that blocks scripts, so the panel is
assembled series by series from the FRED API instead.
"""
from __future__ import annotations

import logging
from typing import Dict, List

import numpy as np

logger = logging.getLogger(__name__)

# id → (group, transformation code, label). Only series with history from about 1970 or earlier, so the panel is
# complete over the whole walk-forward.
SERIES: Dict[str, tuple] = {
    # output and income
    "INDPRO": ("Output & income", 5, "Industrial production"), "IPFINAL": ("Output & income", 5, "IP: final products"),
    "IPCONGD": ("Output & income", 5, "IP: consumer goods"), "IPBUSEQ": ("Output & income", 5, "IP: business equipment"),
    "IPMAT": ("Output & income", 5, "IP: materials"), "IPMANSICS": ("Output & income", 5, "IP: manufacturing"),
    "CUMFNS": ("Output & income", 2, "Capacity utilisation, manufacturing"), "W875RX1": ("Output & income", 5, "Real income ex transfers"),
    "RPI": ("Output & income", 5, "Real personal income"),
    # labour market
    "PAYEMS": ("Labour", 5, "Nonfarm payrolls"), "USGOOD": ("Labour", 5, "Goods-producing jobs"), "MANEMP": ("Labour", 5, "Manufacturing jobs"),
    "SRVPRD": ("Labour", 5, "Service-providing jobs"), "USCONS": ("Labour", 5, "Construction jobs"), "USTRADE": ("Labour", 5, "Trade jobs"),
    "USFIRE": ("Labour", 5, "Finance jobs"), "USGOVT": ("Labour", 5, "Government jobs"), "UNRATE": ("Labour", 2, "Unemployment rate"),
    "UEMPMEAN": ("Labour", 2, "Mean unemployment duration"), "UEMPLT5": ("Labour", 5, "Unemployed < 5 weeks"),
    "UEMP27OV": ("Labour", 5, "Unemployed 27+ weeks"), "CLF16OV": ("Labour", 5, "Labour force"), "CE16OV": ("Labour", 5, "Civilian employment"),
    "AWHMAN": ("Labour", 1, "Weekly hours, manufacturing"), "AWOTMAN": ("Labour", 2, "Overtime hours, manufacturing"),
    "CES0600000008": ("Labour", 6, "Hourly earnings, goods-producing"), "ICSA": ("Labour", 5, "Initial jobless claims"),
    # housing
    "HOUST": ("Housing", 4, "Housing starts"), "HOUSTNE": ("Housing", 4, "Starts, Northeast"), "HOUSTMW": ("Housing", 4, "Starts, Midwest"),
    "HOUSTS": ("Housing", 4, "Starts, South"), "HOUSTW": ("Housing", 4, "Starts, West"), "PERMIT": ("Housing", 4, "Building permits"),
    # consumption, orders and inventories
    "DPCERA3M086SBEA": ("Consumption & orders", 5, "Real consumption"), "UMCSENT": ("Consumption & orders", 2, "Consumer sentiment"),
    "AMDMNO": ("Consumption & orders", 5, "New orders, durable goods"), "AMDMUO": ("Consumption & orders", 5, "Unfilled orders, durable goods"),
    "BUSINV": ("Consumption & orders", 5, "Business inventories"), "ISRATIO": ("Consumption & orders", 2, "Inventory/sales ratio"),
    "TOTALSA": ("Consumption & orders", 5, "Vehicle sales"),
    # money and credit
    "M1SL": ("Money & credit", 6, "M1"), "M2SL": ("Money & credit", 6, "M2"), "M2REAL": ("Money & credit", 5, "Real M2"),
    "BOGMBASE": ("Money & credit", 6, "Monetary base"), "BUSLOANS": ("Money & credit", 6, "Business loans"),
    "REALLN": ("Money & credit", 6, "Real-estate loans"), "NONREVSL": ("Money & credit", 6, "Consumer credit (non-revolving)"),
    "TOTALSL": ("Money & credit", 6, "Consumer credit"),
    # interest rates and spreads (spreads built below)
    "FEDFUNDS": ("Rates & spreads", 2, "Fed funds"), "TB3MS": ("Rates & spreads", 2, "3-month bill"), "TB6MS": ("Rates & spreads", 2, "6-month bill"),
    "GS1": ("Rates & spreads", 2, "1-year Treasury"), "GS5": ("Rates & spreads", 2, "5-year Treasury"), "GS10": ("Rates & spreads", 2, "10-year Treasury"),
    "AAA": ("Rates & spreads", 2, "Aaa corporate"), "BAA": ("Rates & spreads", 2, "Baa corporate"),
    # exchange rates
    "EXSZUS": ("FX", 5, "Swiss franc per $"), "EXJPUS": ("FX", 5, "Yen per $"), "EXUSUK": ("FX", 5, "$ per £"), "EXCAUS": ("FX", 5, "C$ per $"),
    # prices
    "CPIAUCSL": ("Prices", 6, "CPI"), "CPILFESL": ("Prices", 6, "Core CPI"), "PCEPI": ("Prices", 6, "PCE prices"),
    "CPIAPPSL": ("Prices", 6, "CPI apparel"), "CPITRNSL": ("Prices", 6, "CPI transport"), "CPIMEDSL": ("Prices", 6, "CPI medical"),
    "CUSR0000SAC": ("Prices", 6, "CPI commodities"), "CUSR0000SAS": ("Prices", 6, "CPI services"), "WPSFD49207": ("Prices", 6, "PPI finished goods"),
    "WTISPLC": ("Prices", 6, "Oil price"),
}
# spreads over the funds rate (FRED-MD's style), in levels
SPREADS = {"GS10_FF": ("GS10", "FEDFUNDS"), "GS1_FF": ("GS1", "FEDFUNDS"), "TB3_FF": ("TB3MS", "FEDFUNDS"),
           "BAA_FF": ("BAA", "FEDFUNDS"), "AAA_FF": ("AAA", "FEDFUNDS"), "BAA_AAA": ("BAA", "AAA")}
GROUP_OF = {**{f"p_{k}": v[0] for k, v in SERIES.items()}, **{f"p_{k}": "Rates & spreads" for k in SPREADS}}
LABEL_OF = {**{f"p_{k}": v[2] for k, v in SERIES.items()},
            **{f"p_{k}": f"{SERIES[a][2]} − {SERIES[b][2]}" for k, (a, b) in SPREADS.items()}}


def transform(s, code: int):
    if code == 1:
        return s
    if code == 2:
        return s.diff()
    if code == 4:
        return np.log(s.where(s > 0))
    if code == 5:
        return np.log(s.where(s > 0)).diff() * 100
    if code == 6:
        return np.log(s.where(s > 0)).diff().diff() * 100
    raise ValueError(code)


def _build() -> Dict[str, Dict[str, float]]:
    import pandas as pd
    from api.models_ml.recession_ensemble import _fred
    f = _fred()
    raw: Dict[str, object] = {}
    for sid in SERIES:
        try:
            s = f.get_series(sid, observation_start="1959-01-01").dropna()
            s.index = pd.to_datetime(s.index)
            raw[sid] = s.resample("MS").mean()
        except Exception as e:                                          # noqa: BLE001 — a missing series is skipped
            logger.warning("[ml.panel] %s unavailable: %s", sid, e)
    out: Dict[str, Dict[str, float]] = {}
    for sid, (_, code, _) in SERIES.items():
        if sid in raw:
            v = transform(raw[sid], code).shift(1)                       # known at month m from data through m−1
            out[f"p_{sid}"] = {d.strftime("%Y-%m"): float(x) for d, x in v.dropna().items() if np.isfinite(x)}
    for k, (a, b) in SPREADS.items():
        if a in raw and b in raw:
            v = (raw[a] - raw[b]).shift(1)
            out[f"p_{k}"] = {d.strftime("%Y-%m"): float(x) for d, x in v.dropna().items() if np.isfinite(x)}
    return out


def load() -> Dict[str, Dict[str, float]]:
    from api import research_indicators as ri
    data, _ = ri._cached("ml_panel", _build)
    return data or {}


def groups(keys: List[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for k in keys:
        out[GROUP_OF.get(k, "Other")] = out.get(GROUP_OF.get(k, "Other"), 0) + 1
    return out
