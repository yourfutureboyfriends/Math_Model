# IMPROVEMENT_LOG — autonomous self-directed improvement loop

Each cycle: observe the live system → find the highest-value problem → fix at the root →
verify against the running system → check collateral → log + commit.

| Cycle | Problem found | Root cause | Fix | Verification evidence |
|---|---|---|---|---|
| 1 | `/api/earnings/revisions` returned a **hardcoded fake per-sector EPS table** (Tech +2.5%/68%, Comm +3.2%/71%, …) stamped with `updated_at: now()` — fabricated numbers disguised as live data (priority-1 violation). Surfaced in the Sector Allocation panel's "EPS Rev" column. | With no `FINNHUB_API_KEY` (keyless env) the endpoint's fallback branch returned a static sector dict; the real Finnhub path returns a *different* schema (`{revision_breadth, tickers}`) the frontend can't even consume for sectors — so the fake table was the ONLY source the panel ever used. | Backend: replaced the fabricated fallback with structured absence `{available:false, reason, sectors:{}, divergences:[]}`. Frontend `SectorAllocationSection`: EPS becomes `null` (not `0`) when overlay unavailable → renders "—", header shows `EPS REV*` with a footnote naming the reason; the real regime-based Score/Signal/Bar are untouched. | Backend curl now returns `available:false` + reason (no numbers). Live UI (re-login, observed): every sector shows "—" for EPS Rev, `hasFabricated:false` (no 2.5%/3.2%/-2.1% present), footnote "* Sector EPS-revision data requires a Finnhub API key…" shown, real scores intact (Technology +0.50, Financials +0.30). Regime "EXPANSION" consistent app-wide. |
