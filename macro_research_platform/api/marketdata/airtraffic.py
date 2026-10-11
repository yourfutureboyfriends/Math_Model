"""
FLY — live air traffic, free sources:

  world()          every aircraft with a position worldwide: OpenSky Network state vectors
                   (anonymous: 400 credits a day, 4 per world snapshot → refreshed every 15
                   minutes; every 3 minutes with OPENSKY_CLIENT_ID + OPENSKY_CLIENT_SECRET),
                   plus military aircraft from adsb.lol (refreshed every minute)
  area()           everything around a point, live (seconds old) and in detail — model,
                   operator, registration, Mach, wind, outside air temperature: adsb.fi open
                   data (adsb.lol as fallback); 250 nautical miles at most
  detail()         one aircraft: route (origin → destination) and airframe from adsbdb.com,
                   the track flown on this flight from OpenSky, and its live state

Positions in the world snapshot carry their own fix time; the screen may project them forward
along their track and labels that it does.
"""
from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from api.marketdata.core import NotFound, Upstream, _cached

logger = logging.getLogger(__name__)
UA = {"User-Agent": "Mozilla/5.0 (macro research terminal)"}
EMERGENCY = {"7500": "Hijack", "7600": "Radio failure", "7700": "Emergency"}
SNAPSHOT = Path(__file__).resolve().parents[2] / "data" / "processed" / "opensky_states.json"
M_TO_FT, MS_TO_KT, MS_TO_FPM = 3.28084, 1.943844, 196.8504

# world snapshot columns (compact rows keep ~10,000 aircraft to a few hundred kB)
WORLD_COLS = ["hex", "callsign", "country", "lon", "lat", "alt", "ground", "speed", "track", "vrate", "squawk", "fix", "mil", "type"]


def _km(a_lat, a_lon, b_lat, b_lon) -> float:
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371 * 2 * math.asin(min(1, math.sqrt(h)))


# ── OpenSky ─────────────────────────────────────────────────────────────────
_token: Dict[str, Any] = {"value": None, "expires": 0.0}
_credits: Dict[str, Any] = {"remaining": None, "at": None}


def _opensky_auth() -> Dict[str, str]:
    """OAuth2 client-credentials token when both id and secret are configured; anonymous otherwise."""
    cid, sec = os.getenv("OPENSKY_CLIENT_ID") or "", os.getenv("OPENSKY_CLIENT_SECRET") or ""
    if not (cid and sec):
        return {}
    if _token["value"] and time.time() < _token["expires"] - 60:
        return {"Authorization": f"Bearer {_token['value']}"}
    import requests
    try:
        r = requests.post("https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token",
                          data={"grant_type": "client_credentials", "client_id": cid, "client_secret": sec}, timeout=20)
        r.raise_for_status()
        j = r.json()
        _token.update(value=j["access_token"], expires=time.time() + float(j.get("expires_in", 1800)))
        return {"Authorization": f"Bearer {_token['value']}"}
    except Exception as e:
        logger.warning("[opensky] token request failed, using anonymous access: %s", e)
        return {}


def _authenticated() -> bool:
    return bool(os.getenv("OPENSKY_CLIENT_ID") and os.getenv("OPENSKY_CLIENT_SECRET"))


def _opensky_states() -> Dict[str, Any]:
    import requests
    r = requests.get("https://opensky-network.org/api/states/all", params={"extended": 1}, headers={**UA, **_opensky_auth()}, timeout=40)
    rem = r.headers.get("X-Rate-Limit-Remaining")
    if rem is not None:
        _credits.update(remaining=int(rem), at=time.time())
    if r.status_code == 429:
        raise Upstream("OpenSky's daily request allowance is used up")
    r.raise_for_status()
    return r.json()


def _kt(v: Optional[float]) -> Optional[int]:
    """Ground speed in knots; above 750 kt (no airliner, few fighters at cruise) is a bad fix."""
    return round(v) if v is not None and 0 <= v <= 750 else None


def _world_rows(j: Dict[str, Any]) -> List[list]:
    rows = []
    for s in j.get("states") or []:
        # icao24, callsign, origin_country, time_position, last_contact, lon, lat, baro_alt, on_ground,
        # velocity, true_track, vertical_rate, sensors, geo_alt, squawk, spi, position_source, category
        if s[5] is None or s[6] is None:
            continue
        alt = s[7] if s[7] is not None else s[13]
        rows.append([s[0], (s[1] or "").strip(), s[2], round(s[5], 4), round(s[6], 4),
                     round(alt * M_TO_FT) if alt is not None and not s[8] else None, 1 if s[8] else 0,
                     _kt(s[9] * MS_TO_KT if s[9] is not None else None), round(s[10]) if s[10] is not None else None,
                     round(s[11] * MS_TO_FPM) if s[11] is not None else None, s[14], s[3] or s[4], 0, None])
    return rows


def _military() -> List[Dict[str, Any]]:
    def fetch():
        import requests
        try:
            r = requests.get("https://api.adsb.lol/v2/mil", headers=UA, timeout=20)
            r.raise_for_status()
            return [a for a in r.json().get("ac", []) if a.get("lat") is not None]
        except Exception as e:
            logger.info("[mil] adsb.lol: %s", e)
            return []
    return _cached("fly:mil", 60, fetch)


def world() -> Dict[str, Any]:
    """OpenSky snapshot (cached by its allowance) merged with the live regional sweep (refreshed often)."""
    def merge():
        base = _world_base()
        by_hex = {r[0]: r for r in base["rows"]}
        added = replaced = 0
        for r in _sweep_rows():
            old = by_hex.get(r[0])
            if old is None:
                added += 1
            elif (old[11] or 0) >= r[11]:
                continue
            else:
                replaced += 1
                r[2] = old[2]                              # keep OpenSky's registration country
                r[12] = r[12] or old[12]
            by_hex[r[0]] = r
        rows = list(by_hex.values())
        air = [r for r in rows if not r[6]]
        return {**base, "rows": rows, "airborne": len(air), "on_ground": len(rows) - len(air),
                "sweep": {"added": added, "refreshed": replaced, "hubs": len(SWEEP), "live_aircraft": added + replaced},
                "emergencies": [{"hex": r[0], "callsign": r[1], "squawk": r[10], "what": EMERGENCY[str(r[10])], "lat": r[4], "lon": r[3]}
                                for r in rows if str(r[10] or "") in EMERGENCY]}
    return _cached("fly:world:merged", 20, merge)


def _world_base() -> Dict[str, Any]:
    ttl = 180 if _authenticated() else 900

    def build():
        stale = None
        try:
            j = _opensky_states()
            rows, at = _world_rows(j), j.get("time")
            try:
                SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
                SNAPSHOT.write_text(json.dumps({"time": at, "rows": rows}, separators=(",", ":")))
            except Exception:
                pass
        except Exception as e:
            try:                                            # out of allowance / down: the last snapshot, labelled
                d = json.loads(SNAPSHOT.read_text())
                rows, at, stale = d["rows"], d["time"], str(e)
            except Exception:
                raise Upstream(f"OpenSky unavailable: {e}")
        by_hex = {r[0]: r for r in rows}
        now = int(time.time())
        for a in _military():                               # live military positions replace or join OpenSky's
            alt = a.get("alt_baro")
            row = [a.get("hex"), (a.get("flight") or "").strip(), (by_hex.get(a.get("hex")) or [None, None, None])[2],
                   round(a["lon"], 4), round(a["lat"], 4), None if alt == "ground" else alt, 1 if alt == "ground" else 0,
                   _kt(a.get("gs")), round(a["track"]) if a.get("track") is not None else None,
                   a.get("baro_rate"), a.get("squawk"), now - int(a.get("seen_pos") or a.get("seen") or 0), 1, a.get("t")]
            by_hex[row[0]] = row
        rows = list(by_hex.values())
        air = [r for r in rows if not r[6]]
        emerg = [{"hex": r[0], "callsign": r[1], "squawk": r[10], "what": EMERGENCY[str(r[10])], "lat": r[4], "lon": r[3]}
                 for r in rows if str(r[10] or "") in EMERGENCY]
        countries: Dict[str, int] = {}
        for r in air:
            if r[2]:
                countries[r[2]] = countries.get(r[2], 0) + 1
        return {"cols": WORLD_COLS, "rows": rows, "time": at, "airborne": len(air), "on_ground": len(rows) - len(air),
                "military": sum(1 for r in rows if r[12]), "emergencies": emerg,
                "top_registrations": sorted(countries.items(), key=lambda kv: -kv[1])[:12],
                "refresh_s": ttl, "stale": stale, "credits_left": _credits["remaining"],
                "source": "OpenSky Network (state vectors" + (", authenticated" if _authenticated() else ", anonymous") + "); military: adsb.lol",
                "note": ("World positions refresh every " + ("3" if _authenticated() else "15") + " minutes (OpenSky's free allowance); "
                         "around ~60 hubs in China, Asia, the Middle East, Africa and Latin America they are live (adsb.fi + adsb.lol sweep); "
                         "zoom in anywhere for live, seconds-old detail.")}
    return _cached("fly:world", ttl, build)


# ── Live area (adsb.fi, adsb.lol fallback) ─────────────────────────────────
_adsbfi_lock = threading.Lock()
_adsbfi_last = [0.0]


def _adsbfi(path: str) -> Dict[str, Any]:
    """adsb.fi open data allows one request a second per client: space them out."""
    import requests
    with _adsbfi_lock:
        wait = 1.1 - (time.time() - _adsbfi_last[0])
        if wait > 0:
            time.sleep(wait)
        _adsbfi_last[0] = time.time()
    r = requests.get(f"https://opendata.adsb.fi/api/v2/{path}", headers=UA, timeout=20)
    r.raise_for_status()
    return r.json()


def _ac(a: Dict[str, Any]) -> Dict[str, Any]:
    alt = a.get("alt_baro")
    sq = str(a.get("squawk") or "")
    em = EMERGENCY.get(sq) or (a.get("emergency") if a.get("emergency") not in (None, "none") else None)
    return {"hex": a.get("hex"), "flight": (a.get("flight") or "").strip(), "reg": a.get("r"), "type": a.get("t"), "model": a.get("desc"),
            "operator": a.get("ownOp"), "year": a.get("year"), "lat": a.get("lat"), "lon": a.get("lon"),
            "alt": None if alt == "ground" else alt, "alt_geom": a.get("alt_geom"), "on_ground": alt == "ground",
            "speed": _kt(a.get("gs")), "ias": a.get("ias"), "tas": a.get("tas"), "mach": a.get("mach"), "track": a.get("track"),
            "vrate": a.get("baro_rate") if a.get("baro_rate") is not None else a.get("geom_rate"),
            "squawk": a.get("squawk"), "emergency": em, "category": a.get("category"),
            "wind_dir": a.get("wd"), "wind_kt": a.get("ws"), "oat_c": a.get("oat"), "sel_alt": a.get("nav_altitude_mcp") or a.get("nav_altitude_fms"),
            "military": bool((a.get("dbFlags") or 0) & 1), "seen_s": a.get("seen_pos", a.get("seen")), "mlat": bool(a.get("mlat"))}


def area(lat: float, lon: float, radius_nm: int = 120) -> Dict[str, Any]:
    radius_nm = max(5, min(int(radius_nm), 250))
    key_lat, key_lon = round(lat * 4) / 4, round(lon * 4) / 4          # nearby requests share one fetch

    def fetch():
        src = "adsb.fi open data"
        try:
            j = _adsbfi(f"lat/{key_lat}/lon/{key_lon}/dist/{radius_nm}")
            raw = j.get("aircraft") or j.get("ac") or []
        except Exception as e:
            logger.info("[fly] adsb.fi failed (%s) — adsb.lol", e)
            import requests
            r = requests.get(f"https://api.adsb.lol/v2/point/{key_lat}/{key_lon}/{radius_nm}", headers=UA, timeout=20)
            if r.status_code != 200:
                raise Upstream(f"adsb.fi and adsb.lol unavailable ({r.status_code})")
            raw, src = r.json().get("ac", []), "adsb.lol"
        ac = [_ac(a) for a in raw if a.get("lat") is not None]
        air = [x for x in ac if not x["on_ground"]]
        return {"center": [key_lat, key_lon], "radius_nm": radius_nm, "aircraft": ac, "airborne": len(air), "on_ground": len(ac) - len(air),
                "emergencies": [x for x in ac if x["emergency"]], "time": int(time.time()),
                "source": f"{src} (community ADS-B receivers; live, seconds old)"}
    return _cached(f"fly:area:{key_lat}:{key_lon}:{radius_nm}", 8, fetch)


# ── Live sweep of thinly covered regions ────────────────────────────────────
# OpenSky's receivers are sparse in China, South & Southeast Asia, the Middle East, Africa and
# Latin America. adsb.fi and adsb.lol have different volunteer feeders there; a background loop
# queries both around ~55 hubs (250 nm each) and keeps every aircraft heard in the last 5 minutes.
# These live positions replace OpenSky's (up to 15-minute-old) ones in the world layer.
SWEEP = [(40.08, 116.58), (31.14, 121.8), (23.39, 113.3), (30.58, 103.95), (25.1, 102.93), (34.45, 108.75), (30.78, 114.21), (43.9, 87.47),
         (45.62, 126.25), (36.27, 120.37), (22.31, 113.92), (25.08, 121.23), (14.51, 121.02), (10.82, 106.65), (21.22, 105.81), (13.69, 100.75),
         (2.75, 101.71), (1.36, 103.99), (-6.13, 106.65), (-7.38, 112.79), (-8.75, 115.17), (28.56, 77.1), (19.09, 72.87), (13.2, 77.71),
         (22.65, 88.45), (17.24, 78.43), (24.91, 67.16), (31.52, 74.4), (25.25, 55.36), (25.27, 51.61), (24.96, 46.7), (21.68, 39.16),
         (30.12, 31.41), (35.42, 51.15), (33.26, 44.23), (9.03, 38.8), (-1.32, 36.93), (6.58, 3.32), (5.6, -0.17), (-26.14, 28.25),
         (-33.97, 18.6), (33.37, -7.59), (36.69, 3.21), (-23.43, -46.47), (-22.81, -43.25), (-15.87, -47.92), (-34.82, -58.54),
         (-33.39, -70.79), (-12.02, -77.11), (4.7, -74.15), (19.44, -99.07), (21.04, -86.87), (9.07, -79.38), (55.97, 37.41), (43.36, 77.04),
         (41.26, 69.28), (33.62, 73.1), (27.7, 85.36), (23.84, 90.4), (16.9, 96.13)]
_sweep: Dict[str, Dict[str, Any]] = {}
_sweep_lock = threading.Lock()
_lol_last = [0.0]
SWEEP_KEEP = 300


def _adsblol_point(lat: float, lon: float) -> List[Dict[str, Any]]:
    import requests
    wait = 1.5 - (time.time() - _lol_last[0])
    if wait > 0:
        time.sleep(wait)
    _lol_last[0] = time.time()
    r = requests.get(f"https://api.adsb.lol/v2/point/{lat}/{lon}/250", headers=UA, timeout=20)
    r.raise_for_status()
    return r.json().get("ac") or []


def _sweep_once() -> int:
    n = 0
    for i, (lat, lon) in enumerate(SWEEP):
        for fetch in (lambda: (_adsbfi(f"lat/{lat}/lon/{lon}/dist/250").get("aircraft") or []), lambda: _adsblol_point(lat, lon)):
            try:
                raw = fetch()
            except Exception as e:
                logger.debug("[sweep] %s,%s: %s", lat, lon, e)
                continue
            now = time.time()
            with _sweep_lock:
                for a in raw:
                    if a.get("lat") is None or not a.get("hex"):
                        continue
                    fix = now - float(a.get("seen_pos") or a.get("seen") or 0)
                    cur = _sweep.get(a["hex"])
                    if cur is None or cur["fix"] < fix:
                        _sweep[a["hex"]] = {**_ac(a), "fix": fix}
                        n += 1
        with _sweep_lock:                                  # forget aircraft not heard for 5 minutes
            cut = time.time() - SWEEP_KEEP
            for k in [k for k, v in _sweep.items() if v["fix"] < cut]:
                del _sweep[k]
    return n


def sweep_start() -> None:
    def loop():
        while True:
            try:
                _sweep_once()
            except Exception as e:
                logger.warning("[sweep] %s", e)
            time.sleep(20)
    threading.Thread(target=loop, name="adsb-sweep", daemon=True).start()


def _sweep_rows() -> List[list]:
    with _sweep_lock:
        return [[v["hex"], v["flight"], None, round(v["lon"], 4), round(v["lat"], 4), v["alt"], 1 if v["on_ground"] else 0,
                 round(v["speed"]) if v.get("speed") is not None else None, round(v["track"]) if v.get("track") is not None else None,
                 v.get("vrate"), v.get("squawk"), int(v["fix"]), 1 if v.get("military") else 0, v.get("type")] for v in _sweep.values()]


# ── One aircraft ────────────────────────────────────────────────────────────
def _adsbdb(path: str) -> Optional[Dict[str, Any]]:
    import requests
    try:
        r = requests.get(f"https://api.adsbdb.com/v0/{path}", headers=UA, timeout=15)
        if r.status_code != 200:
            return None
        resp = r.json().get("response")
        return resp if isinstance(resp, dict) else None
    except Exception as e:
        logger.debug("[adsbdb] %s: %s", path, e)
        return None


def _airport(a: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not a:
        return None
    return {"iata": a.get("iata_code"), "icao": a.get("icao_code"), "name": a.get("name"), "city": a.get("municipality"),
            "country": a.get("country_name"), "lat": a.get("latitude"), "lon": a.get("longitude")}


def detail(hex_id: str, callsign: Optional[str] = None) -> Dict[str, Any]:
    h = hex_id.strip().lower()
    if not h or len(h) > 8 or not all(c in "0123456789abcdef~" for c in h):
        raise NotFound("Not an aircraft address.")
    cs = (callsign or "").strip().upper() or None

    airframe = _cached(f"fly:frame:{h}", 86400, lambda: (_adsbdb(f"aircraft/{h}") or {}).get("aircraft") or {})
    route = _cached(f"fly:route:{cs}", 6 * 3600, lambda: (_adsbdb(f"callsign/{cs}") or {}).get("flightroute") or {}) if cs else {}

    def track():
        import requests
        try:
            r = requests.get("https://opensky-network.org/api/tracks/all", params={"icao24": h, "time": 0},
                             headers={**UA, **_opensky_auth()}, timeout=20)
            if r.status_code != 200:
                return []
            return [[p[2], p[1], round(p[3] * M_TO_FT) if p[3] is not None else None, p[0]] for p in (r.json().get("path") or []) if p[1] is not None]
        except Exception:
            return []
    path = _cached(f"fly:track:{h}", 120, track)

    def live_state():
        try:
            j = _adsbfi(f"hex/{h}")
            raw = j.get("ac") or j.get("aircraft") or []
            return _ac(raw[0]) if raw else None
        except Exception:
            return None
    live = _cached(f"fly:hex:{h}", 8, live_state)

    org, dst = _airport(route.get("origin")), _airport(route.get("destination"))
    progress, on_route = None, None
    pos = (live["lat"], live["lon"]) if live and live.get("lat") is not None else ((path[-1][1], path[-1][0]) if path else None)
    if org and dst and org.get("lat") is not None and dst.get("lat") is not None and pos:
        total = _km(org["lat"], org["lon"], dst["lat"], dst["lon"])
        left = _km(pos[0], pos[1], dst["lat"], dst["lon"])
        flown = _km(org["lat"], org["lon"], pos[0], pos[1])
        # the route database is the callsign's usual schedule: if the aircraft is well off the
        # great circle between those airports, it is flying something else today
        on_route = flown + left <= total * 1.25 + 150
        if total > 0 and on_route:
            progress = {"total_km": round(total), "remaining_km": round(left), "flown_km": round(flown),
                        "pct": round(max(0.0, min(1.0, flown / (flown + left))) * 100) if flown + left else None}
            spd = (live or {}).get("speed")
            if spd and spd > 80 and not (live or {}).get("on_ground"):
                progress["eta_min"] = round(left / (spd * 1.852) * 60)
    al = route.get("airline") or {}
    return {"hex": h, "callsign": cs, "live": live,
            "airframe": {"type": airframe.get("type"), "icao_type": airframe.get("icao_type"), "manufacturer": airframe.get("manufacturer"),
                         "registration": airframe.get("registration"), "owner": airframe.get("registered_owner"),
                         "owner_country": airframe.get("registered_owner_country_name"), "photo": airframe.get("url_photo"),
                         "photo_thumb": airframe.get("url_photo_thumbnail")} if airframe else None,
            "route": {"airline": al.get("name"), "airline_country": al.get("country"), "iata": route.get("callsign_iata"),
                      "origin": org, "destination": dst, "matches_position": on_route} if route else None,
            "progress": progress, "track": path,
            "source": "Live state: adsb.fi; route & airframe: adsbdb.com (route by callsign — usual schedule, may not match a diverted flight); track: OpenSky"}
