"""
Deep sequence model: one recurrent network (GRU) that reads the last 24 months of the economy and answers every task
at once (multi-task), in PyTorch.

Inputs at each month: every task's core inputs (union), 8 principal-component factors of the ~70-series panel
(re-estimated inside each training window), and the text & news block (with a 'missing' flag per series, since some
start in 1985). A sequence model sees trajectories — a curve that inverted and is now re-steepening, a slide in
hiring — not one month's snapshot. Multi-task learning shares one representation across the six questions, giving
the network roughly six times the training signal of a single task (Caruana 1997; standard at Google/DeepMind).

Training (fixed in advance): GRU 32 units → dropout 0.2 → one logistic output per task; masked binary cross-entropy
(a task's label is used only if its answer was known at the refit); Adam (lr 3e-3, weight decay 1e-4); early stopping
on the last 15% of the training window, chronologically (patience 15, max 150 epochs); an ensemble of 5 seeds.
Walk-forward: refit every two Januaries from 1985 on data known by then; forecasts the next two years' months.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

SEQ = 24
HIDDEN = 32
SEEDS = 5
REFIT_EVERY = 2
N_FACTORS = 8


def _months_between(a: str, b: str) -> int:
    ya, ma = map(int, a.split("-"))
    yb, mb = map(int, b.split("-"))
    return (yb - ya) * 12 + mb - ma


GAP_FILL = 3          # the Oct-2025 shutdown cancelled a CPI report; derived series lost up to three months


def _month_range(a: str, b: str) -> List[str]:
    y, m = map(int, a.split("-"))
    out = []
    while f"{y}-{m:02d}" <= b:
        out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _fill(series: Dict[str, float], months: List[str]) -> Dict[str, float]:
    out, last, age = {}, None, 0
    for m in months:
        if m in series:
            out[m], last, age = series[m], series[m], 0
        elif last is not None and age < GAP_FILL:
            age += 1
            out[m] = last
        else:
            last, age = None, 0
    return out


def assemble(tasks, feats, panel, text, panel_keys: List[str]) -> Dict[str, Any]:
    """Monthly frame: core (union of task inputs), panel (complete series), text (with gaps), labels per task."""
    core_keys = sorted({k for t in tasks for k in t.features})
    # sequences need consecutive months: carry each series' last value across gaps of up to GAP_FILL months (what was
    # known at the time — e.g. quarterly sentiment before 1978, a missing payroll vintage), then keep the longest run
    start = max(min(d) for d in [*(feats[k] for k in core_keys), *(panel[k] for k in panel_keys)])
    end = max(max(d) for d in [*(feats[k] for k in core_keys), *(panel[k] for k in panel_keys)])
    allm = _month_range(start, end)
    src = {**{k: _fill(feats[k], allm) for k in core_keys}, **{k: _fill(panel[k], allm) for k in panel_keys}}
    ok = [all(m in src[k] for k in src) for m in allm]
    best, cur = (0, 0), None
    for i, good in enumerate(ok + [False]):
        if good and cur is None:
            cur = i
        elif not good and cur is not None:
            if i - cur > best[1] - best[0]:
                best = (cur, i)
            cur = None
    months = allm[best[0]:best[1]]
    C = np.array([[src[k][m] for k in core_keys] for m in months], float)
    P = np.array([[src[k][m] for k in panel_keys] for m in months], float)
    tk = sorted(text)
    T = np.array([[text[k].get(m, np.nan) for k in tk] for m in months], float)
    Y = np.full((len(months), len(tasks)), np.nan)
    for j, t in enumerate(tasks):
        tgt = t.target()
        for i, m in enumerate(months):
            if m in tgt:
                Y[i, j] = tgt[m]
    return {"months": months, "C": C, "P": P, "T": T, "Y": Y, "core_keys": core_keys, "text_keys": tk,
            "tasks": [t.name for t in tasks], "known_after": [t.known_after for t in tasks]}


def _features(fr: Dict[str, Any], train_end: int) -> np.ndarray:
    """Per-month input vector with scalers and factors fitted on months [0, train_end) only."""
    C, P, T = fr["C"], fr["P"], fr["T"]
    cm, cs = C[:train_end].mean(0), C[:train_end].std(0) + 1e-9
    pm, ps = P[:train_end].mean(0), P[:train_end].std(0) + 1e-9
    Zp = (P - pm) / ps
    _, _, vt = np.linalg.svd(Zp[:train_end], full_matrices=False)
    F = Zp @ vt[:N_FACTORS].T
    fm, fs = F[:train_end].mean(0), F[:train_end].std(0) + 1e-9
    tm_, ts_ = np.nanmean(T[:train_end], 0), np.nanstd(T[:train_end], 0) + 1e-9
    tm_ = np.where(np.isfinite(tm_), tm_, 0.0)
    ts_ = np.where(np.isfinite(ts_) & (ts_ > 1e-9), ts_, 1.0)
    Tz = (T - tm_) / ts_
    miss = ~np.isfinite(Tz)
    Tz[miss] = 0.0
    return np.hstack([(C - cm) / cs, (F - fm) / fs, Tz, miss.astype(float)]).astype(np.float32)


def _windows(X: np.ndarray, idx: List[int]) -> np.ndarray:
    return np.stack([X[i - SEQ + 1:i + 1] for i in idx]).astype(np.float32)


def _train(Xw: np.ndarray, Yw: np.ndarray, seed: int):
    import torch
    from torch import nn
    torch.manual_seed(seed)
    np.random.seed(seed)

    class Net(nn.Module):
        def __init__(self, d_in: int, d_out: int):
            super().__init__()
            self.gru = nn.GRU(d_in, HIDDEN, batch_first=True)
            self.drop = nn.Dropout(0.2)
            self.head = nn.Linear(HIDDEN, d_out)

        def forward(self, x):
            h, _ = self.gru(x)
            return self.head(self.drop(h[:, -1]))

    n = len(Xw)
    cut = int(n * 0.85)
    net = Net(Xw.shape[2], Yw.shape[1])
    opt = torch.optim.Adam(net.parameters(), lr=3e-3, weight_decay=1e-4)
    xt, yt = torch.tensor(Xw[:cut]), torch.tensor(Yw[:cut])
    xv, yv = torch.tensor(Xw[cut:]), torch.tensor(Yw[cut:])
    bce = nn.BCEWithLogitsLoss(reduction="none")

    def loss(x, y):
        m = ~torch.isnan(y)
        l = bce(net(x), torch.nan_to_num(y))
        return (l * m).sum() / m.sum().clamp(min=1)
    best, best_state, bad = float("inf"), None, 0
    for _ in range(150):
        net.train()
        perm = torch.randperm(len(xt))
        for b in range(0, len(xt), 64):
            ix = perm[b:b + 64]
            opt.zero_grad()
            l = loss(xt[ix], yt[ix])
            l.backward()
            opt.step()
        net.eval()
        with torch.no_grad():
            v = float(loss(xv, yv)) if len(xv) else float(loss(xt, yt))
        if v < best - 1e-4:
            best, best_state, bad = v, {k: t.clone() for k, t in net.state_dict().items()}, 0
        else:
            bad += 1
            if bad >= 15:
                break
    if best_state:
        net.load_state_dict(best_state)
    net.eval()
    return net


def _predict(nets, Xw: np.ndarray) -> np.ndarray:
    import torch
    with torch.no_grad():
        x = torch.tensor(Xw)
        return np.mean([torch.sigmoid(n(x)).numpy() for n in nets], axis=0)      # (rows, tasks)


def _labels_known(fr: Dict[str, Any], upto: str) -> np.ndarray:
    """Labels with each task's answer hidden unless known by `upto` (the refit date)."""
    from api.ml.engine import cutoff
    Y = fr["Y"].copy()
    y0 = int(upto[:4])
    for j, ka in enumerate(fr["known_after"]):
        cut = cutoff(y0, ka)
        for i, m in enumerate(fr["months"]):
            if m >= cut:
                Y[i, j] = np.nan
    return Y


def walk_forward(fr: Dict[str, Any], start_year: int = 1985) -> Dict[str, Dict[str, float]]:
    """Raw out-of-sample probabilities {task: {month: p}} — refit every REFIT_EVERY Januaries on data known by then."""
    import torch
    torch.set_num_threads(max(1, min(4, torch.get_num_threads())))
    months = fr["months"]
    out: Dict[str, Dict[str, float]] = {t: {} for t in fr["tasks"]}
    last_year = int(months[-1][:4])
    for yr in range(start_year, last_year + 1, REFIT_EVERY):
        origin = f"{yr}-01"
        train_end = next((i for i, m in enumerate(months) if m >= origin), len(months))
        if train_end < SEQ + 96:
            continue
        X = _features(fr, train_end)
        Y = _labels_known(fr, origin)
        idx = [i for i in range(SEQ - 1, train_end) if np.isfinite(Y[i]).any()]
        if len(idx) < 120:
            continue
        nets = [_train(_windows(X, idx), Y[idx].astype(np.float32), s) for s in range(SEEDS)]
        test = [i for i, m in enumerate(months) if yr <= int(m[:4]) < yr + REFIT_EVERY and i >= SEQ - 1]
        if not test:
            continue
        p = _predict(nets, _windows(X, test))
        for k, i in enumerate(test):
            for j, t in enumerate(fr["tasks"]):
                out[t][months[i]] = round(float(p[k, j]), 5)
        logger.info("[ml.deep] refit %s: %d training windows, %d test months", origin, len(idx), len(test))
    return out


def live(fr: Dict[str, Any]) -> Tuple[Dict[str, float], Dict[str, List[float]]]:
    """Fit on everything known now; today's probability per task and each seed's (for the uncertainty)."""
    months = fr["months"]
    X = _features(fr, len(months))
    from datetime import datetime, timezone
    Y = _labels_known(fr, datetime.now(timezone.utc).strftime("%Y-%m"))
    idx = [i for i in range(SEQ - 1, len(months)) if np.isfinite(Y[i]).any()]
    nets = [_train(_windows(X, idx), Y[idx].astype(np.float32), s) for s in range(SEEDS)]
    import torch
    with torch.no_grad():
        x = torch.tensor(_windows(X, [len(months) - 1]))
        each = [torch.sigmoid(n(x)).numpy()[0] for n in nets]
    p = np.mean(each, axis=0)
    return ({t: float(p[j]) for j, t in enumerate(fr["tasks"])},
            {t: [float(e[j]) for e in each] for j, t in enumerate(fr["tasks"])})


def build() -> Dict[str, Any]:
    """Assemble, walk forward and fit live — run inside the worker process (see joint)."""
    from api.ml import features as F
    from api.ml import panel as PN
    from api.ml.engine import FFILL_MONTHS, _carry, panel_keys
    from api.ml.tasks import TASKS
    feats, panel, text = F.load(), PN.load(), F.load_text()
    tasks = [t for t in TASKS.values() if all(k in feats for k in t.features)]
    pk = panel_keys(panel)
    recent = sorted({m for k in pk for m in panel[k]})[-FFILL_MONTHS - 1:]
    recent += [m for m in sorted({m for t in tasks for k in t.features for m in feats[k]}) if m > recent[-1]]
    panel = {k: _carry(panel[k], recent) for k in pk}
    fr = assemble(tasks, feats, panel, text, pk)
    bt = walk_forward(fr)
    now, seeds = live(fr)
    return {"backtest": bt, "now": now, "seeds": seeds, "as_of": fr["months"][-1],
            "inputs": len(fr["core_keys"]) + N_FACTORS + 2 * len(fr["text_keys"]), "sequence_months": SEQ, "tasks": fr["tasks"],
            "window": [fr["months"][0], fr["months"][-1]]}


def _run_worker() -> Dict[str, Any]:
    """PyTorch runs in its own process: on macOS its OpenMP runtime and LightGBM's crash one process that loads both
    (a segmentation fault), so the backend never imports torch — it starts this worker and reads its JSON."""
    import json
    import os
    import subprocess
    import sys
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    r = subprocess.run([sys.executable, "-m", "api.ml.deep"], cwd=root, capture_output=True, text=True, timeout=3 * 3600,
                       env={**os.environ, "OMP_NUM_THREADS": "4"})
    if r.returncode != 0:
        raise RuntimeError(f"deep worker exited {r.returncode}: {(r.stderr or '')[-400:]}")
    line = [ln for ln in r.stdout.splitlines() if ln.startswith("{")][-1]
    return json.loads(line)


def joint(force: bool = False) -> Optional[Dict[str, Any]]:
    """The deep model's walk-forward predictions and today's readings for every task (cached a month)."""
    from api import research_indicators as ri
    data, _ = ri._cached("ml_deep_v2", _run_worker, ttl=30 * 24 * 3600)
    return data


if __name__ == "__main__":                                      # the worker: python -m api.ml.deep
    import json
    import sys
    import warnings
    warnings.filterwarnings("ignore")
    try:
        from dotenv import load_dotenv
        load_dotenv(".env")
    except Exception:                                           # noqa: BLE001 — the config module reads the key too
        pass
    sys.stdout.write(json.dumps(build()) + "\n")
