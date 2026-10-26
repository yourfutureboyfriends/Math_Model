"""
Research registry: every hypothesis (with its source, method, data, configuration, results, limitations and whether it
survived validation) and every experiment (stage, configuration, runtime, peak memory, trials, holdout reveals).
Stored in the app database next to the Quant Lab's other tables.

Seeded with the hypotheses from the earlier research notes (projects/quant-research: options/further-options-research,
options/industry-options-refinement, cumulative-research-report) and the sources they cite. Status moves
proposed → testing → survived / rejected / inconclusive only from experiment results.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional

SEED: List[Dict[str, Any]] = [
    {"id": "H01", "title": "Index put-selling earns a volatility risk premium after costs",
     "hypothesis": "Bull put credit spreads on index ETFs (observed implied vol) have positive risk-adjusted returns net of "
                   "modelled spreads and fees, out of sample.",
     "evidence": "CBOE PutWrite (PUT) history vs the S&P 500; AQR 'Covering the World' and 'An Alternative Option to "
                 "Portfolio Rebalancing' (O01, O02): index option premia are positive on average but carry equity and "
                 "crash risk.", "strategy": "bull_put"},
    {"id": "H02", "title": "Single-stock option premia are weaker than index premia",
     "hypothesis": "Credit spreads on single stocks earn less per unit of risk than on index ETFs.",
     "evidence": "Prior research note O02 (single-stock premium evidence is weaker than index evidence); Goyal & Saretto "
                 "(R07) needs real option quotes — modelled stock IV cannot establish a stock-level premium.",
     "strategy": "bull_put"},
    {"id": "H03", "title": "Bull call debit spreads on momentum leaders add return",
     "hypothesis": "Debit call spreads on stocks with strong 12-1 momentum and trend strength have positive expectancy net "
                   "of costs.",
     "evidence": "Prior result: the options sleeve alone returned 2.85–2.91% a year vs a 2.27% cash rate (no strong "
                 "standalone edge); AQR Time Series Momentum (O03).", "strategy": "bull_call"},
    {"id": "H04", "title": "Bear put debit spreads with a momentum-crash guard pay in corrections",
     "hypothesis": "Bear put spreads on downtrending stocks, only in a weak market without a sharp rebound, have positive "
                   "expectancy and help in drawdowns.",
     "evidence": "Daniel & Moskowitz, Momentum Crashes (R03); prior ablation: enabling bearish spreads slightly worsened "
                 "growth and drawdown on a 12-name fixture.", "strategy": "bear_put"},
    {"id": "H05", "title": "Iron condors earn premium when implied vol is rich and markets range",
     "hypothesis": "Short iron condors entered when IV/RV is high and trend strength low have positive risk-adjusted "
                   "returns net of costs.", "evidence": "CBOE Iron Condor index (CNDR) history; the volatility risk "
                                                         "premium literature.", "strategy": "iron_condor"},
    {"id": "H06", "title": "Managing credit spreads early (50% profit-take, 21-DTE exit) improves risk-adjusted returns",
     "hypothesis": "Closing credit spreads at 50% of maximum profit or at 21 days to expiry beats holding to expiry.",
     "evidence": "Practitioner convention (not peer-reviewed); tested here as exit-rule grids.", "strategy": "bull_put"},
    {"id": "H07", "title": "Volatility-managed risk improves Sharpe",
     "hypothesis": "Cutting new short-volatility risk in stressed regimes (high VIX, inverted term structure, drawdowns) "
                   "improves risk-adjusted returns.", "evidence": "Moreira & Muir (R01); Harvey et al. (R02) — benefits "
                                                                    "vary by asset class.", "strategy": "regime"},
    {"id": "H08", "title": "Regime switching beats a fixed four-strategy portfolio out of sample",
     "hypothesis": "Gating the strategies by a market-regime model improves out-of-sample risk-adjusted returns over "
                   "running all four with fixed risk budgets.", "evidence": "Hypothesis of this research; regime "
                                                                             "models are prone to overfitting.",
     "strategy": "regime"},
    {"id": "H09", "title": "Machine-learning regime classifiers beat a rules baseline",
     "hypothesis": "Logistic regression, random forest, gradient boosting or an HMM classify next-month regimes better "
                   "than simple trend/volatility rules, out of sample.", "evidence": "Hypothesis; ML used only if it "
                                                                                     "beats the baseline.",
     "strategy": "regime"},
    {"id": "H10", "title": "Combining the four strategies improves risk-adjusted return",
     "hypothesis": "The combined portfolio's out-of-sample Sharpe exceeds the best single strategy's without "
                   "disproportionate cost.", "evidence": "Diversification across directional and premium strategies; "
                                                         "PIMCO risk-factor diversification (O08): different labels "
                                                         "need not be independent risks.", "strategy": "combined"},
    {"id": "H11", "title": "10–15 concurrent positions beat 5 or 20",
     "hypothesis": "Risk-adjusted return improves from 5 to 10–15 positions and does not improve further at 20.",
     "evidence": "Diversification vs the marginal quality of lower-ranked candidates.", "strategy": "portfolio"},
    {"id": "H12", "title": "Portfolio Greek limits reduce drawdown at little cost",
     "hypothesis": "Capping portfolio dollar delta and vega reduces maximum drawdown without lowering Sharpe.",
     "evidence": "Risk-budgeting practice.", "strategy": "portfolio"},
    {"id": "H13", "title": "Requiring rich implied volatility improves credit-spread expectancy",
     "hypothesis": "Higher IV/RV entry thresholds raise the expectancy of credit spreads.",
     "evidence": "Volatility risk premium: implied usually exceeds subsequent realised volatility.", "strategy": "bull_put"},
    {"id": "H14", "title": "Modelled single-stock IV is accurate enough for research",
     "hypothesis": "The IV model's out-of-sample error against CBOE single-stock volatility indices is below 3 vol points.",
     "evidence": "CBOE VXAPL, VXAZN, VXGOG, VXGS, VXIBM and ETF volatility indices (observed).", "strategy": "data"},
    {"id": "H15", "title": "Cross-sectional ranking of candidates adds value",
     "hypothesis": "Taking the highest-scored candidates beats taking eligible candidates in random order.",
     "evidence": "Cross-sectional selection; AQR trading-cost research (R04) on implementability.", "strategy": "portfolio"},
]


def _conn() -> sqlite3.Connection:
    from api.core.app_db import app_db_path
    c = sqlite3.connect(app_db_path(), timeout=15)
    c.row_factory = sqlite3.Row
    return c


_ready = False


def init() -> None:
    """Create the research registry tables once per process."""
    global _ready
    if _ready:
        return
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS research_hypotheses (id TEXT PRIMARY KEY, title TEXT, hypothesis TEXT,
                     evidence TEXT, strategy TEXT, method TEXT, dataset TEXT, config TEXT, results TEXT, limitations TEXT,
                     status TEXT, experiments TEXT, created REAL, updated REAL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS research_experiments (id TEXT PRIMARY KEY, owner TEXT, kind TEXT, stage INTEGER,
                     label TEXT, config TEXT, data_class TEXT, state TEXT, started REAL, finished REAL, runtime_s REAL,
                     peak_mb REAL, trials INTEGER, summary TEXT, result_path TEXT, holdout_reveals INTEGER DEFAULT 0)""")
        c.execute("""CREATE TABLE IF NOT EXISTS research_holdout_log (experiment_id TEXT, revealed REAL, by_user TEXT,
                     note TEXT)""")
        now = time.time()
        for h in SEED:
            c.execute("INSERT OR IGNORE INTO research_hypotheses (id, title, hypothesis, evidence, strategy, status, "
                      "experiments, created, updated) VALUES (?,?,?,?,?,?,?,?,?)",
                      (h["id"], h["title"], h["hypothesis"], h["evidence"], h["strategy"], "proposed", "[]", now, now))
    _ready = True


def hypotheses() -> List[Dict[str, Any]]:
    """Research hypotheses with status, method, results and linked experiments."""
    init()
    with _conn() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM research_hypotheses ORDER BY id")]
    for r in rows:
        for k in ("config", "results", "experiments"):
            r[k] = json.loads(r[k]) if r.get(k) else None
    return rows


def update_hypothesis(hid: str, *, status: str, method: str, dataset: str, config: Any, results: Any, limitations: str,
                      experiment_id: str) -> None:
    """Record an experiment's outcome against a hypothesis."""
    init()
    with _conn() as c:
        row = c.execute("SELECT experiments FROM research_hypotheses WHERE id = ?", (hid,)).fetchone()
        exps = json.loads(row["experiments"]) if row and row["experiments"] else []
        if experiment_id not in exps:
            exps.append(experiment_id)
        c.execute("UPDATE research_hypotheses SET status=?, method=?, dataset=?, config=?, results=?, limitations=?, "
                  "experiments=?, updated=? WHERE id=?",
                  (status, method, dataset, json.dumps(config, default=str), json.dumps(results, default=str), limitations,
                   json.dumps(exps), time.time(), hid))


def start_experiment(owner: str, kind: str, stage: int, label: str, config: Dict[str, Any], data_class: str) -> str:
    """Register a new experiment; returns its id."""
    init()
    eid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    with _conn() as c:
        c.execute("INSERT INTO research_experiments (id, owner, kind, stage, label, config, data_class, state, started) "
                  "VALUES (?,?,?,?,?,?,?,?,?)", (eid, owner, kind, stage, label, json.dumps(config, default=str), data_class,
                                                 "running", time.time()))
    return eid


def finish_experiment(eid: str, *, state: str, runtime_s: float, peak_mb: float, trials: int, summary: Dict[str, Any],
                      result_path: Optional[str]) -> None:
    """Record an experiment's end: state, runtime, peak memory, trials and summary."""
    init()
    with _conn() as c:
        c.execute("UPDATE research_experiments SET state=?, finished=?, runtime_s=?, peak_mb=?, trials=?, summary=?, "
                  "result_path=? WHERE id=?", (state, time.time(), runtime_s, peak_mb, trials,
                                               json.dumps(summary, default=str), result_path, eid))


def experiments(limit: int = 100) -> List[Dict[str, Any]]:
    """Recent experiments, newest first."""
    init()
    with _conn() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM research_experiments ORDER BY started DESC LIMIT ?", (limit,))]
    for r in rows:
        for k in ("config", "summary"):
            r[k] = json.loads(r[k]) if r.get(k) else None
    return rows


def experiment(eid: str) -> Optional[Dict[str, Any]]:
    """One experiment, or None."""
    init()
    with _conn() as c:
        r = c.execute("SELECT * FROM research_experiments WHERE id = ?", (eid,)).fetchone()
    if not r:
        return None
    r = dict(r)
    for k in ("config", "summary"):
        r[k] = json.loads(r[k]) if r.get(k) else None
    return r


def supersede(eid: str, note: str) -> None:
    """Mark an experiment as superseded (kept for the record; its trials still count towards multiple testing)."""
    init()
    with _conn() as c:
        row = c.execute("SELECT summary FROM research_experiments WHERE id = ?", (eid,)).fetchone()
        summ = json.loads(row["summary"]) if row and row["summary"] else {}
        summ["superseded"] = note
        c.execute("UPDATE research_experiments SET state = 'superseded', summary = ? WHERE id = ?", (json.dumps(summ), eid))


def total_trials(kind_prefix: str = "") -> int:
    """All configurations evaluated so far (for the deflated Sharpe ratio's multiple-testing adjustment)."""
    init()
    with _conn() as c:
        r = c.execute("SELECT COALESCE(SUM(trials), 0) FROM research_experiments WHERE state IN ('done', 'superseded') "
                      "AND kind LIKE ?",
                      (kind_prefix + "%",)).fetchone()
    return int(r[0])


def log_holdout(eid: str, user: str, note: str) -> int:
    """Log a holdout reveal (each reveal is counted); returns the total reveals."""
    init()
    with _conn() as c:
        c.execute("INSERT INTO research_holdout_log VALUES (?,?,?,?)", (eid, time.time(), user, note))
        c.execute("UPDATE research_experiments SET holdout_reveals = holdout_reveals + 1 WHERE id = ?", (eid,))
        n = c.execute("SELECT COUNT(*) FROM research_holdout_log").fetchone()[0]
    return int(n)


def holdout_log() -> List[Dict[str, Any]]:
    """Every holdout reveal, newest first."""
    init()
    with _conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM research_holdout_log ORDER BY revealed DESC")]
