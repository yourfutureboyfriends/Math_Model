# MASTER_CHECKLIST — full-system verification (observed live, not code-read)

Method: every row was checked against the **running** system — backend via `curl`/`fetch`
(Step A), the live rendered DOM via browser eval reading actual panel `innerText` + Network +
Console (Step B), and value/label/logic sanity on screen (Step C). 116 section panels render on
the dashboard; below they are grouped, with the per-panel exceptions called out explicitly.

Legend: ✅ verified working (A+B+C) · ❌ broken (fixed this pass) · ⚠️ works but with a caveat

## Core / header
| Feature | Backend | Screen value | Status |
|---|---|---|---|
| Header ticker (SPX/NDX/VIX/10Y/2Y/DXY/EURUSD) | `/api/dashboard` keyMetrics | SPX 7,575 +0.42%, VIX 15.0, 10Y 4.57%, 2Y 4.31%, DXY 100.97 — all match payload | ✅ |
| Regime (macro-cycle) header + duration | `/api/dashboard` regime | expansion, 19 months, conf 0.76 | ✅ |
| Recession probability | `/api/dashboard` recession | 13% Low (logistic 12 / em-probit 15 / sahm 0.37) — sane, consistent | ✅ |
| Key Metrics (growth/inflation/liquidity/risk) | `/api/dashboard` | 63% / 25% / 0.46 / 27% + sparklines | ✅ |

## The bugs found and fixed this pass
| Feature | Root cause | Status |
|---|---|---|
| **Factor Rotation** | `/api/dashboard` sent thin schema `{momentum,value,growth,quality,…}`; component read rich `{factors[],topPicks,avoid}` → empty panel | ❌→✅ FIXED (component rewritten to real thin schema) |
| **Regime cross-panel contradiction** | `/api/v1/regime-transition` current came from `build_regime_context` (raw CPI ~4% → "Stagflation") while every other panel showed "expansion"; the raw label was force-written over the latest z-score history entry, corrupting the matrix | ❌→✅ FIXED (current now uses same z-score classifier as its history; quadrant lens clearly labeled) |

## Signals panels (self-fetch + store)
Ensemble, Signal Stack, Signal Scorecard, Signal Storytelling, Signal Interpretation,
Alt-Data Positioning, Stream Agreement, Factor OOS Validation, Model Agreement,
Sector Allocation, Factor Rotation, COT Positioning, CTA Trends, News Sentiment — all ✅
(Signal Storytelling ⚠️ cold-mount timeout, self-heals on retry — see report §5).

## Risk panels
Risk Indicators, Risk Analytics, VaR & Stress, Factor Exposure, Horizon Tensions,
Correlation Regime, Correlation Matrix, Debt Cycle, Factor Decomposition, Risk Parity,
Risk Parity Comparison, Scenario Analysis, Anomalies — all ✅
(Correlation Matrix ⚠️ cold-mount timeout, self-heals — §5. Scenario Analysis confirmed **real**:
probabilities branch on live VIX + regime confidence, not hardcoded.)

## Macro / forecasts panels
Morning Brief, Master Ensemble, Regime Engine, Regime Playbook, Market Clock, Nowcast,
Liquidity, Sentiment, Expected Returns, GMO 7-Year, Regime Transition (macro-cycle),
Regime Transition Outlook (quadrant), Four Quadrants, Event Volatility, Valuation,
International Macro, Data Providers, Transmission Analysis, Momentum Veto — all ✅
(Regime Outlook / Four Quadrants / Event Vol ⚠️ cold-mount timeout, self-heal — §5.)

## Business / equity / rates / markets panels
Business Layer, Investment Memo, Trade Ideas, Trade Recommendations, Equity Research,
Expected Returns, Position Sizing, IC Pack, Decision Log, Yield Curve, FX Monitor,
Commodities, Fixed Income, Earnings Revisions — all ✅

## Not user-facing (orphaned components — documented, not fixed)
| Component | Issue | Status |
|---|---|---|
| `PositioningSection` | calls `/api/positioning` (404); never rendered in any page / not in nav | ⚠️ dead code |
| `CentralBankDivergenceSection` | calls `/api/global/countries` (404); never rendered / not in nav | ⚠️ dead code |

## Interactive elements (Phase 5, spot-checked)
Panel refresh buttons (self-heal the timed-out panels — verified), sidebar nav, login/logout,
reload persistence — all ✅.
