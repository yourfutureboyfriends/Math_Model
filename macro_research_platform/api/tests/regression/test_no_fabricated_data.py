"""
SWEEP 4 — stale/static placeholder & fabricated data.

Locks the two fabricated-data bugs fixed in the improvement loop:
- /api/earnings/revisions returned a hardcoded per-sector EPS table when no Finnhub key.
- /api/portfolio/attribution returned a hardcoded factor/sector/regime attribution table.
Both must now return honest structured absence with NO invented numbers.
"""
import os


def test_earnings_revisions_no_fabricated_sector_table(client):
    """Without a Finnhub key, the endpoint must NOT return the old fake sector numbers."""
    if os.getenv("FINNHUB_API_KEY"):
        return  # with a real key, real data is expected; this guards the keyless fallback
    r = client.get("/api/earnings/revisions")
    assert r.status_code == 200
    data = r.json()
    assert data.get("available") is False
    assert data.get("sectors") == {}
    # the exact fabricated values that used to be served must never reappear
    body = r.text
    for fake in ('"eps_revision_pct": 2.5', '"eps_revision_pct": 3.2', '"beats_rate": 68'):
        assert fake not in body, f"fabricated earnings value reappeared: {fake}"


def test_portfolio_attribution_legacy_is_honest_absence(client):
    """The legacy attribution endpoint must return structured absence, not the fake table."""
    r = client.get("/api/portfolio/attribution")
    assert r.status_code == 200
    data = r.json()
    assert data.get("available") is False
    assert data.get("factorAttribution") == []
    assert data.get("sectorAttribution") == []
    # the hardcoded contributions that used to be served must never reappear
    for fake in ('"contributionPct": 4.5', '"contributionPct": 3.2', '"days": 120'):
        assert fake not in r.text, f"fabricated attribution value reappeared: {fake}"


def test_real_attribution_v1_still_available(client):
    """The real, position-derived attribution endpoint the frontend uses must stay healthy."""
    r = client.get("/api/v1/portfolio/attribution")
    assert r.status_code == 200
    # available True (has positions) or a typed absence — never a raw error
    assert "available" in r.json()
