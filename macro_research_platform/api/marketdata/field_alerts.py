"""
Alert fields beyond prices: model outputs (composite, regime, recession probability, the four signals), market
gauges (VIX, 10Y), survey and options sentiment, nowcasts, valuation, any FRED series (``fred:SERIES_ID``) and news
headlines (``news:keyword``). Values come from caches the platform already keeps — checking alerts never forces a
dashboard rebuild.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def _dash():
    from api.handlers.dashboard_handler import _DASHBOARD_CACHE
    hit = _DASHBOARD_CACHE.get("live")
    return hit[1] if hit else None


def _d(fn: Callable[[Any], Any]) -> Callable[[], Any]:
    def get():
        d = _dash()
        if d is None:
            raise LookupError("dashboard not built yet")
        return fn(d)
    return get


def _free(fn_name: str, path: Tuple[str, ...]) -> Callable[[], Any]:
    def get():
        from api.marketdata import freedata
        v: Any = getattr(freedata, fn_name)()
        for k in path:
            v = v[k]
        return v
    return get


FIELDS: Dict[str, Tuple[str, str, Callable[[], Any]]] = {
    # id: (label, "number" | "text", getter)
    "macro.composite": ("Composite signal (0–1)", "number", _d(lambda d: d.ensemble.score)),
    "macro.regime": ("Macro regime", "text", _d(lambda d: d.regime.current)),
    "macro.conviction": ("Conviction", "text", _d(lambda d: d.ensemble.conviction)),
    "macro.recession": ("Recession probability (0–1)", "number", _d(lambda d: d.recession.probability)),
    "macro.growth": ("Growth signal (0–100)", "number", _d(lambda d: d.scores.growth)),
    "macro.inflation": ("Inflation signal (0–100)", "number", _d(lambda d: d.scores.inflation)),
    "macro.liquidity": ("Liquidity signal (0–100)", "number", _d(lambda d: d.scores.liquidity)),
    "macro.risk": ("Risk appetite (0–100)", "number", _d(lambda d: d.scores.risk)),
    "market.vix": ("VIX", "number", _d(lambda d: d.keyMetrics.vix)),
    "market.ten_year": ("US 10Y yield (%)", "number", _d(lambda d: d.keyMetrics.tenYearYield)),
    "sentiment.aaii_spread": ("AAII bull − bear (pts)", "number", _free("aaii_sentiment", ("latest", "spread"))),
    "sentiment.put_call_equity": ("CBOE equity put/call", "number", _free("cboe_put_call", ("latest", "equity"))),
    "nowcast.nyfed": ("NY Fed Staff Nowcast (% SAAR)", "number", _free("nyfed_nowcast", ("nowcast",))),
    "valuation.cape": ("Shiller CAPE", "number", _free("shiller_cape", ("latest",))),
}
FRED_RE = re.compile(r"^fred:[A-Z0-9_]{2,30}$")


def describe() -> Dict[str, Any]:
    return {"fields": {k: {"label": v[0], "type": v[1]} for k, v in FIELDS.items()},
            "fred": "fred:SERIES_ID — any FRED series (latest observation)",
            "news": "a keyword or phrase — fires on a new headline containing it"}


def valid_field(field: str) -> bool:
    return field in FIELDS or bool(FRED_RE.match(field))


def field_type(field: str) -> str:
    return FIELDS[field][1] if field in FIELDS else "number"


def field_label(field: str) -> str:
    return FIELDS[field][0] if field in FIELDS else (f"FRED {field[5:]}" if field.startswith("fred:") else field)


def value(field: str) -> Optional[Any]:
    """Current value of a field, or None when it can't be read now."""
    try:
        if field in FIELDS:
            return FIELDS[field][2]()
        if FRED_RE.match(field):
            from api.handlers.macro_inputs import _fetch_fred_history_sync
            s = _fetch_fred_history_sync(field[5:], 400)
            return s.latest if s else None
    except Exception as e:
        logger.debug("[field-alerts] %s: %s", field, e)
    return None


def news_hits(keyword: str, since_iso: str) -> list:
    """Headlines containing `keyword` published after `since_iso`."""
    from api.marketdata.monitors import news_hub
    items = news_hub(q=keyword, limit=20).get("items") or []
    return [i for i in items if (i.get("time") or "") > since_iso]
