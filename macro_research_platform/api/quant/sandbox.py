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
import re
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
QCALGO = HERE / "qcalgo.py"                      # the QuantConnect-style API, loaded beside the engine
TIMEOUT_S = 240
MAX_CODE = 40_000
IMAGE = "macro-quant-sandbox:1"                  # built from api/quant/sandbox_image/Dockerfile (ensure_image)
IMAGE_DIR = HERE / "sandbox_image"
_DOCKER: Dict[str, Any] = {"ok": None, "at": 0.0, "why": None}

# Isolation lives at the process / container level (see run): a throwaway Docker container with no network, a
# read-only root filesystem, no capabilities and an unprivileged user; macOS sandbox-exec + an audit hook when Docker is
# not running. The code check below is therefore a short blocklist, not a whitelist of Python: any class, decorator,
# super(), properties, private names and the scientific stack are allowed.
ALLOWED_IMPORT_ROOTS = {
    # data and science
    "numpy", "pandas", "scipy", "sklearn", "statsmodels", "math", "cmath", "statistics", "random", "decimal", "fractions",
    "numbers",
    # standard library without I/O
    "datetime", "time", "calendar", "zoneinfo", "collections", "itertools", "functools", "operator", "heapq", "bisect",
    "array", "copy", "enum", "dataclasses", "typing", "abc", "re", "string", "textwrap", "json", "hashlib", "uuid",
    "warnings", "contextlib", "pprint",
    # QuantConnect imports (names are provided by the platform)
    "AlgorithmImports", "QuantConnect", "System",
}
BLOCKED_IMPORT_ROOTS = {"os", "sys", "subprocess", "socket", "ctypes", "cffi", "importlib", "builtins", "shutil", "pathlib",
                        "io", "pickle", "marshal", "shelve", "multiprocessing", "threading", "concurrent", "signal",
                        "requests", "urllib", "http", "ftplib", "smtplib", "asyncio", "code", "codeop", "gc", "inspect",
                        "pty", "resource", "mmap", "tempfile", "glob", "webbrowser"}
# kept for the static report of what the API uses internally (and the engine-integrity rule below)
QC_PRIVATE = {"_ctx", "_capital", "_tickets", "_indicators", "_selectors", "_warm", "_approx", "_log", "_params", "_algo",
              "_account", "_unsettled", "_lots", "_realized", "_rejected", "_framework", "_consolidators", "_store"}
# engine internals: the backtest context holds the whole price history, including the future — reading it would be
# look-ahead, so these stay out of reach even though the sandbox would contain any damage
ENGINE_INTERNALS = {"_ctx", "_data", "_framework", "_consolidators", "_store", "_tickets", "_capital"}
# escape hatches out of Python's object model (harmless inside the container, blocked anyway as defence in depth)
BANNED_DUNDERS = {"__class__", "__bases__", "__base__", "__subclasses__", "__mro__", "__globals__", "__code__",
                  "__closure__", "__builtins__", "__dict__", "__func__", "__self__", "__getattribute__", "__reduce__",
                  "__reduce_ex__", "__loader__", "__spec__", "__import__", "__traceback__", "__frame__", "__defaults__",
                  "__kwdefaults__", "__init_subclass__", "__set_name__", "__module__"}
BANNED_NAMES = {"eval", "exec", "compile", "open", "__import__", "__builtins__", "globals", "locals", "vars", "input",
                "breakpoint", "help", "exit", "quit", "memoryview"}
BANNED_ATTRS = {"system", "popen", "environ", "getenv", "putenv", "spawn", "fork", "f_globals", "f_locals", "f_back",
                "gi_frame", "cr_frame", "ag_frame", "tb_frame", "tb_next", "f_code", "co_code", "subclasses", "mro",
                "import_module", "fromfile", "tofile", "memmap", "loadtxt", "savetxt", "genfromtxt", "DataSource",
                "HDFStore", "ExcelWriter", "ExcelFile", "ctypeslib"}
NUMPY_FILE_IO = {"load", "save", "savez", "savez_compressed"}       # np.load / np.save (object_store.save is fine)
# pandas / numpy I/O: read_* and to_* writers (to_numpy, to_dict … stay allowed). Data comes in through the platform
# (prices, fundamentals, custom data uploads, the object store), never from paths or URLs in strategy code.
ALLOWED_TO = {"to_numpy", "to_frame", "to_period", "to_series", "to_dict", "to_list", "to_timestamp", "to_numeric",
              "to_datetime", "to_timedelta", "to_offset", "to_pydatetime", "to_string", "to_records", "to_markdown"}
CLASS_BASES = {"QCAlgorithm", "object"}                  # (legacy name; any base is accepted now)
DUNDER_METHODS = set()                                   # (legacy name; any special method except the banned ones)


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
    self_attrs = {t.attr for n in ast.walk(tree) if isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign))
                  for t in (n.targets if isinstance(n, ast.Assign) else [n.target])
                  if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self"}
    clash = sorted(self_attrs & QC_PRIVATE)
    if clash and "QCAlgorithm" in code:
        raise SandboxError(f"self.{clash[0]} is a name the QuantConnect API uses internally — pick another name.")
    for node in ast.walk(tree):
        line = getattr(node, "lineno", "?")
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for m in mods:
                root = m.split(".")[0]
                if root in BLOCKED_IMPORT_ROOTS or root not in ALLOWED_IMPORT_ROOTS:
                    raise SandboxError(f"Line {line}: '{m}' cannot be imported in strategy code (no file, network or "
                                       f"system access). Available: numpy, pandas, scipy, scikit-learn, statsmodels, math, "
                                       f"statistics, datetime, collections, itertools, functools, dataclasses, typing, re, json …")
        elif isinstance(node, ast.Name):
            if node.id in BANNED_NAMES or node.id in BANNED_DUNDERS:
                raise SandboxError(f"Line {line}: '{node.id}' is not available in strategy code.")
        elif isinstance(node, ast.Attribute):
            a = node.attr
            if a in BANNED_DUNDERS or a in BANNED_ATTRS or a.startswith("read_") or (
                    a.startswith("to_") and a not in ALLOWED_TO and a[3:] in ("csv", "excel", "json", "parquet", "pickle",
                                                                            "hdf", "sql", "feather", "stata", "html",
                                                                            "xml", "clipboard", "latex", "gbq", "orc")):
                raise SandboxError(f"Line {line}: '.{a}' is not available in strategy code (no file, network or "
                                   "interpreter internals; data comes in through the platform).")
            if a in NUMPY_FILE_IO and isinstance(node.value, ast.Name) and node.value.id in ("np", "numpy"):
                raise SandboxError(f"Line {line}: np.{a} reads or writes files — use self.object_store for state.")
            if a in ENGINE_INTERNALS and not (a == "_data" and isinstance(node.value, ast.Name) and node.value.id == "self"
                                               and a in self_attrs):
                raise SandboxError(f"Line {line}: '.{a}' is the backtest engine's internal state (it holds future prices) — "
                                   "use the API (history, securities, portfolio) instead.")
        elif isinstance(node, (ast.AsyncFunctionDef, ast.Await, ast.AsyncFor, ast.AsyncWith)):
            raise SandboxError(f"Line {line}: async code is not supported in strategy code.")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and re.search(r"\{[^{}]*\.__\w+__", node.value):
            raise SandboxError(f"Line {line}: format strings that reach interpreter internals ('{{x.__…__}}') are not allowed.")
        elif isinstance(node, ast.ClassDef):
            if any(k.arg == "metaclass" for k in node.keywords):
                raise SandboxError(f"Line {line}: class {node.name} — metaclasses are not supported.")
            for f in node.body:
                if isinstance(f, ast.FunctionDef) and f.name in BANNED_DUNDERS:
                    raise SandboxError(f"Line {f.lineno}: special method {f.name} is not supported.")
                if (isinstance(f, ast.FunctionDef) and f.name == "__init__"
                        and any(isinstance(b_, ast.Name) and b_.id == "QCAlgorithm" for b_ in node.bases)):
                    raise SandboxError(f"Line {f.lineno}: put the set-up in initialize(self), not __init__, in a "
                                       "QCAlgorithm class.")
    header: Dict[str, Any] = {}
    qc = None
    from api.quant import qcalgo
    if qcalgo.find_class(tree) is not None:
        try:
            qc = qcalgo.static_header(code)
        except ValueError as e:
            raise SandboxError(str(e))
        blocking = [r for r in qc["report"] if r["level"] == "unsupported"]
        if blocking:
            raise SandboxError("Not supported here: " + "; ".join(f"line {r['line']}: {r['feature']} — {r['message']}"
                                                                    for r in blocking[:4]))
        header.update({"UNIVERSE": qc["universe"] or [qc.get("benchmark") or "SPY"], "START": qc.get("start") or "2015-01-01",
                       "BENCHMARK": qc.get("benchmark") or "SPY"})
        if qc["dynamic_universe"]:
            header["TRADABLE_UNIVERSE"] = "SP500_PIT"
        if qc.get("fundamentals"):
            header["FUNDAMENTALS"] = qc["fundamentals"]
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in ("UNIVERSE", "START", "PARAMS", "BENCHMARK", "HOLDOUT", "TRADABLE_UNIVERSE", "ACCOUNT_CALENDAR",
                        "ACCOUNT_CURRENCY", "FX_HEDGE", "OPTIONS", "FUNDAMENTALS", "CUSTOM_DATA"):
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
    if qc is None and not any(isinstance(n, ast.FunctionDef) and n.name in ("strategy", "on_bar") for n in tree.body):
        raise SandboxError("Define a top-level function strategy(data, **params) — or on_bar(ctx, **params) for an "
                           "event-driven strategy.")
    from api.quant import customdata
    try:
        custom = list(dict.fromkeys(customdata.spec(header.get("CUSTOM_DATA")) + list((qc or {}).get("custom") or [])))
    except ValueError as e:
        raise SandboxError(str(e))
    known = {m["name"] for m in customdata.catalog()}
    missing = [n for n in custom if n not in known]
    if missing:
        raise SandboxError(f"Custom data '{missing[0]}' has not been uploaded — Quant Lab → Custom data.")
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
            "mode": "event" if qc is not None or any(isinstance(n, ast.FunctionDef) and n.name == "on_bar" for n in tree.body) else "weights",
            "calendar": calendar.upper() if calendar else None, "qc": qc, "custom": custom}


STORE_DIR = HERE.parents[1] / "data" / "processed" / "quant_object_store"     # gitignored


def _store_path(cls_name: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_]", "_", cls_name)[:80] or "algorithm"
    return STORE_DIR / f"{safe}.json"


def load_object_store(cls_name: str) -> Dict[str, str]:
    try:
        return json.loads(_store_path(cls_name).read_text())
    except Exception:                                                        # noqa: BLE001 — none saved yet
        return {}


def save_object_store(cls_name: str, data: Dict[str, str]) -> None:
    if not isinstance(data, dict) or sum(len(str(k)) + len(str(v)) for k, v in data.items()) > 10_000_000:
        return
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    _store_path(cls_name).write_text(json.dumps({str(k): str(v) for k, v in data.items()}))


def docker_status(refresh: bool = False) -> Dict[str, Any]:
    """Whether runs go to a container: the docker CLI, a running daemon and the sandbox image. Cached for a minute."""
    now = time.time()
    if not refresh and _DOCKER["ok"] is not None and now - _DOCKER["at"] < 60:
        return {"docker": _DOCKER["ok"], "reason": _DOCKER["why"], "image": IMAGE}
    ok, why = False, None
    if os.getenv("MACRO_SANDBOX_DOCKER", "1") == "0":
        why = "disabled (MACRO_SANDBOX_DOCKER=0)"
    elif not shutil.which("docker"):
        why = "docker is not installed"
    else:
        try:
            r = subprocess.run(["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"], capture_output=True,
                               text=True, timeout=8)
            if r.returncode == 0:
                ok = True
            elif "Cannot connect" in (r.stderr or "") or "daemon" in (r.stderr or ""):
                why = "Docker is not running"
            else:
                why = f"the sandbox image {IMAGE} is not built (python -m api.quant.sandbox --build)"
        except Exception as e:                                              # noqa: BLE001
            why = f"docker check failed ({type(e).__name__})"
    _DOCKER.update(ok=ok, at=now, why=why)
    return {"docker": ok, "reason": why, "image": IMAGE}


def ensure_image() -> None:
    """Build the sandbox image (python:3.12-slim + the platform's numpy / pandas / scipy / scikit-learn / statsmodels)."""
    import numpy as _np, pandas as _pd
    args = ["--build-arg", f"NUMPY={_np.__version__}", "--build-arg", f"PANDAS={_pd.__version__}"]
    for mod, arg in (("scipy", "SCIPY"), ("sklearn", "SKLEARN"), ("statsmodels", "STATSMODELS")):
        try:
            args += ["--build-arg", f"{arg}={__import__(mod).__version__}"]
        except ImportError:
            pass
    subprocess.run(["docker", "build", "-t", IMAGE, *args, str(IMAGE_DIR)], check=True)
    _DOCKER.update(ok=None)


def _docker_cmd(tmp: Path, name: str, cpu: int) -> list:
    """A throwaway container: no network, read-only root, no capabilities, no privilege escalation, an unprivileged
    user, memory / CPU / process caps; only the run's temp folder (data in, result out) and the engine are mounted."""
    return ["docker", "run", "--rm", "--name", name, "--network", "none", "--read-only",
            "--tmpfs", "/tmp:rw,size=256m", "--memory", "4g", "--memory-swap", "4g", "--cpus", "2",
            "--pids-limit", "256", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--ulimit", f"cpu={cpu}:{cpu}", "--ulimit", "nofile=256:256",
            "-v", f"{tmp}:/work:rw", "-v", f"{CHILD}:/engine/sandbox_child.py:ro",
            "-v", f"{ENGINE}:/engine/codelab.py:ro", "-v", f"{QCALGO}:/engine/qcalgo.py:ro",
            "-e", "HOME=/tmp", IMAGE,
            "python", "-I", "/engine/sandbox_child.py", "/work", "/engine/codelab.py", "/engine/qcalgo.py"]


def _profile(tmp: Path) -> str:
    py_prefix = Path(sys.prefix).resolve()
    base = Path(sys.base_prefix).resolve()
    allow_read = [str(py_prefix), str(base), str(tmp), str(ENGINE), str(CHILD), str(QCALGO)]
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


def _prepare(code: str, head: Dict[str, Any], costs: Optional[Dict[str, float]], light: bool, tmp: Path,
             say, cancelled=lambda: False) -> Dict[str, Any]:
    """Load and validate the data for a run and write it into `tmp` for the sandbox child (data.npz, meta.json,
    strategy.py). Returns the CPU allowance and the size. Runs in a helper process for large universes, so the web
    server stays responsive while thousands of price histories are prepared."""
    from api.quant import codelab, codeserver
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
    codeserver.attach_custom(data, head.get("custom"))
    if head.get("calendar"):
        data = codeserver.account_session_data(data, head["calendar"])
        if members is not None:
            members = members.reindex(index=data.close.index, columns=data.tickers).fillna(False)
    if cancelled():
        raise SandboxError("Cancelled.")
    bm = codeserver.benchmark_series(head["benchmark"], data.close.index[0].strftime("%Y-%m-%d"), data.account_currency)
    arrays = {f: getattr(data, f).to_numpy(np.float64) for f in ("close", "open", "high", "low", "volume")}
    arrays["rf"] = data.rf.to_numpy(np.float64)
    arrays["vix"] = data.vix.to_numpy(np.float64)
    arrays["observed"] = data.observed.to_numpy(bool)
    arrays["usd_per_unit"] = data.usd_per_unit.to_numpy(np.float64)
    micro_cols = {}
    frames = {k: getattr(data, k, None) for k in ("tick_bps", "lot_value", "div_yield", "fx", "rf_ccy", "settle", "share_px")}
    frames.update({f"opt_{k}": v for k, v in data.opt.items()})          # synthetic options' analytics
    frames.update({f"fund_{k}": v for k, v in data.fund.items()})        # point-in-time fundamentals
    frames.update({f"cust_{k}": v for k, v in data.custom.items()})       # uploaded custom data
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
    return {"cpu": cpu, "tickers": len(data.tickers), "days": len(data.close)}


def _prepare_proc(code: str, costs: Optional[Dict[str, float]], light: bool, tmp: str, q) -> None:
    """Helper-process entry point: prepare the data, sending progress and the outcome through `q`."""
    try:
        out = _prepare(code, check(code), costs, light, Path(tmp), lambda m: q.put(("progress", m)))
        q.put(("done", out))
    except Exception as e:                                      # noqa: BLE001 — reported to the parent
        q.put(("error", f"{type(e).__name__}: {e}"))


def run(code: str, costs: Optional[Dict[str, float]] = None, job: Optional[Any] = None, light: bool = False) -> Dict[str, Any]:
    """Evaluate user code in the sandbox; returns codelab.evaluate()'s JSON-able output. `job` (api/quant/jobs.py)
    receives progress and can cancel the run (the child process is killed)."""
    from api.quant import codelab
    head = check(code)
    say = (lambda m: job.progress(m)) if job is not None else (lambda m: None)
    cancelled = (lambda: job.cancelled) if job is not None else (lambda: False)
    tmp = Path(tempfile.mkdtemp(prefix="qsbx_")).resolve()
    try:
        if head.get("tradable") or len(head["universe"]) > codelab.UNIVERSE_LIMIT:
            prep = _prepare_elsewhere(code, costs, light, tmp, say, cancelled)
        else:
            prep = _prepare(code, head, costs, light, tmp, say, cancelled)
        cpu = prep["cpu"]
        qc_class = (head.get("qc") or {}).get("class")
        if qc_class:                                       # the algorithm's object store from earlier runs
            (tmp / "object_store.json").write_text(json.dumps({qc_class: load_object_store(qc_class)}))
        dk = docker_status()
        container = None
        if dk["docker"]:
            import uuid
            container = f"qsbx-{uuid.uuid4().hex[:12]}"
            os.chmod(tmp, 0o777)                        # the container's unprivileged user writes result.json here
            cmd = _docker_cmd(tmp, container, cpu)
            env = {**os.environ}
            where = "an isolated container (no network, read-only, unprivileged)"
        else:
            cmd = [sys.executable, "-I", str(CHILD), str(tmp), str(ENGINE), str(QCALGO)]
            if sys.platform == "darwin" and shutil.which("sandbox-exec"):
                (tmp / "profile.sb").write_text(_profile(tmp))
                cmd = ["sandbox-exec", "-f", str(tmp / "profile.sb")] + cmd
            env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp), "TMPDIR": str(tmp), "LANG": "C.UTF-8",
                   "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
            where = f"the process sandbox ({dk['reason']})"
        say(f"Running your strategy in {where} — {prep['tickers']} tickers × {prep['days']} days…")
        out_f, err_f = open(tmp / "stdout.txt", "w"), open(tmp / "stderr.txt", "w")   # files: no pipe-buffer deadlock
        p = subprocess.Popen(cmd, cwd=tmp, env=env, stdout=out_f, stderr=err_f, text=True,
                             preexec_fn=(lambda: _limits(cpu)) if os.name == "posix" and container is None else None)

        def _stop():
            if container:
                subprocess.run(["docker", "kill", container], capture_output=True, timeout=20)
            p.kill()
            p.wait()
        t0 = time.time()
        while p.poll() is None:
            if job is not None and job.cancelled:
                _stop()
                raise SandboxError("Cancelled.")
            if time.time() - t0 > cpu + (90 if container else 30):
                _stop()
                raise SandboxError(f"The strategy ran longer than {cpu} s and was stopped.")
            time.sleep(0.25)
        out_f.close()
        err_f.close()
        stderr_text = (tmp / "stderr.txt").read_text(errors="replace")[-20000:]
        out_file = tmp / "result.json"
        if p.returncode in (-24, -9, 152, 137):                     # SIGXCPU / SIGKILL from the CPU or memory limit
            raise SandboxError(f"The strategy used more than {cpu} s of CPU{' or 4 GB of memory' if container else ''} "
                               "and was stopped.")
        if p.returncode != 0 or not out_file.exists():
            err = stderr_text.strip().splitlines()
            msg = next((l for l in reversed(err) if l.strip()), f"exit code {p.returncode}")
            raise SandboxError(f"Strategy failed: {msg[-400:]}")
        res = json.loads(out_file.read_text())
        if res.get("error"):
            raise SandboxError(res["error"])
        store = (((res.get("execution") or {}).get("algorithm") or {}).get("object_store") or {})
        if qc_class and store.get("class") == qc_class:
            save_object_store(qc_class, store.get("data") or {})
        res.setdefault("provenance", {})["isolation"] = ("docker container (no network, read-only filesystem, no "
                                                         "capabilities, unprivileged user)" if container else
                                                         f"process sandbox ({dk['reason']})")
        return res
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _prepare_elsewhere(code: str, costs: Optional[Dict[str, float]], light: bool, tmp: Path, say, cancelled) -> Dict[str, Any]:
    """_prepare in a separate process (spawned), relaying progress; killed on cancel."""
    import multiprocessing as mp
    import queue as _queue
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    proc = ctx.Process(target=_prepare_proc, args=(code, costs, light, str(tmp), q), daemon=True)
    proc.start()
    try:
        while True:
            if cancelled():
                proc.kill()
                raise SandboxError("Cancelled.")
            try:
                kind, val = q.get(timeout=0.5)
            except _queue.Empty:
                if not proc.is_alive():
                    raise SandboxError(f"Data preparation stopped unexpectedly (exit code {proc.exitcode}).")
                continue
            if kind == "progress":
                say(val)
            elif kind == "done":
                return val
            else:
                raise SandboxError(val)
    finally:
        proc.join(timeout=5)
        if proc.is_alive():
            proc.kill()


if __name__ == "__main__":                       # python -m api.quant.sandbox --build
    if "--build" in sys.argv:
        ensure_image()
        print(docker_status(refresh=True))
