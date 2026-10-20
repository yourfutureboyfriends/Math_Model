"""
JSON-safe responses for every route.

Strict JSON has no NaN or Infinity, so Starlette's encoder raises on them and the whole
endpoint fails with a 500 — one missing data point (a gap in a price series, an empty
group mean) takes down a panel. SafeJSONResponse is the app's default response class:

  * fast path: the usual strict encode (no cost when the payload is clean);
  * otherwise: NaN / ±Infinity → null, numpy and pandas scalars → Python values, sets and
    tuples → lists, non-string keys → strings; then encode.

Every repair is logged once per field path, so the producing code can still be fixed — the
response layer is the safety net, not the place where bad numbers are meant to be handled.
"""
from __future__ import annotations

import json
import logging
import math
from typing import Any, List, Set

from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)
_REPORTED: Set[str] = set()
_MAX_REPORTED = 500


def to_json_safe(obj: Any, path: str = "", fixes: List[str] | None = None) -> Any:
    """Recursively convert `obj` into strict-JSON-encodable values. Paths of replaced
    non-finite numbers are appended to `fixes`."""
    if obj is None or isinstance(obj, (str, bool)):
        return obj
    if isinstance(obj, int):
        return obj
    if isinstance(obj, float):
        if math.isfinite(obj):
            return obj
        if fixes is not None:
            fixes.append(path or "$")
        return None
    if isinstance(obj, dict):
        return {(k if isinstance(k, str) else str(k)): to_json_safe(v, f"{path}.{k}", fixes) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [to_json_safe(v, f"{path}[{i}]", fixes) for i, v in enumerate(obj)]
    try:                                    # numpy / pandas without importing them eagerly
        import numpy as np
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return to_json_safe(float(obj), path, fixes)
        if isinstance(obj, np.ndarray):
            return to_json_safe(obj.tolist(), path, fixes)
    except ImportError:
        pass
    try:
        import pandas as pd
        if obj is pd.NaT or obj is pd.NA:
            return None
        if isinstance(obj, pd.Timestamp):
            return obj.isoformat()
    except ImportError:
        pass
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj


class SafeJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        try:
            return json.dumps(content, ensure_ascii=False, allow_nan=False, indent=None,
                              separators=(",", ":")).encode("utf-8")
        except (ValueError, TypeError):
            fixes: List[str] = []
            safe = to_json_safe(content, "", fixes)
            new = [p for p in fixes[:20] if p not in _REPORTED]
            if new and len(_REPORTED) < _MAX_REPORTED:
                _REPORTED.update(new)
                logger.warning("[json] %d non-finite value(s) sent as null, e.g. %s", len(fixes), ", ".join(new[:5]))
            return json.dumps(safe, ensure_ascii=False, allow_nan=False, indent=None,
                              separators=(",", ":"), default=str).encode("utf-8")


def install_numpy_encoders() -> None:
    """Teach FastAPI's jsonable_encoder (which runs before the response renders) about numpy
    scalars and arrays — np.float32, np.int64 and ndarray otherwise raise TypeError there.
    Exact types are registered because FastAPI looks up type(obj) first."""
    import numpy as np
    from fastapi import encoders
    scalar = [np.bool_, np.float16, np.float32, np.float64, np.int8, np.int16, np.int32, np.int64,
              np.uint8, np.uint16, np.uint32, np.uint64]
    for t in scalar:
        encoders.ENCODERS_BY_TYPE.setdefault(t, lambda v: v.item())
    encoders.ENCODERS_BY_TYPE.setdefault(np.ndarray, lambda a: a.tolist())


install_numpy_encoders()
