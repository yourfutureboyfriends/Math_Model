# Moriah Capital Partners — the plan on the platform

Source: *Moriah Capital Partners — Future Growth Strategy*, internal discussion document, 21 October 2026.
The fund `main` is configured as Moriah Capital Partners (`api/moriah.py`, re-runnable:
`POST /api/v1/governance/setup/moriah`, admin). Panel: **Trading → Fund Governance**.

| Plan section | On the platform | Where |
|---|---|---|
| 01 Decision framework: £0 capital, 0 external AUM, phases I–IV | Stage = Phase I (research and paper portfolio). Capital is a £25,000 **paper notional**, labelled "not capital" everywhere it shows. Live capital (gate G4) is refused until the stage is Phase II. | Fund settings `stage`, `capital_basis` |
| 02–03 Mandate, initial universe, sleeves, capital allocation | Written mandate stored and shown. Approved-instruments list: 20 proposed (UCITS / London listings; spot FX as research series only). Each needs approval by a second person (PM or risk). Orders outside the approved, tradable list are blocked. | Governance → Overview, Approved instruments |
| 04 Macro Transmission Engine; engineering principles | Research runs in Quant Lab (versioned code and data hashes, holdout, walk-forward, cost model, causality check). Research code cannot place orders: an order must name a model that passed G3. | Quant Lab; Governance → Models |
| 05 Model governance G0–G5 | Model registry and gates. G0 needs mechanism, target, horizon, dataset and null hypothesis. G1 is signed by the research lead plus an independent reviewer. G2 is the IC, and the platform checks the linked backtest's costs, out-of-sample period, look-ahead and multiple-testing control. G3 is risk, and needs a loss budget and retirement criterion. G4 is IC + risk, and needs a tested kill switch and clean reconciliations. The owner can never sign off their own model. Rejected models stay in the research log. A research change after G2 makes a new version and sends the model back to G1. | Governance → Models |
| 06 Risk policy | Ex-ante risk share per model book ≤ 25% and per theme ≤ 35% (warnings needing risk sign-off). No leverage (gross ≤ 100%), no short selling, 1% daily-loss pause, strategy drawdown review at 5% and suspension at 8% from the model's high-water mark. Order size ≤ 20% of NAV, fill price within ±5% of the last close, price no older than 4 days — platform defaults, because the plan names these checks without levels. Fund limits: gross 95/100%, drawdown 5/8%. | `api/governance.py` `order_controls`; pre-trade compliance; NAV snapshot job |
| 06 Operational incident | Kill switch (manual halt or test). Any incident halt needs the fix recorded and signed off by a different person before risk can resume trading. A reconciliation break or price-band breach opens an incident. | Governance → Controls |
| 07 Organisation and governance cadence | Roles: admin (managing partner), pm (investment committee), analyst (research), quant (engineering), risk (controls). Four-eyes approval on orders, instruments, gates, incidents, expenses and milestones. | Accounts; audit log |
| 08 Technology: ledger, audit trail, reconciliation | Positions are reconciled against the fills ledger every weekday at 06:30 UTC (T+1) and on demand. The audit log is append-only. Cash comes from the ledger only, because no broker statement is connected — the reconciliation says so. | Governance → Controls |
| 09 Phase I deliverables: mandate, research archive, paper portfolio, monthly reporting | Mandate (Overview); research archive (Quant Lab results with provenance, plus the model research log); paper portfolio (simulated fills with modelled costs); monthly pack. | Governance tabs |
| 10–11 What counts as a live record; how the record is maintained | Every performance view in the fund is labelled "Simulated / paper results — not a fund track record". The monthly pack covers returns (flow-adjusted, net), risk, attribution (by sleeve, instrument and regime), implementation (signal-to-fill delay, slippage, rejected orders, outages), research changes and validation. | Governance → Monthly pack; Fund cockpit; My Desk |
| 13–15 Cost discipline, break-even AUM | First-year budget lines (£1,000 data and infrastructure, £500 hosting/tools, £1,000 external review, £500 contingency) and an expense ledger. Expenses are approved by a second person. Break-even AUM calculator using the plan's formula and its US$ illustrative grid. | Governance → Budget, Break-even AUM |
| 17–18 48-month gates, board scorecard, first 90 days | Both plans are tracked as milestones with owner, acceptance criterion and evidence. "Done" needs evidence, and sign-off is by another person. The scorecard is computed from the ledger, models, reconciliations and budget. Commercial items are entered by the team. | Governance → Roadmap, Overview |
| 12, 16 Fund formation, seed sequence | Not automated: these are legal and commercial projects. Record their milestones on the roadmap. | — |

## Added 26 Oct 2026

| Plan item | On the platform | Where |
|---|---|---|
| 04 Event dataset ("surprise, timing, regime"), months 3–6 milestone | Macro event dataset: US CPI, core CPI, payrolls and unemployment as published at the time (ALFRED vintages), and FOMC decisions. Each event has a labelled surprise proxy (consensus forecasts are licensed) and the cross-asset reaction from the first close after the release. Versioned by hash, with CSV export. | Overview → Macro Event Dataset; `/api/v1/research/events` |
| 05 G3 shadow trading; 08 "execute only approved builds" | In a governed fund, a Quant Lab paper deployment must name a model at G2 or later. Its locked daily record is the G3 evidence: sessions recorded, plus live vs backtest volatility and Sharpe, with drift flags. | Governance → Models (shadow box); Quant Lab deploy |
| 06 Stress conditions | Historical replays of the actual book in base currency: COVID crash, Brexit gap, gilt crisis, 2022 stocks-and-bonds sell-off, March 2020 dash for cash. Also a sterling +10% shock and a data-outage procedure check. Shown in the monthly pack with coverage. | Governance → Monthly pack |
| 08 Security: MFA | Two-factor sign-in with an authenticator app (TOTP) and single-use recovery codes. An administrator can require it for every account and reset a lost device. | Account → Two-factor |
| 08 Licence check of every data supplier | Data-source register. Every source starts unreviewed until the fund records allowed / restricted / not allowed, citing the terms it read. | Governance → Data licences |
| 11 Attribution by sleeve / instrument | Daily position snapshots, so month-end P&L = realised + change in unrealised. | Monthly pack |

**Benchmark:** cash in GBP (iShares £ Ultrashort Bond ETF proxy), the plan's "no-trade alternative". Sector Brinson
attribution does not apply to it; attribution is by sleeve, instrument and regime in the monthly pack. The plan's
other counterfactuals (simple trend, carry) are models in the registry: the benchmark / baseline sleeve.

**Decisions left to the founders:** approve or change the instrument list; set the paper notional; adjust the
illustrative limits; assign people to roles; record the founders' agreement and the other day 1–15 outputs.
