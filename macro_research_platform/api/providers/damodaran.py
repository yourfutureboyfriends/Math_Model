"""
Aswath Damodaran's public valuation datasets (NYU Stern, free; updated each January, the
implied equity risk premium monthly). These are the inputs a careful DCF uses instead of
single-company estimates, which are noisy:

  implied ERP          ERPbymonth.xlsx — the premium the S&P 500's price implies today
  industry betas       betas / betaEurope / betaJapan / betaemerg / betaGlobal — unlevered,
                       corrected for cash; relevered with the firm's own debt-to-equity
  country risk         ctryprem.xls — sovereign default spread and the country risk premium
  industry margins     margin.xls / marginGlobal.xls — pre-tax operating margin
  sales-to-capital     capex.xls / capexGlobal.xls — revenue per unit of invested capital
  target leverage      wacc.xls / waccGlobal.xls — industry D/(D+E)

Files are cached on disk for 7 days (ERP: 1 day); a failed download falls back to the last
copy on disk, so a valuation never fails because NYU's site is slow.
"""
from __future__ import annotations

import logging
import threading
import time
import warnings
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

BASE = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/"
ERP_URL = "https://pages.stern.nyu.edu/~adamodar/pc/implprem/ERPbymonth.xlsx"
CACHE = Path(__file__).resolve().parents[2] / "data" / "processed" / "damodaran"
TTL = 7 * 86400
_lock = threading.Lock()
_mem: Dict[str, Any] = {}

# Yahoo industry → Damodaran industry (his 94 groupings).
YAHOO_TO_DAMODARAN: Dict[str, str] = {
    "Advertising Agencies": "Advertising", "Aerospace & Defense": "Aerospace/Defense", "Agricultural Inputs": "Chemical (Specialty)",
    "Airlines": "Air Transport", "Airports & Air Services": "Transportation", "Aluminum": "Metals & Mining",
    "Apparel Manufacturing": "Apparel", "Apparel Retail": "Retail (Special Lines)", "Asset Management": "Investments & Asset Management",
    "Auto & Truck Dealerships": "Retail (Automotive)", "Auto Manufacturers": "Auto & Truck", "Auto Parts": "Auto Parts",
    "Banks—Diversified": "Bank (Money Center)", "Banks—Regional": "Banks (Regional)", "Beverages—Brewers": "Beverage (Alcoholic)",
    "Beverages—Non-Alcoholic": "Beverage (Soft)", "Beverages—Wineries & Distilleries": "Beverage (Alcoholic)",
    "Biotechnology": "Drugs (Biotechnology)", "Broadcasting": "Broadcasting", "Building Materials": "Building Materials",
    "Building Products & Equipment": "Building Materials", "Business Equipment & Supplies": "Office Equipment & Services",
    "Capital Markets": "Brokerage & Investment Banking", "Chemicals": "Chemical (Diversified)", "Coking Coal": "Coal & Related Energy",
    "Communication Equipment": "Telecom. Equipment", "Computer Hardware": "Computers/Peripherals", "Confectioners": "Food Processing",
    "Conglomerates": "Diversified", "Consulting Services": "Business & Consumer Services", "Consumer Electronics": "Computers/Peripherals",
    "Copper": "Metals & Mining", "Credit Services": "Financial Svcs. (Non-bank & Insurance)", "Department Stores": "Retail (General)",
    "Diagnostics & Research": "Healthcare Products", "Discount Stores": "Retail (General)",
    "Drug Manufacturers—General": "Drugs (Pharmaceutical)", "Drug Manufacturers—Specialty & Generic": "Drugs (Pharmaceutical)",
    "Education & Training Services": "Education", "Electrical Equipment & Parts": "Electrical Equipment",
    "Electronic Components": "Electronics (General)", "Electronic Gaming & Multimedia": "Software (Entertainment)",
    "Electronics & Computer Distribution": "Retail (Distributors)", "Engineering & Construction": "Engineering/Construction",
    "Entertainment": "Entertainment", "Farm & Heavy Construction Machinery": "Machinery", "Farm Products": "Farming/Agriculture",
    "Financial Conglomerates": "Financial Svcs. (Non-bank & Insurance)", "Financial Data & Stock Exchanges": "Information Services",
    "Food Distribution": "Food Wholesalers", "Footwear & Accessories": "Shoe", "Furnishings, Fixtures & Appliances": "Furn/Home Furnishings",
    "Gambling": "Hotel/Gaming", "Gold": "Precious Metals", "Grocery Stores": "Retail (Grocery and Food)",
    "Health Information Services": "Heathcare Information and Technology", "Healthcare Plans": "Healthcare Support Services",
    "Home Improvement Retail": "Retail (Building Supply)", "Household & Personal Products": "Household Products",
    "Industrial Distribution": "Retail (Distributors)", "Information Technology Services": "Computer Services",
    "Infrastructure Operations": "Engineering/Construction", "Insurance Brokers": "Insurance (General)",
    "Insurance—Diversified": "Insurance (General)", "Insurance—Life": "Insurance (Life)", "Insurance—Property & Casualty": "Insurance (Prop/Cas.)",
    "Insurance—Reinsurance": "Reinsurance", "Insurance—Specialty": "Insurance (General)", "Integrated Freight & Logistics": "Transportation",
    "Internet Content & Information": "Software (Internet)", "Internet Retail": "Retail (General)", "Leisure": "Recreation",
    "Lodging": "Hotel/Gaming", "Lumber & Wood Production": "Paper/Forest Products", "Luxury Goods": "Apparel",
    "Marine Shipping": "Shipbuilding & Marine", "Medical Care Facilities": "Hospitals/Healthcare Facilities",
    "Medical Devices": "Healthcare Products", "Medical Distribution": "Healthcare Support Services",
    "Medical Instruments & Supplies": "Healthcare Products", "Metal Fabrication": "Steel", "Mortgage Finance": "Financial Svcs. (Non-bank & Insurance)",
    "Oil & Gas Drilling": "Oilfield Svcs/Equip.", "Oil & Gas E&P": "Oil/Gas (Production and Exploration)",
    "Oil & Gas Equipment & Services": "Oilfield Svcs/Equip.", "Oil & Gas Integrated": "Oil/Gas (Integrated)",
    "Oil & Gas Midstream": "Oil/Gas Distribution", "Oil & Gas Refining & Marketing": "Oil/Gas (Integrated)",
    "Other Industrial Metals & Mining": "Metals & Mining", "Other Precious Metals & Mining": "Precious Metals",
    "Packaged Foods": "Food Processing", "Packaging & Containers": "Packaging & Container", "Paper & Paper Products": "Paper/Forest Products",
    "Personal Services": "Business & Consumer Services", "Pharmaceutical Retailers": "Retail (Special Lines)",
    "Pollution & Treatment Controls": "Environmental & Waste Services", "Publishing": "Publishing & Newspapers",
    "REIT—Diversified": "R.E.I.T.", "REIT—Healthcare Facilities": "R.E.I.T.", "REIT—Hotel & Motel": "R.E.I.T.", "REIT—Industrial": "R.E.I.T.",
    "REIT—Mortgage": "R.E.I.T.", "REIT—Office": "R.E.I.T.", "REIT—Residential": "R.E.I.T.", "REIT—Retail": "Retail (REITs)",
    "REIT—Specialty": "R.E.I.T.", "Railroads": "Transportation (Railroads)", "Real Estate Services": "Real Estate (Operations & Services)",
    "Real Estate—Development": "Real Estate (Development)", "Real Estate—Diversified": "Real Estate (General/Diversified)",
    "Recreational Vehicles": "Recreation", "Rental & Leasing Services": "Business & Consumer Services",
    "Residential Construction": "Homebuilding", "Resorts & Casinos": "Hotel/Gaming", "Restaurants": "Restaurant/Dining",
    "Scientific & Technical Instruments": "Electronics (General)", "Security & Protection Services": "Business & Consumer Services",
    "Semiconductor Equipment & Materials": "Semiconductor Equip", "Semiconductors": "Semiconductor", "Shell Companies": "Diversified",
    "Silver": "Precious Metals", "Software—Application": "Software (System & Application)",
    "Software—Infrastructure": "Software (System & Application)", "Solar": "Green & Renewable Energy",
    "Specialty Business Services": "Business & Consumer Services", "Specialty Chemicals": "Chemical (Specialty)",
    "Specialty Industrial Machinery": "Machinery", "Specialty Retail": "Retail (Special Lines)",
    "Staffing & Employment Services": "Business & Consumer Services", "Steel": "Steel", "Telecom Services": "Telecom. Services",
    "Textile Manufacturing": "Apparel", "Thermal Coal": "Coal & Related Energy", "Tobacco": "Tobacco", "Tools & Accessories": "Machinery",
    "Travel Services": "Transportation", "Trucking": "Trucking", "Uranium": "Metals & Mining", "Utilities—Diversified": "Utility (General)",
    "Utilities—Independent Power Producers": "Power", "Utilities—Regulated Electric": "Utility (General)",
    "Utilities—Regulated Gas": "Utility (General)", "Utilities—Regulated Water": "Utility (Water)", "Utilities—Renewable": "Green & Renewable Energy",
    "Waste Management": "Environmental & Waste Services",
}

EUROPE = {"united kingdom", "germany", "france", "italy", "spain", "netherlands", "switzerland", "sweden", "norway", "denmark",
          "finland", "belgium", "austria", "ireland", "portugal", "luxembourg", "greece", "poland", "czech republic", "hungary"}
DEVELOPED_OTHER = {"canada", "australia", "new zealand", "singapore", "hong kong", "israel"}


def _norm_industry(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    n = name.replace(" - ", "—").strip()
    if n in YAHOO_TO_DAMODARAN:
        return YAHOO_TO_DAMODARAN[n]
    for k, v in YAHOO_TO_DAMODARAN.items():                 # tolerate dash / spacing variants
        if k.replace("—", "").replace(" ", "").lower() == n.replace("—", "").replace("-", "").replace(" ", "").lower():
            return v
    return None


def _download(name: str, url: str, ttl: float) -> Optional[Path]:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / name
    if path.exists() and time.time() - path.stat().st_mtime < ttl:
        return path
    try:
        import requests
        r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0 (research; macro terminal)"})
        r.raise_for_status()
        if len(r.content) < 5000:
            raise ValueError("file too small")
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(r.content)
        tmp.replace(path)
        return path
    except Exception as e:
        logger.warning("[damodaran] %s download failed (%s) — using the cached copy if any", name, e)
        return path if path.exists() else None


def _table(fname: str, header_label: str = "Industry Name", sheet: str = "Industry Averages"):
    """An industry table as {industry: {column: value}} (header row found by its label)."""
    key = f"t:{fname}"
    with _lock:
        if key in _mem and time.time() - _mem[key][0] < 3600:
            return _mem[key][1]
    path = _download(fname, BASE + fname, TTL)
    if path is None:
        return {}
    import pandas as pd
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = pd.read_excel(path, sheet_name=sheet, header=None)
    hdr = next((r for r in range(min(40, len(raw))) if str(raw.iloc[r, 0]).strip() == header_label), None)
    if hdr is None:
        return {}
    cols = [str(c).strip() for c in raw.iloc[hdr].tolist()]
    out: Dict[str, Dict[str, Any]] = {}
    for r in range(hdr + 1, len(raw)):
        name = raw.iloc[r, 0]
        if not isinstance(name, str) or not name.strip():
            continue
        out[name.strip()] = {c: raw.iloc[r, j] for j, c in enumerate(cols)}
    with _lock:
        _mem[key] = (time.time(), out)
    return out


def _num(v) -> Optional[float]:
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def implied_erp() -> Dict[str, Any]:
    """Damodaran's latest monthly implied ERP for the S&P 500 (mature-market premium)."""
    with _lock:
        if "erp" in _mem and time.time() - _mem["erp"][0] < 3600:
            return _mem["erp"][1]
    out = {"erp": None, "as_of": None, "tbond": None, "source": None}
    path = _download("ERPbymonth.xlsx", ERP_URL, 86400)
    if path is not None:
        try:
            import pandas as pd
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                df = pd.read_excel(path, sheet_name="Last 12 months data")
            df = df.dropna(subset=["Date", "ERP"])
            last = df.iloc[-1]
            out = {"erp": float(last["ERP"]), "as_of": str(pd.Timestamp(last["Date"]).date()),
                   "tbond": _num(last.get("10-year US Treasury")),
                   "source": f"Damodaran implied ERP for the S&P 500, {pd.Timestamp(last['Date']):%b %Y}"}
        except Exception as e:
            logger.warning("[damodaran] ERP parse failed: %s", e)
    with _lock:
        _mem["erp"] = (time.time(), out)
    return out


def _region_files(country: Optional[str]) -> Dict[str, str]:
    c = (country or "").strip().lower()
    if c in ("united states", "usa", "us", ""):
        return {"beta": "betas.xls", "margin": "margin.xls", "capex": "capex.xls", "wacc": "wacc.xls", "region": "US"}
    beta = ("betaEurope.xls" if c in EUROPE else "betaJapan.xls" if c == "japan"
            else "betaGlobal.xls" if c in DEVELOPED_OTHER else "betaemerg.xls")
    region = "Europe" if c in EUROPE else "Japan" if c == "japan" else "Global" if c in DEVELOPED_OTHER else "Emerging markets"
    return {"beta": beta, "margin": "marginGlobal.xls", "capex": "capexGlobal.xls", "wacc": "waccGlobal.xls", "region": region}


def industry(yahoo_industry: Optional[str], country: Optional[str]) -> Dict[str, Any]:
    """Industry benchmarks for a company: unlevered beta, operating margin, sales-to-capital,
    D/(D+E), from the regional file that matches the company's home market."""
    dname = _norm_industry(yahoo_industry)
    files = _region_files(country)
    out: Dict[str, Any] = {"industry": dname, "region": files["region"], "unlevered_beta": None, "levered_beta": None, "margin": None,
                           "sales_to_capital": None, "debt_ratio": None, "firms": None}
    if not dname:
        return out
    try:
        b = _table(files["beta"]).get(dname) or {}
        out["unlevered_beta"] = _num(b.get("Unlevered beta corrected for cash"))
        out["levered_beta"] = _num(b.get("Beta"))
        out["firms"] = _num(b.get("Number of firms"))
        m = _table(files["margin"]).get(dname) or {}
        out["margin"] = _num(m.get("Pre-tax Unadjusted Operating Margin"))
        cx = _table(files["capex"]).get(dname) or {}
        out["sales_to_capital"] = _num(cx.get("Sales/ Invested Capital (LTM)"))
        w = _table(files["wacc"]).get(dname) or {}
        out["debt_ratio"] = _num(w.get("D/(D+E)"))
        out["source"] = f"Damodaran {files['region']} industry data — {dname}"
    except Exception as e:
        logger.warning("[damodaran] industry lookup failed: %s", e)
    return out


def country_risk(country: Optional[str]) -> Dict[str, Any]:
    """Country risk premium and sovereign default spread for a company's home country."""
    out = {"country": country, "crp": 0.0, "default_spread": 0.0, "rating": None}
    if not country:
        return out
    key = "ctry"
    with _lock:
        cached = _mem.get(key)
    if not cached or time.time() - cached[0] > 3600:
        path = _download("ctryprem.xls", BASE + "ctryprem.xls", TTL)
        table: Dict[str, Dict[str, Any]] = {}
        if path is not None:
            try:
                import pandas as pd
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    raw = pd.read_excel(path, sheet_name="ERPs by country", header=None)
                hdr = next(r for r in range(30) if str(raw.iloc[r, 0]).strip() == "Country")
                for r in range(hdr + 1, len(raw)):
                    n = raw.iloc[r, 0]
                    if isinstance(n, str) and n.strip():
                        table[n.strip().lower()] = {"rating": raw.iloc[r, 2], "default_spread": _num(raw.iloc[r, 3]),
                                                    "crp": _num(raw.iloc[r, 5])}
            except Exception as e:
                logger.warning("[damodaran] country table parse failed: %s", e)
        cached = (time.time(), table)
        with _lock:
            _mem[key] = cached
    alias = {"usa": "united states", "uk": "united kingdom", "south korea": "korea", "czechia": "czech republic"}
    c = country.strip().lower()
    row = cached[1].get(alias.get(c, c))
    if row:
        out.update({"crp": row["crp"] or 0.0, "default_spread": row["default_spread"] or 0.0,
                    "rating": row["rating"] if isinstance(row["rating"], str) else None})
    return out
