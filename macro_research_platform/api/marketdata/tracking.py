"""
Physical-economy trackers, free sources:

  SHIP  · Chokepoints: IMF PortWatch — daily vessel transits and cargo capacity through 28
          maritime chokepoints (Suez, Panama, Hormuz, Malacca…) from satellite AIS, by
          vessel type. Updated weekly, a few days behind.
        · Live vessels: aisstream.io, one whole-world subscription (free API key in
          AISSTREAM_API_KEY) holding every ship heard in the last hour with an 8-hour track;
          without a key, Fintraffic Digitraffic (Finland / Baltic Sea, open data).
        · Port congestion: ships at anchor / moored / moving near 55 major ports.
  FLY   · See airtraffic.py (world snapshot, live areas, routes and tracks).
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
    MAX_AGE = 60 * 60                  # a moored ship reports every 3 min, its identity every 6
    TRACK_EVERY = 300                  # one track point per 5 minutes…
    TRACK_POINTS = 96                  # …for the last 8 hours

    def __init__(self, key: str):
        import threading
        self.key = key
        # the whole world: one subscription keeps every vessel the volunteer network hears
        self.boxes = [(-90.0, -180.0, 90.0, 180.0)]
        self.ships: Dict[int, Dict[str, Any]] = {}
        self.tracks: Dict[int, Any] = {}               # mmsi → array('f') of [t-offset, lat, lon, speed] × n
        self.t0 = time_now()
        self.msgs = 0
        self.pruned = time_now()
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
        """Kept for callers: the subscription already covers the whole world."""
        return None

    def all(self) -> List[Dict[str, Any]]:
        cutoff = time_now() - self.MAX_AGE
        with self.lock:
            return [v for v in self.ships.values() if v.get("lat") is not None and v.get("seen", 0) >= cutoff]

    def one(self, mmsi: int) -> Optional[Dict[str, Any]]:
        with self.lock:
            v = self.ships.get(mmsi)
            if v is None:
                return None
            tr = self.tracks.get(mmsi)
            pts = [[round(self.t0 + tr[i]), round(tr[i + 1], 5), round(tr[i + 2], 5), tr[i + 3] if tr[i + 3] >= 0 else None]
                   for i in range(0, len(tr), 4)] if tr is not None else []
            return {**v, "track": pts}

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
                lat, lon = p.get("Latitude"), p.get("Longitude")
                if lat is None or lon is None or abs(lat) > 90 or abs(lon) > 180 or (lat == 0 and lon == 0):
                    return                                   # 91/181 = "not available"
                v.update({"lat": lat, "lon": lon, "speed": sp, "course": co,
                          "heading": hd, "status": p.get("NavigationalStatus"), "seen": now})
                self.msgs += 1
                self._track(mmsi, now, lat, lon, sp)
            elif kind == "ShipStaticData":
                d = m["Message"]["ShipStaticData"]
                dim = d.get("Dimension") or {}
                length = (dim.get("A") or 0) + (dim.get("B") or 0)
                beam = (dim.get("C") or 0) + (dim.get("D") or 0)
                eta = d.get("Eta") or {}
                ident = {"type": _ship_type(d.get("Type")), "type_code": d.get("Type"), "destination": (d.get("Destination") or "").strip(),
                         "draught": d.get("MaximumStaticDraught") or None, "imo": d.get("ImoNumber") or None, "callsign": (d.get("CallSign") or "").strip(),
                         "length_m": length if 0 < length < 500 else None, "beam_m": beam if 0 < beam < 80 else None,
                         "eta": (f"{eta['Month']:02d}-{eta['Day']:02d} {eta.get('Hour', 0):02d}:{eta.get('Minute', 0):02d}"
                                 if eta.get("Month") and eta.get("Day") and eta.get("Hour", 24) < 24 and eta.get("Minute", 60) < 60 else None)}
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
            if now - self.pruned > 300 or len(self.ships) > 400000:     # drop ships not heard for an hour
                self.pruned = now
                cutoff = now - self.MAX_AGE
                for k in [k for k, x in self.ships.items() if x.get("seen", 0) < cutoff]:
                    self.ships.pop(k, None)
                    self.tracks.pop(k, None)

    def _track(self, mmsi: int, now: float, lat: float, lon: float, sp: Optional[float]) -> None:
        """Compact track history (called under the lock): a point every 5 minutes, 8 hours kept."""
        from array import array
        tr = self.tracks.get(mmsi)
        t = now - self.t0
        if tr is None:
            self.tracks[mmsi] = array("f", [t, lat, lon, sp if sp is not None else -1])
            return
        if t - tr[-4] < self.TRACK_EVERY:
            return
        if abs(lat - tr[-3]) < 0.0005 and abs(lon - tr[-2]) < 0.0005:       # not moving: refresh the time only
            tr[-4] = t
            return
        tr.extend((t, lat, lon, sp if sp is not None else -1))
        if len(tr) > 4 * self.TRACK_POINTS:
            del tr[:4]


def _ais_clean(speed, course, heading):
    """AIS 'not available' codes (speed 102.3 kn, course 360°, heading 511) and impossible speeds → None."""
    sp = speed if speed is not None and speed <= 60 else None          # 102.3 = not available; above ~60 kn is a bad fix
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


# Maritime identification digits (first 3 of an MMSI) → flag state, for the common registries
MID = {201: "Albania", 205: "Belgium", 209: "Cyprus", 210: "Cyprus", 211: "Germany", 212: "Cyprus", 215: "Malta", 218: "Germany",
       219: "Denmark", 220: "Denmark", 224: "Spain", 225: "Spain", 226: "France", 227: "France", 228: "France", 229: "Malta",
       230: "Finland", 231: "Faroe Islands", 232: "United Kingdom", 233: "United Kingdom", 234: "United Kingdom", 235: "United Kingdom",
       236: "Gibraltar", 237: "Greece", 238: "Croatia", 239: "Greece", 240: "Greece", 241: "Greece", 244: "Netherlands", 245: "Netherlands",
       246: "Netherlands", 247: "Italy", 248: "Malta", 249: "Malta", 250: "Ireland", 255: "Portugal (Madeira)", 256: "Malta", 257: "Norway",
       258: "Norway", 259: "Norway", 261: "Poland", 263: "Portugal", 265: "Sweden", 266: "Sweden", 271: "Türkiye", 272: "Ukraine",
       273: "Russia", 275: "Latvia", 276: "Estonia", 277: "Lithuania", 304: "Antigua & Barbuda", 305: "Antigua & Barbuda", 308: "Bahamas",
       309: "Bahamas", 311: "Bahamas", 314: "Barbados", 316: "Canada", 319: "Cayman Islands", 338: "United States", 341: "St Kitts & Nevis",
       345: "Mexico", 351: "Panama", 352: "Panama", 353: "Panama", 354: "Panama", 355: "Panama", 356: "Panama", 357: "Panama", 366: "United States",
       367: "United States", 368: "United States", 369: "United States", 370: "Panama", 371: "Panama", 372: "Panama", 373: "Panama",
       374: "Panama", 375: "St Vincent & Grenadines", 376: "St Vincent & Grenadines", 377: "St Vincent & Grenadines", 403: "Saudi Arabia",
       405: "Bangladesh", 412: "China", 413: "China", 414: "China", 416: "Taiwan", 417: "Sri Lanka", 419: "India", 422: "Iran", 425: "Iraq",
       428: "Israel", 431: "Japan", 432: "Japan", 436: "Kazakhstan", 440: "South Korea", 441: "South Korea", 445: "North Korea",
       447: "Kuwait", 450: "Lebanon", 457: "Mongolia", 461: "Oman", 463: "Pakistan", 466: "Qatar", 468: "Syria", 470: "UAE", 471: "UAE",
       477: "Hong Kong", 501: "France (Adélie)", 503: "Australia", 512: "New Zealand", 514: "Cambodia", 525: "Indonesia", 533: "Malaysia",
       538: "Marshall Islands", 548: "Philippines", 563: "Singapore", 564: "Singapore", 565: "Singapore", 566: "Singapore", 567: "Thailand",
       574: "Vietnam", 576: "Vanuatu", 577: "Vanuatu", 620: "Comoros", 622: "Egypt", 636: "Liberia", 637: "Liberia", 667: "Sierra Leone",
       671: "Togo", 677: "Tanzania", 701: "Argentina", 710: "Brazil", 725: "Chile", 730: "Colombia", 735: "Ecuador", 760: "Peru", 770: "Uruguay",
       775: "Venezuela", 518: "Cook Islands", 572: "Tuvalu", 312: "Belize", 325: "Jamaica", 339: "Jamaica", 362: "Trinidad & Tobago"}
NAV_STATUS = {0: "Under way (engine)", 1: "At anchor", 2: "Not under command", 3: "Restricted manoeuvrability", 4: "Constrained by draught",
              5: "Moored", 6: "Aground", 7: "Fishing", 8: "Under way (sailing)", 14: "AIS-SART (distress)"}
TYPE_CODES = ["Cargo", "Tanker", "Passenger", "Fishing", "Tug", "Towing", "Military", "Sailing/pleasure", "Other", "Unknown"]
WORLD_SHIP_COLS = ["mmsi", "lat", "lon", "speed", "heading", "type", "status", "name", "sat", "tag"]   # sat: 1 = GFW position (days old)
# tag letters (vessel_intel.notable_reasons): s sanctioned, m military, l gas carrier, g giant, h dangerous goods, z tanker in a hot zone


def flag_of(mmsi: Any) -> Optional[str]:
    m = str(mmsi or "")
    return MID.get(int(m[:3])) if len(m) == 9 and m[:3].isdigit() and m[0] in "234567" else None


def _phase(v: Dict[str, Any]) -> str:
    """underway / anchored / moored, from the navigational status (and speed when it's unset)."""
    st, sp = v.get("status"), v.get("speed")
    if st == 5:
        return "moored"
    if st == 1 or (st in (None, 15) and sp is not None and sp < 0.5):
        return "anchored"
    return "underway"


# ── Satellite + terrestrial AIS presence (Global Fishing Watch), worldwide, ~3 days behind ──
# The live feed only hears ships near volunteer receivers — thin in China, most of Asia, Africa,
# Latin America and the open ocean. GFW's presence data (satellite and terrestrial AIS) covers all
# of it, a few days late and on a 0.1° grid. A background job pulls the last available day in
# 15° boxes once a day and keeps each vessel's latest cell.
GFW_TYPES = {"CARGO": "Cargo", "CARRIER": "Cargo", "TANKER": "Tanker", "BUNKER": "Tanker", "FISHING": "Fishing", "PASSENGER": "Passenger",
             "SUPPORT": "Other", "SEISMIC_VESSEL": "Other", "OTHER": "Other", "DISCREPANCY": "Unknown", "NA": "Unknown", "": "Unknown"}
_presence: Dict[str, Any] = {"rows": {}, "day": None, "built": None, "status": "not started", "boxes_done": 0, "boxes": 0}
_presence_lock = __import__("threading").Lock()


def _presence_path():
    from pathlib import Path
    return Path(__file__).resolve().parents[2] / "data" / "processed" / "gfw_presence.json"


def _presence_load() -> None:
    try:
        d = json.loads(_presence_path().read_text())
        with _presence_lock:
            _presence.update(rows={int(k): v for k, v in d["rows"].items()}, day=d["day"], built=d["built"], status="ready (from disk)")
    except Exception:
        pass


def _presence_build() -> None:
    """Pull one day of GFW presence for the whole world (≈240 boxes) and keep each vessel's latest
    0.1° cell. Runs in a background thread; takes several minutes."""
    import requests
    import time as _t
    token = os.getenv("GFW_API_TOKEN") or ""
    if not token:
        _presence["status"] = "no GFW token"
        return
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", **UA}
    url = f"{GFW}/4wings/report"
    # latest day with data: GFW's presence layer runs ~2–4 days behind
    day = None
    for back in (2, 3, 4, 5):
        d0 = date.today() - timedelta(days=back)
        probe = {"type": "Polygon", "coordinates": [[[103, 1], [104.5, 1], [104.5, 1.5], [103, 1.5], [103, 1]]]}    # Singapore Strait
        try:
            r = requests.post(url, headers=h, timeout=60, json={"geojson": probe}, params={
                "spatial-resolution": "LOW", "temporal-resolution": "ENTIRE", "datasets[0]": "public-global-presence:latest",
                "date-range": f"{d0},{d0 + timedelta(days=1)}", "format": "JSON", "group-by": "VESSEL_ID"})
            if r.ok and any(list(e.values())[0] for e in r.json().get("entries", [])):
                day = d0
                break
        except Exception as e:
            logger.info("[gfw] probe %s: %s", d0, e)
    if not day:
        _presence["status"] = "GFW presence data unavailable"
        return
    boxes = [(lo, la) for la in range(-75, 90, 15) for lo in range(-180, 180, 15)]
    _presence.update(status="building", boxes=len(boxes), boxes_done=0)
    latest: Dict[int, list] = {}
    for lo, la in boxes:
        geo = {"type": "Polygon", "coordinates": [[[lo, la], [lo + 15, la], [lo + 15, la + 15], [lo, la + 15], [lo, la]]]}
        for attempt in range(3):
            try:
                r = requests.post(url, headers=h, timeout=180, json={"geojson": geo}, params={
                    "spatial-resolution": "LOW", "temporal-resolution": "ENTIRE", "datasets[0]": "public-global-presence:latest",
                    "date-range": f"{day},{day + timedelta(days=1)}", "format": "JSON", "group-by": "VESSEL_ID"})
                if r.status_code == 429:
                    _t.sleep(20 * (attempt + 1))
                    continue
                r.raise_for_status()
                for e in r.json().get("entries", []):
                    for x in list(e.values())[0] or []:
                        vt = (x.get("vesselType") or "").upper()
                        mmsi = str(x.get("mmsi") or "")
                        if vt == "GEAR" or not mmsi.isdigit() or len(mmsi) != 9:      # net buoys and bad ids
                            continue
                        m, ts = int(mmsi), x.get("exitTimestamp") or ""
                        if m in latest and latest[m][7] >= ts:
                            continue
                        latest[m] = [round(x["lat"], 2), round(x["lon"], 2), GFW_TYPES.get(vt, "Other"), x.get("flag") or "",
                                     (x.get("shipName") or "").strip(), x.get("imo") or "", x.get("callsign") or "", ts]
                break
            except Exception as e:
                logger.info("[gfw] box %s,%s: %s", lo, la, e)
                _t.sleep(3)
        _presence["boxes_done"] += 1
        _t.sleep(0.3)
    if latest:
        built = int(time_now())
        with _presence_lock:
            _presence.update(rows=latest, day=str(day), built=built, status="ready")
        try:
            _presence_path().write_text(json.dumps({"rows": latest, "day": str(day), "built": built}, separators=(",", ":")))
        except Exception as e:
            logger.info("[gfw] not saved: %s", e)
        logger.info("[gfw] presence: %d vessels for %s", len(latest), day)
    else:
        _presence["status"] = "no vessels returned"


def presence_start() -> None:
    """Load the last presence snapshot, then rebuild in the background when it is a day old."""
    import threading
    _presence_load()
    def loop():
        import time as _t
        while True:
            if not _presence.get("built") or time_now() - _presence["built"] > 20 * 3600:
                try:
                    _presence_build()
                except Exception as e:
                    logger.warning("[gfw] presence build failed: %s", e)
                    _presence["status"] = f"failed: {e}"
            _t.sleep(3600)
    threading.Thread(target=loop, name="gfw-presence", daemon=True).start()


_sat_cache: Dict[str, Any] = {"built": None, "rows": []}


def _sat_rows() -> List[list]:
    idx = {t: i for i, t in enumerate(TYPE_CODES)}
    with _presence_lock:
        if _sat_cache["built"] != _presence.get("built"):
            # GFW positions are 0.1° cell centres: scatter each vessel within its cell (stable per MMSI) so a
            # busy area reads as traffic, not a grid — the true position is only known to ±5 km anyway
            def jit(m: int, salt: int) -> float:
                z = (m * 0x9E3779B97F4A7C15 + salt * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF   # splitmix64: no pattern
                z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
                z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
                z ^= z >> 31
                return (z / 0xFFFFFFFFFFFFFFFF - 0.5) * 0.095
            def wrap(lon: float) -> float:                  # scatter near the date line must stay on the map
                return ((lon + 180) % 360) - 180
            from api.marketdata import vessel_intel as VI

            def tag(m: int, p: list) -> str:
                return "".join(t for _, t, _ in VI.notable_reasons({"mmsi": m, "imo": p[5], "name": p[4], "type": p[2], "lat": p[0], "lon": p[1]}))
            _sat_cache["rows"] = [[m, round(max(-89.99, min(89.99, p[0] + jit(m, 1))), 4), round(wrap(p[1] + jit(m, 2)), 4), None, None,
                                   idx.get(p[2], idx["Other"]), None, p[4], 1, tag(m, p)] for m, p in _presence["rows"].items()]
            _sat_cache["built"] = _presence.get("built")
        return _sat_cache["rows"]


def world_vessels_json() -> bytes:
    """world_vessels() pre-serialised (≈250,000 rows: generic response encoding takes seconds)."""
    return _cached("ship:world:bytes", 15, lambda: json.dumps(world_vessels(), separators=(",", ":")).encode())


def world_vessels() -> Dict[str, Any]:
    col = ais_collector()
    if not col:
        raise NotFound("Global ship tracking needs a free aisstream.io key (AISSTREAM_API_KEY).")

    def build():
        from api.marketdata import vessel_intel as VI
        rows, by_type, phase = [], {t: 0 for t in TYPE_CODES}, {"underway": 0, "anchored": 0, "moored": 0}
        idx = {t: i for i, t in enumerate(TYPE_CODES)}
        live_ids = set()
        for v in col.all():
            live_ids.add(v["mmsi"])
            t = v.get("type") or "Unknown"
            ti = idx.get(t, idx["Other"])
            by_type[TYPE_CODES[ti]] += 1
            phase[_phase(v)] += 1
            hd = v.get("heading") if v.get("heading") is not None else v.get("course")
            rows.append([v["mmsi"], round(v["lat"], 4), round(v["lon"], 4), round(v["speed"], 1) if v.get("speed") is not None else None,
                         round(hd) if hd is not None else None, ti, v.get("status"), v.get("name") or "", 0,
                         "".join(t for _, t, _ in VI.notable_reasons(v))])
        n_live = len(rows)
        sat_by_type = {t: 0 for t in TYPE_CODES}
        for r in _sat_rows():                          # prebuilt once per daily snapshot
            if r[0] in live_ids:
                continue
            sat_by_type[TYPE_CODES[r[5]]] += 1
            rows.append(r)
        age = time_now() - col.started
        return {"cols": WORLD_SHIP_COLS, "types": TYPE_CODES, "rows": rows, "by_type": by_type, "phase": phase, "status": col.status,
                "live_count": n_live, "satellite_count": len(rows) - n_live, "satellite_by_type": sat_by_type,
                "satellite": {"day": _presence.get("day"), "status": _presence.get("status"), "boxes_done": _presence.get("boxes_done"), "boxes": _presence.get("boxes"),
                              "source": "Global Fishing Watch AIS presence (satellite + terrestrial), last available day, 0.1° grid"},
                "listening_s": int(age), "time": int(time_now()),
                "source": "Live: aisstream.io (volunteer AIS receivers). Elsewhere: Global Fishing Watch satellite AIS, a few days behind",
                "coverage": "Coastal and port waters where volunteer receivers exist — dense in Europe, North America, Japan, "
                            "Singapore and parts of China; open ocean is not covered (no satellite AIS)."
                            + (f" The picture is still filling in ({int(age // 60)} min since start — anchored ships report every "
                               "few minutes, identities every 6)." if age < 900 else "")}
    return _cached("ship:world", 15, build)


TAG_NAMES = {"s": "Sanctioned (OFAC)", "m": "Military", "l": "Gas carriers", "g": "Giants (VLCC / ULCV)", "h": "Dangerous goods (cat. A)",
             "z": "Tankers in hot zones"}


def notable_ships(limit: int = 600) -> Dict[str, Any]:
    """Ships worth following, with the reason: sanctioned vessels first, then warships, gas carriers,
    giants, dangerous cargo and tankers in the Gulf / Red Sea / Black Sea / Taiwan Strait."""
    def build():
        from api.marketdata import vessel_intel as VI
        w = world_vessels()
        ix = {c: i for i, c in enumerate(w["cols"])}
        col = ais_collector()
        out, counts = [], {k: 0 for k in TAG_NAMES}
        for r in w["rows"]:
            tags = r[ix["tag"]]
            if not tags:
                continue
            m = r[ix["mmsi"]]
            if r[ix["sat"]]:
                p = _presence["rows"].get(m) or [None] * 8
                rec = {"mmsi": m, "imo": p[5], "name": p[4], "type": p[2], "lat": r[ix["lat"]], "lon": r[ix["lon"]]}
            else:
                with col.lock:
                    rec = dict(col.ships.get(m) or {})
            reasons = VI.notable_reasons(rec)
            for t in set(tags):
                if t in counts:
                    counts[t] += 1
            out.append({"mmsi": m, "name": r[ix["name"]] or f"MMSI {m}", "type": w["types"][r[ix["type"]]], "lat": r[ix["lat"]], "lon": r[ix["lon"]],
                        "speed": r[ix["speed"]], "satellite": bool(r[ix["sat"]]), "tags": tags, "priority": reasons[0][0] if reasons else 9,
                        "reasons": [x for _, _, x in reasons], "destination": (rec.get("destination") or None) if not r[ix["sat"]] else None})
        out.sort(key=lambda x: (x["priority"], x["satellite"], x["name"]))
        return {"ships": out[:limit], "total": len(out), "counts": counts, "tag_names": TAG_NAMES,
                "source": "OFAC SDN list (US Treasury), live AIS and Global Fishing Watch positions",
                "note": "Sanctioned = the IMO or MMSI appears on the US Treasury's SDN list. Sizes and gas carriers come from AIS dimensions "
                        "and names; hot zones are the Gulf/Hormuz, Red Sea, Gulf of Aden, Black Sea and Taiwan Strait."}
    return _cached("ship:notable", 60, build)


def vessel_live(mmsi: int) -> Dict[str, Any]:
    col = ais_collector()
    v = col.one(int(mmsi)) if col else None
    if not v:
        p = _presence["rows"].get(int(mmsi))
        if not p:
            raise NotFound(f"No recent AIS position for MMSI {mmsi}.")
        return _enrich({"mmsi": int(mmsi), "name": p[4] or None, "type": p[2], "imo": p[5] or None, "callsign": p[6] or None,
                        "lat": p[0], "lon": p[1], "flag": FLAGS.get(p[3], p[3]) if p[3] else flag_of(mmsi), "phase": None,
                        "status_text": f"Satellite position ({(p[7] or '')[:16].replace('T', ' ')} UTC)", "satellite": True,
                        "position_time": p[7], "track": [],
                        "note": "Outside live receiver range: last position from Global Fishing Watch satellite AIS (a few days old, ±5 km)."})
    out = {k: v.get(k) for k in ("mmsi", "name", "type", "type_code", "callsign", "imo", "destination", "eta", "draught", "length_m", "beam_m",
                                  "lat", "lon", "speed", "course", "heading", "status")}
    out.update({"flag": flag_of(v.get("mmsi")), "status_text": NAV_STATUS.get(v.get("status")), "phase": _phase(v),
                "seen_s": round(time_now() - v.get("seen", time_now())), "track": v.get("track") or []})
    return _enrich(out)


def _enrich(out: Dict[str, Any]) -> Dict[str, Any]:
    """Voyage, cargo profile, sanctions and notable reasons for one vessel record."""
    from api.marketdata import vessel_intel as VI
    out["profile"] = VI.profile(out)
    out["voyage"] = VI.decode_dest(out.get("destination"))
    s = VI.sanctioned(out.get("imo"), out.get("mmsi"))
    out["sanctions"] = s
    out["notable"] = [r for _, _, r in VI.notable_reasons(out)]
    # where it came from: the last completed port call (Global Fishing Watch, cached 6 h)
    try:
        info = vessel_info(str(out.get("imo") or out.get("mmsi")))
        calls = [c for c in info.get("port_calls") or [] if c.get("departed")]
        if calls:
            out["last_port"] = calls[0]
        out["owners"] = info.get("owners")
        out["built"] = info.get("built")
        out["tonnage_gt"] = info.get("tonnage_gt")
        # satellite-only ships carry no AIS dimensions: the registry's length and type fill the profile
        refine = False
        if not out.get("length_m") and info.get("length_m"):
            out["length_m"], refine = info["length_m"], True
        if info.get("tonnage_gt"):
            refine = True
        sanc_type = ((out.get("sanctions") or {}).get("type") or "")
        types = (" ".join(info.get("types") or []) + " " + sanc_type).upper()
        if out.get("type") in (None, "Other", "Unknown") and types:
            t = "Tanker" if "TANKER" in types or "LNG" in types or "LPG" in types else "Cargo" if any(k in types for k in ("CARGO", "CONTAINER", "BULK", "CARRIER")) \
                else "Passenger" if "PASSENGER" in types else "Fishing" if "FISH" in types else None
            if t:
                out["type"], refine = t, True
        if refine:
            out["profile"] = VI.profile(out)
            out["notable"] = [r for _, _, r in VI.notable_reasons(out)]
    except Exception as e:
        logger.debug("[ship] no GFW record for %s: %s", out.get("mmsi"), e)
    return out


def port_congestion(radius_km: float = 30) -> Dict[str, Any]:
    """Ships waiting (at anchor) and berthed (moored) near each major port, by kind — a live
    read on port congestion from the AIS picture."""
    col = ais_collector()
    if not col:
        raise NotFound("Port congestion needs a free aisstream.io key (AISSTREAM_API_KEY).")

    def build():
        cells: Dict[tuple, List[Dict[str, Any]]] = {}
        for v in col.all():
            cells.setdefault((int(math.floor(v["lat"])), int(math.floor(v["lon"]))), []).append(v)
        out = []
        for name, (plat, plon) in MAJOR_PORTS.items():
            c = {"port": name, "lat": plat, "lon": plon, "anchored": 0, "moored": 0, "underway": 0, "cargo_waiting": 0, "tankers_waiting": 0}
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    for v in cells.get((int(math.floor(plat)) + dy, int(math.floor(plon)) + dx), []):
                        if _km(plat, plon, v["lat"], v["lon"]) > radius_km:
                            continue
                        ph = _phase(v)
                        c[ph] += 1
                        if ph == "anchored" and v.get("type") == "Cargo":
                            c["cargo_waiting"] += 1
                        if ph == "anchored" and v.get("type") == "Tanker":
                            c["tankers_waiting"] += 1
            c["total"] = c["anchored"] + c["moored"] + c["underway"]
            out.append(c)
        out.sort(key=lambda c: -c["anchored"])
        return {"ports": out, "radius_km": radius_km, "listening_s": int(time_now() - col.started),
                "note": "Within 30 km of each port: at anchor (usually waiting for a berth), moored (at berth) and moving. "
                        "Counts depend on receiver coverage, so compare a port with itself over time rather than across ports."}
    return _cached("ship:ports", 60, build)


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
