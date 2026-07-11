# BUGFIX_ROUND_REPORT — News Sentiment + Panel Numbering

## Issue 1 — News Sentiment panel not working

**Root cause (a double bug):**
1. **Stub data source.** The "NLP News Sentiment Engine" was a stub — `get_news_sentiment_data`
   and the dashboard's `_news_sentiment` both *faked* a sentiment label from the VIX level and
   returned `articles: []`. No news, no NLP, ever fetched.
2. **Contract mismatch.** Even with data, the panel reads `data.overall.score`,
   `data.byTheme.{inflation,growth,fed}`, and `data.topBullish/BearishHeadlines` from the
   dashboard payload — but the backend produced `{overallSentiment, score, articles}`. So the
   panel read `undefined` → `0.0`, no themes, "No articles today".

**Fix (at the real root cause — a real integration, not a patch):**
- `api/calculations/news_sentiment.py` — a pure, finance-lexicon headline scorer
  (Loughran-McDonald-style word lists), `score_headline` in [-1,+1] + `aggregate_sentiment`.
  **6 known-answer tests.**
- `dashboard_handler._build_news_sentiment` — fetches **real live headlines** from the keyless
  RSS `NewsProvider` (Reuters / Bloomberg / FT), scores each, and builds the exact shape the
  panel reads: `overall`, per-theme (inflation/growth/fed), top bullish/bearish headlines,
  regime-consistency. Cached 10 min (feeds move slowly). **Honest empty fallback** if feeds
  are unreachable — never a fabricated number.
- The panel now shows a **source + timestamp** line ("RSS (Reuters/Bloomberg/FT) +
  finance-lexicon NLP · HH:MM").
- General-rule pass: the `/api/news-sentiment` **endpoint** was the same stub — rewired to the
  same real source (mapped to its `NewsSentimentData` response model).

**Evidence (live, after clean restart + hard refresh):** panel renders **"10 articles"**, Fed
theme, "Consistent with regime", source + timestamp. Endpoint returns 200 with 10 real
headlines ("Apple sues OpenAI…", …). Today's headlines score Neutral 0.0 — an honest real
result, not a placeholder. Zero console errors.

## Issue 2 — panel numbering wrong (12, 13, then 34, 35)

**Root cause:** section numbers were **hardcoded per component** (`<span className="section-tag">33</span>`)
and never re-sequenced as panels were added/removed/reordered. The 34 numeric badges had
**duplicates** (04×3, 08×3, 30×4) and **gaps** (no 01, 02, 05, 11, 13, 17, …) and did not match
render order — exactly the reported "12,13 then 34,35".

**Fix strategy — Option A (remove).** Verified nothing references these numbers as stable IDs
(checked command palette, help, deep-links → none); 17 newer panels already used a meaningful
icon in `section-tag` instead of a number. So the broken hardcoded sequence was removed: all 34
numeric badges → a neutral **◆** marker (matching the sidebar's bullets). Result: **zero numeric
badges page-wide** → no gaps, no duplicates, no wrong-order possible, and the app is consistent
(icon or ◆, never a stale number).

**Evidence:** live DOM scan → `numericBadgesRemaining: []`; screenshot shows "◆ SENTIMENT",
"◆ VALUATION FILTER", "◆ EXPECTED RETURNS" etc.

## Panel ordering (2E) — status
The **navigation order** (what users actually use) was already re-sequenced to the trading-day
workflow in the prior round (sidebar: BRIEF → SIGNALS → RISK → FORECASTS → DECIDE → POSITIONS →
SYSTEM; see IA_CURRENT.md). The single-scroll **render order** in `DashboardPage` still follows
the original build sequence. Reordering the 56 inline JSX blocks is a higher-risk change with
low marginal value now that the misleading numbers are gone and the sidebar drives navigation —
**flagged, not done this round** (honest).

## Same-pattern check elsewhere (general rule)
- **Hardcoded sequence numbers:** all 34 removed; none remain.
- **Stub "never wired" data sources:** the news stub (both the dashboard path and the endpoint)
  is now real. Other signal handlers checked (`get_longterm_forecasts_data`,
  `get_reflexivity_data`) derive from **real** dashboard values (yields/regime), not empty stubs
  — simplified models, but not fabricated-empty. No other empty-stub providers found this pass.

## Verification
Clean backend restart (0 errors); `/api/news-sentiment` 200 with real data; panel renders real
sourced sentiment; **0 numeric badges**; **188 backend unit tests pass**; frontend build passes;
zero console errors in the walkthrough.
