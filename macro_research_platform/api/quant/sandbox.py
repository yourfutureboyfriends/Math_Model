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
    """Static checks; returns the literal header (UNIVERSE, START, PARAMS, BENCHMARK)."""
    if not code or len(code) > MAX_CODE:
        raise SandboxError(f"Code must be 1–{MAX_CODE:,} characters.")
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise SandboxError(f"Syntax error on line {e.lineno}: {e.msg}")
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
            if name in ("UNIVERSE", "START", "PARAMS", "BENCHMARK"):
                try:
                    header[name] = ast.literal_eval(node.value)
                except Exception:
                    raise SandboxError(f"{name} must be a plain literal (list, string or dict of lists).")
    uni = header.get("UNIVERSE")
    if not isinstance(uni, (list, tuple)) or not 1 <= len(uni) <= 80 or not all(isinstance(u, str) for u in uni):
        raise SandboxError("UNIVERSE must be a literal list of 1–80 ticker strings.")
    if not any(isinstance(n, ast.FunctionDef) and n.name == "strategy" for n in tree.body):
        raise SandboxError("Define a top-level function strategy(data, **params).")
    params = header.get("PARAMS") or {}
    if not isinstance(params, dict) or not all(isinstance(v, (list, tuple)) and v for v in params.values()):
        raise SandboxError("PARAMS must be a dict of non-empty lists.")
    n = 1
    for v in params.values():
        n *= len(v)
    if n > 48:
        raise SandboxError(f"PARAMS has {n} combinations — keep it to 48 or fewer.")
    return {"universe": [str(u).upper() for u in uni], "start": str(header.get("START") or "2005-01-01")[:10],
            "params": params, "benchmark": str(header.get("BENCHMARK") or "SPY").upper()}


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


def _limits():                                  # runs in the child before exec
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (TIMEOUT_S, TIMEOUT_S))
    resource.setrlimit(resource.RLIMIT_FSIZE, (50_000_000, 50_000_000))
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
    except (ValueError, OSError):
        pass
    if sys.platform.startswith("linux"):
        resource.setrlimit(resource.RLIMIT_AS, (4_000_000_000, 4_000_000_000))
    os.setsid()


def run(code: str, costs: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """Evaluate user code in the sandbox; returns codelab.evaluate()'s JSON-able output."""
    from api.quant import codeserver
    head = check(code)
    data = codeserver.load_data(head["universe"], head["start"])
    bm = codeserver._index_series(head["benchmark"], data.close.index[0].strftime("%Y-%m-%d"))
    tmp = Path(tempfile.mkdtemp(prefix="qsbx_")).resolve()
    try:
        arrays = {f: getattr(data, f).to_numpy(np.float64) for f in ("close", "open", "high", "low", "volume")}
        arrays["rf"] = data.rf.to_numpy(np.float64)
        arrays["vix"] = data.vix.to_numpy(np.float64)
        arrays["dates"] = data.close.index.values.astype("datetime64[ns]").astype(np.int64)
        if bm is not None:
            arrays["benchmark"] = bm.reindex(data.close.index).to_numpy(np.float64)
        np.savez(tmp / "data.npz", **arrays)
        (tmp / "meta.json").write_text(json.dumps({"tickers": data.tickers, "start": head["start"],
                                                   "params": head["params"], "costs": costs or {}}))
        (tmp / "strategy.py").write_text(code)
        cmd = [sys.executable, "-I", str(CHILD), str(tmp), str(ENGINE)]
        if sys.platform == "darwin" and shutil.which("sandbox-exec"):
            (tmp / "profile.sb").write_text(_profile(tmp))
            cmd = ["sandbox-exec", "-f", str(tmp / "profile.sb")] + cmd
        env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp), "TMPDIR": str(tmp), "LANG": "C.UTF-8",
               "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
        try:
            p = subprocess.run(cmd, cwd=tmp, env=env, capture_output=True, text=True, timeout=TIMEOUT_S + 10,
                               preexec_fn=_limits if os.name == "posix" else None)
        except subprocess.TimeoutExpired:
            raise SandboxError(f"The strategy ran longer than {TIMEOUT_S} s and was stopped.")
        out_file = tmp / "result.json"
        if p.returncode in (-24, -9, 152, 137):                     # SIGXCPU / SIGKILL from the CPU limit
            raise SandboxError(f"The strategy used more than {TIMEOUT_S} s of CPU and was stopped.")
        if p.returncode != 0 or not out_file.exists():
            err = (p.stderr or "").strip().splitlines()
            msg = next((l for l in reversed(err) if l.strip()), f"exit code {p.returncode}")
            raise SandboxError(f"Strategy failed: {msg[-400:]}")
        res = json.loads(out_file.read_text())
        if res.get("error"):
            raise SandboxError(res["error"])
        return res
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
