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
def chokepoints(days: int = 1100) -> Dict[str, Any]:
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
                        "series": [{"date": str(x["date"])[:10], "n": x["n_total"], "tankers": x["n_tanker"], "containers": x["n_container"],
                                    "dry_bulk": x["n_dry_bulk"]} for x in xs]})
        out.sort(key=lambda c: -(c["transits_7d"] or 0))
        return {"chokepoints": out, "as_of": max(c["date"] for c in out),
                "source": "IMF PortWatch (satellite AIS; daily transits through maritime chokepoints, updated weekly)"}
    def persisted():   # PortWatch updates weekly and a cold pull pages ~30k rows (≈1 min): keep a disk copy
        import time as _t
        from pathlib import Path
        path = Path(__file__).resolve().parents[2] / "data" / "processed" / f"portwatch_chokepoints_{days}.json"
        try:
            if path.exists() and _t.time() - path.stat().st_mtime < 6 * 3600:
                return json.loads(path.read_text())
        except Exception:
            pass
        try:
            data = fetch()
        except Exception:
            if path.exists():                        # upstream down: serve the last copy rather than nothing
                return json.loads(path.read_text())
            raise
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, separators=(",", ":")))
        except Exception:
            pass
        return data
    return _cached(f"chokepoints:{days}", 6 * 3600, persisted)


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


# Preset sea areas the live collector always watches (lat_min, lon_min, lat_max, lon_max)
AIS_AREAS = {"Singapore / Malacca": (0, 100, 5, 106), "Hong Kong / Pearl River": (21.3, 112.5, 23.2, 115.5), "Suez / Red Sea": (26, 31, 32, 35),
             "Strait of Hormuz": (24.5, 54.5, 27.5, 58), "English Channel": (49.5, -3, 52, 3), "Rotterdam / North Sea": (51.3, 2.5, 53, 5.5),
             "LA / Long Beach": (33.3, -119, 34, -117.8), "Shanghai": (30.5, 121, 32, 123), "Panama Canal": (8.6, -80.2, 9.6, -79.3),
             "Baltic": (59, 19, 61, 26)}


class _AisCollector:
    """One persistent aisstream.io connection (the free key allows a single connection) that
    keeps the latest position and identity of every vessel in the watched areas. Requests are
    answered from this picture instantly, and slow-reporting ships (at anchor: every ~3 min)
    accumulate instead of being missed by a short listen."""
    MAX_AGE = 30 * 60

    def __init__(self, key: str):
        import threading
        self.key = key
        self.boxes = list(AIS_AREAS.values())
        self.ships: Dict[int, Dict[str, Any]] = {}
        # Identity (type, destination, IMO…) is broadcast only every ~6 minutes: keep the last
        # known copy on disk so ships aren't all "Unknown" for minutes after a restart.
        self.static: Dict[int, Dict[str, Any]] = self._load_static()
        self.static_saved = time_now()
        self.lock = threading.Lock()
        self.resubscribe = False
        self.started = time_now()
        self.status = "connecting"
        threading.Thread(target=self._run, name="aisstream", daemon=True).start()

    def watch(self, box) -> None:
        with self.lock:
            if not any(b[0] <= box[0] and b[1] <= box[1] and b[2] >= box[2] and b[3] >= box[3] for b in self.boxes):
                self.boxes = (self.boxes + [box])[-24:]
                self.resubscribe = True

    def snapshot(self, box) -> List[Dict[str, Any]]:
        cutoff = time_now() - self.MAX_AGE
        with self.lock:
            return [dict(v) for v in self.ships.values() if v.get("lat") is not None and v["seen"] >= cutoff
                    and box[0] <= v["lat"] <= box[2] and box[1] <= v["lon"] <= box[3]]

    @staticmethod
    def _static_path():
        from pathlib import Path
        return Path(__file__).resolve().parents[2] / "data" / "processed" / "ais_static.json"

    def _load_static(self) -> Dict[int, Dict[str, Any]]:
        try:
            return {int(k): v for k, v in json.loads(self._static_path().read_text()).items()}
        except Exception:
            return {}

    def _save_static(self, snap: Dict[int, Dict[str, Any]]) -> None:
        try:
            items = dict(list(snap.items())[-150000:])
            path = self._static_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(items, separators=(",", ":")))
            tmp.replace(path)
        except Exception as e:
            logger.debug("[ais] static cache not saved: %s", e)

    def _sub(self):
        return json.dumps({"APIKey": self.key, "BoundingBoxes": [[[b[0], b[1]], [b[2], b[3]]] for b in self.boxes],
                           "FilterMessageTypes": ["PositionReport", "ShipStaticData", "StandardClassBPositionReport", "StaticDataReport"]})

    def _run(self):
        import asyncio
        import websockets

        async def loop():
            backoff = 5
            while True:
                try:
                    async with websockets.connect("wss://stream.aisstream.io/v0/stream", open_timeout=20, ping_interval=20) as ws:
                        await ws.send(self._sub())
                        self.status, backoff = "live", 5
                        while True:
                            if self.resubscribe:
                                self.resubscribe = False
                                await ws.send(self._sub())
                            try:
                                raw = await asyncio.wait_for(ws.recv(), timeout=60)
                            except asyncio.TimeoutError:
                                continue
                            self._ingest(json.loads(raw))
                except Exception as e:                     # reconnect with backoff (429 = another connection open)
                    self.status = f"reconnecting ({type(e).__name__})"
                    logger.warning("[ais] %s — reconnecting in %ss", e, backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 300)
        asyncio.run(loop())

    def _ingest(self, m: Dict[str, Any]) -> None:
        meta, kind = m.get("MetaData") or {}, m.get("MessageType")
        mmsi = meta.get("MMSI")
        if not mmsi:
            return
        now = time_now()
        with self.lock:
            v = self.ships.get(mmsi)
            if v is None:
                v = self.ships[mmsi] = {"mmsi": mmsi, **self.static.get(mmsi, {})}
            name = (meta.get("ShipName") or "").strip()
            if name:
                v["name"] = name
            if kind in ("PositionReport", "StandardClassBPositionReport"):
                p = m["Message"][kind]
                sp, co, hd = _ais_clean(p.get("Sog"), p.get("Cog"), p.get("TrueHeading"))
                v.update({"lat": p.get("Latitude"), "lon": p.get("Longitude"), "speed": sp, "course": co,
                          "heading": hd, "status": p.get("NavigationalStatus"), "seen": now})
            elif kind == "ShipStaticData":
                d = m["Message"]["ShipStaticData"]
                ident = {"type": _ship_type(d.get("Type")), "destination": (d.get("Destination") or "").strip(),
                         "draught": d.get("MaximumStaticDraught"), "imo": d.get("ImoNumber") or None, "callsign": (d.get("CallSign") or "").strip()}
                v.update(ident)
                self.static[mmsi] = {**ident, **({"name": v["name"]} if v.get("name") else {})}
                v.setdefault("seen", now)
            elif kind == "StaticDataReport":             # class B (smaller vessels): part B carries the type
                d = m["Message"]["StaticDataReport"]
                rb = d.get("ReportB") or {}
                if rb.get("Valid") and rb.get("ShipType") is not None:
                    v["type"] = _ship_type(rb.get("ShipType"))
                    self.static[mmsi] = {**self.static.get(mmsi, {}), "type": v["type"], **({"name": v["name"]} if v.get("name") else {})}
                v.setdefault("seen", now)
            if now - self.static_saved > 300 and self.static:
                self.static_saved = now
                import threading
                snap = dict(self.static)                 # copied under the lock; written off the stream thread
                threading.Thread(target=self._save_static, args=(snap,), daemon=True).start()
            if len(self.ships) > 60000:                   # prune stale ships
                cutoff = now - self.MAX_AGE
                for k in [k for k, x in self.ships.items() if x.get("seen", 0) < cutoff]:
                    self.ships.pop(k, None)


def _ais_clean(speed, course, heading):
    """AIS 'not available' codes: speed 102.3 kn, course 360°, heading 511 → None."""
    sp = speed if speed is not None and speed < 102.2 else None
    co = course if course is not None and course < 360 else None
    hd = heading if heading is not None and heading < 360 else None
    return sp, co, hd


def time_now() -> float:
    import time as _t
    return _t.time()


_collector: Optional[_AisCollector] = None


def ais_collector() -> Optional[_AisCollector]:
    """Start the live collector once (only when a key is configured)."""
    global _collector
    key = os.getenv("AISSTREAM_API_KEY") or ""
    if key and _collector is None:
        _collector = _AisCollector(key)
    return _collector


def vessels(lat_min: float, lon_min: float, lat_max: float, lon_max: float, seconds: int = 12) -> Dict[str, Any]:
    """Live vessel positions in a bounding box: aisstream.io (global, persistent collector) if a
    key is configured, otherwise Fintraffic Digitraffic (Baltic Sea only)."""
    box = (round(lat_min, 2), round(lon_min, 2), round(lat_max, 2), round(lon_max, 2))
    col = ais_collector()
    if col:
        col.watch(box)
        ships = col.snapshot(box)
        age = time_now() - col.started
        for v in ships:
            v.setdefault("type", "Unknown")
        return {"source": "aisstream.io (live AIS, community receivers)", "box": box, "vessels": ships, "status": col.status,
                "coverage": "global where volunteer receivers exist — dense in NW Europe, thinner in parts of Asia and the Middle East"
                            + (f"; still building the picture ({int(age)}s since start — anchored ships report every few minutes)" if age < 300 else ""),
                "listening_since": int(age)}
    return _cached("digitraffic", 120, lambda: _digitraffic(box))


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
        sp, co, hd = _ais_clean(p.get("sog"), p.get("cog"), p.get("heading"))
        out.append({"mmsi": p["mmsi"], "lat": lat, "lon": lon, "speed": sp, "course": co, "heading": hd,
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


# ── Vessel identity and port calls (Global Fishing Watch API, free token) ───
GFW = "https://gateway.api.globalfishingwatch.org/v3"
FLAGS = {"PAN": "Panama", "LBR": "Liberia", "MHL": "Marshall Islands", "HKG": "Hong Kong", "SGP": "Singapore", "MLT": "Malta",
         "BHS": "Bahamas", "GRC": "Greece", "CHN": "China", "CYP": "Cyprus", "NOR": "Norway", "GBR": "United Kingdom", "JPN": "Japan",
         "DNK": "Denmark", "PRT": "Portugal", "ITA": "Italy", "USA": "United States", "TWN": "Taiwan", "KOR": "South Korea", "DEU": "Germany",
         "NLD": "Netherlands", "IND": "India", "IDN": "Indonesia", "MYS": "Malaysia", "RUS": "Russia", "TUR": "Türkiye", "BEL": "Belgium",
         "FRA": "France", "ESP": "Spain", "LKA": "Sri Lanka", "ARE": "UAE", "SAU": "Saudi Arabia", "EGY": "Egypt", "VNM": "Vietnam"}


def vessel_info(query: str) -> Dict[str, Any]:
    token = os.getenv("GFW_API_TOKEN") or ""
    if not token:
        raise NotFound("Vessel identity needs a free Global Fishing Watch token (GFW_API_TOKEN).")
    q = query.strip()

    def fetch():
        import requests
        h = {"Authorization": f"Bearer {token}", **UA}
        r = requests.get(f"{GFW}/vessels/search", headers=h, timeout=30,
                         params={"query": q, "datasets[0]": "public-global-vessel-identity:latest", "limit": 10, "includes[0]": "OWNERSHIP"})
        if r.status_code in (401, 403):
            raise Upstream("Global Fishing Watch refused the token.")
        r.raise_for_status()
        entries = r.json().get("entries") or []
        if not entries:
            raise NotFound(f"No vessel found for '{q}'.")

        def ident(e):
            return (e.get("selfReportedInfo") or [{}])[0]
        # the vessel asked for: exact MMSI match first, else the most recently transmitting
        best = next((e for e in entries if ident(e).get("ssvid") == q), None) or \
            max(entries, key=lambda e: ident(e).get("transmissionDateTo") or "")
        imo = ident(best).get("imo")
        same = [e for e in entries if imo and ident(e).get("imo") == imo] or [best]
        history = sorted(({"name": ident(e).get("shipname"), "flag": ident(e).get("flag"), "flag_name": FLAGS.get(ident(e).get("flag") or "", ident(e).get("flag")),
                           "mmsi": ident(e).get("ssvid"), "callsign": ident(e).get("callsign"), "from": (ident(e).get("transmissionDateFrom") or "")[:10],
                           "to": (ident(e).get("transmissionDateTo") or "")[:10]} for e in same), key=lambda x: x["to"], reverse=True)
        owners = [{"name": o.get("name"), "flag": o.get("flag"), "from": (o.get("dateFrom") or "")[:10], "to": (o.get("dateTo") or "")[:10]}
                  for e in same for o in (e.get("registryOwners") or [])]
        types = sorted({t["name"] for e in same for c in (e.get("combinedSourcesInfo") or []) for t in c.get("shiptypes", [])} - {"NA", "OTHER"})
        reg = next((ri for e in same for ri in (e.get("registryInfo") or [])), {})
        ids = [ident(e).get("id") for e in same if ident(e).get("id")]
        params = {"datasets[0]": "public-global-port-visits-events:latest", "start-date": str(date.today() - timedelta(days=180)),
                  "end-date": str(date.today()), "limit": 25, "offset": 0, "sort": "-start"}
        for i, vid in enumerate(ids[:5]):
            params[f"vessels[{i}]"] = vid
        calls = []
        try:
            ev = requests.get(f"{GFW}/events", headers=h, params=params, timeout=30)
            ev.raise_for_status()
            for e in ev.json().get("entries") or []:
                pv = e.get("port_visit") or {}
                a = pv.get("intermediateAnchorage") or pv.get("startAnchorage") or {}
                calls.append({"port": (a.get("name") or "").title() or None, "country": FLAGS.get(a.get("flag") or "", a.get("flag")),
                              "arrived": (e.get("start") or "")[:16].replace("T", " "), "departed": (e.get("end") or "")[:16].replace("T", " "),
                              "hours": round(pv.get("durationHrs") or 0, 1)})
        except Exception as e:
            logger.debug("[gfw] events: %s", e)
        cur = history[0] if history else {}
        return {"query": q, "name": cur.get("name"), "imo": imo, "mmsi": cur.get("mmsi"), "flag": cur.get("flag_name"), "callsign": cur.get("callsign"),
                "types": types, "length_m": reg.get("lengthM"), "tonnage_gt": reg.get("tonnageGt"), "built": reg.get("builtYear"),
                "history": history, "owners": owners, "port_calls": calls,
                "source": "Global Fishing Watch (vessel identity from AIS and registries; port visits from AIS)"}
    return _cached(f"gfw:{q}", 6 * 3600, fetch)
