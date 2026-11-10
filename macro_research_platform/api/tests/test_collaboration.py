import pytest


@pytest.fixture()
def ut():
    from api.marketdata import usertools
    usertools._ready = False
    return usertools


def test_shared_watchlist_visible_read_only_to_colleagues(ut):
    w = ut.create_watchlist("alice_c", "Energy", ["XOM", "CVX"])
    assert not any(x.get("shared_by") == "alice_c" for x in ut.list_watchlists("bob_c"))
    ut.update_watchlist("alice_c", w["id"], None, None, True)
    seen = [x for x in ut.list_watchlists("bob_c") if x.get("shared_by") == "alice_c"]
    assert seen and seen[0]["read_only"] and seen[0]["symbols"] == ["XOM", "CVX"]
    with pytest.raises(LookupError):
        ut.update_watchlist("bob_c", w["id"], "mine now", None)


def test_team_notes_author_only_delete(ut):
    n = ut.add_note("alice_c", "AAPL", "Supply chain check: iPhone Duo stock tight.")
    assert ut.list_notes("AAPL")[0]["text"].startswith("Supply chain")
    with pytest.raises(LookupError):
        ut.delete_note("bob_c", n["id"])
    ut.delete_note("alice_c", n["id"])
    assert not ut.list_notes("AAPL")
    with pytest.raises(ValueError):
        ut.add_note("alice_c", "AAPL", "x" * 2001)
