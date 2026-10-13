"""
Locked-down server execution of user strategy code — used only to paper-trade a deployed code
strategy (testing runs in the browser). Layers, each sufficient against common escapes on its own:

1. Static checks (AST): only `import numpy as np`, `import pandas as pd`, `import math`; no names or
   attributes starting with "_" (closes the __class__/__globals__ escape routes); no eval/exec/open/
   getattr…; no pandas/numpy file or network I/O (read_*, to_csv, np.load, …).
2. UNIVERSE / START / PARAMS / BENCHMARK must be literals — read without running the code.
3. A separate Python process (-I: no user site, no PYTHON* env vars) with a scrubbed environment (no
   API keys), CPU/file-size/open-file limits, a wall-clock timeout, restricted builtins and an audit
   hook that refuses sockets, subprocesses, ctypes and file writes once the strategy starts.
4. On macOS, sandbox-exec: no network, no writes outside a temp dir, no reading files under /Users
   except the Python environment and the engine.
Data goes in as an .npz (no pickle) and results come back as JSON — the parent never unpickles.
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

HERE = Path(__file__).resolve().parent
CHILD = HERE / "sandbox_child.py"
ENGINE = HERE / "codelab.py"
TIMEOUT_S = 240
MAX_CODE = 40_000

ALLOWED_IMPORTS = {"numpy": "np", "pandas": "pd", "math": None}
BANNED_NAMES = {"eval", "exec", "compile", "open", "getattr", "setattr", "delattr", "globals", "locals", "vars",
                "input", "breakpoint", "help", "exit", "quit", "memoryview", "type", "super", "classmethod",
                "staticmethod", "property", "object", "__import__", "__builtins__", "dir", "id", "hash"}
BANNED_ATTRS = {"load", "save", "savez", "savez_compressed", "fromfile", "tofile", "memmap", "loadtxt", "savetxt",
                "genfromtxt", "fromregex", "ctypeslib", "ctypes", "lib", "f2py", "testing", "distutils", "DataSource",
                "eval", "query", "io", "api", "HDFStore", "ExcelWriter", "ExcelFile", "plotting", "plot", "style",
                "system", "popen", "environ", "getenv", "os", "sys", "builtins", "modules", "import_module",
                "frame", "f_globals", "f_locals", "f_back", "gi_frame", "cr_frame", "tb_frame", "code", "format",
                "format_map", "mro", "subclasses", "options", "set_option", "util", "core", "compat", "errors"}
ALLOWED_TO = {"to_numpy", "to_frame", "to_period", "to_series", "to_dict", "to_list", "to_timestamp", "to_numeric",
              "to_datetime", "to_timedelta", "to_offset"}


class SandboxError(ValueError):
    pass


def check(code: str) -> Dict[str, Any]:
    """Static checks; returns the literal header (UNIVERSE, START, PARAMS, BENCHMARK, HOLDOUT, TRADABLE_UNIVERSE,
    ACCOUNT_CALENDAR, ACCOUNT_CURRENCY)."""
    if not code or len(code) > MAX_CODE:
        raise SandboxError(f"Code must be 1–{MAX_CODE:,} characters.")
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        line = (code.splitlines()[e.lineno - 1].strip() if e.lineno and e.lineno <= len(code.splitlines()) else "")
        hint = ""
        first = line.split(" ", 1)[0] if line else ""
        for kw in ("import", "from", "def", "return", "if", "for"):
            if first != kw and first.endswith(kw) and len(first) <= len(kw) + 2:
                hint = f" — did you mean '{kw}'? ('{first[:len(first) - len(kw)]}' looks like a stray keystroke)"
                break
        raise SandboxError(f"Syntax error on line {e.lineno}: {e.msg}" + (f": `{line[:120]}`" if line else "") + hint)
    for node in ast.walk(tree):
        line = getattr(node, "lineno", "?")
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name not in ALLOWED_IMPORTS:
                    raise SandboxError(f"Line {line}: only numpy, pandas and math can be imported (not '{a.name}').")
        elif isinstance(node, ast.ImportFrom):
            if node.module != "math":
                raise SandboxError(f"Line {line}: 'from … import' is only allowed for math.")
        elif isinstance(node, ast.Name):
            if node.id.startswith("_") or node.id in BANNED_NAMES:
                raise SandboxError(f"Line {line}: '{node.id}' is not available in strategy code.")
        elif isinstance(node, ast.Attribute):
            a = node.attr
            if a.startswith("_") or a in BANNED_ATTRS or a.startswith("read_") or (a.startswith("to_") and a not in ALLOWED_TO):
                raise SandboxError(f"Line {line}: '.{a}' is not available in strategy code (no file, network or internals access).")
        elif isinstance(node, (ast.Global, ast.Nonlocal, ast.AsyncFunctionDef, ast.Await, ast.Yield, ast.YieldFrom)):
            raise SandboxError(f"Line {line}: {type(node).__name__} is not supported in strategy code.")
        elif isinstance(node, ast.ClassDef):
            raise SandboxError(f"Line {line}: classes are not supported in strategy code — use functions.")
    header: Dict[str, Any] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in ("UNIVERSE", "START", "PARAMS", "BENCHMARK", "HOLDOUT", "TRADABLE_UNIVERSE", "ACCOUNT_CALENDAR",
                        "ACCOUNT_CURRENCY", "FX_HEDGE", "OPTIONS", "FUNDAMENTALS"):
                try:
                    header[name] = ast.literal_eval(node.value)
                except Exception:
                    raise SandboxError(f"{name} must be a plain literal (list, string or dict of lists).")
    uni = header.get("UNIVERSE")
    from api.quant.codelab import LARGE_UNIVERSE_LIMIT, tradable_spec, universe_error
    if isinstance(uni, str):
        uni = [uni]
    if not uni and isinstance(header.get("OPTIONS"), (list, tuple)):     # options-only: trade the underlyings
        uni = list(dict.fromkeys(str(o.get("underlying", "")).upper() for o in header["OPTIONS"] if isinstance(o, dict)))
    if not uni:
        raise SandboxError(universe_error(code))
    if not isinstance(uni, (list, tuple)) or not 1 <= len(uni) <= LARGE_UNIVERSE_LIMIT or not all(isinstance(u, str) and u for u in uni):
        raise SandboxError(f"UNIVERSE must be a literal list of 1–{LARGE_UNIVERSE_LIMIT} ticker strings.")
    tradable = header.get("TRADABLE_UNIVERSE")
    if tradable is not None and not (isinstance(tradable, str) or (isinstance(tradable, (list, tuple))
                                                                   and all(isinstance(t, str) for t in tradable))):
        raise SandboxError('TRADABLE_UNIVERSE must be a string ("GLOBAL", "JP+HK") or a list of strings.')
    acc = header.get("ACCOUNT_CURRENCY")
    if acc is not None and not isinstance(acc, str):
        raise SandboxError('ACCOUNT_CURRENCY must be a currency code string, e.g. "EUR".')
    from api.quant import options as opt_mod
    try:
        opts = opt_mod.parse(header.get("OPTIONS"))
    except ValueError as e:
        raise SandboxError(str(e))
    from api.quant.codelab import FUNDAMENTAL_NAMES, fundamentals_spec
    fh = header.get("FUNDAMENTALS")
    if fh is not None and not (isinstance(fh, (bool, str)) or (isinstance(fh, (list, tuple)) and all(isinstance(x, str) for x in fh))):
        raise SandboxError("FUNDAMENTALS must be True or a list of names.")
    funds = fundamentals_spec(fh)
    if any(n not in FUNDAMENTAL_NAMES for n in funds):
        raise SandboxError(f"Unknown FUNDAMENTALS. Available: {', '.join(FUNDAMENTAL_NAMES)}.")
    hedge = header.get("FX_HEDGE")
    if hedge is not None and (isinstance(hedge, bool) or not isinstance(hedge, (int, float)) or not 0 <= hedge <= 1):
        raise SandboxError("FX_HEDGE must be a number from 0 (unhedged) to 1 (fully hedged).")
    from api.quant import instruments
    try:
        account = instruments.account_currency(acc)
    except ValueError as e:
        raise SandboxError(str(e))
    if not any(isinstance(n, ast.FunctionDef) and n.name in ("strategy", "on_bar") for n in tree.body):
        raise SandboxError("Define a top-level function strategy(data, **params) — or on_bar(ctx, **params) for an "
                           "event-driven strategy.")
    calendar = header.get("ACCOUNT_CALENDAR")
    if calendar is not None and (not isinstance(calendar, str) or calendar.upper() not in [u.upper() for u in uni]
                                 or not header.get("TRADABLE_UNIVERSE")):
        raise SandboxError("ACCOUNT_CALENDAR must be a ticker in UNIVERSE and requires a named server universe")
    params = header.get("PARAMS") or {}
    if not isinstance(params, dict) or not all(isinstance(v, (list, tuple)) and v for v in params.values()):
        raise SandboxError("PARAMS must be a dict of non-empty lists.")
    n = 1
    for v in params.values():
        n *= len(v)
    if n > 48:
        raise SandboxError(f"PARAMS has {n} combinations — keep it to 48 or fewer.")
    return {"universe": [str(u).upper() for u in uni], "start": str(header.get("START") or "2005-01-01")[:10],
            "params": params, "benchmark": str(header.get("BENCHMARK") or "SPY").upper(),
            "holdout": str(header["HOLDOUT"])[:10] if header.get("HOLDOUT") else None,
            "tradable": tradable_spec(tradable), "account": account,
            "fx_hedge": float(hedge) if hedge is not None else None, "options": opts, "fundamentals": funds,
            "mode": "event" if any(isinstance(n, ast.FunctionDef) and n.name == "on_bar" for n in tree.body) else "weights",
            "calendar": calendar.upper() if calendar else None}


def _profile(tmp: Path) -> str:
    py_prefix = Path(sys.prefix).resolve()
    base = Path(sys.base_prefix).resolve()
    allow_read = [str(py_prefix), str(base), str(tmp), str(ENGINE), str(CHILD)]
    reads = " ".join(f'(subpath "{p}")' if not p.endswith(".py") else f'(literal "{p}")' for p in allow_read)
    return f"""(version 1)
(allow default)
(deny network*)
(deny file-write*)
(allow file-write* (subpath "{tmp}") (literal "/dev/null"))
(deny file-read-data (subpath "/Users") (subpath "/private/etc") (subpath "/etc") (subpath "/Volumes"))
(allow file-read-data {reads})
"""


def _limits(cpu: int = TIMEOUT_S):              # runs in the child before exec
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    resource.setrlimit(resource.RLIMIT_FSIZE, (50_000_000, 50_000_000))
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
    except (ValueError, OSError):
        pass
    if sys.platform.startswith("linux"):
        resource.setrlimit(resource.RLIMIT_AS, (4_000_000_000, 4_000_000_000))
    os.setsid()


def run(code: str, costs: Optional[Dict[str, float]] = None, job: Optional[Any] = None, light: bool = False) -> Dict[str, Any]:
    """Evaluate user code in the sandbox; returns codelab.evaluate()'s JSON-able output. `job` (api/quant/jobs.py)
    receives progress and can cancel the run (the child process is killed)."""
    from api.quant import codelab, codeserver
    head = check(code)
    say = (lambda m: job.progress(m)) if job is not None else (lambda m: None)
    members = None
    if head.get("tradable") == "SP500_PIT":
        from api.quant import membership
        names, minfo = membership.universe_since(head["start"])
        universe = list(dict.fromkeys(head["universe"] + names))
        say(f"Loading prices for {len(universe)} past and present S&P 500 members (first run downloads them)…")
        data = codeserver.load_data(universe, head["start"], limit=codelab.LARGE_UNIVERSE_LIMIT, allow_missing=True,
                                    account=head["account"], options=head["options"], fundamentals=head["fundamentals"])
        members = membership.members_frame(data.close.index, data.tickers)
        # Explicit delisting events (the engine settles only these): a former member whose trading stopped more
        # than 10 sessions before the data ends AND that had already left the index by then — two independent
        # records of a real exit, not a feed gap. Effective (and known) on the session after its last bar.
        events = {}
        idx = data.close.index
        for c in data.tickers:
            if c in head["universe"]:
                continue
            obs = data.observed[c]
            if not obs.any():
                continue
            last = obs[obs].index[-1]
            k = idx.get_loc(last)
            if len(idx) - 1 - k > 10 and not bool(members[c].iloc[k + 1:].any()):
                when = str(idx[k + 1].date())
                events[c] = {"effective_date": when, "known_at": when, "reason": "left the S&P 500 and stopped trading"}
        data.provenance["delisting_events"] = events
        dropped = data.provenance.get("dropped_no_data") or []
        data.provenance["universe_selection"] = (
            f"TRADABLE_UNIVERSE 'SP500_PIT': point-in-time S&P 500 membership ({len(names)} names that were members "
            f"since {head['start']}); data.members says who was a member each day. {len(dropped)} former members have "
            "no free price history and are absent — a smaller, reported survivorship effect.")
        data.provenance["membership"] = minfo
        cpu = TIMEOUT_S * 4
    elif head.get("tradable"):
        names = codeserver.tradable_universe(head["tradable"])
        universe = list(dict.fromkeys(head["universe"] + names))
        say(f"Loading prices for {len(universe)} tickers (first run downloads them; later runs use the cache)…")
        data = codeserver.load_data(universe, head["start"], limit=codelab.LARGE_UNIVERSE_LIMIT, allow_missing=True,
                                    account=head["account"], options=head["options"], fundamentals=head["fundamentals"])
        data.provenance["universe_selection"] = (f"TRADABLE_UNIVERSE '{head['tradable']}': today's list of "
                                                 f"{len(names)} names — retrospective / survivor-selected (names that failed "
                                                 "or were delisted earlier are absent)")
        cpu = TIMEOUT_S * (4 if len(universe) <= 1000 else 12)        # a 3,000-name global cross-section takes longer
    else:
        big = len(head["universe"]) > codelab.UNIVERSE_LIMIT
        if big:
            say(f"Loading prices for {len(head['universe'])} tickers (first run downloads them; later runs use the cache)…")
        data = codeserver.load_data(head["universe"], head["start"], limit=codelab.LARGE_UNIVERSE_LIMIT,
                                    account=head["account"], options=head["options"], fundamentals=head["fundamentals"])
        cpu = TIMEOUT_S * (4 if big else 1)
    if head.get("calendar"):
        data = codeserver.account_session_data(data, head["calendar"])
        if members is not None:
            members = members.reindex(index=data.close.index, columns=data.tickers).fillna(False)
    if job is not None and job.cancelled:
        raise SandboxError("Cancelled.")
    bm = codeserver.benchmark_series(head["benchmark"], data.close.index[0].strftime("%Y-%m-%d"), data.account_currency)
    tmp = Path(tempfile.mkdtemp(prefix="qsbx_")).resolve()
    try:
        arrays = {f: getattr(data, f).to_numpy(np.float64) for f in ("close", "open", "high", "low", "volume")}
        arrays["rf"] = data.rf.to_numpy(np.float64)
        arrays["vix"] = data.vix.to_numpy(np.float64)
        arrays["observed"] = data.observed.to_numpy(bool)
        arrays["usd_per_unit"] = data.usd_per_unit.to_numpy(np.float64)
        micro_cols = {}
        frames = {k: getattr(data, k, None) for k in ("tick_bps", "lot_value", "div_yield", "fx", "rf_ccy", "settle")}
        frames.update({f"opt_{k}": v for k, v in data.opt.items()})          # synthetic options' analytics
        frames.update({f"fund_{k}": v for k, v in data.fund.items()})        # point-in-time fundamentals
        for k, fr in frames.items():                                           # market rules (float32 keeps it small)
            if fr is not None:
                arrays[f"m_{k}"] = fr.to_numpy(np.float32)
                micro_cols[k] = [str(c) for c in fr.columns]
        if members is not None:
            arrays["members"] = members.to_numpy(bool)
        arrays["dates"] = data.close.index.values.astype("datetime64[ns]").astype(np.int64)
        if bm is not None:
            arrays["benchmark"] = bm.reindex(data.close.index).to_numpy(np.float64)
        np.savez(tmp / "data.npz", **arrays)
        (tmp / "meta.json").write_text(json.dumps({"tickers": data.tickers, "start": head["start"],
                                                   "params": head["params"], "costs": costs or {},
                                                   "rf_known": data.rf_known, "provenance": data.provenance,
                                                   "instruments": data.instruments, "account_currency": data.account_currency,
                                                   "micro_cols": micro_cols, "light": light}))
        (tmp / "strategy.py").write_text(code)
        cmd = [sys.executable, "-I", str(CHILD), str(tmp), str(ENGINE)]
        if sys.platform == "darwin" and shutil.which("sandbox-exec"):
            (tmp / "profile.sb").write_text(_profile(tmp))
            cmd = ["sandbox-exec", "-f", str(tmp / "profile.sb")] + cmd
        env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp), "TMPDIR": str(tmp), "LANG": "C.UTF-8",
               "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
        say(f"Running your strategy in the sandbox ({len(data.tickers)} tickers × {len(data.close)} days)…")
        out_f, err_f = open(tmp / "stdout.txt", "w"), open(tmp / "stderr.txt", "w")   # files: no pipe-buffer deadlock
        p = subprocess.Popen(cmd, cwd=tmp, env=env, stdout=out_f, stderr=err_f, text=True,
                             preexec_fn=(lambda: _limits(cpu)) if os.name == "posix" else None)
        t0 = time.time()
        while p.poll() is None:
            if job is not None and job.cancelled:
                p.kill()
                p.wait()
                raise SandboxError("Cancelled.")
            if time.time() - t0 > cpu + 30:
                p.kill()
                p.wait()
                raise SandboxError(f"The strategy ran longer than {cpu} s and was stopped.")
            time.sleep(0.25)
        out_f.close()
        err_f.close()
        stderr_text = (tmp / "stderr.txt").read_text(errors="replace")[-20000:]
        out_file = tmp / "result.json"
        if p.returncode in (-24, -9, 152, 137):                     # SIGXCPU / SIGKILL from the CPU limit
            raise SandboxError(f"The strategy used more than {cpu} s of CPU and was stopped.")
        if p.returncode != 0 or not out_file.exists():
            err = stderr_text.strip().splitlines()
            msg = next((l for l in reversed(err) if l.strip()), f"exit code {p.returncode}")
            raise SandboxError(f"Strategy failed: {msg[-400:]}")
        res = json.loads(out_file.read_text())
        if res.get("error"):
            raise SandboxError(res["error"])
        return res
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
