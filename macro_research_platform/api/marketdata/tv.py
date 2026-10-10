"""
TV — live business and news channels (their official YouTube live streams) and recent clips
about a country's economy, for the world map.

  live()            each channel's current live stream (video id + title), or off air
  clips(country)    recent videos from these channels whose titles mention the country and an
                    economic subject (rates, inflation, markets, trade…) — YouTube's public RSS

Only official channel streams are embedded (youtube-nocookie player); nothing is re-hosted.
"""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from api.marketdata.core import _cached

logger = logging.getLogger(__name__)
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 Chrome/126 Safari/537.36",
      "Accept-Language": "en"}
# YouTube's EU/UK consent wall: the "reject all" choice cookie (no tracking consent given)
COOKIES = {"SOCS": "CAI"}

# channel id → (name, focus, home countries ISO-2 ("*" = global), region)
CHANNELS: Dict[str, tuple] = {
    "UCIALMKvObZNtJ6AmdCLP7Lg": ("Bloomberg Television", "business", ["*", "US"], "americas"),
    "UCEAZeUIeJs0IjQiqTCdVSIg": ("Yahoo Finance", "business", ["US"], "americas"),
    "UCrp_UI8XtuYfpiqluWLD7Lw": ("CNBC Television", "business", ["US"], "americas"),
    "UCBi2mrWuNuyYy4gbM6fU18Q": ("ABC News (US)", "news", ["US"], "americas"),
    "UCuFFtHWoLl5fauMMD5Ww2jA": ("CBC News", "news", ["CA"], "americas"),
    "UCoMdktPbSTixAyNGwb-UYkQ": ("Sky News", "news", ["GB"], "europe"),
    "UCknLrEdhRCp1aegoMqRaCZg": ("DW News", "news", ["DE", "AT", "CH"], "europe"),
    "UCQfwfsi5VrQ8yKZ-UWmAEFg": ("France 24 English", "news", ["FR", "BE", "LU"], "europe"),
    "UCSrZ3UV4jOidv8ppoVuvW9Q": ("Euronews", "news", ["EU", "IT", "ES", "NL", "PT", "GR", "IE", "PL", "SE"], "europe"),
    "UC7fWeaHhqgM4Ry-RMpM2YYw": ("TRT World", "news", ["TR"], "europe"),
    "UCNye-wNBqNL5ZzHSJj3l8Bg": ("Al Jazeera English", "news", ["QA", "SA", "AE", "KW", "OM", "BH", "IL", "IR", "IQ", "EG", "JO", "LB"], "mea"),
    "UCI3RT5PGmdi1KVp9FG_CneA": ("eNCA", "news", ["ZA"], "mea"),
    "UCSPEjw8F2nQDtmUKPFNF7_A": ("NHK WORLD-JAPAN", "news", ["JP"], "apac"),
    "UC83jt4dlz1Gjl58fzQrrKZg": ("CNA", "news", ["SG", "MY", "ID", "TH", "PH", "VN"], "apac"),
    "UCgrNz-aDmcr2uuto8_DL2jg": ("CGTN", "news", ["CN", "HK"], "apac"),
    "UC_gUM8rL-Lrg6O3adPW9K1g": ("WION", "news", ["IN"], "apac"),
    "UCQIycDaLsBpMKjOCeaKUYVg": ("CNBC-TV18", "business", ["IN"], "apac"),
    "UCVgO39Bk5sMo66-6o6Spn6Q": ("ABC News Australia", "news", ["AU", "NZ"], "apac"),
}

ECON = re.compile(r"\b(econom\w*|inflation|interest rates?|rate (cut|hike)s?|central bank|fed\b|federal reserve|ecb|boj|boe|rba|pboc|"
                  r"gdp|recession|growth|jobs|unemployment|wages?|markets?|stocks?|shares|bonds?|yields?|currency|yen|euro|pound|yuan|"
                  r"rupee|dollar|tariffs?|trade|exports?|imports?|budget|debt|deficit|tax(es)?|oil|gas|energy|prices|property|housing|"
                  r"banks?|investors?|earnings|imf|world bank|opec|crypto|bitcoin)\b", re.I)


def _resolve(cid: str) -> Dict[str, Any]:
    """A channel's /live page redirects to its current live video when it is on air."""
    import requests
    name, focus, homes, region = CHANNELS[cid]
    base = {"channel_id": cid, "channel": name, "focus": focus, "countries": homes, "region": region,
            "live": False, "video_id": None, "title": None}
    try:
        t = requests.get(f"https://www.youtube.com/channel/{cid}/live", headers=UA, cookies=COOKIES, timeout=15).text
    except Exception as e:
        logger.debug("[tv] %s: %s", name, e)
        return base
    canon = re.search(r'<link rel="canonical" href="https://www\.youtube\.com/watch\?v=([\w-]{11})"', t)
    live = '"isLive":true' in t or '"isLiveContent":true' in t
    if canon and live:
        title = re.search(r"<title>(.*?)</title>", t, re.S)
        import html
        base.update({"live": True, "video_id": canon.group(1),
                     "title": html.unescape(re.sub(r"\s*-\s*YouTube\s*$", "", title.group(1))) if title else None})
    return base


def live() -> Dict[str, Any]:
    def build():
        with ThreadPoolExecutor(8) as ex:
            chans = list(ex.map(_resolve, CHANNELS))
        return {"channels": chans, "note": "Official live streams on YouTube; channels off air are shown greyed out.",
                "source": "YouTube (official channel live streams)"}
    return _cached("tv:live", 900, build)


def _feed(cid: str) -> List[Dict[str, Any]]:
    import html
    import requests

    def fetch():
        try:
            t = requests.get("https://www.youtube.com/feeds/videos.xml", params={"channel_id": cid}, headers=UA, cookies=COOKIES, timeout=15).text
        except Exception:
            return []
        out = []
        for e in re.findall(r"<entry>(.*?)</entry>", t, re.S):
            vid = re.search(r"<yt:videoId>([\w-]{11})</yt:videoId>", e)
            title = re.search(r"<title>(.*?)</title>", e, re.S)
            pub = re.search(r"<published>(.*?)</published>", e)
            if vid and title:
                out.append({"video_id": vid.group(1), "title": html.unescape(title.group(1)).strip(),
                            "published": pub.group(1) if pub else None, "channel": CHANNELS[cid][0], "channel_id": cid})
        return out
    return _cached(f"tv:feed:{cid}", 1800, fetch)


# established news / business outlets whose search results are kept (commentary channels are not)
OUTLETS = re.compile(r"\b(Bloomberg|CNBC|Reuters|Financial Times|FT\b|The Economist|Wall Street Journal|WSJ|Yahoo Finance|Sky News|"
                     r"DW\b|DW News|France 24|NHK|CNA\b|CNA Insider|Al Jazeera|CGTN|ABC News|CBC News|Euronews|TRT World|WION|"
                     r"Nikkei|South China Morning Post|SCMP|BBC|Channel 4 News|Associated Press|Fox Business|PBS NewsHour|"
                     r"Arirang|KBS|NDTV|Times Now|Mint|Moneycontrol|SABC|eNCA|ABC News Australia|9 News|RNZ|Global News)", re.I)


def _search(query: str) -> List[Dict[str, Any]]:
    """YouTube search (newest first), keeping videos from established outlets uploaded in the
    last ~6 months."""
    import json as _json
    import requests

    def fetch():
        try:
            t = requests.get("https://www.youtube.com/results", params={"search_query": query, "sp": "CAI="},
                             headers=UA, cookies=COOKIES, timeout=15).text
            m = re.search(r"var ytInitialData = (\{.*?\});</script>", t, re.S)
            data = _json.loads(m.group(1)) if m else {}
        except Exception as e:
            logger.debug("[tv] search %s: %s", query, e)
            return []
        out: List[Dict[str, Any]] = []

        def walk(o):
            if isinstance(o, dict):
                v = o.get("videoRenderer")
                if v and v.get("videoId"):
                    owner = ((v.get("ownerText") or {}).get("runs") or [{}])[0].get("text") or ""
                    age = (v.get("publishedTimeText") or {}).get("simpleText") or ""
                    live = any(b.get("metadataBadgeRenderer", {}).get("style") == "BADGE_STYLE_TYPE_LIVE_NOW" for b in v.get("badges", []))
                    # "8mo ago", "1y ago", "2 years ago": keep the last ~6 months
                    old = bool(re.search(r"\d+\s*(y|yr|yrs|years?)\b|\b([7-9]|1[0-2])\s*(mo|mos|months?)\b", age))
                    if OUTLETS.search(owner) and not old:
                        out.append({"video_id": v["videoId"], "title": "".join(r.get("text", "") for r in v["title"]["runs"]),
                                    "channel": owner, "age": age or ("live" if live else None), "live": live, "published": None})
                for x in o.values():
                    walk(x)
            elif isinstance(o, list):
                for x in o:
                    walk(x)
        walk(data)
        return out
    return _cached(f"tv:search:{query.lower()}", 1800, fetch)


def clips(country: Optional[str] = None, limit: int = 24) -> Dict[str, Any]:
    """Recent economy-related clips; for a country, ones whose titles mention it (any channel)."""
    from api.marketdata.countries import COUNTRY_ALIASES, BY_ISO2, countries_in
    with ThreadPoolExecutor(8) as ex:
        vids = [v for feed in ex.map(_feed, CHANNELS) for v in feed]
    c = (country or "").upper()
    out = []
    for v in vids:
        if not ECON.search(v["title"]):
            continue
        if c:
            hit = c in countries_in(v["title"]) or (c not in COUNTRY_ALIASES and BY_ISO2.get(c, {}).get("name", "§").lower() in v["title"].lower())
            if not hit:
                continue
        out.append(v)
    out.sort(key=lambda v: v.get("published") or "", reverse=True)
    if c and BY_ISO2.get(c):                     # plus outlet videos found by searching for the country's economy
        out += _search(f"{BY_ISO2[c]['name']} economy")
    def age_h(v):
        if v.get("live"):
            return 0.0
        if v.get("published"):
            from datetime import datetime, timezone
            try:
                return (datetime.now(timezone.utc) - datetime.fromisoformat(v["published"])).total_seconds() / 3600
            except Exception:
                return 1e6
        m = re.search(r"(\d+)\s*(min|minute|h|hour|d|day|w|week|mo|month)", v.get("age") or "")
        if not m:
            return 1e6
        mult = {"min": 1 / 60, "minute": 1 / 60, "h": 1, "hour": 1, "d": 24, "day": 24, "w": 168, "week": 168, "mo": 720, "month": 720}[m.group(2)]
        return int(m.group(1)) * mult
    out.sort(key=age_h)                          # newest first across feeds and search
    seen, uniq = set(), []
    for v in out:
        if v["video_id"] not in seen:
            seen.add(v["video_id"])
            uniq.append(v)
    return {"country": c or None, "clips": uniq[:limit], "source": "YouTube channel feeds (official uploads)"}
