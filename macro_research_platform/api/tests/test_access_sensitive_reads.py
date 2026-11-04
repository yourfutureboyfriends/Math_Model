"""The firm's own information is not readable without signing in (backend audit, Oct 2026)."""
import pytest

from api.core.access import needs_auth


@pytest.mark.parametrize("path", ["/api/morning-brief", "/api/v1/model/sleeve", "/api/business/decision-log",
                                  "/api/business/ic-pack", "/api/v1/portfolio/positions", "/api/v1/desk"])
def test_internal_reads_need_auth(path):
    assert needs_auth("GET", path)


@pytest.mark.parametrize("path", ["/api/market", "/api/v1/mkt/wei", "/api/geopolitical-risk"])
def test_market_data_stays_open(path):
    assert not needs_auth("GET", path)


def test_writes_always_need_auth():
    assert needs_auth("POST", "/api/v1/brief/send") and not needs_auth("POST", "/api/auth/login")
