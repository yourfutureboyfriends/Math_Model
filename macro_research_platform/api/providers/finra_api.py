"""FINRA Query API with credentials — the datasets FINRA keeps behind a free API account (TRACE corporate-bond market
breadth and sentiment). Off until FINRA_API_CLIENT_ID and FINRA_API_CLIENT_SECRET are in .env; the owner creates the
account at developer.finra.org and pastes the keys. Public datasets (dark-pool volume) need none of this.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

TOKEN_URL = "https://ews.fip.finra.org/fip/rest/ews/oauth2/access_token"
API = "https://api.finra.org/data/group/{group}/name/{name}"
_token: Dict[str, Any] = {}


class FinraError(RuntimeError):
    """No credentials, or FINRA refused the request."""


def credentials() -> Optional[Tuple[str, str]]:
    cid, sec = os.getenv("FINRA_API_CLIENT_ID"), os.getenv("FINRA_API_CLIENT_SECRET")
    if not (cid and sec):
        try:
            from dotenv import dotenv_values
            env = dotenv_values(Path(__file__).resolve().parents[2] / ".env")
            cid, sec = cid or env.get("FINRA_API_CLIENT_ID"), sec or env.get("FINRA_API_CLIENT_SECRET")
        except Exception:
            pass
    return (cid, sec) if cid and sec else None


def available() -> bool:
    return credentials() is not None


def _bearer() -> str:
    if _token.get("value") and time.time() < _token.get("expires", 0) - 60:
        return _token["value"]
    cred = credentials()
    if not cred:
        raise FinraError("FINRA API credentials are not set (FINRA_API_CLIENT_ID / FINRA_API_CLIENT_SECRET in .env).")
    r = requests.post(TOKEN_URL, params={"grant_type": "client_credentials"}, auth=cred, timeout=30)
    if r.status_code != 200:
        raise FinraError(f"FINRA refused the credentials (HTTP {r.status_code}).")
    j = r.json()
    _token.update(value=j["access_token"], expires=time.time() + float(j.get("expires_in", 1800)))
    return _token["value"]


def query(group: str, name: str, body: Dict[str, Any]) -> List[Dict[str, Any]]:
    r = requests.post(API.format(group=group, name=name), json=body,
                      headers={"Authorization": f"Bearer {_bearer()}", "Accept": "application/json"}, timeout=40)
    if r.status_code == 204 or not r.text.strip():
        return []
    if r.status_code != 200:
        raise FinraError(f"FINRA {group}/{name}: HTTP {r.status_code}")
    return r.json()
