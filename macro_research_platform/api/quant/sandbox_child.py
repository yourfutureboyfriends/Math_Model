"""Child process for api/quant/sandbox.py. argv: <tmpdir> <path to codelab.py>. Writes result.json."""
import importlib.util
import json
import sys
import traceback


def main() -> None:
    tmp, engine_path = sys.argv[1], sys.argv[2]
    import numpy as np
    import pandas as pd
    spec = importlib.util.spec_from_file_location("codelab", engine_path)
    codelab = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(codelab)
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
                           for k, c in (meta.get("micro_cols") or {}).items() if not k.startswith(("opt_", "fund_"))},
                        fundamentals={k[5:]: pd.DataFrame(z[f"m_{k}"].astype(np.float64), index=idx, columns=c)
                                      for k, c in (meta.get("micro_cols") or {}).items() if k.startswith("fund_")} or None)
    if "roll" in data.opt:
        data.opt["roll"] = data.opt["roll"].fillna(0).astype(bool)
    bm = pd.Series(z["benchmark"], index=idx) if "benchmark" in z.files else None
    # point-in-time index membership (TRADABLE_UNIVERSE = "SP500_PIT"): True where the ticker was a member that day
    data.members = pd.DataFrame(z["members"], index=idx, columns=cols) if "members" in z.files else None
    # warm pandas' lazy imports before locking down
    pd.DataFrame({"a": [1.0, 2.0]}).rolling(2).mean().ewm(span=2).std().rank(axis=1)

    ALLOWED_MODULES = ("numpy", "pandas", "math", "dateutil", "pytz", "tzdata", "datetime", "_", "encodings",
                       "collections", "functools", "itertools", "operator", "re", "decimal", "numbers", "warnings",
                       "typing", "abc", "copy", "textwrap", "string", "calendar", "time", "zoneinfo", "bisect",
                       "heapq", "weakref", "contextlib", "enum", "inspect", "dis", "opcode", "keyword", "token",
                       "tokenize", "linecache", "codecs", "unicodedata", "struct", "statistics", "fractions", "random")
    result_path = f"{tmp}/result.json"

    def hook(event, args):
        if event in ("socket.connect", "socket.bind", "socket.getaddrinfo", "socket.__new__", "subprocess.Popen",
                     "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork", "os.forkpty", "os.kill",
                     "os.putenv", "ctypes.dlopen", "ctypes.dlsym", "ctypes.cdata", "os.remove", "os.rename",
                     "os.rmdir", "os.mkdir", "shutil.rmtree", "os.chmod", "os.symlink", "os.link", "pty.spawn",
                     "webbrowser.open", "urllib.Request", "http.client.connect", "code.__new__", "function.__new__"):
            raise PermissionError(f"blocked: {event}")
        if event == "open":
            path, mode = str(args[0]), args[1] if len(args) > 1 else "r"
            writing = isinstance(mode, str) and any(c in mode for c in "wax+")
            if writing and path != result_path:
                raise PermissionError("blocked: file write")
        if event == "import":
            name = str(args[0])
            if not name.startswith(ALLOWED_MODULES):
                raise PermissionError(f"blocked: import {name}")

    safe_builtins = {k: __builtins__[k] if isinstance(__builtins__, dict) else getattr(__builtins__, k) for k in (
        "abs", "all", "any", "bool", "dict", "divmod", "enumerate", "filter", "float", "frozenset", "int", "isinstance",
        "len", "list", "map", "max", "min", "pow", "print", "range", "reversed", "round", "set", "slice", "sorted",
        "str", "sum", "tuple", "zip", "ValueError", "KeyError", "IndexError", "TypeError", "ZeroDivisionError",
        "Exception", "ArithmeticError", "RuntimeError", "True", "False", "None", "__build_class__")}
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def limited_import(name, *a, **k):
        if name.split(".")[0] not in ("numpy", "pandas", "math"):
            raise ImportError(f"import of '{name}' is not allowed")
        return real_import(name, *a, **k)
    safe_builtins["__import__"] = limited_import
    out = {}
    try:
        sys.addaudithook(hook)
        st = codelab.load_strategy(code, {"__builtins__": safe_builtins})
        out = codelab.evaluate(st["strategy"], data, st["params"], meta["start"], codelab.run_costs(st, meta["costs"]) or None, bm,
                               st["holdout"], st["code_hash"], signal=None if meta.get("light") else st.get("signal"),
                               on_bar=st.get("on_bar"), setup=st.get("setup"), light=bool(meta.get("light")))
        out["provenance"]["runtime"] = f"server sandbox — pandas {pd.__version__}, numpy {np.__version__}"
    except Exception as e:                                    # report the user's error, not ours
        tb = traceback.extract_tb(e.__traceback__)
        where = next((f" (line {f.lineno})" for f in reversed(tb) if f.filename == "<strategy>"), "")
        if not where and tb:                                  # failure inside the platform: name the engine location
            f = tb[-1]
            where = f" (in the engine: {f.filename.rsplit('/', 1)[-1]}:{f.lineno}, {f.name})"
        out = {"error": f"{type(e).__name__}: {e}{where}"[:500]}
    with open(result_path, "w") as f:
        json.dump(out, f)


if __name__ == "__main__":
    main()
