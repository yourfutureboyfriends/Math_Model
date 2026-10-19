"""
Options strategy research — the Quant Lab's research environment for defined-risk option strategies (bull put credit
spreads, bull call debit spreads, bear put debit spreads, short iron condors), market-regime models, portfolio
construction and validation, with a research registry and a controlled export of approved configurations for the
separate Quant Algorithm. Research only: nothing here places orders.

Data classes — every result carries one, and they are never mixed silently:

  observed            published market series: underlying prices, CBOE volatility indices (ATM implied volatility for
                      16 underlyings since 2011) and CBOE strategy benchmark indices (PUT, CNDR, BFLY, BXM, …).
  model_observed_iv   option prices from Black–Scholes–Merton with OBSERVED at-the-money implied volatility (a CBOE
                      index for that underlying) and a MODELLED smile, term structure and bid/ask.
  model_iv            option prices with MODELLED implied volatility (from realised volatility and the market's
                      implied/realised ratio, fitted on 2011–2018 observed-IV names and tested after) — single stocks
                      without a CBOE index.

No historical option quotes (bid/ask, open interest, listed strikes) are available from free sources; option-level
results are model-based simulations and are labelled so. See docs/options_research_2026-10.md.

Modules: pricing (BSM, greeks, strikes, expiries), vol (CBOE data, IV model, calibration), market (cached research
panel), strategies (the four spreads, signals, grids), simulate (vectorised trade paths and exits), portfolio
(position limits, risk budgets, Greeks, NAV), regimes, validate, analytics, registry, deploy, runner.
"""
