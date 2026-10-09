"""
Country reference table (ISO 3166-1 alpha-2 / alpha-3 / numeric, ISO 4217 currency) and the
world-map data built on it: every country gets markets (country ETF, main index, currency,
10-year yield), economy (IMF World Economic Outlook) and risk (Damodaran sovereign rating,
country risk premium) — all free sources.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# alpha2, alpha3, numeric, currency, name
_ROWS = """AF AFG 004 AFN Afghanistan|AL ALB 008 ALL Albania|DZ DZA 012 DZD Algeria|AO AGO 024 AOA Angola|AR ARG 032 ARS Argentina
AM ARM 051 AMD Armenia|AU AUS 036 AUD Australia|AT AUT 040 EUR Austria|AZ AZE 031 AZN Azerbaijan|BS BHS 044 BSD Bahamas
BH BHR 048 BHD Bahrain|BD BGD 050 BDT Bangladesh|BY BLR 112 BYN Belarus|BE BEL 056 EUR Belgium|BZ BLZ 084 BZD Belize
BJ BEN 204 XOF Benin|BT BTN 064 BTN Bhutan|BO BOL 068 BOB Bolivia|BA BIH 070 BAM Bosnia and Herzegovina|BW BWA 072 BWP Botswana
BR BRA 076 BRL Brazil|BN BRN 096 BND Brunei|BG BGR 100 BGN Bulgaria|BF BFA 854 XOF Burkina Faso|BI BDI 108 BIF Burundi
KH KHM 116 KHR Cambodia|CM CMR 120 XAF Cameroon|CA CAN 124 CAD Canada|CF CAF 140 XAF Central African Republic|TD TCD 148 XAF Chad
CL CHL 152 CLP Chile|CN CHN 156 CNY China|CO COL 170 COP Colombia|CG COG 178 XAF Congo|CD COD 180 CDF DR Congo
CR CRI 188 CRC Costa Rica|CI CIV 384 XOF Côte d'Ivoire|HR HRV 191 EUR Croatia|CU CUB 192 CUP Cuba|CY CYP 196 EUR Cyprus
CZ CZE 203 CZK Czechia|DK DNK 208 DKK Denmark|DJ DJI 262 DJF Djibouti|DO DOM 214 DOP Dominican Republic|EC ECU 218 USD Ecuador
EG EGY 818 EGP Egypt|SV SLV 222 USD El Salvador|GQ GNQ 226 XAF Equatorial Guinea|ER ERI 232 ERN Eritrea|EE EST 233 EUR Estonia
SZ SWZ 748 SZL Eswatini|ET ETH 231 ETB Ethiopia|FJ FJI 242 FJD Fiji|FI FIN 246 EUR Finland|FR FRA 250 EUR France
GA GAB 266 XAF Gabon|GM GMB 270 GMD Gambia|GE GEO 268 GEL Georgia|DE DEU 276 EUR Germany|GH GHA 288 GHS Ghana
GR GRC 300 EUR Greece|GL GRL 304 DKK Greenland|GT GTM 320 GTQ Guatemala|GN GIN 324 GNF Guinea|GW GNB 624 XOF Guinea-Bissau
GY GUY 328 GYD Guyana|HT HTI 332 HTG Haiti|HN HND 340 HNL Honduras|HK HKG 344 HKD Hong Kong|HU HUN 348 HUF Hungary
IS ISL 352 ISK Iceland|IN IND 356 INR India|ID IDN 360 IDR Indonesia|IR IRN 364 IRR Iran|IQ IRQ 368 IQD Iraq
IE IRL 372 EUR Ireland|IL ISR 376 ILS Israel|IT ITA 380 EUR Italy|JM JAM 388 JMD Jamaica|JP JPN 392 JPY Japan
JO JOR 400 JOD Jordan|KZ KAZ 398 KZT Kazakhstan|KE KEN 404 KES Kenya|KP PRK 408 KPW North Korea|KR KOR 410 KRW South Korea
XK XKX 412 EUR Kosovo|KW KWT 414 KWD Kuwait|KG KGZ 417 KGS Kyrgyzstan|LA LAO 418 LAK Laos|LV LVA 428 EUR Latvia
LB LBN 422 LBP Lebanon|LS LSO 426 LSL Lesotho|LR LBR 430 LRD Liberia|LY LBY 434 LYD Libya|LT LTU 440 EUR Lithuania
LU LUX 442 EUR Luxembourg|MO MAC 446 MOP Macao|MG MDG 450 MGA Madagascar|MW MWI 454 MWK Malawi|MY MYS 458 MYR Malaysia
ML MLI 466 XOF Mali|MT MLT 470 EUR Malta|MR MRT 478 MRU Mauritania|MU MUS 480 MUR Mauritius|MX MEX 484 MXN Mexico
MD MDA 498 MDL Moldova|MN MNG 496 MNT Mongolia|ME MNE 499 EUR Montenegro|MA MAR 504 MAD Morocco|MZ MOZ 508 MZN Mozambique
MM MMR 104 MMK Myanmar|NA NAM 516 NAD Namibia|NP NPL 524 NPR Nepal|NL NLD 528 EUR Netherlands|NZ NZL 554 NZD New Zealand
NI NIC 558 NIO Nicaragua|NE NER 562 XOF Niger|NG NGA 566 NGN Nigeria|MK MKD 807 MKD North Macedonia|NO NOR 578 NOK Norway
OM OMN 512 OMR Oman|PK PAK 586 PKR Pakistan|PS PSE 275 ILS Palestine|PA PAN 591 PAB Panama|PG PNG 598 PGK Papua New Guinea
PY PRY 600 PYG Paraguay|PE PER 604 PEN Peru|PH PHL 608 PHP Philippines|PL POL 616 PLN Poland|PT PRT 620 EUR Portugal
PR PRI 630 USD Puerto Rico|QA QAT 634 QAR Qatar|RO ROU 642 RON Romania|RU RUS 643 RUB Russia|RW RWA 646 RWF Rwanda
SA SAU 682 SAR Saudi Arabia|SN SEN 686 XOF Senegal|RS SRB 688 RSD Serbia|SL SLE 694 SLE Sierra Leone|SG SGP 702 SGD Singapore
SK SVK 703 EUR Slovakia|SI SVN 705 EUR Slovenia|SB SLB 090 SBD Solomon Islands|SO SOM 706 SOS Somalia|ZA ZAF 710 ZAR South Africa
SS SSD 728 SSP South Sudan|ES ESP 724 EUR Spain|LK LKA 144 LKR Sri Lanka|SD SDN 729 SDG Sudan|SR SUR 740 SRD Suriname
SE SWE 752 SEK Sweden|CH CHE 756 CHF Switzerland|SY SYR 760 SYP Syria|TW TWN 158 TWD Taiwan|TJ TJK 762 TJS Tajikistan
TZ TZA 834 TZS Tanzania|TH THA 764 THB Thailand|TL TLS 626 USD Timor-Leste|TG TGO 768 XOF Togo|TT TTO 780 TTD Trinidad and Tobago
TN TUN 788 TND Tunisia|TR TUR 792 TRY Turkey|TM TKM 795 TMT Turkmenistan|UG UGA 800 UGX Uganda|UA UKR 804 UAH Ukraine
AE ARE 784 AED United Arab Emirates|GB GBR 826 GBP United Kingdom|US USA 840 USD United States|UY URY 858 UYU Uruguay
UZ UZB 860 UZS Uzbekistan|VU VUT 548 VUV Vanuatu|VE VEN 862 VES Venezuela|VN VNM 704 VND Vietnam|EH ESH 732 MAD Western Sahara
YE YEM 887 YER Yemen|ZM ZMB 894 ZMW Zambia|ZW ZWE 716 ZWG Zimbabwe|NC NCL 540 XPF New Caledonia|FK FLK 238 FKP Falkland Islands
GF GUF 254 EUR French Guiana|TF ATF 260 EUR French Southern Territories|AQ ATA 010 USD Antarctica|CV CPV 132 CVE Cabo Verde
KM COM 174 KMF Comoros|ST STP 678 STN São Tomé and Príncipe|SC SYC 690 SCR Seychelles|MV MDV 462 MVR Maldives|BB BRB 052 BBD Barbados
"""
COUNTRIES: List[Dict[str, str]] = []
for chunk in _ROWS.replace("\n", "|").split("|"):
    parts = chunk.strip().split(" ", 4)
    if len(parts) == 5:
        a2, a3, num, ccy, name = parts
        COUNTRIES.append({"iso2": a2, "iso3": a3, "numeric": num, "currency": ccy, "name": name})
BY_ISO2 = {c["iso2"]: c for c in COUNTRIES}
ISO3_TO_ISO2 = {c["iso3"]: c["iso2"] for c in COUNTRIES}
NUMERIC_TO_ISO2 = {c["numeric"]: c["iso2"] for c in COUNTRIES}

# Main local equity index per market (Yahoo symbols)
MAIN_INDEX: Dict[str, Tuple[str, str]] = {
    "US": ("^GSPC", "S&P 500"), "CA": ("^GSPTSE", "S&P/TSX"), "MX": ("^MXX", "IPC Mexico"), "BR": ("^BVSP", "Ibovespa"),
    "AR": ("^MERV", "Merval"), "CL": ("^IPSA", "S&P IPSA"), "GB": ("^FTSE", "FTSE 100"), "DE": ("^GDAXI", "DAX"), "FR": ("^FCHI", "CAC 40"),
    "IT": ("FTSEMIB.MI", "FTSE MIB"), "ES": ("^IBEX", "IBEX 35"), "NL": ("^AEX", "AEX"), "CH": ("^SSMI", "SMI"), "SE": ("^OMX", "OMX Stockholm 30"),
    "NO": ("OBX.OL", "OBX"), "DK": ("^OMXC25", "OMX Copenhagen 25"), "FI": ("^OMXH25", "OMX Helsinki 25"), "BE": ("^BFX", "BEL 20"),
    "AT": ("^ATX", "ATX"), "IE": ("^ISEQ", "ISEQ Overall"), "PT": ("PSI20.LS", "PSI"), "GR": ("GD.AT", "Athens General"),
    "PL": ("WIG20.WA", "WIG20"), "TR": ("XU100.IS", "BIST 100"), "IL": ("^TA125.TA", "TA-125"), "SA": ("^TASI.SR", "Tadawul All Share"),
    "ZA": ("^J203.JO", "JSE All Share"), "EG": ("^CASE30", "EGX 30"), "IN": ("^NSEI", "Nifty 50"), "CN": ("000001.SS", "Shanghai Composite"),
    "HK": ("^HSI", "Hang Seng"), "TW": ("^TWII", "TAIEX"), "KR": ("^KS11", "KOSPI"), "JP": ("^N225", "Nikkei 225"), "SG": ("^STI", "Straits Times"),
    "MY": ("^KLSE", "FTSE Bursa Malaysia KLCI"), "TH": ("^SET.BK", "SET"), "ID": ("^JKSE", "Jakarta Composite"), "PH": ("PSEI.PS", "PSEi"),
    "AU": ("^AXJO", "S&P/ASX 200"), "NZ": ("^NZ50", "S&P/NZX 50"), "VN": ("^VNINDEX.VN", "VN-Index"),
}
# OECD 10-year government yields on FRED (monthly)
YIELD_SERIES: Dict[str, str] = {c: f"IRLTLT01{c}M156N" for c in (
    "AU AT BE CA CL CZ DK FI FR DE GR HU IS IE IL IT JP KR LU MX NL NZ NO PL PT SK SI ES SE CH GB US ZA CO IN".split())}
IMF_INDICATORS = {"gdp_growth": "NGDP_RPCH", "inflation": "PCPIPCH", "unemployment": "LUR", "gov_debt": "GGXWDG_NGDP",
                  "current_account": "BCA_NGDPD", "gdp_per_capita": "NGDPDPC"}


def _imf(year: int) -> Dict[str, Dict[str, Optional[float]]]:
    """IMF World Economic Outlook values for `year` (and the next year for GDP growth / inflation)."""
    import requests
    out: Dict[str, Dict[str, Optional[float]]] = {}

    def one(item):
        key, code = item
        try:
            r = requests.get(f"https://www.imf.org/external/datamapper/api/v1/{code}", params={"periods": f"{year},{year + 1}"}, timeout=30)
            r.raise_for_status()
            return key, (r.json().get("values") or {}).get(code) or {}
        except Exception as e:
            logger.warning("[worldmap] IMF %s failed: %s", code, e)
            return key, {}
    with ThreadPoolExecutor(6) as ex:
        for key, vals in ex.map(one, IMF_INDICATORS.items()):
            for iso3, series in vals.items():
                iso2 = ISO3_TO_ISO2.get(iso3)
                if not iso2:
                    continue
                rec = out.setdefault(iso2, {})
                rec[key] = series.get(str(year))
                if key in ("gdp_growth", "inflation"):
                    rec[key + "_next"] = series.get(str(year + 1))
    return out


def _closes(symbols: List[str], period: str = "13mo"):
    import yfinance as yf
    try:
        return yf.download(symbols, period=period, interval="1d", auto_adjust=True, group_by="ticker", progress=False, threads=True)
    except Exception as e:
        logger.warning("[worldmap] price download failed: %s", e)
        return None


def _moves(df, sym: str) -> Optional[Dict[str, Any]]:
    try:
        c = df[sym]["Close"].dropna()
    except Exception:
        return None
    if len(c) < 30:
        return None
    last = float(c.iloc[-1])
    prior_year = c[c.index.year < c.index[-1].year]
    return {"price": last, "date": c.index[-1].strftime("%Y-%m-%d"), "change_1d": last / float(c.iloc[-2]) - 1,
            "change_1m": last / float(c.iloc[-22]) - 1 if len(c) > 22 else None,
            "change_ytd": last / float(prior_year.iloc[-1]) - 1 if len(prior_year) else None,
            "change_1y": last / float(c.iloc[-253]) - 1 if len(c) > 253 else None}


def _yields() -> Dict[str, Dict[str, Any]]:
    from api.providers.fred_provider import FREDProvider
    fp = FREDProvider()
    out: Dict[str, Dict[str, Any]] = {}

    def one(item):
        iso, sid = item
        try:
            obs = [o for o in (fp.fetch_series(sid).data or []) if o.value is not None]
            if not obs:
                return iso, None
            import pandas as pd
            when = lambda o: pd.Timestamp(str(o.date)[:10])
            prev = next((o for o in reversed(obs[:-1]) if (when(obs[-1]) - when(o)).days >= 360), None)
            return iso, {"yield_10y": obs[-1].value, "yield_date": str(obs[-1].date)[:10], "yield_source": "OECD monthly",
                         "yield_change_1y_bp": (obs[-1].value - prev.value) * 100 if prev else None}
        except Exception:
            return iso, None
    with ThreadPoolExecutor(4) as ex:
        for iso, rec in ex.map(one, YIELD_SERIES.items()):
            if rec:
                out[iso] = rec
    return out


def world_data() -> Dict[str, Any]:
    """Everything the world map shows, keyed by ISO alpha-2."""
    from api.marketdata.core import _cached
    from api.marketdata.monitors import COUNTRY_ETFS
    year = date.today().year

    def slow():          # IMF, yields and risk change at most daily
        from api.providers import damodaran
        imf = _imf(year)
        ylds = _yields()
        try:                                     # the US 10-year live rather than the monthly average
            from api.marketdata.core import quote
            tnx = quote("^TNX")["price"]
            if tnx:
                ylds.setdefault("US", {}).update({"yield_10y": round(tnx, 3), "yield_date": str(date.today()), "yield_source": "^TNX live"})
        except Exception:
            pass
        risk: Dict[str, Dict[str, Any]] = {}
        for c in COUNTRIES:
            r = damodaran.country_risk(c["name"])
            if r.get("rating") or r.get("crp"):
                risk[c["iso2"]] = {"rating": r.get("rating"), "crp": r.get("crp"), "default_spread": r.get("default_spread")}
        erp = damodaran.implied_erp().get("erp")
        return {"imf": imf, "yields": ylds, "risk": risk, "mature_erp": erp}

    def fast():          # prices: every 10 minutes
        etf_syms = sorted({v[0] for v in COUNTRY_ETFS.values()})
        idx_syms = sorted({v[0] for v in MAIN_INDEX.values()})
        ccys = sorted({c["currency"] for c in COUNTRIES if c["currency"] not in ("USD",)})
        fx_syms = [f"{c}=X" for c in ccys]
        df = _closes(etf_syms + idx_syms + fx_syms)
        etf, idx, fx = {}, {}, {}
        if df is not None:
            for iso, (sym, label) in COUNTRY_ETFS.items():
                m = _moves(df, sym)
                if m:
                    etf[iso] = {"etf": sym, "label": label, **m}
            for iso, (sym, label) in MAIN_INDEX.items():
                m = _moves(df, sym)
                if m:
                    idx[iso] = {"symbol": sym, "label": label, **m}
            for ccy in ccys:
                m = _moves(df, f"{ccy}=X")
                if m:
                    # CCY=X is local currency per dollar: the currency's own move is the inverse
                    inv = lambda x: (1 / (1 + x) - 1) if x is not None else None
                    fx[ccy] = {"symbol": f"{ccy}=X", "per_usd": m["price"], "change_1d": inv(m["change_1d"]),
                               "change_1m": inv(m["change_1m"]), "change_ytd": inv(m["change_ytd"]), "change_1y": inv(m["change_1y"])}
        return {"etf": etf, "index": idx, "fx": fx}

    def slow_persisted():   # survives restarts: the cold fetch (IMF + 34 FRED series) takes about a minute
        import json, time
        from pathlib import Path
        path = Path(__file__).resolve().parents[2] / "data" / "processed" / "worldmap_slow.json"
        try:
            if path.exists() and time.time() - path.stat().st_mtime < 86400:
                return json.loads(path.read_text())
        except Exception:
            pass
        data = slow()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, default=str))
        except Exception:
            pass
        return data

    s = _cached("worldmap:slow", 86400, slow_persisted)
    f = _cached("worldmap:fast", 600, fast)
    countries: Dict[str, Dict[str, Any]] = {}
    for c in COUNTRIES:
        iso = c["iso2"]
        rec: Dict[str, Any] = {"name": c["name"], "currency": c["currency"], "iso3": c["iso3"]}
        if iso in f["etf"]:
            rec["etf"] = f["etf"][iso]
            for k in ("change_1d", "change_1m", "change_ytd", "change_1y"):
                rec[k] = f["etf"][iso][k]                    # USD total return (comparable across countries)
        if iso in f["index"]:
            rec["index"] = f["index"][iso]
        if c["currency"] == "USD":
            rec["fx"] = {"symbol": None, "per_usd": 1.0, "change_1d": 0.0, "change_1m": 0.0, "change_ytd": 0.0, "change_1y": 0.0}
        elif c["currency"] in f["fx"]:
            rec["fx"] = f["fx"][c["currency"]]
        rec.update(s["imf"].get(iso, {}))
        rec.update(s["yields"].get(iso, {}))
        if iso in s["risk"]:
            rk = s["risk"][iso]
            rec.update({"rating": rk["rating"], "crp": rk["crp"], "default_spread": rk["default_spread"],
                        "erp_total": (s["mature_erp"] or 0) + (rk["crp"] or 0) if s["mature_erp"] else None})
        countries[iso] = rec
    return {"countries": countries, "numeric_to_iso2": NUMERIC_TO_ISO2, "year": year,
            "sources": {"markets": "Yahoo Finance — MSCI country ETFs (USD), local indices, currencies",
                        "yields": "OECD 10-year government yields via FRED (monthly)",
                        "economy": f"IMF World Economic Outlook ({year} estimates; {year + 1} projections)",
                        "risk": "Damodaran (NYU Stern) sovereign ratings and country risk premiums"}}
