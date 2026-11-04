"""NaN-safe JSON responses: one bad number must never turn an endpoint into a 500."""
import math
from typing import Optional

import numpy as np
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from api.core.json_safe import SafeJSONResponse, to_json_safe


def test_to_json_safe_converts_non_finite_and_numpy():
    fixes = []
    out = to_json_safe({"a": float("nan"), "b": [1.0, float("inf"), np.float64("-inf")], "c": np.int64(3),
                        "d": np.array([1.5, np.nan]), "e": (1, 2), 5: np.bool_(True)}, "", fixes)
    assert out == {"a": None, "b": [1.0, None, None], "c": 3, "d": [1.5, None], "e": [1, 2], "5": True}
    assert set(fixes) == {".a", ".b[1]", ".b[2]", ".d[1]"}


def test_clean_payload_is_untouched():
    payload = {"x": 1.25, "y": [1, "a", None, True], "z": {"k": -0.0}}
    assert to_json_safe(payload) == payload


class Row(BaseModel):
    value: Optional[float] = None


def _app():
    app = FastAPI(default_response_class=SafeJSONResponse)
    r = APIRouter()

    @r.get("/plain")
    def plain():
        return {"avg_setup": float("nan"), "ok": 1}

    @r.get("/model", response_model=Row)
    def model():
        return Row(value=float("inf"))

    @r.get("/numpy")
    def numpy_():
        return {"v": np.float64("nan"), "n": [np.float32(2.5)]}

    app.include_router(r)
    return app


def test_router_routes_return_null_instead_of_500():
    c = TestClient(_app())
    assert c.get("/plain").json() == {"avg_setup": None, "ok": 1}
    assert c.get("/model").json() == {"value": None}
    assert c.get("/numpy").json() == {"v": None, "n": [2.5]}


def test_every_app_route_uses_the_safe_response_class():
    from fastapi.routing import APIRoute
    from api.main import app
    bad = [r.path for r in app.routes if isinstance(r, APIRoute)
           and not issubclass(getattr(r.response_class, "value", r.response_class), SafeJSONResponse)]
    assert not bad, bad
