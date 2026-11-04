"""Fed watch: statement redline, tone lexicon, dissent and vote parsing (network mocked)."""


def test_redline_marks_word_changes():
    from api.marketdata.fedwatch import redline
    out = redline("The Committee decided to raise the target range by 1/4 percentage point.",
                  "The Committee decided to maintain the target range.")
    ops = [(x["op"], x["text"]) for x in out]
    assert ("del", "raise") in ops and ("add", "maintain") in ops
    assert "".join(x["text"] for x in out if x["op"] != "del").replace(" ", "") == "TheCommitteedecidedtomaintainthetargetrange."


def test_tone_counts_phrases_not_words():
    from api.marketdata.fedwatch import tone
    hawk = tone("Inflation remains elevated. The Committee is prepared for further tightening.")
    dove = tone("Inflation has eased and downside risks to employment have risen; the Committee will lower the target range.")
    assert hawk["score"] > 0 and hawk["label"] == "hawkish" and "further tightening" in hawk["hawkish"]
    assert dove["score"] < 0 and dove["label"] == "dovish"
    assert tone("Inflation was discussed.")["score"] == 0                  # a bare topic word is neutral


def test_statement_parsing_vote_and_dissent(monkeypatch, tmp_path):
    from api.marketdata import fedwatch as F
    monkeypatch.setattr(F, "ARCHIVE", tmp_path)
    monkeypatch.setattr(F, "_cached", lambda k, t, fn: fn())
    feed = """<rss><item><title>Federal Reserve issues FOMC statement</title><link>https://x/monetary20261028a.htm</link>
      <pubDate>Wed, 28 Oct 2026 14:00:00 EST</pubDate></item><item><title>Federal Reserve issues FOMC statement</title>
      <link>https://x/monetary20260916a.htm</link><pubDate>Wed, 16 Sep 2026 14:00:00 EST</pubDate></item></rss>"""
    pages = {
        "https://x/monetary20261028a.htm": '<div id="article"><p>October 28, 2026</p><p>approved by a 10–2 vote:</p>'
                                           '<p>The Committee decided to maintain the target range.</p>'
                                           '<p>Voting against the monetary policy action were Lisa D. Cook and Beth M. Hammack, who preferred to raise.</p>'
                                           '<p>For media inquiries, call 202</p></div>',
        "https://x/monetary20260916a.htm": '<div id="article"><p>approved by a 12–0 vote:</p><p>The Committee decided to raise the target range.</p></div>',
    }
    monkeypatch.setattr(F, "_get", lambda url: feed if url.endswith(".xml") else pages[url])
    d = F.fedwatch()
    assert d["latest"]["date"] == "2026-10-28" and d["previous"]["date"] == "2026-09-16"
    assert d["latest"]["vote"] == "10–2" and d["latest"]["dissents"] == 2
    assert d["latest"]["dissent"].endswith("who preferred to raise.") and "Lisa D. Cook" in d["latest"]["dissent"]
    assert "media inquiries" not in d["latest"]["text"] and d["latest"]["text"].startswith("The Committee")
    assert ("add", "maintain") in [(x["op"], x["text"]) for x in d["redline"]]


def test_margin_debt_yoy_and_net(monkeypatch):
    """FINRA margin statistics: year-on-year growth and debit net of free credit, newest month last."""
    import io
    import pandas as pd
    from api.marketdata import freedata as F
    months = [f"{y}-{m:02d}" for y in (2025, 2026) for m in range(1, 13)][:21][::-1]      # newest first, as FINRA ships it
    df = pd.DataFrame({"Year-Month": months,
                       "Debit Balances in Customers' Securities Margin Accounts": [1000.0 + 10 * (20 - i) for i in range(21)],
                       "Free Credit Balances in Customers' Cash Accounts": [200.0] * 21,
                       "Free Credit Balances in Customers' Securities Margin Accounts": [100.0] * 21})
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    monkeypatch.setattr(F, "_cached", lambda k, t, fn: fn())
    monkeypatch.setattr(F, "_get", lambda url, timeout=30, **k: type("R", (), {"content": buf.getvalue()})())
    d = F.margin_debt()
    assert d["latest"]["month"] == "2026-09" and d["latest"]["debit_bn"] == 1.2
    assert abs(d["latest"]["yoy"] - (1200 / 1080 - 1)) < 1e-3 and d["latest"]["net_bn"] == 0.9
