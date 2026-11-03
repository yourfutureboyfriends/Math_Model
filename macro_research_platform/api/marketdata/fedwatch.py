"""
Fed watch: what changed in the FOMC statement, who dissented, and how hawkish or dovish the Fed's words are.

Statements and speeches come from the Federal Reserve's own RSS feeds and press pages (federalreserve.gov, free, no
key). Each statement is compared word by word with the one before — the redline desks read first on decision day.
Tone is a transparent lexicon score (hawkish minus dovish phrases per 1,000 words), not a model: it shows direction
and change, and every matched phrase is listed so the score can be checked.
"""
from __future__ import annotations

import difflib
import html
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from api.marketdata.core import Upstream, _cached

logger = logging.getLogger(__name__)
UA = {"User-Agent": "Mozilla/5.0 (macro research terminal; contact via repository)"}
FEEDS = {"monetary": "https://www.federalreserve.gov/feeds/press_monetary.xml",
         "speeches": "https://www.federalreserve.gov/feeds/speeches.xml"}
ARCHIVE = Path(__file__).resolve().parents[2] / "data" / "processed" / "fedwatch"

# Phrases, not single words: "inflation" alone is neutral; "inflation remains elevated" is not.
HAWKISH = ["inflation remains elevated", "elevated inflation", "upside risks to inflation", "inflation risks",
           "further tightening", "additional policy firming", "firming", "raise the target range", "restrictive",
           "higher for longer", "strong labor market", "tight labor market", "robust", "solid pace", "overheating",
           "price stability", "not yet confident", "premature", "vigilant", "unacceptably high", "persistent",
           "reduce its holdings", "balance sheet runoff"]
DOVISH = ["lower the target range", "reduce the target range", "rate cut", "easing", "accommodative", "accommodation",
          "downside risks", "softening", "slowed", "moderated", "has eased", "cooling", "weakened", "unemployment rate has moved up",
          "labor market has softened", "patient", "support the economy", "greater confidence", "disinflation",
          "slower pace", "end the reduction", "conclude the reduction", "financial conditions have tightened"]


def _get(url: str) -> str:
    import requests
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    r.encoding = "utf-8"                    # the pages are UTF-8; requests guessed Latin-1 and mangled "10–2"
    return r.text


def _feed(name: str) -> List[Dict[str, str]]:
    xml = _get(FEEDS[name])
    out = []
    for it in re.findall(r"<item>(.*?)</item>", xml, re.S):
        g = lambda tag: html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", (re.search(rf"<{tag}>(.*?)</{tag}>", it, re.S) or [None, ""])[1])).strip()
        try:
            from email.utils import parsedate_to_datetime
            when = parsedate_to_datetime(g("pubDate")).date().isoformat()
        except (TypeError, ValueError):
            when = None
        out.append({"title": g("title"), "link": g("link"), "date": when, "description": g("description")})
    return out


def _page_text(url: str) -> str:
    """The article body of a federalreserve.gov press release or speech, cached on disk (they never change)."""
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    path = ARCHIVE / (re.sub(r"[^a-z0-9]+", "_", url.lower())[-90:] + ".txt")
    if path.exists():
        return path.read_text()
    page = _get(url)
    m = re.search(r'<div[^>]+id="article"[^>]*>(.*?)<div[^>]+(?:id="lastUpdate"|class="[^"]*lastUpdate)', page, re.S) \
        or re.search(r'<div[^>]+id="article"[^>]*>(.*)', page, re.S)
    body = m.group(1) if m else page
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body, flags=re.S)
    paras = [html.unescape(re.sub(r"<[^>]+>", " ", p)) for p in re.findall(r"<p[^>]*>(.*?)</p>", body, re.S)]
    text = "\n\n".join(re.sub(r"\s+", " ", p).strip() for p in paras if p.strip())
    path.write_text(text)
    return text


def _statement_core(text: str) -> str:
    """The statement proper: from the opening paragraph to the vote, without the media boilerplate."""
    paras = [p for p in text.split("\n\n") if p.strip()]
    # skip the page header (date, "For release at…", share links): the statement starts with its first sentence
    start = next((i for i, p in enumerate(paras) if re.match(r"(The Federal Open Market Committee|Recent indicators|"
                                                             r"Although|Inflation|The Committee)", p)), 0)
    paras = paras[start:]
    keep = []
    for p in paras:
        if re.match(r"(For media inquiries|Implementation Note|Last Update|Board of Governors)", p):
            break
        keep.append(p)
    return "\n\n".join(keep)


def tone(text: str) -> Dict[str, Any]:
    t = " " + re.sub(r"\s+", " ", text.lower()) + " "
    words = max(1, len(t.split()))
    hits = lambda lex: {p: t.count(" " + p) for p in lex if t.count(" " + p)}
    h, d = hits(HAWKISH), hits(DOVISH)
    hs, ds = sum(h.values()), sum(d.values())
    return {"score": round((hs - ds) / words * 1000, 2), "hawkish": h, "dovish": d, "words": words,
            "label": "hawkish" if hs > ds * 1.25 else "dovish" if ds > hs * 1.25 else "balanced"}


def redline(old: str, new: str) -> List[Dict[str, str]]:
    """Word-level differences: [{op: eq|add|del, text}], merged into readable runs."""
    a, b = re.findall(r"\S+|\n\n", old), re.findall(r"\S+|\n\n", new)
    out: List[Dict[str, str]] = []

    def push(op: str, toks: List[str]):
        if not toks:
            return
        text = " ".join(toks).replace(" \n\n ", "\n\n").replace("\n\n ", "\n\n").replace(" \n\n", "\n\n")
        if out and out[-1]["op"] == op:
            out[-1]["text"] += " " + text
        else:
            out.append({"op": op, "text": text})
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if tag == "equal":
            push("eq", a[i1:i2])
        else:
            push("del", a[i1:i2])
            push("add", b[j1:j2])
    return out


def _dissent(text: str) -> Optional[str]:
    """The vote paragraph naming dissenters (names carry initials, so it is taken whole, not to the first period)."""
    return next((p.strip() for p in text.split("\n\n") if p.strip().startswith("Voting against")), None)


def fedwatch() -> Dict[str, Any]:
    def build():
        try:
            monetary, speeches = _feed("monetary"), _feed("speeches")
        except Exception as e:                                           # noqa: BLE001 — shown as unavailable
            raise Upstream(f"Federal Reserve feeds unavailable: {e}")
        # statements seen before stay on disk, so the comparison survives the feed rolling over
        ARCHIVE.mkdir(parents=True, exist_ok=True)
        idx_path = ARCHIVE / "statements.json"
        try:
            known = json.loads(idx_path.read_text())
        except Exception:
            known = {}
        for it in monetary:
            if "FOMC statement" in it["title"] and it["link"] not in known:
                known[it["link"]] = {"date": it["date"], "link": it["link"]}
        idx_path.write_text(json.dumps(known))
        stmts = sorted(known.values(), key=lambda s: s["date"] or "")[-8:]
        for s in stmts:
            try:
                s["text"] = _statement_core(_page_text(s["link"]))
            except Exception as e:                                       # noqa: BLE001
                logger.info("[fedwatch] %s: %s", s["link"], e)
                s["text"] = ""
            s["tone"] = tone(s["text"]) if s["text"] else None
            s["dissent"] = _dissent(s["text"]) if s["text"] else None
            v = re.search(r"by a (\d+)\s*[–-]\s*(\d+) vote", _page_text(s["link"]) if s["text"] else "")   # in the page header
            s["vote"] = f"{v.group(1)}–{v.group(2)}" if v else None
            s["dissents"] = int(v.group(2)) if v else (1 if s["dissent"] else 0)
        stmts = [s for s in stmts if s["text"]]
        latest = stmts[-1] if stmts else None
        prev = stmts[-2] if len(stmts) > 1 else None
        diff = redline(prev["text"], latest["text"]) if latest and prev else None
        changed = sum(len(x["text"].split()) for x in diff or [] if x["op"] != "eq")
        sp = []
        for it in speeches[:12]:
            speaker, _, topic = it["title"].partition(",")
            row = {"date": it["date"], "speaker": speaker.strip(), "title": topic.strip() or it["title"], "link": it["link"]}
            try:
                row["tone"] = tone(_page_text(it["link"]))
            except Exception as e:                                       # noqa: BLE001 — listed without a score
                logger.info("[fedwatch] speech %s: %s", it["link"], e)
                row["tone"] = None
            sp.append(row)
        return {"latest": {k: latest[k] for k in ("date", "link", "tone", "dissent", "vote", "dissents", "text")} if latest else None,
                "previous": {k: prev[k] for k in ("date", "link", "tone")} if prev else None,
                "redline": diff, "words_changed": changed,
                "statements": [{"date": s["date"], "link": s["link"], "score": (s["tone"] or {}).get("score"),
                                "label": (s["tone"] or {}).get("label"), "dissent": s["dissent"], "vote": s["vote"],
                                "dissents": s["dissents"]} for s in stmts],
                "speeches": sp,
                "method": "Tone = (hawkish − dovish phrases) per 1,000 words, from a fixed phrase list (every match is shown). "
                          "A reading aid, not a forecast: context and negation are not parsed.",
                "source": "Federal Reserve Board press releases and speeches (federalreserve.gov RSS)"}
    return _cached("fedwatch:v3", 3 * 3600, build)
