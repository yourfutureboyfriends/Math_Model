"""
Physical-economy trackers, free sources:

  SHIP  · Chokepoints: IMF PortWatch — daily vessel transits and cargo capacity through 28
          maritime chokepoints (Suez, Panama, Hormuz, Malacca…) from satellite AIS, by
          vessel type. Updated weekly, a few days behind.
        · Live vessels: aisstream.io (global, needs a free API key in AISSTREAM_API_KEY) or,
          without a key, Fintraffic Digitraffic (Finland / Baltic Sea, open data).
  FLY   · Live aircraft around any point: adsb.lol (community ADS-B network, open data).
  QUAK  · Earthquakes M4.5+ in the last week: USGS, with distance to the nearest major port.
"""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from api.marketdata.core import NotFound, Upstream, _cached

logger = logging.getLogger(__name__)
UA = {"User-Agent": "Mozilla/5.0 (macro research terminal)"}
PORTWATCH = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Chokepoints_Data/FeatureServer/0/query"

# Chokepoint locations (for the map) and the trade they matter for
CHOKEPOINTS: Dict[str, Dict[str, Any]] = {
    "Suez Canal": {"lat": 30.6, "lon": 32.35, "why": "Europe–Asia containers, oil and LNG"},
    "Panama Canal": {"lat": 9.1, "lon": -79.7, "why": "US East Coast–Asia trade, US grain and LNG"},
    "Strait of Hormuz": {"lat": 26.6, "lon": 56.3, "why": "~20% of world oil, Qatar LNG"},
    "Bab el-Mandeb Strait": {"lat": 12.6, "lon": 43.4, "why": "Red Sea route to Suez"},
    "Malacca Strait": {"lat": 2.5, "lon": 101.5, "why": "Asia's main oil and container artery"},
    "Cape of Good Hope": {"lat": -34.4, "lon": 18.5, "why": "Suez/Red Sea diversions"},
    "Taiwan Strait": {"lat": 24.5, "lon": 119.5, "why": "China–Japan/Korea trade, chips"},
    "Bosporus Strait": {"lat": 41.1, "lon": 29.05, "why": "Black Sea grain and oil"},
    "Gibraltar Strait": {"lat": 35.95, "lon": -5.6, "why": "Mediterranean–Atlantic"},
    "Dover Strait": {"lat": 51.0, "lon": 1.45, "why": "Busiest shipping lane, North Sea ports"},
    "Korea Strait": {"lat": 34.5, "lon": 129.3, "why": "Korea–Japan–China trade"},
    "Luzon Strait": {"lat": 20.5, "lon": 121.0, "why": "Pacific–South China Sea"},
    "Lombok Strait": {"lat": -8.7, "lon": 115.75, "why": "Large bulk carriers bypassing Malacca"},
    "Sunda Strait": {"lat": -6.0, "lon": 105.8, "why": "Indian Ocean–Java Sea"},
    "Makassar Strait": {"lat": -2.0, "lon": 118.0, "why": "Bulk and LNG, Indonesia"},
    "Bering Strait": {"lat": 65.8, "lon": -169.0, "why": "Arctic route"}, "Bohai Strait": {"lat": 38.3, "lon": 121.0, "why": "Northern China ports"},
    "Kerch Strait": {"lat": 45.3, "lon": 36.5, "why": "Sea of Azov grain"}, "Magellan Strait": {"lat": -53.5, "lon": -70.5, "why": "Panama alternative"},
    "Mindoro Strait": {"lat": 12.5, "lon": 120.6, "why": "Philippines"}, "Balabac Strait": {"lat": 7.6, "lon": 117.0, "why": "South China Sea–Sulu Sea"},
    "Mona Passage": {"lat": 18.2, "lon": -67.9, "why": "Caribbean–Atlantic"}, "Ombai Strait": {"lat": -8.4, "lon": 125.0, "why": "Timor"},
    "Oresund Strait": {"lat": 55.9, "lon": 12.7, "why": "Baltic Sea access"}, "Torres Strait": {"lat": -10.6, "lon": 142.2, "why": "Australia–Asia"},
    "Tsugaru Strait": {"lat": 41.5, "lon": 140.6, "why": "Sea of Japan–Pacific"}, "Windward Passage": {"lat": 20.0, "lon": -73.8, "why": "US East Coast–Panama"},
    "Yucatan Channel": {"lat": 21.8, "lon": -85.8, "why": "Gulf of Mexico–Caribbean"},
}
MAJOR_PORTS = {"Shanghai": (31.23, 121.47), "Singapore": (1.26, 103.84), "Ningbo-Zhoushan": (29.87, 121.55), "Shenzhen": (22.5, 113.9),
               "Busan": (35.1, 129.04), "Hong Kong": (22.3, 114.17), "Rotterdam": (51.95, 4.14), "Antwerp": (51.26, 4.4),
               "Los Angeles / Long Beach": (33.74, -118.26), "Tokyo / Yokohama": (35.45, 139.65), "Kaohsiung": (22.61, 120.29),
               "Dubai (Jebel Ali)": (25.01, 55.06), "Hamburg": (53.54, 9.97), "New York / New Jersey": (40.67, -74.05),
               "Port Klang": (3.0, 101.39), "Tanjung Pelepas": (1.36, 103.55), "Santos": (-23.96, -46.3), "Manzanillo (MX)": (19.05, -104.31),
               "Houston": (29.73, -95.27), "Valparaíso": (-33.03, -71.63), "Durban": (-29.87, 31.03), "Mumbai (Nhava Sheva)": (18.95, 72.95),
               "Kobe / Osaka": (34.67, 135.2), "Vancouver": (49.29, -123.11), "Sydney / Botany": (-33.97, 151.22),
               "Balboa (Panama)": (8.95, -79.57), "Colón (Panama)": (9.36, -79.9), "Port Said": (31.26, 32.3), "Piraeus": (37.94, 23.62),
               "Algeciras": (36.13, -5.44), "Colombo": (6.95, 79.85), "Laem Chabang": (13.08, 100.88), "Tianjin": (38.98, 117.75),
               "Qingdao": (36.07, 120.32), "Guangzhou": (22.75, 113.6), "Xiamen": (24.45, 118.07), "Jeddah": (21.47, 39.17),
               "Salalah": (16.95, 54.0), "Chittagong": (22.3, 91.8), "Ho Chi Minh City": (10.77, 106.75), "Manila": (14.6, 120.95),
               "Jakarta (Tanjung Priok)": (-6.1, 106.88), "Callao": (-12.05, -77.15), "Savannah": (32.08, -81.09), "Seattle / Tacoma": (47.27, -122.41),
               "Felixstowe": (51.95, 1.32), "Le Havre": (49.48, 0.11), "Bremerhaven": (53.56, 8.55), "Valencia": (39.44, -0.32),
               "Istanbul (Ambarli)": (40.97, 28.68), "Novorossiysk": (44.72, 37.8), "Tokyo Bay (Chiba)": (35.6, 140.1), "Melbourne": (-37.83, 144.9)}
AIRPORTS = {"HKG": ("Hong Kong", 22.308, 113.918), "LHR": ("London Heathrow", 51.47, -0.454), "JFK": ("New York JFK", 40.641, -73.778),
            "LAX": ("Los Angeles", 33.942, -118.408), "NRT": ("Tokyo Narita", 35.772, 140.393), "HND": ("Tokyo Haneda", 35.549, 139.78),
            "SIN": ("Singapore", 1.364, 103.991), "DXB": ("Dubai", 25.253, 55.364), "FRA": ("Frankfurt", 50.037, 8.562),
            "CDG": ("Paris CDG", 49.01, 2.55), "ORD": ("Chicago O'Hare", 41.974, -87.907), "ATL": ("Atlanta", 33.64, -84.427),
            "PEK": ("Beijing Capital", 40.08, 116.584), "PVG": ("Shanghai Pudong", 31.144, 121.808), "ICN": ("Seoul Incheon", 37.46, 126.44),
            "SYD": ("Sydney", -33.94, 151.175), "AMS": ("Amsterdam", 52.31, 4.768), "IST": ("Istanbul", 41.275, 28.752),
            "DOH": ("Doha", 25.273, 51.608), "MEM": ("Memphis (FedEx hub)", 35.042, -89.977), "ANC": ("Anchorage (cargo)", 61.174, -149.996)}


def _km(a_lat, a_lon, b_lat, b_lon) -> float:
    p = math.pi / 180
    h = math.sin((b_lat - a_lat) * p / 2) ** 2 + math.cos(a_lat * p) * math.cos(b_lat * p) * math.sin((b_lon - a_lon) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


# ── SHIP: chokepoints ────────────────────────────────────────────────────────
def chokepoints(days: int = 400) -> Dict[str, Any]:
    def fetch():
        import requests
        since = (date.today() - timedelta(days=days)).isoformat()
        rows, offset = [], 0
        while True:
            r = requests.get(PORTWATCH, params={"where": f"date >= DATE '{since}'", "outFields": "date,portname,n_total,n_tanker,n_container,n_dry_bulk,capacity",
                                                "orderByFields": "date ASC", "resultOffset": offset, "resultRecordCount": 2000, "f": "json"},
                             headers=UA, timeout=60)
            r.raise_for_status()
            j = r.json()
            feats = j.get("features") or []
            rows += [f["attributes"] for f in feats]
            if not j.get("exceededTransferLimit") or not feats:
                break
            offset += len(feats)
        if not rows:
            raise Upstream("IMF PortWatch returned no data.")
        by: Dict[str, List[Dict[str, Any]]] = {}
        for x in rows:
            by.setdefault(x["portname"], []).append(x)
        out = []
        for name, xs in by.items():
            xs.sort(key=lambda x: x["date"])
            last_date = xs[-1]["date"]
            def avg(lo: int, hi: int, field: str) -> Optional[float]:
                v = [x[field] or 0 for x in xs[-hi:len(xs) - lo]] if lo else [x[field] or 0 for x in xs[-hi:]]
                return sum(v) / len(v) if v else None
            wk = avg(0, 7, "n_total")
            # same 7 days a year earlier
            ya = [x for x in xs if 358 <= (datetime.fromisoformat(str(last_date)[:10]) - datetime.fromisoformat(str(x["date"])[:10])).days <= 371]
            ya_avg = sum((x["n_total"] or 0) for x in ya) / len(ya) if ya else None
            yr = [x["n_total"] or 0 for x in xs[-365:]]
            meta = CHOKEPOINTS.get(name, {})
            out.append({"name": name, "lat": meta.get("lat"), "lon": meta.get("lon"), "why": meta.get("why"), "date": str(last_date)[:10],
                        "transits_7d": wk, "vs_last_year": (wk / ya_avg - 1) if wk is not None and ya_avg else None,
                        "vs_1y_avg": (wk / (sum(yr) / len(yr)) - 1) if wk is not None and yr and sum(yr) else None,
                        "tankers_7d": avg(0, 7, "n_tanker"), "containers_7d": avg(0, 7, "n_container"), "dry_bulk_7d": avg(0, 7, "n_dry_bulk"),
                        "capacity_7d": avg(0, 7, "capacity"),
                        "series": [{"date": str(x["date"])[:10], "n": x["n_total"]} for x in xs[-180:]]})
        out.sort(key=lambda c: -(c["transits_7d"] or 0))
        return {"chokepoints": out, "as_of": max(c["date"] for c in out),
                "source": "IMF PortWatch (satellite AIS; daily transits through maritime chokepoints, updated weekly)"}
    return _cached(f"chokepoints:{days}", 6 * 3600, fetch)


# ── SHIP: live vessels ───────────────────────────────────────────────────────
SHIP_TYPES = {range(70, 80): "Cargo", range(80, 90): "Tanker", range(60, 70): "Passenger", range(30, 31): "Fishing",
              range(31, 33): "Towing", range(52, 53): "Tug", range(35, 36): "Military", range(36, 38): "Sailing/pleasure"}


def _ship_type(code: Optional[int]) -> str:
    if code is None:
        return "Unknown"
    for r, name in SHIP_TYPES.items():
        if code in r:
            return name
    return "Other"


def vessels(lat_min: float, lon_min: float, lat_max: float, lon_max: float, seconds: int = 12) -> Dict[str, Any]:
    """Live vessel positions in a bounding box: aisstream.io if a key is configured (global),
    otherwise Fintraffic Digitraffic (Baltic Sea only)."""
    key = os.getenv("AISSTREAM_API_KEY") or ""
    box = (round(lat_min, 2), round(lon_min, 2), round(lat_max, 2), round(lon_max, 2))
    if key:
        return _cached(f"ais:{box}", 120, lambda: _aisstream(key, box, seconds))
    return _cached("digitraffic", 120, lambda: _digitraffic(box))


def _aisstream(key: str, box, seconds: int) -> Dict[str, Any]:
    import asyncio
    import websockets

    async def run():
        ships: Dict[int, Dict[str, Any]] = {}
        sub = {"APIKey": key, "BoundingBoxes": [[[box[0], box[1]], [box[2], box[3]]]],
               "FilterMessageTypes": ["PositionReport", "ShipStaticData"]}
        async with websockets.connect("wss://stream.aisstream.io/v0/stream", open_timeout=15) as ws:
            await ws.send(json.dumps(sub))
            end = asyncio.get_event_loop().time() + seconds
            while asyncio.get_event_loop().time() < end:
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=max(0.1, end - asyncio.get_event_loop().time())))
                except asyncio.TimeoutError:
                    break
                meta = msg.get("MetaData") or {}
                mmsi = meta.get("MMSI")
                if not mmsi:
                    continue
                s = ships.setdefault(mmsi, {"mmsi": mmsi})
                s["name"] = (meta.get("ShipName") or s.get("name") or "").strip()
                if msg.get("MessageType") == "PositionReport":
                    p = msg["Message"]["PositionReport"]
                    s.update({"lat": p.get("Latitude"), "lon": p.get("Longitude"), "speed": p.get("Sog"), "course": p.get("Cog"),
                              "heading": p.get("TrueHeading"), "status": p.get("NavigationalStatus")})
                elif msg.get("MessageType") == "ShipStaticData":
                    d = msg["Message"]["ShipStaticData"]
                    s.update({"type": _ship_type(d.get("Type")), "destination": (d.get("Destination") or "").strip(),
                              "draught": d.get("MaximumStaticDraught")})
        return [s for s in ships.values() if s.get("lat") is not None]
    try:
        ships = asyncio.run(run())
    except Exception as e:
        raise Upstream(f"aisstream.io: {e}")
    return {"source": "aisstream.io (live AIS)", "coverage": "global", "box": box, "vessels": ships, "listen_seconds": seconds}


def _digitraffic(box) -> Dict[str, Any]:
    import requests
    loc = requests.get("https://meri.digitraffic.fi/api/ais/v1/locations", headers={**UA, "Accept-Encoding": "gzip"}, timeout=30)
    loc.raise_for_status()
    meta = {}
    try:
        v = requests.get("https://meri.digitraffic.fi/api/ais/v1/vessels", headers={**UA, "Accept-Encoding": "gzip"}, timeout=30)
        meta = {x["mmsi"]: x for x in v.json()}
    except Exception:
        pass
    out = []
    for f in loc.json().get("features", []):
        lon, lat = f["geometry"]["coordinates"][:2]
        p = f["properties"]
        m = meta.get(p["mmsi"], {})
        out.append({"mmsi": p["mmsi"], "lat": lat, "lon": lon, "speed": p.get("sog"), "course": p.get("cog"), "heading": p.get("heading"),
                    "status": p.get("navStat"), "name": (m.get("name") or "").strip(), "type": _ship_type(m.get("shipType")),
                    "destination": (m.get("destination") or "").strip()})
    return {"source": "Fintraffic Digitraffic (open AIS data)", "coverage": "Baltic Sea / Finland only — add a free aisstream.io key "
            "(AISSTREAM_API_KEY) for global live ships", "box": [53.5, 9.0, 66.0, 31.0], "vessels": out}


# ── FLY: live aircraft ───────────────────────────────────────────────────────
EMERGENCY = {"7500": "Hijack", "7600": "Radio failure", "7700": "Emergency"}


def flights(lat: float, lon: float, radius_nm: int = 100) -> Dict[str, Any]:
    radius_nm = max(5, min(int(radius_nm), 250))

    def fetch():
        import requests
        r = requests.get(f"https://api.adsb.lol/v2/point/{lat:.3f}/{lon:.3f}/{radius_nm}", headers=UA, timeout=25)
        if r.status_code != 200:
            raise Upstream(f"adsb.lol returned {r.status_code}")
        ac = []
        for a in r.json().get("ac", []):
            if a.get("lat") is None:
                continue
            alt = a.get("alt_baro")
            ac.append({"hex": a.get("hex"), "flight": (a.get("flight") or "").strip(), "reg": a.get("r"), "type": a.get("t"),
                       "lat": a["lat"], "lon": a["lon"], "alt": None if alt == "ground" else alt, "on_ground": alt == "ground",
                       "speed": a.get("gs"), "track": a.get("track"), "vrate": a.get("baro_rate"), "squawk": a.get("squawk"),
                       "emergency": EMERGENCY.get(str(a.get("squawk") or "")) or (a.get("emergency") if a.get("emergency") not in (None, "none") else None),
                       "category": a.get("category")})
        airborne = [x for x in ac if not x["on_ground"]]
        return {"center": [lat, lon], "radius_nm": radius_nm, "aircraft": ac, "airborne": len(airborne), "on_ground": len(ac) - len(airborne),
                "emergencies": [x for x in ac if x["emergency"]],
                "source": "adsb.lol (open community ADS-B network; coverage depends on volunteer receivers)"}
    return _cached(f"fly:{lat:.2f}:{lon:.2f}:{radius_nm}", 20, fetch)


# ── QUAK: earthquakes ────────────────────────────────────────────────────────
def earthquakes(min_mag: float = 4.5) -> Dict[str, Any]:
    def fetch():
        import requests
        r = requests.get("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson", headers=UA, timeout=30)
        r.raise_for_status()
        out = []
        for f in r.json().get("features", []):
            p, (lon, lat, depth) = f["properties"], f["geometry"]["coordinates"]
            if (p.get("mag") or 0) < min_mag:
                continue
            port, dist = min(((n, _km(lat, lon, *c)) for n, c in MAJOR_PORTS.items()), key=lambda t: t[1])
            cp, cdist = min(((n, _km(lat, lon, c["lat"], c["lon"])) for n, c in CHOKEPOINTS.items()), key=lambda t: t[1])
            out.append({"nearest_chokepoint": cp, "chokepoint_km": round(cdist),
                        "trade_risk": bool((p.get("mag") or 0) >= 6.5 and min(dist, cdist) < 300),"time": datetime.fromtimestamp(p["time"] / 1000, tz=timezone.utc).isoformat(timespec="minutes"), "mag": p.get("mag"),
                        "place": p.get("place"), "lat": lat, "lon": lon, "depth_km": depth, "tsunami": bool(p.get("tsunami")),
                        "alert": p.get("alert"), "url": p.get("url"), "nearest_port": port, "port_km": round(dist)})
        out.sort(key=lambda x: -(x["mag"] or 0))
        return {"quakes": out, "source": "USGS (M4.5+, past 7 days); PAGER alert level where issued"}
    return _cached(f"quakes:{min_mag}", 900, fetch)
