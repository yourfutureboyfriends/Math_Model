"""
DBnomics — one free API (no key) over 90+ official statistical sources: IMF, OECD, ECB,
Eurostat, BIS, World Bank, ILO, national statistics offices and central banks (Cepremap).

Used where FRED's international coverage is thin. Series are addressed as
provider/dataset/series, e.g. IMF/CPI/M.DE.PCPI_IX.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)
API = "https://api.db.nomics.world/v22"
CACHE = Path(__file__).resolve().parents[2] / "data" / "processed" / "dbnomics"
TTL = 12 * 3600


class DBnomicsError(RuntimeError):
    pass


def _get(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    r = requests.get(f"{API}/{path}", params=params, timeout=40)
    if r.status_code == 404:
        raise DBnomicsError(f"Not found on DBnomics: {path}")
    r.raise_for_status()
    return r.json()


def series(code: str) -> Dict[str, Any]:
    """{code, name, provider, frequency, last_update, observations: [{period, value}]}."""
    code = code.strip().strip("/")
    if code.count("/") != 2:
        raise DBnomicsError("Use provider/dataset/series, e.g. IMF/CPI/M.DE.PCPI_IX")
    path = CACHE / (code.replace("/", "__") + ".json")
    try:
        if time.time() - path.stat().st_mtime < TTL:
            return json.loads(path.read_text())
    except Exception:
        pass
    try:
        j = _get(f"series/{code}", {"observations": 1, "format": "json"})
        docs = (j.get("series") or {}).get("docs") or []
        if not docs:
            raise DBnomicsError(f"No data for {code}")
        d = docs[0]
        obs = [{"period": p, "value": (float(v) if isinstance(v, (int, float)) else None)}
               for p, v in zip(d.get("period", []), d.get("value", []))]
        out = {"code": code, "name": d.get("series_name") or code, "provider": d.get("provider_code"),
               "dataset": d.get("dataset_name") or d.get("dataset_code"), "frequency": d.get("@frequency"),
               "last_update": d.get("indexed_at"), "observations": obs, "source": "DBnomics"}
    except DBnomicsError:
        raise
    except Exception as e:
        try:
            return json.loads(path.read_text())
        except Exception:
            raise DBnomicsError(f"DBnomics request failed: {e}") from e
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out))
    return out


def search(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    j = _get("search", {"q": query, "limit": min(limit, 50)})
    docs = (j.get("results") or {}).get("docs") or []
    return [{"provider": d.get("provider_code"), "dataset": d.get("code"), "name": d.get("name"),
             "series_count": d.get("nb_series"), "updated": d.get("indexed_at")} for d in docs]


def latest_value(code: str) -> Optional[Dict[str, Any]]:
    s = series(code)
    for o in reversed(s["observations"]):
        if o["value"] is not None:
            return {"period": o["period"], "value": o["value"], "name": s["name"], "source": f"DBnomics · {s['provider']}"}
    return None
