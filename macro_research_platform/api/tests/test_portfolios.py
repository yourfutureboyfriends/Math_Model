"""Portfolios: holding review rules and access control for the auto book."""
from api.core.access import needs_auth
from api.portfolio_review import review_action


def test_review_action_mapping():
    assert review_action("AVOID", 1.0) == "exit"
    assert review_action("BUY", -1.0) == "exit"            # long-term trend broken overrides
    assert review_action("BUY", 1.0) == "add"
    assert review_action("WAIT", 0.5) == "hold_extended"
    assert review_action("BUY_SMALL", 1.0) == "hold_riskoff"
    assert review_action("WATCH", 0.5) == "watch"
    assert review_action("N/A", None) == "none"


def test_auto_book_and_review_require_login():
    for path in ("/api/v1/auto/status", "/api/v1/portfolio/model-review", "/api/v1/portfolio/optimize"):
        assert needs_auth("GET", path), path
    assert needs_auth("POST", "/api/v1/auto/run")
    assert needs_auth("PUT", "/api/v1/auto/settings")


def test_auto_endpoints_reject_anonymous():
    from fastapi.testclient import TestClient
    from api.main import app
    c = TestClient(app)
    assert c.get("/api/v1/auto/status").status_code == 401
    assert c.post("/api/v1/auto/run").status_code == 401
    assert c.post("/api/v1/auto/reset", json={}).status_code == 401


def test_short_positions_mirror_the_rules():
    assert review_action("BUY", 1.0, short=True) == "cover"         # an up-trend hurts a short
    assert review_action("AVOID", -1.0, short=True) == "hold_short"
    assert review_action("WATCH", 0.0, short=True) == "watch_short"
