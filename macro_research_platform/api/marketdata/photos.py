"""
Photos of a ship or an aircraft, shown inside the terminal with their credit line:

  ship      Wikimedia Commons files whose description carries the vessel's IMO number
  aircraft  adsbdb.com's airframe photo, then Commons files titled with the registration

Commons images are freely licensed; the author and licence are returned for attribution.
"""
from __future__ import annotations

import html
import logging
import re
from typing import Any, Dict, List, Optional

from api.marketdata.core import _cached

logger = logging.getLogger(__name__)
UA = {"User-Agent": "MacroTerminal/1.0 (research terminal; photos via the Commons API)"}
COMMONS = "https://commons.wikimedia.org/w/api.php"


def _plain(s: Optional[str]) -> Optional[str]:
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip() if s else None


def _commons(search: str, must: str, limit: int = 4) -> List[Dict[str, Any]]:
    """Commons file search; keeps files whose title or description really contains `must`."""
    import requests
    try:
        r = requests.get(COMMONS, headers=UA, timeout=20, params={
            "action": "query", "format": "json", "generator": "search", "gsrsearch": search, "gsrnamespace": 6, "gsrlimit": 10,
            "prop": "imageinfo", "iiprop": "url|extmetadata|mime", "iiurlwidth": 800})
        pages = (r.json().get("query") or {}).get("pages") or {}
    except Exception as e:
        logger.debug("[photos] commons %s: %s", search, e)
        return []
    out = []
    key = must.lower().replace(" ", "")
    for p in sorted(pages.values(), key=lambda p: p.get("index", 99)):
        ii = (p.get("imageinfo") or [{}])[0]
        if not str(ii.get("mime", "")).startswith("image/") or ii.get("mime") == "image/svg+xml":
            continue
        md = ii.get("extmetadata") or {}
        text = f"{p.get('title', '')} {_plain((md.get('ImageDescription') or {}).get('value')) or ''}".lower().replace(" ", "")
        if key not in text:
            continue
        out.append({"url": ii.get("thumburl") or ii.get("url"), "title": p.get("title", "").removeprefix("File:"),
                    "author": _plain((md.get("Artist") or {}).get("value")), "license": (md.get("LicenseShortName") or {}).get("value"),
                    "date": _plain((md.get("DateTimeOriginal") or {}).get("value")), "source": "Wikimedia Commons"})
        if len(out) >= limit:
            break
    return out


def ship(imo: Optional[str] = None, name: Optional[str] = None) -> Dict[str, Any]:
    """Photos of a ship from Wikimedia Commons, matched by IMO number."""
    imo = re.sub(r"\D", "", imo or "")
    if not imo or len(imo) != 7:
        return {"photos": [], "note": "Photos are matched by IMO number; this vessel has none on record."}
    photos = _cached(f"photo:ship:{imo}", 86400, lambda: _commons(f'"IMO {imo}"', f"IMO{imo}") or _commons(f"IMO {imo}", imo))
    return {"photos": photos, "imo": imo, "name": name,
            "note": None if photos else "No freely licensed photo of this vessel was found on Wikimedia Commons."}


def aircraft(hex_id: str, registration: Optional[str] = None) -> Dict[str, Any]:
    """Photos of an aircraft by registration."""
    from api.marketdata.airtraffic import _adsbdb
    h = (hex_id or "").strip().lower()
    reg = (registration or "").strip().upper()

    def fetch():
        out: List[Dict[str, Any]] = []
        frame = (_adsbdb(f"aircraft/{h}") or {}).get("aircraft") or {} if h else {}
        r = reg or frame.get("registration") or ""
        if frame.get("url_photo"):
            out.append({"url": frame["url_photo"], "title": f"{r} {frame.get('type') or ''}".strip(), "author": None, "license": None,
                        "source": "airport-data.com via adsbdb"})
        if r and len(r) >= 4:
            out += _commons(f'intitle:"{r}"', r, limit=3)
        return out
    photos = _cached(f"photo:ac:{h}:{reg}", 86400, fetch)
    return {"photos": photos, "registration": reg or None,
            "note": None if photos else "No photo of this airframe was found (adsbdb, Wikimedia Commons)."}
