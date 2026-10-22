"""Child process for api/quant/sandbox.py. argv: <tmpdir> <path to codelab.py>. Writes result.json."""
import importlib.util
import json
import sys
import traceback


def main() -> None:
    tmp, engine_path = sys.argv[1], sys.argv[2]
    import numpy as np
    import pandas as pd
    if len(sys.argv) > 3:                                      # the QuantConnect-style API, imported by the engine
        qspec = importlib.util.spec_from_file_location("qcalgo", sys.argv[3])
        qmod = importlib.util.module_from_spec(qspec)
        sys.modules["qcalgo"] = qmod
        qspec.loader.exec_module(qmod)
        try:                                                     # object store saved by earlier runs (per class)
            qmod.OBJECT_STORE_SEED.update(json.loads(open(f"{tmp}/object_store.json").read()))
        except OSError:
            pass
    spec = importlib.util.spec_from_file_location("codelab", engine_path)
    codelab = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(codelab)
    if "--discover" in sys.argv:
        return _discover_only(tmp, codelab)
    z = np.load(f"{tmp}/data.npz", allow_pickle=False)
    meta = json.loads(open(f"{tmp}/meta.json").read())
    code = open(f"{tmp}/strategy.py").read()
    idx = pd.DatetimeIndex(z["dates"].astype("datetime64[ns]"))
    cols = meta["tickers"]
    frames = {f: pd.DataFrame(z[f], index=idx, columns=cols) for f in ("close", "open", "high", "low", "volume")}
    data = codelab.Data(frames["close"], frames["open"], frames["high"], frames["low"], frames["volume"],
                        rf=pd.Series(z["rf"], index=idx) if meta.get("rf_known", True) else None,
                        vix=pd.Series(z["vix"], index=idx),
                        observed=pd.DataFrame(z["observed"], index=idx, columns=cols) if "observed" in z.files else None,
                        rf_known=meta.get("rf_known", True), provenance=meta.get("provenance"),
                        instruments=meta.get("instruments"), account_currency=meta.get("account_currency") or "USD",
                        usd_per_unit=z["usd_per_unit"] if "usd_per_unit" in z.files else None,
                        options={k[4:]: pd.DataFrame(z[f"m_{k}"].astype(np.float64), index=idx, columns=c)
                                 for k, c in (meta.get("micro_cols") or {}).items() if k.startswith("opt_")} or None,
                        **{k: pd.DataFrame(z[f"m_{k}"].astype(np.float64), index=idx, columns=c)
                           for k, c in (meta.get("micro_cols") or {}).items() if not k.startswith(("opt_", "fund_", "cust_"))},
                        custom={k[5:]: pd.DataFrame(z[f"m_{k}"].astype(np.float64), index=idx, columns=c)
                                for k, c in (meta.get("micro_cols") or {}).items() if k.startswith("cust_")} or None,
                        fundamentals={k[5:]: pd.DataFrame(z[f"m_{k}"].astype(np.float64), index=idx, columns=c)
                                      for k, c in (meta.get("micro_cols") or {}).items() if k.startswith("fund_")} or None)
    if "roll" in data.opt:
        data.opt["roll"] = data.opt["roll"].fillna(0).astype(bool)
    bm = pd.Series(z["benchmark"], index=idx) if "benchmark" in z.files else None
    # point-in-time index membership (TRADABLE_UNIVERSE = "SP500_PIT"): True where the ticker was a member that day
    data.members = pd.DataFrame(z["members"], index=idx, columns=cols) if "members" in z.files else None
    # warm pandas' lazy imports before locking down
    pd.DataFrame({"a": [1.0, 2.0]}).rolling(2).mean().ewm(span=2).std().rank(axis=1)

    hook, safe_builtins, result_path = _policy(tmp)
    _preload(code)
    out = {}
    try:
        sys.addaudithook(hook)
        st = codelab.load_strategy(code, {"__builtins__": safe_builtins, "__name__": "strategy"})
        data = codelab.until(data, st.get("end"))                 # set_end_date: nothing after it is visible
        out = codelab.evaluate(st["strategy"], data, st["params"], meta["start"], codelab.run_costs(st, meta["costs"]) or None, bm,
                               st["holdout"], st["code_hash"], signal=None if meta.get("light") else st.get("signal"),
                               on_bar=st.get("on_bar"), setup=st.get("setup"), light=bool(meta.get("light")))
        out["provenance"]["runtime"] = f"server sandbox — pandas {pd.__version__}, numpy {np.__version__}"
    except Exception as e:                                    # report the user's error, not ours
        tb = traceback.extract_tb(e.__traceback__)
        where = next((f" (line {f.lineno})" for f in reversed(tb) if f.filename == "<strategy>"), "")
        last_user = max((k for k, f in enumerate(tb) if f.filename == "<strategy>"), default=None)
        inner = [f for f in tb[last_user + 1:] if f.filename.endswith(("qcalgo.py", "codelab.py"))] if last_user is not None else []
        if inner:                                             # raised inside the platform's layer, below the user's line
            f = inner[-1]
            where += (f" — raised inside the platform's QuantConnect compatibility layer ({f.filename.rsplit('/', 1)[-1]}:"
                      f"{f.lineno}, {f.name}): if the call is valid on QuantConnect the gap is the layer's, and \"Run on real LEAN\" runs it on "
                      f"QuantConnect's own engine")
        if not where and tb:                                  # failure inside the platform: name the engine location
            f = tb[-1]
            where = f" (in the engine: {f.filename.rsplit('/', 1)[-1]}:{f.lineno}, {f.name})"
        out = {"error": f"{type(e).__name__}: {e}{where}"[:800]}
    with open(result_path, "w") as f:
        json.dump(out, f)


def _policy(tmp):
    """The run-time lockdown: an audit hook (no sockets, subprocesses or ctypes; no reading the run's own folder, which
    holds the whole price history; writes only to the scratch folder and result.json) and the builtins and import
    function strategy code gets — every installed library except system, network and platform modules."""
    import os
    BLOCKED = {"os", "sys", "subprocess", "ctypes", "cffi", "importlib", "builtins", "multiprocessing", "signal", "pty",
               "resource", "mmap", "gc", "inspect", "marshal", "code", "codeop", "webbrowser", "shutil", "tempfile",
               "pathlib", "glob", "fcntl", "posix", "nt", "sysconfig", "site", "faulthandler", "tracemalloc", "_thread",
               "socket", "requests", "urllib", "urllib3", "http", "httpx", "aiohttp", "ftplib", "smtplib", "websocket",
               "websockets", "ssl", "telnetlib", "xmlrpc", "socketserver", "yfinance", "pandas_datareader",
               "api", "codelab", "qcalgo", "sandbox", "sandbox_child", "leanrun"}
    run_dir = os.path.realpath(tmp)
    scratch = os.path.realpath(os.environ.get("QL_SCRATCH") or "/tmp")
    result_path = f"{tmp}/result.json"
    result_real = os.path.realpath(result_path)

    def inside(path, root):
        p = os.path.realpath(str(path))
        return p == root or p.startswith(root + os.sep)

    # In the container (no network, read-only, no capabilities) libraries built on ctypes (xgboost, lightgbm, TA-Lib …)
    # may call their C functions; the process sandbox (no container) refuses ctypes entirely. Strategy code itself
    # cannot import ctypes either way (static check and the import function below).
    in_container = os.environ.get("QL_CONTAINER") == "1"
    ctypes_events = () if in_container else ("ctypes.dlopen", "ctypes.dlsym", "ctypes.cdata")

    def hook(event, args):
        if event in ("socket.connect", "socket.bind", "socket.getaddrinfo", "socket.__new__", "subprocess.Popen",
                     "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork", "os.forkpty", "os.kill",
                     "pty.spawn", "webbrowser.open", "urllib.Request", "http.client.connect") or event in ctypes_events:
            raise PermissionError(f"blocked: {event}")
        if event == "open":
            path, mode = args[0], args[1] if len(args) > 1 else "r"
            if not isinstance(path, (str, bytes, os.PathLike)):
                return
            path = os.fsdecode(path)
            writing = isinstance(mode, str) and any(c in mode for c in "wax+")
            if os.path.realpath(path) == result_real:
                return
            if inside(path, scratch) and not inside(path, run_dir) or (inside(path, scratch) and scratch != run_dir
                                                                         and inside(scratch, run_dir)):
                return                                       # the scratch folder: libraries' caches, temp files
            if writing:
                raise PermissionError("blocked: file write outside the scratch folder")
            if inside(path, run_dir):
                raise PermissionError("blocked: the run's data folder (it holds the whole price history)")
        if event in ("os.remove", "os.rename", "os.rmdir", "os.mkdir", "shutil.rmtree", "os.chmod", "os.symlink",
                     "os.link"):
            if not all(inside(x, scratch) for x in args[:2] if isinstance(x, (str, bytes, os.PathLike))):
                raise PermissionError(f"blocked: {event} outside the scratch folder")

    import builtins as _b
    BANNED = {"eval", "exec", "compile", "__import__", "breakpoint", "input", "help", "exit", "quit", "__loader__",
              "__spec__"}
    safe_builtins = {k: getattr(_b, k) for k in dir(_b) if k not in BANNED and not (k.startswith("__") and k not in
                                                                                  ("__build_class__", "__name__"))}
    real_import = _b.__import__

    def limited_import(name, globals=None, locals=None, fromlist=(), level=0):
        if level == 0 and name.split(".")[0] in BLOCKED:
            raise ImportError(f"import of '{name}' is not allowed in strategy code (system, network or engine module)")
        try:
            return real_import(name, globals, locals, fromlist, level)
        except ModuleNotFoundError as e:
            raise ModuleNotFoundError(f"{e} — not installed in this sandbox runtime") from None
    safe_builtins["__import__"] = limited_import
    return hook, safe_builtins, result_path


HEADER_NAMES = ("UNIVERSE", "START", "PARAMS", "BENCHMARK", "HOLDOUT", "TRADABLE_UNIVERSE", "ACCOUNT_CALENDAR",
                "ACCOUNT_CURRENCY", "FX_HEDGE", "OPTIONS", "FUNDAMENTALS", "CUSTOM_DATA")


def _jsonable(v):
    """Header values as JSON: tuples / sets / ranges / numpy values become lists and numbers, dates become strings."""
    import datetime as _dt
    if isinstance(v, (str, bool, int, float)) or v is None:
        return v
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set, frozenset, range)):
        return [_jsonable(x) for x in v]
    if isinstance(v, (_dt.date, _dt.datetime)):
        return v.isoformat()[:10]
    if hasattr(v, "tolist"):
        return _jsonable(v.tolist())
    if hasattr(v, "item"):
        return v.item()
    return str(v)


def _preload(code: str) -> None:
    """Import the installed libraries the strategy names before the lockdown: their own start-up (loading C libraries,
    writing caches) is library code, not strategy code. Blocked modules and the project's own files are skipped."""
    import ast
    import importlib
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return
    blocked = {"os", "sys", "subprocess", "ctypes", "cffi", "importlib", "builtins", "multiprocessing", "signal", "pty",
               "resource", "mmap", "gc", "inspect", "marshal", "code", "codeop", "webbrowser", "shutil", "tempfile",
               "pathlib", "glob", "socket", "requests", "urllib", "urllib3", "http", "httpx", "aiohttp",
               "api", "codelab", "qcalgo", "sandbox", "sandbox_child", "leanrun", "AlgorithmImports", "QuantConnect",
               "System", "clr"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            names = [node.module]
        else:
            continue
        for n in names:
            if n.split(".")[0] in blocked:
                continue
            try:
                importlib.import_module(n)
            except Exception:                               # noqa: BLE001 — a project file, or reported when run
                pass


def _discover_only(tmp, codelab) -> None:
    """--discover: run the algorithm's initialize() without data and write what it added (universe, custom data)."""
    import ast as _ast
    import types as _types
    hook, safe_builtins, result_path = _policy(tmp)
    code = open(f"{tmp}/strategy.py").read()
    _preload(code)
    out = {}
    try:
        sys.addaudithook(hook)
        q = sys.modules["qcalgo"]
        algo_cls = q.find_class(_ast.parse(code))
        ns = {"__builtins__": safe_builtins, "__name__": "strategy", **q.NAMES}
        sys.modules.setdefault("strategy", _types.ModuleType("strategy"))
        codelab._exec_project(q.prepare_source(code) if algo_cls is not None else code, ns)   # noqa: S102 — sandbox
        if algo_cls is not None:
            out = q.discover(ns[algo_cls.name])
        else:                                    # a plain strategy: the header values its top level computes
            out = {"header": {k: _jsonable(ns[k]) for k in HEADER_NAMES if k in ns}}
    except Exception as e:                                                   # noqa: BLE001
        out = {"error": f"{type(e).__name__}: {str(e)[:300]}"}
    with open(result_path, "w") as f:
        json.dump(out, f)


if __name__ == "__main__":
    main()
