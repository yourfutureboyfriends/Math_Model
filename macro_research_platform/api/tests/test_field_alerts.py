import pytest


@pytest.fixture()
def ut(monkeypatch):
    from api.marketdata import usertools, field_alerts
    usertools._ready = False
    vals = {"macro.composite": 0.55, "macro.regime": "goldilocks"}
    monkeypatch.setattr(field_alerts, "value", lambda f: vals.get(f))
    sent = []
    import api.notify as notify
    monkeypatch.setattr(notify, "deliver", lambda owner, text: sent.append((owner, text)) or {})
    return usertools, vals, sent


def test_field_threshold_and_change_alerts_fire_and_deliver(ut):
    usertools, vals, sent = ut
    a = usertools.create_alert("u1", "macro.composite", "field_above", 0.7, "risk-on")
    b = usertools.create_alert("u1", "macro.regime", "field_changes", 0)
    assert a["field_label"].startswith("Composite") and b["baseline"] == "goldilocks"
    assert usertools.check_alerts()["triggered"] == 0
    vals["macro.composite"], vals["macro.regime"] = 0.72, "reflation"
    assert usertools.check_alerts()["triggered"] == 2
    texts = [t for _, t in sent]
    assert any("Composite signal" in t and "risk-on" in t for t in texts)
    assert any("goldilocks → reflation" in t for t in texts)


def test_field_alert_validation(ut):
    usertools, vals, _ = ut
    with pytest.raises(ValueError, match="Unknown field"):
        usertools.create_alert("u1", "macro.nope", "field_above", 1)
    with pytest.raises(ValueError, match="already"):
        usertools.create_alert("u1", "macro.composite", "field_below", 0.6)
    with pytest.raises(ValueError, match="text"):
        usertools.create_alert("u1", "macro.regime", "field_above", 1)
    assert usertools.create_alert("u1", "fred:UNRATE", "field_above", 99)["symbol"] == "fred:UNRATE"


def test_news_alert_fires_on_new_headline(ut, monkeypatch):
    usertools, _, sent = ut
    from api.marketdata import field_alerts
    a = usertools.create_alert("u2", "Tariff", "news_mentions", 0)
    assert a["symbol"] == "news:tariff"
    monkeypatch.setattr(field_alerts, "news_hits", lambda kw, since: [{"title": "New tariff announced", "source": "Reuters"}])
    assert usertools.check_alerts()["triggered"] == 1
    assert "New tariff announced" in sent[-1][1]
