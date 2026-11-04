"""
Operational due-diligence pack: the questions an allocator's ODD reviewer asks (AIMA DDQ / ILPA-style sections), each
answered from the platform's own records — or marked as a gap, never filled with a promise.

  status  in place · partial · gap · n/a   (gap = what to fix before a reviewer finds it)
  source  every answer names where it came from (the governance record, the ledger, the ops monitor, the backup log)

Answers about people, legal structure, insurance and service providers cannot come from software: they are listed as
"to be written" so the pack is honest about what is missing.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List


def _q(section: str, q: str, answer: str, status: str, source: str) -> Dict[str, Any]:
    return {"section": section, "question": q, "answer": answer, "status": status, "source": source}


def pack() -> Dict[str, Any]:
    from api import backup, fund_store, governance as gov, governance_reports as gr, ops_monitor, positions
    gov.init_db()
    st = gov.settings()
    fs = fund_store.get_settings()
    models = gov.list_models()
    recs = gov.reconciliations(90)
    incs = gov.incidents()
    srcs = gov.data_sources()
    ms = gov.milestones()
    pos = positions.list_positions()
    filled = [p for p in pos if p.get("holders")]
    halts = gr._halts()
    tr = gr.track_record()
    ops = ops_monitor.summary()
    bk = backup.status()
    out: List[Dict[str, Any]] = []

    # 1 organisation
    out.append(_q("Organisation", "What stage is the firm at, and what is it not?",
                  f"{st['stage_label']}. Capital basis: {st.get('capital_basis') or 'not stated'}.",
                  "in place" if st["enabled"] else "gap", "Fund settings"))
    out.append(_q("Organisation", "Who holds which role, and are key functions separated?",
                  f"{len(pos)} positions defined" + (f", {len(filled)} filled" if filled else "") +
                  ". Separation is enforced in software: a model's owner cannot sign off their own gate; expenses need a second approver.",
                  "partial" if len(pos) else "gap", "Team & positions; governance sign-off rules"))
    out.append(_q("Organisation", "Legal entity, regulatory status, insurance, auditor, administrator, custodian?",
                  "To be written — not recorded in the platform.", "gap", "—"))

    # 2 investment process
    by_gate: Dict[str, int] = {}
    for m in models:
        by_gate[m["gate"]] = by_gate.get(m["gate"], 0) + 1
    approved = [m for m in models if gov.GATES.index(m["gate"]) >= 2 and m["status"] != "rejected"]
    out.append(_q("Investment process", "How does a strategy go from idea to capital?",
                  "Six gates G0–G5 (proposal, data approval, backtest, paper, live-small, scale), each with named evidence and an "
                  "independent sign-off. " + (f"Models by gate: {', '.join(f'{k} {v}' for k, v in sorted(by_gate.items()))}."
                                              if by_gate else "No model has been entered yet."),
                  "in place" if models else "partial", "Models G0–G5"))
    out.append(_q("Investment process", "Which strategies are approved to trade?",
                  f"{len(approved)} at G2 or later." + (" Orders require an approved model." if st["require_approved_model"] else ""),
                  "in place" if approved else "gap", "Models G0–G5"))
    out.append(_q("Investment process", "How do you detect that a signal has stopped working?",
                  "Signal decay monitor: early vs recent information coefficient, trend t-statistic and half-life, with a stated "
                  "retirement rule; strategy drawdown triggers review / suspension under the risk policy.",
                  "in place", "Signal Lab → Signal health; risk policy"))

    # 3 risk
    pol = st["risk_policy"]
    out.append(_q("Risk management", "What are the hard limits?",
                  f"Gross leverage ≤ {pol['max_gross_leverage']:.0%}, one model ≤ {pol['max_model_risk_share']:.0%} of risk, one theme "
                  f"≤ {pol['max_theme_risk_share']:.0%}, new orders pause at a {pol['daily_loss_pause']:.0%} daily loss, strategy review at "
                  f"{pol['strategy_dd_review']:.0%} and suspension at {pol['strategy_dd_suspend']:.0%} drawdown; shorting "
                  f"{'allowed' if pol.get('allow_short') else 'not allowed'}.", "in place", "Risk policy (pre-trade checks)"))
    tests = [h for h in halts if h.get("test")]
    out.append(_q("Risk management", "Is there a kill switch, and has it been tested?",
                  f"Execution halt with incident record. Tested {len(tests)} time(s)" +
                  (f", last {max(str(h['started_at']) for h in tests)[:10]}." if tests else "."),
                  "in place" if tests else "partial", "Controls → halts"))

    # 4 operations
    clean = sum(1 for r in recs if r["ok"])
    out.append(_q("Operations", "Are positions reconciled, and how often?",
                  f"Daily T+1 against the fills ledger: {len(recs)} runs in the last 90 days, {clean} clean. No broker statement is "
                  "connected yet, so this is an internal reconciliation.", "partial" if recs else "gap", "Reconciliations"))
    open_inc = [i for i in incs if i["status"] != "signed_off"]
    out.append(_q("Operations", "How are errors and incidents handled?",
                  f"Logged, fixed and signed off by a second person: {len(incs)} recorded, {len(open_inc)} open.",
                  "in place", "Incidents"))
    out.append(_q("Operations", "Is every decision auditable?",
                  "Append-only decision log of orders, approvals, gate sign-offs, settings changes and overrides, with user and time.",
                  "in place", "decision_log"))
    out.append(_q("Valuation", "How are positions priced, and from what source?",
                  "Daily close from the market-data feed; a feed failure is detected within 10 minutes and the accuracy audit "
                  "cross-checks US prices against the Massive daily-bar store after each close. London-listed holdings have no "
                  "independent free source yet — a licensed second feed (or the administrator's prices) is needed.",
                  "partial", "Ops monitor; accuracy audit"))

    # 5 data & technology
    unrev = [s for s in srcs if s["status"] == "unreviewed"]
    out.append(_q("Data & technology", "Are you licensed to use every data source?",
                  f"{len(srcs)} sources registered; {len(srcs) - len(unrev)} reviewed against their terms, {len(unrev)} not yet.",
                  "in place" if not unrev else "partial" if len(unrev) < len(srcs) else "gap", "Data licences"))
    la = ops.get("last_audit")
    out.append(_q("Data & technology", "How would you know if data were wrong or late?",
                  f"Feeds probed every 10 minutes ({len(ops['open_incidents'])} open data incidents); accuracy audit after each close"
                  + (f", last {la['time'][:10]}: {la['detail']}." if la else " (not yet run)."),
                  "in place" if la else "partial", "System health → data incidents"))
    last = bk.get("last")
    rt = bk.get("restore_tested")
    out.append(_q("Data & technology", "Backups: how often, where, and has a restore been tested?",
                  (f"Daily; last {last['day']} ({'ok' if last['ok'] else 'with errors'}); {len(bk['kept_days'])} days kept"
                   if last else "No automated backup has run yet") +
                  ("; copied off this disk" if bk["off_disk"] else "; no off-disk copy configured (BACKUP_COPY_DIR)") +
                  (f"; restore tested {rt['time'][:10]}." if rt else "; restore not yet tested."),
                  "in place" if last and bk["off_disk"] and rt else "partial" if last else "gap", "backups/auto/manifest.json"))
    out.append(_q("Data & technology", "Business continuity: what if the server or its operator is unavailable?",
                  "The platform runs on one workstation. A hosted server, documented runbook and a second person able to operate "
                  "it are not yet in place.", "gap", "docs/operations.md"))

    # 6 performance
    s = tr["stats"]
    out.append(_q("Performance", "What is the record, and how is it described?",
                  f"{tr['label']}. Since {tr['inception'] or '—'}: {s['months']} months, cumulative "
                  f"{s['cumulative_pct'] if s['cumulative_pct'] is not None else '—'}%, max drawdown "
                  f"{s['max_drawdown_pct'] if s['max_drawdown_pct'] is not None else '—'}%. Monthly packs archived: "
                  f"{len(tr['archived_packs'])}.", "partial" if s["months"] else "gap", "Track record; monthly packs"))
    out.append(_q("Performance", "Has the record been independently verified?",
                  "No — internal, flow-adjusted NAV only.", "gap", "—"))

    # 7 roadmap
    done = sum(1 for m in ms if m["status"] == "done")
    out.append(_q("Plan", "What has been delivered against the plan?",
                  f"{done} of {len(ms)} milestones done, {sum(1 for m in ms if m.get('signed_off_by'))} signed off.",
                  "in place" if ms and done == len(ms) else "partial" if ms else "gap", "Roadmap"))

    counts = {k: sum(1 for x in out if x["status"] == k) for k in ("in place", "partial", "gap")}
    return {"fund": st["fund_name"] or fs.get("fund_name"), "stage": st["stage_label"], "label": tr["label"],
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "answers": out, "counts": counts,
            "note": "Answers are generated from the platform's records at the time shown. 'Gap' items are what a reviewer "
                    "would flag; fix them (or write them up) before sending a DDQ."}
