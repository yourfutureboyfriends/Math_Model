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
    """The run-time lockdown: an audit hook (no sockets, subprocesses, ctypes or file writes except result.json) and the
    builtins and import function strategy code gets."""
    # what strategy code itself may import (the static check in sandbox.py says the same); libraries import what they
    # need internally — the hook below still refuses sockets, subprocesses, ctypes and file writes at run time
    USER_IMPORTS = {"numpy", "pandas", "scipy", "sklearn", "statsmodels", "math", "cmath", "statistics", "random",
                    "decimal", "fractions", "numbers", "datetime", "time", "calendar", "zoneinfo", "collections",
                    "itertools", "functools", "operator", "heapq", "bisect", "array", "copy", "enum", "dataclasses",
                    "typing", "abc", "re", "string", "textwrap", "json", "hashlib", "uuid", "warnings", "contextlib",
                    "pprint"}
    result_path = f"{tmp}/result.json"

    def hook(event, args):
        if event in ("socket.connect", "socket.bind", "socket.getaddrinfo", "socket.__new__", "subprocess.Popen",
                     "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork", "os.forkpty", "os.kill",
                     "ctypes.dlopen", "ctypes.dlsym", "ctypes.cdata", "os.remove", "os.rename",
                     "os.rmdir", "os.mkdir", "shutil.rmtree", "os.chmod", "os.symlink", "os.link", "pty.spawn",
                     "webbrowser.open", "urllib.Request", "http.client.connect"):
            # (code.__new__ / function.__new__ are allowed: patsy and statsmodels build functions at import; strategy
            # code cannot reach types.CodeType — the static check blocks the types module and dunder access)
            raise PermissionError(f"blocked: {event}")
        if event == "open":
            path, mode = str(args[0]), args[1] if len(args) > 1 else "r"
            writing = isinstance(mode, str) and any(c in mode for c in "wax+")
            if writing and path != result_path:
                raise PermissionError("blocked: file write")

    import builtins as _b
    BANNED = {"eval", "exec", "compile", "open", "__import__", "globals", "locals", "vars", "input", "breakpoint", "help",
              "exit", "quit", "memoryview", "__loader__", "__spec__"}
    safe_builtins = {k: getattr(_b, k) for k in dir(_b) if k not in BANNED and not (k.startswith("__") and k not in
                                                                                  ("__build_class__", "__name__"))}
    real_import = _b.__import__

    def limited_import(name, globals=None, locals=None, fromlist=(), level=0):
        if level == 0 and name.split(".")[0] not in USER_IMPORTS:
            raise ImportError(f"import of '{name}' is not allowed in strategy code")
        return real_import(name, globals, locals, fromlist, level)
    safe_builtins["__import__"] = limited_import
    return hook, safe_builtins, result_path


def _discover_only(tmp, codelab) -> None:
    """--discover: run the algorithm's initialize() without data and write what it added (universe, custom data)."""
    import ast as _ast
    import types as _types
    hook, safe_builtins, result_path = _policy(tmp)
    code = open(f"{tmp}/strategy.py").read()
    out = {}
    try:
        sys.addaudithook(hook)
        q = sys.modules["qcalgo"]
        cls_name = q.find_class(_ast.parse(code)).name
        ns = {"__builtins__": safe_builtins, "__name__": "strategy", **q.NAMES}
        sys.modules.setdefault("strategy", _types.ModuleType("strategy"))
        codelab._exec_project(q.prepare_source(code), ns)                    # noqa: S102 — inside the sandbox
        out = q.discover(ns[cls_name])
    except Exception as e:                                                   # noqa: BLE001
        out = {"error": f"{type(e).__name__}: {str(e)[:300]}"}
    with open(result_path, "w") as f:
        json.dump(out, f)


if __name__ == "__main__":
    main()
