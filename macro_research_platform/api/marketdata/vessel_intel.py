"""
Ship intelligence on top of the live AIS picture (free sources):

  sanctions()        vessels on the US Treasury OFAC SDN list (IMO / MMSI, programme), cached a day
  decode_dest(text)  AIS destination text → port (UN/LOCODE: "CNSHA", "CN SHA", ">SGSIN", "RUNVS>INSIK")
  profile(v)         size class, likely cargo, laden-or-ballast estimate, dangerous-goods category
  notable(rows)      the ships worth following: sanctioned, giants, gas carriers, warships, dangerous
                     cargo, tankers in the Gulf / Red Sea — with the reason
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from api.marketdata.core import _cached

logger = logging.getLogger(__name__)
UA = {"User-Agent": "Mozilla/5.0 (macro research terminal)"}
DATA = Path(__file__).resolve().parents[2] / "data" / "processed"


# ── OFAC sanctioned vessels ─────────────────────────────────────────────────
def sanctions() -> Dict[str, Dict[str, Any]]:
    """{'imo:1234567' | 'mmsi:123456789': {name, program, flag, type}} from the OFAC SDN list."""
    path = DATA / "ofac_vessels.json"

    def fetch():
        import requests
        try:
            if path.exists() and time.time() - path.stat().st_mtime < 86400:
                return json.loads(path.read_text())
        except Exception:
            pass
        try:
            r = requests.get("https://www.treasury.gov/ofac/downloads/sdn.csv", headers=UA, timeout=90)
            r.raise_for_status()
            out: Dict[str, Dict[str, Any]] = {}
            for row in csv.reader(io.StringIO(r.text)):
                if len(row) < 12 or row[2].strip().lower() != "vessel":
                    continue
                rec = {"name": row[1].strip(), "program": row[3].strip(), "type": None if row[6].strip() == "-0-" else row[6].strip(),
                       "flag": None if row[9].strip() == "-0-" else row[9].strip()}
                rem = row[11]
                for imo in re.findall(r"IMO (\d{7})", rem):
                    out[f"imo:{imo}"] = rec
                for mmsi in re.findall(r"MMSI (\d{9})", rem):
                    out[f"mmsi:{mmsi}"] = rec
            if out:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(out))
            return out
        except Exception as e:
            logger.info("[ofac] %s", e)
            try:
                return json.loads(path.read_text())
            except Exception:
                return {}
    return _cached("intel:ofac", 6 * 3600, fetch)


def sanctioned(imo: Any, mmsi: Any) -> Optional[Dict[str, Any]]:
    """The SDN record for a vessel. The IMO number is permanent, so when we know it, it alone decides;
    an MMSI (which is reassigned when a ship re-flags) only counts when no IMO is known, and is marked."""
    s = sanctions()
    imo = str(imo or "").strip()
    if imo and imo != "0":
        rec = s.get(f"imo:{imo}")
        return {**rec, "program": _programs(rec["program"]), "match": "IMO"} if rec else None
    rec = s.get(f"mmsi:{mmsi}")
    return {**rec, "program": _programs(rec["program"]), "match": "MMSI (to confirm — MMSIs are reassigned)"} if rec else None


def _programs(p: str) -> str:
    return ", ".join(x.strip(" []") for x in re.split(r"\]\s*\[", p or "") if x.strip(" []"))


# ── Ports (UN/LOCODE) ───────────────────────────────────────────────────────
def _coord(s: str) -> Optional[Tuple[float, float]]:
    m = re.match(r"(\d{2})(\d{2})([NS])\s+(\d{3})(\d{2})([EW])", s or "")
    if not m:
        return None
    lat = (int(m[1]) + int(m[2]) / 60) * (1 if m[3] == "N" else -1)
    lon = (int(m[4]) + int(m[5]) / 60) * (1 if m[6] == "E" else -1)
    return round(lat, 3), round(lon, 3)


def ports() -> Dict[str, Any]:
    """{'CNSHA': [name, country, lat, lon]} for every UN/LOCODE location with a port function, plus a
    name index for destinations typed as words ('SINGAPORE')."""
    path = DATA / "locode_ports.json"

    def fetch():
        try:
            if path.exists():
                return json.loads(path.read_text())
        except Exception:
            pass
        import requests
        r = requests.get("https://raw.githubusercontent.com/datasets/un-locode/main/data/code-list.csv", headers=UA, timeout=120)
        r.raise_for_status()
        codes, names = {}, {}
        for row in csv.DictReader(io.StringIO(r.text)):
            if not row.get("Location"):
                continue
            code = f"{row['Country']}{row['Location']}"
            c = _coord(row.get("Coordinates") or "")
            # every code (crews type airport-flagged codes such as CNSHA for Shanghai's port too)
            codes[code] = [row.get("NameWoDiacritics") or row.get("Name"), row["Country"], c[0] if c else None, c[1] if c else None]
            n = (row.get("NameWoDiacritics") or "").upper()
            # names: ports only; the first with coordinates wins (big ports tend to have them)
            if n and c and n not in names and (row.get("Function") or "").startswith("1"):
                names[n] = code
        out = {"codes": codes, "names": names}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, separators=(",", ":")))
        return out
    return _cached("intel:locode", 86400 * 30, fetch)


# names typed in AIS that UN/LOCODE spells differently, or that the first-match rule gets wrong
PORT_ALIASES = {"SINGAPORE": "SGSIN", "ROTTERDAM": "NLRTM", "SHANGHAI": "CNSHA", "NINGBO": "CNNGB", "QINGDAO": "CNTAO", "TIANJIN": "CNTSN",
                "HONG KONG": "HKHKG", "HONGKONG": "HKHKG", "BUSAN": "KRPUS", "PUSAN": "KRPUS", "ANTWERP": "BEANR", "HAMBURG": "DEHAM",
                "LOS ANGELES": "USLAX", "LONG BEACH": "USLGB", "NEW YORK": "USNYC", "HOUSTON": "USHOU", "FUJAIRAH": "AEFJR", "JEBEL ALI": "AEJEA",
                "PORT KLANG": "MYPKG", "KLANG": "MYPKG", "COLOMBO": "LKCMB", "PIRAEUS": "GRPIR", "ALGECIRAS": "ESALG", "SUEZ": "EGSUZ",
                "PORT SAID": "EGPSD", "SANTOS": "BRSSZ", "DURBAN": "ZADUR", "YOKOHAMA": "JPYOK", "KAOHSIUNG": "TWKHH", "GIBRALTAR": "GIGIB",
                "RAS TANURA": "SARTA", "BASRAH": "IQBSR", "NOVOROSSIYSK": "RUNVS", "PRIMORSK": "RUPRI", "UST-LUGA": "RULUG", "SIKKA": "INSIK"}


def decode_dest(text: Optional[str]) -> Optional[Dict[str, Any]]:
    """Destination as typed by the crew → port. Handles UN/LOCODE ('CNSHA', 'CN SHA', 'CN-SHA'),
    'FROM>TO' forms and plain port names. None when it can't be read (e.g. 'FOR ORDERS')."""
    raw = (text or "").strip().upper()
    if not raw or raw in ("", "0", "NONE", "N/A"):
        return None
    P = ports()
    codes, names = P["codes"], P["names"]

    def known(code: str) -> Optional[List[Any]]:
        """Major ports pinned to their harbour (the code list has some only as airports, without coordinates)."""
        from api.marketdata.tracking import MAJOR_PORTS
        for alias, c in PORT_ALIASES.items():
            if c == code:
                for pn, (la, lo) in MAJOR_PORTS.items():
                    if pn.upper().startswith(alias) or alias in pn.upper():
                        return [alias.title(), code[:2], la, lo]
        return None

    def one(t: str) -> Optional[Dict[str, Any]]:
        t = t.strip(" .>-_/")
        c = re.sub(r"[\s\-_.]", "", t)
        if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{3}", c) and c in codes:
            code = c
        else:
            code = PORT_ALIASES.get(t) or names.get(t)
        if not code or (code not in codes and not known(code)):
            return None
        k = known(code)
        n, ctry, lat, lon = k if k else codes[code]
        if k and code in codes and codes[code][0] and "Apt" not in codes[code][0]:
            n = codes[code][0]
        return {"code": code, "name": n, "country": ctry, "lat": lat, "lon": lon}
    parts = [p for p in re.split(r"\s*(?:>+|=>|->| TO )\s*", raw) if p.strip()]
    dest = one(parts[-1]) if parts else None
    origin = one(parts[0]) if len(parts) >= 2 else None
    if not dest and not origin:
        return {"raw": raw, "port": None}
    return {"raw": raw, "port": dest, "from": origin}


# ── Vessel profile ──────────────────────────────────────────────────────────
# container lines' naming patterns (generic words such as CAPE / SAN / BALTIC are left out: bulkers use them too)
CONTAINER_LINES = re.compile(r"^(MSC |MAERSK |CMA CGM |COSCO SHIPPING |CSCL |EVER |ONE |OOCL |HMM |YM |YANG MING |ZIM |APL |HAPAG|WAN HAI |"
                             r"X-PRESS |SEASPAN |KOTA |NYK |SITC |TS |KMTC |CONTSHIP )", re.I)
GAS = re.compile(r"\b(LNG|LPG|GAS|METHANE|ETHANE|AMMONIA)\b", re.I)
HAZ = {1: "A", 2: "B", 3: "C", 4: "D"}


def profile(v: Dict[str, Any]) -> Dict[str, Any]:
    """What a vessel likely carries and its size class, estimating length from gross tonnage when AIS gives no
    dimensions.
    """
    t, code, L, d, name = v.get("type"), v.get("type_code"), v.get("length_m"), v.get("draught"), (v.get("name") or "")
    gt = v.get("tonnage_gt")
    if not L and gt:
        # no AIS dimensions (satellite-only ships): approximate the hull length from gross tonnage, by kind
        if t == "Tanker":
            L = 330 if gt >= 140000 else 274 if gt >= 75000 else 245 if gt >= 50000 else 228 if gt >= 38000 else 183 if gt >= 20000 else 130
        elif t == "Cargo":
            L = 290 if gt >= 85000 else 230 if gt >= 38000 else 195 if gt >= 28000 else 170 if gt >= 15000 else 120
    out: Dict[str, Any] = {"class": None, "cargo": None, "laden": None, "laden_note": None, "hazard": None,
                           "size_from": "tonnage" if L and not v.get("length_m") else "length" if L else None}
    if isinstance(code, int) and 70 <= code <= 89 and code % 10 in HAZ:
        out["hazard"] = f"Dangerous goods / pollutant, category {HAZ[code % 10]}"
    k = None
    if t == "Tanker":
        if GAS.search(name):
            out["cargo"] = "Liquefied gas (LNG/LPG)"
            out["class"] = ("Q-Max/Q-Flex LNG carrier" if L and L >= 315 else "LNG/LPG carrier")
            k = 0.04
        elif L:
            out["class"] = ("VLCC" if L >= 320 else "Suezmax" if L >= 260 else "Aframax / LR2" if L >= 220 else
                            "Panamax / LR1" if L >= 200 else "MR product tanker" if L >= 150 else "Small tanker")
            out["cargo"] = "Crude oil" if L >= 250 else "Crude or refined products" if L >= 200 else "Refined products / chemicals"
            k = 0.068
        else:
            out["cargo"] = "Liquid bulk (oil, products or chemicals)"
    elif t == "Cargo":
        boxes = bool(CONTAINER_LINES.search(name))
        if boxes:
            out["cargo"] = "Containers"
            if L:
                out["class"] = ("Ultra-large container ship" if L >= 366 else "Neo-Panamax container ship" if L >= 300 else
                                "Panamax container ship" if L >= 250 else "Feeder / regional container ship")
            k = 0.04
        else:
            out["cargo"] = "Dry bulk or general cargo"
            if L:
                out["class"] = ("Valemax / VLOC" if L >= 340 else "Capesize bulker" if L >= 270 else "Panamax / Kamsarmax" if L >= 220 else
                                "Supramax / Ultramax" if L >= 185 else "Handysize" if L >= 150 else "Coaster")
            k = 0.064
    elif t == "Passenger":
        out["cargo"] = "Passengers"
        out["class"] = "Cruise ship" if L and L >= 200 else "Ferry / passenger ship"
    elif t == "Fishing":
        out["cargo"] = "Fishing"
    elif t == "Military":
        out["cargo"] = "Military / law enforcement"
    # laden or in ballast: the crew-entered draught against a typical design draught for the hull
    if k and L and d and v.get("length_m"):
        design = L * k
        r = d / design
        out["laden"] = "laden" if r >= 0.82 else "in ballast" if r <= 0.62 else "part laden"
        out["laden_note"] = f"draught {d:.1f} m vs ~{design:.1f} m typical design draught for a {L:.0f} m hull (estimate)"
    return out


# Sea areas where a tanker is news
HOT_ZONES = {"Strait of Hormuz / Gulf": (24.0, 50.0, 27.5, 58.5), "Red Sea / Bab el-Mandeb": (11.5, 32.0, 28.0, 44.0),
             "Black Sea": (40.8, 27.5, 46.8, 41.8), "Taiwan Strait": (22.0, 117.5, 26.0, 121.0), "Gulf of Aden": (10.5, 44.0, 15.0, 52.0)}


def zone_of(lat: float, lon: float) -> Optional[str]:
    """The named hot zone (strait, chokepoint) a position is in, or None."""
    for n, (s, w, nn, e) in HOT_ZONES.items():
        if s <= lat <= nn and w <= lon <= e:
            return n
    return None


def notable_reasons(v: Dict[str, Any]) -> List[Tuple[int, str, str]]:
    """[(priority, tag, reason)] — tag is one letter for the map: s sanctioned, g giant, l gas,
    m military, h dangerous goods, z tanker in a hot zone."""
    out: List[Tuple[int, str, str]] = []
    s = sanctioned(v.get("imo"), v.get("mmsi"))
    if s:
        out.append((0, "s", f"US sanctions (OFAC: {s['program']})" + (f" — listed as {s['name']}" if s.get("name") and s["name"] != v.get("name") else "")
                    + ("" if s["match"] == "IMO" else " — matched by MMSI only, confirm")))
    t, L, name = v.get("type"), v.get("length_m") or 0, v.get("name") or ""
    if v.get("type") == "Military":
        out.append((2, "m", "Military / law-enforcement vessel"))
    if t == "Tanker" and GAS.search(name):
        out.append((3, "l", "Gas carrier (LNG/LPG)"))
    if (t == "Tanker" and L >= 320) or (t == "Cargo" and L >= 366):
        out.append((3, "g", "VLCC — 2 million barrels of crude" if t == "Tanker" else "Ultra-large container ship (20,000+ boxes)"))
    code = v.get("type_code")
    if isinstance(code, int) and code in (71, 81):
        out.append((4, "h", "Carrying dangerous goods, category A"))
    if t == "Tanker" and v.get("lat") is not None:
        z = zone_of(v["lat"], v["lon"])
        if z:
            out.append((5, "z", f"Tanker in the {z}"))
    return sorted(out)


# ── What a ship is probably carrying, from where it loaded ──────────────────
# Major export terminals by commodity (name fragments as they appear in port-call and LOCODE data).
# Exact manifests are not public; a laden ship leaving one of these is very likely carrying its export.
TERMINALS: List[Tuple[str, str, str]] = [
    # (fragment, kind, what)
    ("primorsk", "crude", "Russian Urals crude"), ("ust-luga", "crude", "Russian Urals crude / products"), ("ust luga", "crude", "Russian Urals crude / products"),
    ("novorossiysk", "crude", "Russian Urals or CPC Blend crude"), ("kozmino", "crude", "Russian ESPO crude"), ("de-kastri", "crude", "Russian Sokol crude"),
    ("ras tanura", "crude", "Saudi Arab Light / Medium crude"), ("juaymah", "crude", "Saudi Arab crude"), ("yanbu", "crude", "Saudi crude / products (Red Sea)"),
    ("basrah", "crude", "Iraqi Basrah crude"), ("basra", "crude", "Iraqi Basrah crude"), ("kharg", "crude", "Iranian crude"), ("jask", "crude", "Iranian crude"),
    ("mina al ahmadi", "crude", "Kuwaiti crude"), ("ahmadi", "crude", "Kuwaiti crude"), ("jebel dhanna", "crude", "UAE Murban crude"), ("ruwais", "crude", "UAE crude / products"),
    ("fujairah", "crude", "crude or fuel oil (Fujairah storage hub)"), ("ceyhan", "crude", "Kirkuk / Azeri BTC crude"), ("es sider", "crude", "Libyan crude"),
    ("zawiya", "crude", "Libyan crude"), ("bonny", "crude", "Nigerian Bonny Light crude"), ("forcados", "crude", "Nigerian Forcados crude"),
    ("puerto jose", "crude", "Venezuelan Merey crude"), ("corpus christi", "crude", "US WTI crude"), ("loop", "crude", "US crude"), ("galveston", "crude", "US crude / products"),
    ("sullom voe", "crude", "North Sea crude"), ("mongstad", "crude", "North Sea crude"), ("sao sebastiao", "crude", "Brazilian crude"), ("acu", "crude", "Brazilian pre-salt crude"),
    ("ras laffan", "lng", "Qatari LNG"), ("sabine pass", "lng", "US LNG"), ("cameron", "lng", "US LNG"), ("freeport", "lng", "US LNG"), ("corpus christi lng", "lng", "US LNG"),
    ("bintulu", "lng", "Malaysian LNG"), ("gladstone", "lng", "Australian LNG (Curtis Island) or coal"), ("darwin", "lng", "Australian LNG"), ("karratha", "lng", "Australian LNG"),
    ("hammerfest", "lng", "Norwegian LNG"), ("sabetta", "lng", "Russian Yamal LNG"), ("bonny lng", "lng", "Nigerian LNG"), ("idku", "lng", "Egyptian LNG"),
    ("port hedland", "ore", "iron ore (Pilbara)"), ("dampier", "ore", "iron ore (Pilbara)"), ("cape lambert", "ore", "iron ore (Pilbara)"), ("port walcott", "ore", "iron ore (Pilbara)"),
    ("tubarao", "ore", "iron ore (Brazil)"), ("ponta da madeira", "ore", "iron ore (Brazil)"), ("itaqui", "ore", "iron ore (Brazil)"), ("saldanha", "ore", "iron ore (South Africa)"),
    ("sept-iles", "ore", "iron ore (Canada)"), ("narvik", "ore", "iron ore (Sweden)"),
    ("newcastle", "coal", "thermal coal (Australia)"), ("hay point", "coal", "coking coal (Australia)"), ("dalrymple", "coal", "coking coal (Australia)"),
    ("abbot point", "coal", "coal (Australia)"), ("richards bay", "coal", "coal (South Africa)"), ("taboneo", "coal", "coal (Indonesia)"), ("samarinda", "coal", "coal (Indonesia)"),
    ("muara pantai", "coal", "coal (Indonesia)"), ("vostochny", "coal", "coal (Russia)"), ("vanino", "coal", "coal (Russia)"), ("roberts bank", "coal", "coal (Canada)"),
    ("puerto bolivar", "coal", "coal (Colombia)"),
    ("santos", "grain", "soybeans / corn / sugar (Brazil)"), ("paranagua", "grain", "soybeans / corn (Brazil)"), ("rio grande", "grain", "soybeans (Brazil)"),
    ("rosario", "grain", "soybeans / meal / corn (Argentina)"), ("san lorenzo", "grain", "soybean meal / corn (Argentina)"), ("bahia blanca", "grain", "wheat / corn (Argentina)"),
    ("darrow", "grain", "US corn / soybeans (Mississippi)"), ("kalama", "grain", "US soybeans / corn (Pacific NW)"),
    ("longview", "grain", "US grain (Pacific NW)"), ("chornomorsk", "grain", "Ukrainian grain"), ("pivdennyi", "grain", "Ukrainian grain"), ("odesa", "grain", "Ukrainian grain"),
    ("odessa", "grain", "Ukrainian grain"), ("izmail", "grain", "Ukrainian grain"), ("constanta", "grain", "grain (Black Sea)"), ("kamsar", "bauxite", "bauxite (Guinea)"),
    ("weipa", "bauxite", "bauxite (Australia)"),
]
KIND_FITS = {"Tanker": {"crude", "lng"}, "Cargo": {"ore", "coal", "grain", "bauxite"}}


def infer_cargo(v: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Likely cargo from the terminal it loaded at (crew 'FROM>TO' or last port call) and its load state."""
    voy, lp = v.get("voyage") or {}, v.get("last_port") or {}
    origin = ((voy.get("from") or {}).get("name") or lp.get("port") or "")
    if not origin:
        return None
    o = origin.lower()
    t = v.get("type")
    prof = v.get("profile") or {}
    gas = "gas" in (prof.get("cargo") or "").lower()
    hit = next(((frag, kind, what) for frag, kind, what in TERMINALS
                if re.search(rf"\b{re.escape(frag)}\b", o) and kind in KIND_FITS.get(t, set()) and (kind != "lng" or gas) and (kind != "crude" or not gas)), None)
    laden = prof.get("laden")
    if not hit:
        if t == "Cargo" and "Containers" == prof.get("cargo"):
            return {"text": f"Containers, last loaded or discharged at {origin.title()}", "confidence": "possible", "basis": "last port call"}
        return None
    _, kind, what = hit
    if laden == "in ballast":
        return {"text": f"Empty (in ballast) — last called at {origin.title()}, a {what} export terminal: likely sailing to load or after discharging",
                "confidence": "likely", "basis": "draught and last port"}
    conf = "likely" if laden in ("laden", "part laden") else "possible"
    lead = "Likely carrying" if conf == "likely" else "Possibly carrying"
    return {"text": f"{lead} {what}, loaded at {origin.title()}", "confidence": conf,
            "basis": "export terminal it left" + (" and a laden draught" if conf == "likely" else " (load state unknown)")}
