# IA_CURRENT — information architecture, before → proposed (Phase 3)

The app is a **single scrolling dashboard with a grouped left sidebar** (not tabs); the
sidebar groups ARE the IA. Below is the current grouping and a workflow-driven re-grouping.

## Current sidebar groups (order = as built, by data category)
1. **MORNING BRIEF** — morning-brief
2. **OVERVIEW** — anomalies, master-signal, key-metrics, regime, regime-playbook, market-clock
3. **SIGNALS** — signal-interp, ensemble, signal-stack, signal-story, signal-scorecard, alt-data, sector-allocation, factor-rotation, cot, model-agreement, cta-trend, news-sentiment
4. **RISK** — risk-indicators, risk-analytics, factor-exposure, var-stress, debt-cycle, advanced, correlation, correlation-matrix, factor-decomposition, risk-parity, horizon-tension
5. **FORECASTS** — nowcast, liquidity, sentiment, yield-curve, valuation
6. **STRATEGY** — expected-returns, gmo, fx-monitor, commodities, fixed-income, international, reflexivity, transmission, regime-transition, regime-outlook, momentum-veto
7. **RESEARCH** — equity-research
8. **PORTFOLIO** — positions, trade-workflow, trade-ideas, trade-recommendations, scenario-analysis, model-portfolio, performance-attribution, data-to-watch, investment-memo, business-layer, economic-calendar, event-vol
9. **SYSTEM** — system-health, data-providers, system-audit

### The core IA problem (matches the prompt's diagnosis)
**Decisions are buried under PORTFOLIO next to review activities.** `trade-ideas`,
`trade-recommendations`, `trade-workflow`, `scenario-analysis` (EXECUTION/DECISION) sit in the
same group as `performance-attribution`, `investment-memo` (REVIEW). RESEARCH is a one-item
group. STRATEGY mixes forward decisions (expected-returns) with market monitors (fx/commodities).

## Proposed grouping (workflow: Brief → Signals → Risk → Forecasts → Decide → Positions → System)

1. **BRIEF** (merge MORNING BRIEF + OVERVIEW) — start-here glance: morning-brief, master-signal, key-metrics, anomalies, regime, regime-playbook, market-clock
2. **SIGNALS** — actionable consensus first: ensemble, signal-stack, signal-scorecard, signal-story, signal-interp, alt-data, model-agreement, sector-allocation, factor-rotation, cot, cta-trend, news-sentiment
3. **RISK** — risk-indicators, risk-analytics, var-stress, factor-exposure, **horizon-tension** (forward risk timing, moved in), correlation, correlation-matrix, debt-cycle, factor-decomposition, risk-parity, advanced
4. **FORECASTS** — decision-relevant first: valuation, nowcast, yield-curve, liquidity, sentiment, expected-returns, gmo, regime-transition, regime-outlook, event-vol
5. **DECIDE** (NEW — the key fix) — trade-ideas, trade-recommendations, trade-workflow, scenario-analysis, momentum-veto
6. **POSITIONS** — model-portfolio, positions, performance-attribution, equity-research, business-layer, fx-monitor, commodities, fixed-income, international, reflexivity, transmission
7. **SYSTEM** — economic-calendar, data-to-watch, investment-memo, system-health, data-providers, system-audit

**Rationale:** DECIDE separates execution from review (the headline fix); BRIEF is the single
glanceable start; SIGNALS leads with consensus not raw breakdowns; horizon-tension joins RISK;
market monitors move to POSITIONS/monitoring; low-frequency items (calendar, memos, system) sink.

## Scope note
Implemented: the sidebar **re-grouping** above (the IA users actually navigate), with the
command-palette registry already covering the new panel names. The full Phase-4 conversion to
7 discrete **tabbed views** with every panel rebuilt on shared primitives is a separate,
high-regression rewrite of 56 working panels — see OVERHAUL_REPORT.md for the honest status.
