# Quant Lab — audit against industry standard (13 October 2026)

Engine after this audit: `2026.10-ledger.5` (`api/quant/codelab.py`). Reference points: QuantConnect LEAN and
Zipline/Quantopian (backtest engines), Alphalens and pyfolio (signal and performance tear sheets), Bloomberg PORT /
MSCI Barra / Axioma (risk, attribution, optimisation), López de Prado and Bailey et al. (overfitting statistics),
AQR / Frazzini–Israel–Moskowitz and Almgren–Chriss (trading costs), CBOE strategy indices (options).

## Verdict

The engine's accounting and cost modelling were already at or above the open-source standard (LEAN, Zipline).
The gaps were **around** the backtest: volume-limited execution, capacity, overfitting statistics beyond the deflated
Sharpe ratio, look-ahead protection for vectorised code, attribution, ex-ante risk, portfolio construction tools
and signal research. All of those are now in. What remains is mostly **data** that is not free: point-in-time
fundamentals, survivorship-free global universes, historical option quotes, intraday bars and real borrow rates.

## Scorecard

| Area | Industry standard | Before | Now | Remaining gap |
|---|---|---|---|---|
| Accounting | Self-financing cash + positions ledger (LEAN, Zipline) | ✅ units + cash, NAV reconciled daily | ✅ | — |
| Timing / causality | Event-driven engines make look-ahead impossible; vectorised ones (BQuant, Zipline pipeline) rely on discipline | ⚠️ next-open fills, causal helpers, but user code could peek (`shift(-1)`, full-sample stats) | ✅ **look-ahead detector**: every run recomputes decisions from data truncated at two dates and must match | Detects, not prevents; unseeded randomness also flags |
| Fills | Next bar, VWAP or close; partial fills by volume (Zipline: 2.5% of bar volume) | ⚠️ next open only, unlimited size | ✅ next open / next-day VWAP / next close; **volume participation cap** (default 10% of ADV), remainder carried | No limit or stop orders; no intraday |
| Trading costs | Commission, spread, square-root impact, fees, taxes | ✅ AQR-calibrated impact, vol/ADV spread, SEC fee, stamp duties, FX conversion, lots, ticks | ✅ + new listings no longer escape impact/caps (bug fixed) | Spread model is calibrated on US data |
| Short selling | Borrow fees by name; locate; recalls | ⚠️ one flat fee | ✅ **hard-to-borrow tiers** by liquidity (0.3% → 5%) | No real borrow rates, locates or recalls (not free) |
| Margin | Reg-T / portfolio margin, margin calls (LEAN) | ❌ gross cap only | ✅ maintenance margin with **forced deleveraging** events; option margin | Simplified option margin |
| Multi-currency | Base currency, FX marks, hedging | ✅ (built earlier today) | ✅ 38 account currencies, hedging, withholding | — |
| Options | Historical chains (OptionMetrics/ORATS — paid) | ✅ synthetic, validated vs CBOE PUT (corr 0.96) | ✅ + spreads library entry, notional sizing | No quotes: no real skew, bid/ask or early exercise |
| Universe / survivorship | Point-in-time, delisted names included (CRSP, QuantConnect) | ⚠️ PIT S&P 500 only | ⚠️ same | Global PIT membership not free |
| Fundamentals | Point-in-time, as-reported (Compustat PIT) | ❌ (13F only) | ❌ | Needs a PIT fundamentals source |
| Walk-forward / holdout | Rolling re-estimation, untouched holdout | ✅ continuous walk-forward, HOLDOUT, trial registry | ✅ | — |
| Overfitting statistics | DSR, PBO (CSCV), CPCV | ⚠️ PSR / deflated Sharpe | ✅ + **PBO by CSCV** over the PARAMS grid | CPCV for ML-style models |
| Signal research | Alphalens: IC by horizon, quantile returns, turnover, decay | ❌ | ✅ optional `signal()` → **IC table, quintile returns, turnover, autocorrelation** | Sector-neutral IC option |
| Capacity | AUM vs net Sharpe curve | ❌ | ✅ **capacity curve** at $1m–$1bn | Uses daily ADV only |
| Ex-post analytics | pyfolio tear sheet | ✅ deep report (drawdowns, rolling, regimes, crises, bootstrap, VaR/CVaR, capture) | ✅ | — |
| Attribution | Holdings-based P&L by security/sector/country/currency (PORT) | ⚠️ cost breakdown + ETF factor lens | ✅ **P&L by holding, sector, country, currency; currency vs local** | Brinson vs benchmark weights |
| Ex-ante risk | Factor risk model, VaR, risk decomposition, stress tests (Barra, PORT) | ❌ | ✅ **shrinkage-covariance risk model**: vol, beta, VaR/ES (parametric + historical), risk contribution by position/group, **today's book through 8 crises** | Statistical, not a fundamental factor model |
| Portfolio construction | Optimiser with constraints (Axioma, cvxpy) | ❌ | ✅ `cov_shrink`, `optimize` (mean-variance, box, budget, long/short, group caps, turnover penalty), `min_variance`, `risk_parity` | No factor-exposure constraints |
| Reproducibility | Versioned engine, data and code hashes; stored runs | ✅ versions + hashes + trial registry | ✅ | Full run artefacts not stored for side-by-side comparison |
| Paper / live | Paper and broker integration (LEAN) | ✅ paper books from daily sandboxed re-runs | ✅ | No OMS or broker by policy; no live option snapshots (no quotes) |
| Security | Isolated execution of user code | ✅ AST rules, audit hook, sandbox-exec, limits | ✅ | — |

## What was wrong (found in this audit, fixed)

1. **New listings escaped the volume model.** Without 63 days of history the average traded value was missing, so
   orders were neither impact-charged nor size-limited — a $1m order in a $100k/day stock filled at once. Now the
   previous day's traded value is used until the average exists.
2. **Look-ahead was possible and invisible.** A strategy using next month's prices showed 77.8% a year (Sharpe 4.1);
   nothing flagged it. The new check catches it (first divergent decision: 2018-10-01, IEF 25% → 0%).
3. **PBO on identical parameter sets** reported 100% instead of "not applicable" — fixed.
4. **Unclear errors for live-trading code.** A strategy written for a live option chain (`data.options`,
   `data.asof`, returns orders) failed with a UNIVERSE size message. It now explains the difference between a live
   order generator and a backtest, and points to the backtestable "Index put credit spreads" strategy.
   Options-only strategies no longer need a UNIVERSE line (the underlyings are used).
5. Earlier today: the sandbox dropped venue taxes; options were sized by premium instead of notional (2020 put-write
   off by 15 points); a last option contract expiring after the data was settled early. All fixed and tested.

## What we got right (keep)

- One self-financing ledger shared by every surface, reconciled daily; next-session fills; explicit delistings.
- A cost model that is more complete than LEAN's or Zipline's defaults (square-root impact calibrated on live
  trades, liquidity-based spreads with exchange tick floors, stamp duties, FX conversion, lots, withholding).
- Overfitting discipline built into the workflow: continuous walk-forward, holdout views counted, trial registry,
  deflated Sharpe, an equal-weight baseline under identical costs — results that remove hindsight are shown next to
  the flattering ones.
- Code runs in the browser for research and in a locked sandbox for deployment; the same engine file in both.

## Evidence (runs on real data, this session)

| Check | Result |
|---|---|
| 15-ETF momentum, PARAMS 3 sets | causality passed; PBO 33%; capacity ≥ $1bn (Sharpe 0.66 → 0.56, costs 0.2% → 1.9%/yr); ex-ante vol 14%, beta 0.64; today's book in the GFC −46% (S&P −46%) |
| Same with a 21-day peek | causality **failed**; signal IC 0.95 (t = 161) — the classic signature of look-ahead |
| Synthetic PutWrite vs CBOE ^PUT, 2008–2026 | monthly corr 0.96; 8.1% vs 7.2%/yr; worst drawdown −36.7% vs −37.1% |
| Tests | `api/tests/test_research_grade.py` (10), `test_options.py`, `test_market_rules.py`, `test_account_currency.py`; full suite green |

## Follow-up (same day): the next steps, built — engine `2026.10-ledger.5`

| Item | What it is | Where |
|---|---|---|
| Point-in-time fundamentals | `FUNDAMENTALS = True` (or a list) → `data.fund[...]`: SEC XBRL figures as first filed, from the session after filing; value ratios on the USD price (book/price, earnings/fcf/sales yield, ROE, gross profitability, leverage, market cap…). US filers | `codeserver.fundamental_frames`, `providers/sec_edgar.py` |
| Fundamental factor risk model | Barra-style: daily cross-sectional regressions on sector dummies + styles (momentum, volatility, size; value and quality with fundamentals); factor covariance + shrunk specific risk; the book's style exposures, factor vs specific share, risk by factor. `style_exposures(data, date)` for strategies | `codelab.factor_risk`, `style_frames` |
| Optimiser | Exact quadratic programme (ADMM, as in OSQP; numpy only) with box, budget, long/short gross & net, sector caps and **factor-exposure bands** (`exposures`, `factor_bounds`); quadratic turnover cost. 0.04 s for 30 names (was 5 s with projections) | `codelab.optimize`, `_qp` |
| Event-driven mode | `on_bar(ctx, **params)` after every close, seeing only the past and the real account (`ctx.history`, `positions`, `nav`, `cash`, `fills`, `state`); market (`ctx.target`), **limit** and **stop** orders (triggered on the next session's range, filled at the order price or a worse/better open on gaps), cancel, expiry; optional `setup(data)` indicators (look-ahead-checked). PARAMS walk-forward switches parameter sets on one continuing account. Event grids run as server jobs | `codelab.Ctx`, `backtest(on_bar=…)`, `_run_events` |
| Brinson attribution | Brinson–Fachler vs the equal-weight universe by sector (or country): allocation, selection, interaction, cash | `codelab.backtest` (daily), `attribution()` |
| CPCV | Combinatorial purged cross-validation of the parameter choice: 6 blocks, 2 held out, 5-day embargo → 5 out-of-sample paths; Sharpe distribution | `codelab.cpcv` |
| Stored runs & comparison | Every run stored (newest 50 per user); Runs & compare tab: reopen any run, open its code, tick 2–4 to overlay growth on a common window with statistics, validation and differing settings side by side | `store.save_result`, `/api/v1/quant/code/runs`, `Runs.tsx` |

Also fixed while building these: the look-ahead check could not read `setup()` output (now checked); interactive
Code Lab requests queued behind paper-trader book refreshes after a restart (now a separate queue).

Remaining, by value: real (non-modelled) option and borrow data; global survivorship-free universes; intraday bars.
