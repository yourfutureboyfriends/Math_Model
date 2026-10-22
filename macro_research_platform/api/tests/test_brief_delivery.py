"""Daily Brief delivery: plain-text rendering, the weekday schedule (once a day), send-now through the alert channels."""
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from api import brief_delivery as bd

BRIEF = {"date": "2026-10-22", "headline": "Macro regime: Reflation", "summary": "Reflation regime.",
         "priorities": [{"priority": 1, "severity": "HIGH", "title": "Hang Seng -3.03% (-3.3σ)", "implication": "Largest move"}],
         "overnight": [{"name": "US 10Y yield", "unit": "bp", "change": -13.7, "sigma": -3.1},
                       {"name": "DAX", "unit": "pct", "change": -1.04, "sigma": -1.4}],
         "todaysReleases": [{"time_et": "08:30", "event": "Jobless claims", "importance": "high", "forecast": "225K",
                             "forecast_label": "consensus", "previous": "219K"}],
         "earnings": {"available": True, "holdings": [{"symbol": "MSFT", "datetime": "2026-10-28T20:00:00+00:00", "timing": "After close"}],
                      "large_caps": []},
         "positioning": {"put_call": {"latest": {"equity": 0.52}, "equity_10d_avg": 0.585, "contrarian": "neutral"}},
         "sinceLastBrief": {"since": "2026-10-20", "changes": [{"text": "VIX +1.6 (now 18.95)"}]},
         "tradeIdeas": [{"direction": "LONG", "asset": "GLD", "entry": 371.3, "stop": 357.9, "target": 394, "conviction": "HIGH", "rationale": "real assets"}],
         "risks": [{"severity": "WARNING", "text": "Inflation above target"}]}


def test_render_is_readable_plain_text():
    t = bd.render(BRIEF)
    first = t.splitlines()[0]
    assert first == "Daily Brief 2026-10-22 — Macro regime: Reflation"            # the e-mail subject
    for s in ("1. [HIGH] Hang Seng", "US 10Y yield: -13.70bp (-3.1σ)", "08:30 Jobless claims [high] — consensus 225K, previous 219K",
              "MSFT", "put/call 0.52", "VIX +1.6 (now 18.95)", "LONG GLD @ 371.3", "[WARNING] Inflation above target"):
        assert s in t, s
    assert "None:" not in t and "{" not in t


def test_schedule_weekdays_once_a_day(monkeypatch, tmp_path):
    monkeypatch.setattr(bd, "STATE", tmp_path / "s.json")
    monkeypatch.setenv("BRIEF_DELIVERY_TIME", "07:00")
    ny = ZoneInfo("America/New_York")
    assert not bd.due(datetime(2026, 10, 22, 6, 59, tzinfo=ny))                # before the time
    assert bd.due(datetime(2026, 10, 22, 7, 0, tzinfo=ny))
    assert not bd.due(datetime(2026, 10, 24, 9, 0, tzinfo=ny))                 # Saturday
    bd._save_state({"scheduled_for": "2026-10-22"})
    assert not bd.due(datetime(2026, 10, 22, 9, 0, tzinfo=ny))                 # already sent today
    monkeypatch.setenv("BRIEF_DELIVERY_TIME", "7am")
    assert bd.schedule()["invalid"] and not bd.due(datetime(2026, 10, 23, 9, 0, tzinfo=ny))


def test_send_needs_a_channel_and_delivers(monkeypatch, tmp_path):
    from api import notify
    from api.handlers import business_handler
    monkeypatch.setattr(bd, "STATE", tmp_path / "s.json")
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("ALERT_SMTP_HOST", raising=False)
    assert "No delivery channel" in asyncio.run(bd.send())["error"]
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://example.invalid/hook")

    async def brief():
        return BRIEF
    monkeypatch.setattr(business_handler, "get_morning_brief_data", brief)
    got = {}
    monkeypatch.setattr(notify, "deliver", lambda owner, text: got.update(owner=owner, text=text) or {"webhook": True})
    r = asyncio.run(bd.send("test"))
    assert r["sent"] == {"webhook": True} and got["text"].startswith("Daily Brief 2026-10-22")
    assert bd.status()["last_result"]["reason"] == "test"


def test_email_subject_is_one_line(monkeypatch):
    """A multi-line text used to become the whole Subject header (a newline there makes the send fail)."""
    import smtplib
    from api import notify
    sent = {}

    class FakeSMTP:
        def __init__(self, *a, **k):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def starttls(self):
            pass
        def login(self, *a):
            pass
        def send_message(self, m):
            sent["subject"] = m["Subject"]
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("ALERT_SMTP_HOST", "smtp.example.invalid")
    monkeypatch.setenv("ALERT_EMAIL_TO", "desk@example.invalid")
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    assert notify.deliver("Daily Brief", "Line one\nLine two") == {"email": True}
    assert sent["subject"] == "Line one"
