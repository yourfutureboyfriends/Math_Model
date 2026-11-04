"""The source monitor tells a source that parses from one that broke, went stale, or served an old copy."""
from datetime import date, timedelta

from api import source_monitor as sm


def _src(fetch, latest=lambda v: v["latest"], max_age=5, partial=None):
    s = {"name": "X", "feeds": "y", "max_age": max_age, "fetch": fetch, "latest": latest}
    if partial:
        s["partial"] = partial
    return s


def test_statuses():
    today = date.today().isoformat()
    old = (date.today() - timedelta(days=30)).isoformat()
    assert sm.check_one(_src(lambda: {"latest": today}))["status"] == "ok"
    assert sm.check_one(_src(lambda: {"latest": old}))["status"] == "stale"
    assert sm.check_one(_src(lambda: {"latest": today, "stale": True, "stale_age_s": 7200}))["status"] == "degraded"
    assert sm.check_one(_src(lambda: {"latest": today, "f": ["x"]}, partial=lambda v: v["f"]))["status"] == "degraded"
    assert sm.check_one(_src(lambda: {"latest": None}))["status"] == "failing"

    def broken():
        raise ValueError("not enough values to unpack (expected 3, got 1)")      # the Fed EBP date-format change
    r = sm.check_one(_src(broken))
    assert r["status"] == "failing" and "unpack" in r["error"]
    assert sm._d("2026-09") == "2026-09-30" and sm._d("2026-10-25T10:49-04:00") == "2026-10-25"


def test_run_records_transitions_and_alerts(monkeypatch, tmp_path):
    from api import notify
    monkeypatch.setattr(sm, "STATE", tmp_path / "s.json")
    state = {"ok": True}

    def fetch():
        if not state["ok"]:
            raise RuntimeError("format changed")
        return {"latest": date.today().isoformat()}
    monkeypatch.setattr(sm, "_sources", lambda: [_src(fetch)])
    sent = []
    monkeypatch.setattr(notify, "channels", lambda: {"webhook": True})
    monkeypatch.setattr(notify, "deliver", lambda owner, text: sent.append(text) or {"webhook": True})
    sm.run_checks()
    assert sm.status()["summary"]["ok"] == 1 and not sent
    state["ok"] = False
    sm.run_checks()
    st = sm.status()
    assert st["summary"]["failing"] == 1 and st["sources"][0]["since"] == st["sources"][0]["checked_at"]
    assert sent and "ok→failing" in sent[0] and "format changed" in sent[0]
    sm.run_checks()
    assert len(sent) == 1                                     # alerted once per change, not every check
