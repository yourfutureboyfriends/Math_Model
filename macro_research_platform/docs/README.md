# Documentation index

**Start here:** [CODEBASE_MAP.md](CODEBASE_MAP.md) — every module and UI file with what it does (generated:
`python scripts/gen_codebase_map.py`).

## Running the funds
| Document | What it covers |
|---|---|
| [multi_fund.md](multi_fund.md) | Several funds on one platform: what is kept per fund and what is shared |
| [moriah_operating_model.md](moriah_operating_model.md) | Moriah Capital Partners' plan mapped to the platform (governance, gates, controls, reporting) |
| [bifs_audit_2026-10.md](bifs_audit_2026-10.md) | BIFS trading-desk audit, what was implemented, roadmap |
| [platform_audit_2026-10.md](platform_audit_2026-10.md) | Platform-wide audit (Oct 2026) |

## Methodology (how the numbers are made)
| Document | Topic |
|---|---|
| [macro_model_economies.md](macro_model_economies.md) | Macro model for the US, the euro area and the rest of the world: method, data sources, backtests |
| [METHODOLOGY_PHASE1_POSITIONS.md](METHODOLOGY_PHASE1_POSITIONS.md) | Positions and P&L |
| [METHODOLOGY_PHASE2_FACTOR_MODEL.md](METHODOLOGY_PHASE2_FACTOR_MODEL.md) | Factor model |
| [METHODOLOGY_PHASE3_VAR_STRESS.md](METHODOLOGY_PHASE3_VAR_STRESS.md) | VaR, Expected Shortfall, stress tests, VaR backtesting |
| [METHODOLOGY_PHASE4_BACKTESTING.md](METHODOLOGY_PHASE4_BACKTESTING.md) | Signal backtesting |
| [METHODOLOGY_PHASE5_ATTRIBUTION.md](METHODOLOGY_PHASE5_ATTRIBUTION.md) | Performance attribution |
| [METHODOLOGY_PHASE6_TRADE_WORKFLOW.md](METHODOLOGY_PHASE6_TRADE_WORKFLOW.md) | Orders, approvals, execution |
| [METHODOLOGY_PHASE7_ALTDATA.md](METHODOLOGY_PHASE7_ALTDATA.md) | Alternative data |
| [METHODOLOGY_PHASE8_AUDIT.md](METHODOLOGY_PHASE8_AUDIT.md) | Audit trail |
| [METHODOLOGY_PHASE9_INFRA.md](METHODOLOGY_PHASE9_INFRA.md) | Infrastructure |

## Quant Lab
| Document | Topic |
|---|---|
| [quant_lab_algorithm_api.md](quant_lab_algorithm_api.md) | Writing strategies (Code Lab and QuantConnect-style algorithms) |
| [quant_lab_vs_quantconnect_2026-10.md](quant_lab_vs_quantconnect_2026-10.md) | Compatibility with QuantConnect / LEAN |
| [quant_lab_audit_2026-10.md](quant_lab_audit_2026-10.md), [quant_corrections_2026-10.md](quant_corrections_2026-10.md) | Audit and corrections |
| [options_decision_engine.md](options_decision_engine.md), [options_research_2026-10.md](options_research_2026-10.md) | Options decision engine (separate project) |

Older top-level documents (`ARCHITECTURE.md`, `API.md`, `FILE_INVENTORY.md`, `IA_CURRENT.md`) were last revised in
July 2026 and do not cover the fund, governance, positions, broker or Quant Lab work since; the codebase map and the
live API reference at `/docs` (FastAPI) are current.
