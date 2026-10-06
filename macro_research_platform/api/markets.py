"""
Market reference data: every equity market the platform can screen or analyse.

For each country: MSCI market classification (Developed / Emerging / Frontier / Standalone,
per MSCI's Global Market Accessibility & Annual Market Classification Review), region,
Yahoo screener region code and primary exchange codes, ticker suffixes (to classify any
symbol, e.g. from a search or a position), home benchmark index and quote currency.

Quote units: some exchanges quote in minor units (London in pence 'GBp', Johannesburg in
cents 'ZAc', Tel Aviv in agorot 'ILA'); `minor_unit_factor` converts them to the major
currency before any FX conversion.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

DM, EM, FM, SA = "Developed", "Emerging", "Frontier", "Standalone"
AMERICAS, EUROPE, APAC, MEA = "Americas", "Europe", "Asia-Pacific", "Middle East & Africa"

# code: name, MSCI class, region, Yahoo screener region, primary exchange codes, ticker
# suffixes, benchmark (Yahoo), currency, target universe size (largest N by market cap)
COUNTRIES: Dict[str, Dict[str, Any]] = {
    # ── Developed ────────────────────────────────────────────────────────────
    "US": {"name": "United States", "msci": DM, "region": AMERICAS, "yr": "us",
           "exch": ["NMS", "NYQ", "NGM", "NCM", "ASE"], "sfx": [""], "bench": "^GSPC", "ccy": "USD", "n": 700},
    "CA": {"name": "Canada", "msci": DM, "region": AMERICAS, "yr": "ca", "exch": ["TOR"],
           "sfx": [".TO", ".V", ".NE", ".CN"], "bench": "^GSPTSE", "ccy": "CAD", "n": 150},
    "GB": {"name": "United Kingdom", "msci": DM, "region": EUROPE, "yr": "gb", "exch": ["LSE"],
           "sfx": [".L", ".IL"], "bench": "^FTSE", "ccy": "GBP", "n": 150},
    "IE": {"name": "Ireland", "msci": DM, "region": EUROPE, "yr": "ie", "exch": ["ISE"],
           "sfx": [".IR"], "bench": "^ISEQ", "ccy": "EUR", "n": 15},
    "DE": {"name": "Germany", "msci": DM, "region": EUROPE, "yr": "de", "exch": ["GER"],
           "sfx": [".DE", ".F", ".BE", ".DU", ".HM", ".MU", ".HA", ".SG"], "bench": "^GDAXI", "ccy": "EUR", "n": 100},
    "FR": {"name": "France", "msci": DM, "region": EUROPE, "yr": "fr", "exch": ["PAR"],
           "sfx": [".PA"], "bench": "^FCHI", "ccy": "EUR", "n": 90},
    "NL": {"name": "Netherlands", "msci": DM, "region": EUROPE, "yr": "nl", "exch": ["AMS"],
           "sfx": [".AS"], "bench": "^AEX", "ccy": "EUR", "n": 40},
    "BE": {"name": "Belgium", "msci": DM, "region": EUROPE, "yr": "be", "exch": ["BRU"],
           "sfx": [".BR"], "bench": "^BFX", "ccy": "EUR", "n": 25},
    "AT": {"name": "Austria", "msci": DM, "region": EUROPE, "yr": "at", "exch": ["VIE"],
           "sfx": [".VI"], "bench": "^ATX", "ccy": "EUR", "n": 20},
    "CH": {"name": "Switzerland", "msci": DM, "region": EUROPE, "yr": "ch", "exch": ["EBS"],
           "sfx": [".SW"], "bench": "^SSMI", "ccy": "CHF", "n": 60},
    "IT": {"name": "Italy", "msci": DM, "region": EUROPE, "yr": "it", "exch": ["MIL"],
           "sfx": [".MI"], "bench": "FTSEMIB.MI", "ccy": "EUR", "n": 60},
    "ES": {"name": "Spain", "msci": DM, "region": EUROPE, "yr": "es", "exch": ["MCE"],
           "sfx": [".MC"], "bench": "^IBEX", "ccy": "EUR", "n": 40},
    "PT": {"name": "Portugal", "msci": DM, "region": EUROPE, "yr": "pt", "exch": ["LIS"],
           "sfx": [".LS"], "bench": "PSI20.LS", "ccy": "EUR", "n": 12},
    "SE": {"name": "Sweden", "msci": DM, "region": EUROPE, "yr": "se", "exch": ["STO"],
           "sfx": [".ST"], "bench": "^OMX", "ccy": "SEK", "n": 60},
    "NO": {"name": "Norway", "msci": DM, "region": EUROPE, "yr": "no", "exch": ["OSL"],
           "sfx": [".OL"], "bench": "OSEBX.OL", "ccy": "NOK", "n": 30},
    "DK": {"name": "Denmark", "msci": DM, "region": EUROPE, "yr": "dk", "exch": ["CPH"],
           "sfx": [".CO"], "bench": "^OMXC25", "ccy": "DKK", "n": 30},
    "FI": {"name": "Finland", "msci": DM, "region": EUROPE, "yr": "fi", "exch": ["HEL"],
           "sfx": [".HE"], "bench": "^OMXH25", "ccy": "EUR", "n": 25},
    "IL": {"name": "Israel", "msci": DM, "region": MEA, "yr": "il", "exch": ["TLV"],
           "sfx": [".TA"], "bench": "TA35.TA", "ccy": "ILS", "n": 30},
    "JP": {"name": "Japan", "msci": DM, "region": APAC, "yr": "jp", "exch": ["JPX"],
           "sfx": [".T"], "bench": "^N225", "ccy": "JPY", "n": 250},
    "AU": {"name": "Australia", "msci": DM, "region": APAC, "yr": "au", "exch": ["ASX"],
           "sfx": [".AX"], "bench": "^AXJO", "ccy": "AUD", "n": 100},
    "NZ": {"name": "New Zealand", "msci": DM, "region": APAC, "yr": "nz", "exch": ["NZE"],
           "sfx": [".NZ"], "bench": "^NZ50", "ccy": "NZD", "n": 15},
    "HK": {"name": "Hong Kong", "msci": DM, "region": APAC, "yr": "hk", "exch": ["HKG"],
           "sfx": [".HK"], "bench": "^HSI", "ccy": "HKD", "n": 120},
    "SG": {"name": "Singapore", "msci": DM, "region": APAC, "yr": "sg", "exch": ["SES"],
           "sfx": [".SI"], "bench": "^STI", "ccy": "SGD", "n": 30},
    # ── Emerging ─────────────────────────────────────────────────────────────
    "CN": {"name": "China (A-shares)", "msci": EM, "region": APAC, "yr": "cn", "exch": ["SHH", "SHZ"],
           "sfx": [".SS", ".SZ"], "bench": "000001.SS", "ccy": "CNY", "n": 200},
    "IN": {"name": "India", "msci": EM, "region": APAC, "yr": "in", "exch": ["NSI", "BSE"],
           "sfx": [".NS", ".BO"], "bench": "^NSEI", "ccy": "INR", "n": 150},
    "KR": {"name": "South Korea", "msci": EM, "region": APAC, "yr": "kr", "exch": ["KSC", "KOE"],
           "sfx": [".KS", ".KQ"], "bench": "^KS11", "ccy": "KRW", "n": 100},
    "TW": {"name": "Taiwan", "msci": EM, "region": APAC, "yr": "tw", "exch": ["TAI", "TWO"],
           "sfx": [".TW", ".TWO"], "bench": "^TWII", "ccy": "TWD", "n": 100},
    "ID": {"name": "Indonesia", "msci": EM, "region": APAC, "yr": "id", "exch": ["JKT"],
           "sfx": [".JK"], "bench": "^JKSE", "ccy": "IDR", "n": 30},
    "MY": {"name": "Malaysia", "msci": EM, "region": APAC, "yr": "my", "exch": ["KLS"],
           "sfx": [".KL"], "bench": "^KLSE", "ccy": "MYR", "n": 30},
    "TH": {"name": "Thailand", "msci": EM, "region": APAC, "yr": "th", "exch": ["SET"],
           "sfx": [".BK"], "bench": None, "ccy": "THB", "n": 30},
    "PH": {"name": "Philippines", "msci": EM, "region": APAC, "yr": "ph", "exch": ["PHS"],
           "sfx": [".PS"], "bench": None, "ccy": "PHP", "n": 15},
    "BR": {"name": "Brazil", "msci": EM, "region": AMERICAS, "yr": "br", "exch": ["SAO"],
           "sfx": [".SA"], "bench": "^BVSP", "ccy": "BRL", "n": 60},
    "MX": {"name": "Mexico", "msci": EM, "region": AMERICAS, "yr": "mx", "exch": ["MEX"],
           "sfx": [".MX"], "bench": "^MXX", "ccy": "MXN", "n": 30},
    "CL": {"name": "Chile", "msci": EM, "region": AMERICAS, "yr": "cl", "exch": ["SGO"],
           "sfx": [".SN"], "bench": None, "ccy": "CLP", "n": 15},
    "ZA": {"name": "South Africa", "msci": EM, "region": MEA, "yr": "za", "exch": ["JNB"],
           "sfx": [".JO"], "bench": "^J203.JO", "ccy": "ZAR", "n": 40},
    "SA": {"name": "Saudi Arabia", "msci": EM, "region": MEA, "yr": "sa", "exch": ["SAU"],
           "sfx": [".SR"], "bench": None, "ccy": "SAR", "n": 40},
    "QA": {"name": "Qatar", "msci": EM, "region": MEA, "yr": "qa", "exch": ["DOH"],
           "sfx": [".QA"], "bench": None, "ccy": "QAR", "n": 12},
    "KW": {"name": "Kuwait", "msci": EM, "region": MEA, "yr": "kw", "exch": ["KUW"],
           "sfx": [".KW"], "bench": None, "ccy": "KWD", "n": 12},
    "TR": {"name": "Turkey", "msci": EM, "region": EUROPE, "yr": "tr", "exch": ["IST"],
           "sfx": [".IS"], "bench": "XU100.IS", "ccy": "TRY", "n": 30},
    "PL": {"name": "Poland", "msci": EM, "region": EUROPE, "yr": "pl", "exch": ["WSE"],
           "sfx": [".WA"], "bench": None, "ccy": "PLN", "n": 25},
    "CZ": {"name": "Czech Republic", "msci": EM, "region": EUROPE, "yr": "cz", "exch": ["PRA"],
           "sfx": [".PR"], "bench": None, "ccy": "CZK", "n": 5},
    "HU": {"name": "Hungary", "msci": EM, "region": EUROPE, "yr": "hu", "exch": ["BUD"],
           "sfx": [".BD"], "bench": None, "ccy": "HUF", "n": 5},
    "GR": {"name": "Greece", "msci": EM, "region": EUROPE, "yr": "gr", "exch": ["ATH"],
           "sfx": [".AT"], "bench": None, "ccy": "EUR", "n": 15},
    "EG": {"name": "Egypt", "msci": EM, "region": MEA, "yr": "eg", "exch": ["CAI"],
           "sfx": [".CA"], "bench": None, "ccy": "EGP", "n": 10},
    # ── Frontier / standalone ────────────────────────────────────────────────
    "RO": {"name": "Romania", "msci": FM, "region": EUROPE, "yr": "ro", "exch": ["BVB"],
           "sfx": [".RO"], "bench": None, "ccy": "RON", "n": 10},
    "IS": {"name": "Iceland", "msci": FM, "region": EUROPE, "yr": "is", "exch": ["ICE"],
           "sfx": [".IC"], "bench": None, "ccy": "ISK", "n": 8},
    "EE": {"name": "Estonia", "msci": FM, "region": EUROPE, "yr": "ee", "exch": ["TAL"],
           "sfx": [".TL"], "bench": None, "ccy": "EUR", "n": 5},
    "LT": {"name": "Lithuania", "msci": FM, "region": EUROPE, "yr": "lt", "exch": ["LIT"],
           "sfx": [".VS"], "bench": None, "ccy": "EUR", "n": 5},
    "VN": {"name": "Vietnam", "msci": FM, "region": APAC, "yr": None, "exch": [],
           "sfx": [".VN"], "bench": None, "ccy": "VND", "n": 0},
    "AR": {"name": "Argentina", "msci": SA, "region": AMERICAS, "yr": "ar", "exch": ["BUE"],
           "sfx": [".BA"], "bench": "^MERV", "ccy": "ARS", "n": 15},
}

# Minor-unit quote currencies (Yahoo codes) → (major currency, divisor)
MINOR_UNITS = {"GBp": ("GBP", 100.0), "GBX": ("GBP", 100.0), "ZAc": ("ZAR", 100.0), "ILA": ("ILS", 100.0)}

_SUFFIX = sorted(((s, c) for c, m in COUNTRIES.items() for s in m["sfx"] if s), key=lambda x: -len(x[0]))


GLOBAL_BENCHMARK = "ACWI"   # MSCI ACWI ETF — regime filter where no home index is available


def benchmark_of(country: str) -> str:
    return (COUNTRIES.get(country) or {}).get("bench") or GLOBAL_BENCHMARK


def country_of(symbol: str) -> str:
    """Country code from a Yahoo ticker suffix ('' / unknown suffix → US)."""
    s = (symbol or "").upper()
    for sfx, c in _SUFFIX:
        if s.endswith(sfx.upper()):
            return c
    return "US"


def classify(symbol: str, country: Optional[str] = None) -> Dict[str, Any]:
    c = country or country_of(symbol)
    m = COUNTRIES.get(c, {})
    return {"country": c, "country_name": m.get("name", c), "market_class": m.get("msci", "Unclassified"),
            "region": m.get("region", "Other"), "benchmark": m.get("bench"), "home_currency": m.get("ccy")}


def minor_unit_factor(quote_ccy: Optional[str]) -> tuple:
    """(major currency, divisor) for a quote currency; minor units → (major, 100)."""
    if quote_ccy in MINOR_UNITS:
        return MINOR_UNITS[quote_ccy]
    return (quote_ccy or "USD", 1.0)


def fx_ticker(ccy: str) -> Optional[str]:
    """Yahoo ticker giving units of `ccy` per 1 USD (None for USD)."""
    return None if ccy == "USD" else f"{ccy}=X"
