"""
Scheduled delivery of the Daily Brief through the alert channels (api/notify.py: webhook and / or email, configured
only in .env). Opt-in:

  BRIEF_DELIVERY_TIME   "07:00" — send each weekday at this time (24 h clock); unset = no scheduled sends
  BRIEF_DELIVERY_TZ     time zone of that time (default America/New_York)

Sent once a day (the date of the last send is kept in data/processed/brief_delivery.json, so a restart does not send
twice); "send now" (POST /api/v1/brief/send) sends whenever asked. Nothing is sent when no channel is configured.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
STATE = Path(__file__).resolve().parents[1] / "data" / "processed" / "brief_delivery.json"      # gitignored


def _state() -> Dict[str, Any]:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def _save_state(s: Dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s))


def schedule() -> Dict[str, Any]:
    t = (os.getenv("BRIEF_DELIVERY_TIME") or "").strip()
    tz = (os.getenv("BRIEF_DELIVERY_TZ") or "America/New_York").strip()
    ok = False
    if t:
        try:
            h, m = (int(x) for x in t.split(":"))
            ok = 0 <= h < 24 and 0 <= m < 60
        except ValueError:
            ok = False
    return {"time": t or None, "tz": tz, "enabled": ok, "invalid": bool(t) and not ok}


def status() -> Dict[str, Any]:
    from api import notify
    s = _state()
    return {"schedule": schedule(), "channels": notify.channels(), "last_sent": s.get("last_sent"),
            "last_result": s.get("last_result"),
            "how": "Set BRIEF_DELIVERY_TIME (e.g. 07:00) and a channel (ALERT_WEBHOOK_URL, or ALERT_SMTP_* with "
                   "ALERT_EMAIL_TO) in .env, then restart."}


def _fmt_move(m: Dict[str, Any]) -> str:
    unit = "bp" if m.get("unit") == "bp" else "%"
    ch = m.get("change")
    return f"{m.get('name')}: {ch:+.2f}{unit} ({m.get('sigma'):+.1f}σ)" if ch is not None and m.get("sigma") is not None \
        else f"{m.get('name')}: —"


def render(b: Dict[str, Any]) -> str:
    """The brief as plain text (subject on the first line: notify uses it as the e-mail subject)."""
    lines: List[str] = [f"Daily Brief {b.get('date', '')} — {b.get('headline') or b.get('regime') or ''}".strip(), ""]
    if b.get("summary"):
        lines += [b["summary"], ""]
    pr = b.get("priorities") or []
    if pr:
        lines.append("PRIORITIES")
        lines += [f"{p.get('priority', i + 1)}. [{p.get('severity', '')}] {p.get('title', '')} — {p.get('implication', '')}"
                  for i, p in enumerate(pr[:8])]
        lines.append("")
    mv = sorted(b.get("overnight") or [], key=lambda m: -abs(m.get("sigma") or 0))
    if mv:
        lines.append("OVERNIGHT (largest moves vs their last 60 sessions)")
        lines += ["  " + _fmt_move(m) for m in mv[:10]]
        lines.append("")
    rel = b.get("todaysReleases") or []
    if rel:
        lines.append("TODAY'S RELEASES (New York time)")
        for r in rel[:10]:
            cons = r.get("forecast")
            lines.append(f"  {r.get('time_et') or ''} {r.get('event', '')} [{r.get('importance', '')}]"
                         + (f" — {r.get('forecast_label') or 'consensus'} {cons}" if cons not in (None, "") else "")
                         + (f", previous {r['previous']}" if r.get("previous") not in (None, "") else ""))
        lines.append("")
    ern = b.get("earnings") if isinstance(b.get("earnings"), dict) else {}
    for key, title in (("holdings", "EARNINGS — YOUR HOLDINGS (7 days)"), ("large_caps", "EARNINGS — LARGEST REPORTERS (7 days)")):
        rows = ern.get(key) or []
        if rows:
            lines.append(title)
            lines += [f"  {e.get('symbol')} {e.get('company') or ''}: {str(e.get('datetime') or '')[:10]} {e.get('timing') or ''}"
                      + (f", EPS est. {e['eps_estimate']}" if e.get("eps_estimate") is not None else "") for e in rows[:8]]
            lines.append("")
    pos = b.get("positioning") if isinstance(b.get("positioning"), dict) else {}
    pc, aaii, cot = pos.get("put_call") or {}, pos.get("aaii") or {}, pos.get("cot_extremes") or []
    if pc or aaii or cot:
        lines.append("POSITIONING")
        if pc.get("latest"):
            lines.append(f"  Cboe equity put/call {pc['latest'].get('equity')} (10-day {pc.get('equity_10d_avg')}) — {pc.get('contrarian')}")
        if aaii.get("latest"):
            a = aaii["latest"]
            lines.append(f"  AAII bulls {a.get('bullish')} / bears {a.get('bearish')} ({a.get('date')})")
        lines += [f"  COT extreme: {c.get('market')} index {c.get('cot_index')} — {c.get('signal')}" for c in cot[:5]]
        lines.append("")
    since = b.get("sinceLastBrief")
    if isinstance(since, dict) and since.get("changes"):
        lines.append(f"SINCE {since.get('since') or 'THE LAST BRIEF'}")
        lines += [f"  {c.get('text') if isinstance(c, dict) else c}" for c in since["changes"][:8]]
        lines.append("")
    ideas = b.get("tradeIdeas") or []
    if ideas:
        lines.append("TRADE IDEAS (model)")
        lines += [f"  {i.get('direction')} {i.get('asset')} @ {i.get('entry')} stop {i.get('stop')} target {i.get('target')}"
                  f" [{i.get('conviction')}] — {i.get('rationale')}" for i in ideas[:6]]
        lines.append("")
    if b.get("risks"):
        lines.append("RISKS")
        lines += [f"  [{r.get('severity', '')}] {r.get('text') or r.get('title')}" if isinstance(r, dict) else f"  {r}"
                  for r in b["risks"][:6]]
    return "\n".join(lines).rstrip() + "\n"


async def send(reason: str = "manual") -> Dict[str, Any]:
    import asyncio
    from api import notify
    from api.handlers.business_handler import get_morning_brief_data
    ch = notify.channels()
    if not any(ch.values()):
        return {"sent": {}, "error": "No delivery channel configured (ALERT_WEBHOOK_URL or ALERT_SMTP_* in .env)."}
    brief = await get_morning_brief_data()
    text = render(brief)
    sent = await asyncio.to_thread(notify.deliver, "Daily Brief", text)
    s = _state()
    s.update(last_sent=datetime.now().isoformat(timespec="seconds"), last_result={"sent": sent, "reason": reason},
             last_date=brief.get("date"))
    _save_state(s)
    logger.info("[brief] delivered (%s): %s", reason, sent)
    return {"sent": sent, "chars": len(text), "preview": text[:600]}


def due(now: Optional[datetime] = None) -> bool:
    """Whether the scheduled send is due: a weekday, at or after the configured time, not yet sent that day."""
    from zoneinfo import ZoneInfo
    sc = schedule()
    if not sc["enabled"]:
        return False
    try:
        tz = ZoneInfo(sc["tz"])
    except Exception:                                                         # noqa: BLE001
        tz = ZoneInfo("America/New_York")
    now = (now or datetime.now(tz)).astimezone(tz)
    if now.weekday() >= 5:
        return False
    h, m = (int(x) for x in sc["time"].split(":"))
    if (now.hour, now.minute) < (h, m):
        return False
    return _state().get("scheduled_for") != now.strftime("%Y-%m-%d")


async def loop() -> None:
    """Background: check once a minute; send when due (one send per weekday)."""
    import asyncio
    from zoneinfo import ZoneInfo
    while True:
        try:
            if due():
                tz = ZoneInfo(schedule()["tz"])
                s = _state()
                s["scheduled_for"] = datetime.now(tz).strftime("%Y-%m-%d")     # mark first: never twice on errors
                _save_state(s)
                await send("scheduled")
        except Exception as e:                                                # noqa: BLE001
            logger.warning("[brief] scheduled delivery failed: %s", str(e)[:160])
        await asyncio.sleep(60)
