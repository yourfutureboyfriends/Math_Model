"""
Run a QuantConnect algorithm on QuantConnect's own LEAN engine (the official `quantconnect/lean` Docker image), unmodified,
with the platform's free daily prices converted to LEAN's data format — US equities, crypto pairs (any venue LEAN knows:
Coinbase, Binance, Kraken, …) and FX pairs (Oanda, FXCM) — so the algorithm runs exactly as LEAN runs it.

Data written per run (api/quant/leanrun.prepare):
  equity/usa/daily/<ticker>.zip       <ticker>.csv rows "YYYYMMDD 00:00,open,high,low,close,volume", prices × 10,000
  equity/usa/map_files/<ticker>.csv   the ticker from before the data starts to 2050 (no renames)
  equity/usa/factor_files/<ticker>.csv  factors 1 — prices are already split- and dividend-adjusted (total return)
LEAN's market-hours and symbol-properties databases come from the image.

Isolation: the container has no network, every capability dropped, no privilege escalation, memory / CPU / process
caps; only the algorithm, the run's data and a results folder are mounted.

Crypto: trade and quote bars per venue (a USD pair also stands in for its stablecoin pairs, 1 stablecoin = 1 USD); FX: bid
and ask bars. Free daily data has no spread, so bid = ask = the traded price.

Not available on this path (free data): minute / second / tick data, options and futures chains, QuantConnect's
fundamental and alternative datasets (coarse / fine universes) — those algorithms run on the Python layer instead.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

IMAGE = os.getenv("MACRO_LEAN_IMAGE", "quantconnect/lean:latest")
LEAN_DATA = "/Lean/Data"
_STATUS: Dict[str, Any] = {"at": 0.0}


class LeanError(RuntimeError):
    pass


def status(refresh: bool = False) -> Dict[str, Any]:
    """Whether real-LEAN runs are possible: docker, a running daemon and the LEAN image. Cached for a minute."""
    if not refresh and time.time() - _STATUS["at"] < 60:
        return {k: v for k, v in _STATUS.items() if k != "at"}
    ok, why, version = False, None, None
    if not shutil.which("docker"):
        why = "docker is not installed"
    else:
        try:
            r = subprocess.run(["docker", "image", "inspect", IMAGE, "--format", "{{.Id}} {{.Created}}"],
                               capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                ok, version = True, r.stdout.strip().split(" ", 1)[-1][:10]
            elif "daemon" in (r.stderr or "") or "Cannot connect" in (r.stderr or ""):
                why = "Docker is not running"
            else:
                why = f"the LEAN image {IMAGE} is not downloaded (docker pull {IMAGE})"
        except Exception as e:                                               # noqa: BLE001
            why = f"docker check failed ({type(e).__name__})"
    _STATUS.update(at=time.time(), available=ok, reason=why, image=IMAGE, image_date=version)
    return {"available": ok, "reason": why, "image": IMAGE, "image_date": version}


def lean_ticker(t: str) -> Optional[str]:
    """Platform ticker → LEAN's US-equity ticker (lower case; BRK-B → brk.b). None for non-US listings."""
    t = str(t).upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9]{0,5}([-.][A-Z])?", t):
        return None
    return t.replace("-", ".").lower()


def write_daily(root: Path, ticker: str, frame: pd.DataFrame) -> int:
    """One ticker's daily bars in LEAN's equity format. `frame` has open, high, low, close, volume (index = dates)."""
    f = frame.dropna(subset=["close"]).copy()
    if f.empty:
        return 0
    for c in ("open", "high", "low"):
        f[c] = f[c].fillna(f["close"])
    f["volume"] = f["volume"].fillna(0)
    rows = [f"{d.strftime('%Y%m%d')} 00:00,{int(round(o * 10000))},{int(round(h * 10000))},{int(round(l * 10000))},"
            f"{int(round(c * 10000))},{int(v)}"
            for d, o, h, l, c, v in zip(f.index, f["open"], f["high"], f["low"], f["close"], f["volume"])]
    daily = root / "equity" / "usa" / "daily"
    daily.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(daily / f"{ticker}.zip", "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{ticker}.csv", "\n".join(rows) + "\n")
    first = f.index[0] - pd.Timedelta(days=10)
    for sub, body in (("map_files", f"{first:%Y%m%d},{ticker}\n20501231,{ticker}\n"),
                      ("factor_files", f"{first:%Y%m%d},1,1,1\n20501231,1,1,0\n")):
        d = root / "equity" / "usa" / sub
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{ticker}.csv").write_text(body)
    return len(rows)


CRYPTO_VENUES = ("coinbase", "binance", "binanceus", "kraken", "bitfinex", "bybit")
FX_VENUES = ("oanda", "fxcm")


def _bars_csv(f: pd.DataFrame, quote: bool) -> str:
    """Unscaled daily rows; quote=True writes bid and ask bars (both at the traded price — free data has no spread)."""
    out = []
    for d, o, h, l, c, v in zip(f.index, f["open"], f["high"], f["low"], f["close"], f["volume"]):
        px = f"{o:.10g},{h:.10g},{l:.10g},{c:.10g}"
        out.append(f"{d:%Y%m%d} 00:00,{px},0,{px},0" if quote else f"{d:%Y%m%d} 00:00,{px},{float(v or 0):.10g}")
    return "\n".join(out) + "\n"


def _write_zip(path: Path, inner: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(inner, body)


def write_crypto(root: Path, base: str, quote: str, frame: pd.DataFrame) -> List[str]:
    """A crypto pair's daily trade and quote bars for every venue LEAN might ask (Market.COINBASE, BINANCE, …); a USD
    pair also stands in for its stablecoin pairs (USDT, USDC, BUSD)."""
    f = frame.dropna(subset=["close"]).fillna({"volume": 0})
    for c in ("open", "high", "low"):
        f[c] = f[c].fillna(f["close"])
    pairs = [f"{base}{quote}".lower()] + ([f"{base}{s}".lower() for s in ("usdt", "usdc", "busd", "fdusd")]
                                          if quote == "USD" else [])
    trade, quotes = _bars_csv(f, False), _bars_csv(f, True)
    for venue in CRYPTO_VENUES:
        for pair in pairs:
            d = root / "crypto" / venue / "daily"
            _write_zip(d / f"{pair}_trade.zip", f"{pair}.csv", trade)
            _write_zip(d / f"{pair}_quote.zip", f"{pair}.csv", quotes)
    return pairs


def write_forex(root: Path, pair: str, frame: pd.DataFrame) -> None:
    f = frame.dropna(subset=["close"]).fillna({"volume": 0})
    for c in ("open", "high", "low"):
        f[c] = f[c].fillna(f["close"])
    for venue in FX_VENUES:
        _write_zip(root / "forex" / venue / "daily" / f"{pair.lower()}.zip", f"{pair.lower()}.csv", _bars_csv(f, True))


def classify(ticker: str):
    """('equity', lean ticker) | ('crypto', (base, quote)) | ('forex', pair) | (None, None)."""
    t = str(ticker).upper()
    m = re.fullmatch(r"([A-Z]{6})=X", t)
    if m:
        return "forex", m.group(1)
    if re.fullmatch(r"[A-Z0-9]{2,10}-(USD|USDT|USDC|EUR|GBP|JPY|BTC|ETH)", t):
        b, q = t.split("-")
        return "crypto", (b, q)
    lt = lean_ticker(t)
    return ("equity", lt) if lt else (None, None)


def prepare(tickers: List[str], start: str, root: Path, say=lambda m: None) -> Dict[str, Any]:
    """Convert the platform's daily prices for `tickers` (+ SPY, LEAN's default benchmark) into LEAN's format."""
    from api.quant import codeserver
    want = list(dict.fromkeys([t.upper() for t in tickers] + ["SPY"]))
    kinds = {t: classify(t) for t in want}
    skipped = [t for t, (k, _) in kinds.items() if k is None]
    usable = [t for t, (k, _) in kinds.items() if k is not None]
    if not usable:
        raise LeanError("No tickers LEAN can take (US equities, crypto pairs, FX pairs).")
    say(f"Converting daily prices for {len(usable)} instruments to LEAN's format…")
    warm = (pd.Timestamp(start) - pd.Timedelta(days=500)).strftime("%Y-%m-%d")    # history before the start for warm-up
    d = codeserver.load_data(usable, warm, allow_missing=True)
    rows, notes = {}, []
    for t in usable:
        if t not in d.close.columns:
            skipped.append(t)
            continue
        obs = d.observed[t]
        fr = pd.DataFrame({"open": d.open[t], "high": d.high[t], "low": d.low[t], "close": d.close[t],
                           "volume": d.volume[t]})[obs]
        kind, key = kinds[t]
        if kind == "equity":
            rows[t] = write_daily(root, key, fr)
        elif kind == "crypto":
            pairs = write_crypto(root, key[0], key[1], fr)
            rows[t] = int(len(fr))
            if len(pairs) > 1:
                notes.append(f"{t} also stands in for {', '.join(p.upper() for p in pairs[1:])} (stablecoin = 1 USD)")
        else:
            write_forex(root, key, fr)
            rows[t] = int(len(fr))
    if any(kinds[t][0] in ("crypto", "forex") for t in rows):
        notes.append("crypto and FX bid/ask are both the traded price (free daily data has no spread)")
    return {"tickers": rows, "skipped": skipped, "notes": notes, "data_start": str(d.close.index[0].date()),
            "data_end": str(d.close.index[-1].date())}


def _docker_cmd(name: str, algo_dir: Path, data_dir: Path, results: Path, cls: str, cpu: int) -> List[str]:
    mounts = []
    for sub in ("daily", "map_files", "factor_files"):
        p = data_dir / "equity" / "usa" / sub
        if p.exists():
            mounts += ["-v", f"{p}:{LEAN_DATA}/equity/usa/{sub}:ro"]
    for cls_dir in ("crypto", "forex"):
        for venue in sorted((data_dir / cls_dir).glob("*/daily")) if (data_dir / cls_dir).exists() else []:
            mounts += ["-v", f"{venue}:{LEAN_DATA}/{cls_dir}/{venue.parent.name}/daily:ro"]
    return ["docker", "run", "--rm", "--name", name, "--network", "none", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--memory", "6g", "--memory-swap", "6g", "--cpus", "2",
            "--pids-limit", "512", "--ulimit", f"cpu={cpu}:{cpu}",
            "-v", f"{algo_dir}:/Algorithm:ro", "-v", f"{results}:/Results:rw", *mounts,
            "-w", "/Lean/Launcher/bin/Debug", IMAGE,                   # the image's entrypoint is the LEAN launcher
            "--environment", "backtesting", "--algorithm-language", "Python",
            "--algorithm-type-name", cls, "--algorithm-location", "/Algorithm/main.py",
            "--data-folder", LEAN_DATA, "--results-destination-folder", "/Results",
            "--close-automatically", "true"]


def _series(chart: Dict[str, Any], name: str) -> List[List[float]]:
    s = ((chart or {}).get("series") or (chart or {}).get("Series") or {}).get(name) or {}
    vals = s.get("values") or s.get("Values") or []
    out = []
    for v in vals:
        if isinstance(v, dict):
            out.append([float(v.get("x")), float(v.get("y"))])
        elif isinstance(v, (list, tuple)) and len(v) >= 2:
            out.append([float(v[0]), float(v[-1] if len(v) == 5 else v[1])])     # candles: [t, o, h, l, c]
    return out


def parse_results(results: Path) -> Dict[str, Any]:
    """LEAN's result JSON → statistics, equity curve, orders, logs."""
    files = sorted(p for p in results.glob("*.json") if not p.name.endswith(("-summary.json", "-order-events.json",
                                                                                "data-monitor-report.json")))
    main = next((p for p in files if not re.search(r"-(log|alpha|insights)", p.name)), None)
    if main is None:
        raise LeanError("LEAN wrote no result file.")
    r = json.loads(main.read_text())
    stats = r.get("statistics") or r.get("Statistics") or {}
    rt = r.get("runtimeStatistics") or r.get("RuntimeStatistics") or {}
    charts = r.get("charts") or r.get("Charts") or {}
    eq = _series(charts.get("Strategy Equity") or {}, "Equity")
    bm = _series(charts.get("Benchmark") or {}, "Benchmark")
    orders = r.get("orders") or r.get("Orders") or {}
    order_list = list(orders.values()) if isinstance(orders, dict) else list(orders)
    log = ""
    for p in results.glob("*log*.txt"):
        log += p.read_text(errors="replace")[-8000:]
    curve = [{"date": time.strftime("%Y-%m-%d", time.gmtime(x)), "equity": y} for x, y in eq]
    return {"statistics": stats, "runtime_statistics": rt, "equity_curve": curve,
            "benchmark_curve": [{"date": time.strftime("%Y-%m-%d", time.gmtime(x)), "value": y} for x, y in bm],
            "orders": [{k: o.get(k) for k in ("Id", "Symbol", "Time", "Type", "Status", "Quantity", "Price", "Tag",
                                              "id", "symbol", "time", "type", "status", "quantity", "price", "tag")
                        if k in o} for o in order_list[:500]],
            "order_count": len(order_list), "log_tail": log[-4000:]}


def run(code: str, job: Optional[Any] = None, timeout: int = 1800) -> Dict[str, Any]:
    """Backtest a QuantConnect algorithm on real LEAN. Returns LEAN's statistics, equity curve and orders."""
    from api.quant import qcalgo, sandbox
    say = (lambda m: job.progress(m)) if job is not None else (lambda m: None)
    st = status(refresh=True)
    if not st["available"]:
        raise LeanError(f"Real-LEAN runs are unavailable: {st['reason']}.")
    head = sandbox.check(code)                         # same static and discovery checks as every server run
    qc = head.get("qc")
    if not qc:
        raise LeanError("Real-LEAN runs take a QuantConnect algorithm (a class deriving from QCAlgorithm).")
    if qc.get("dynamic_universe"):
        raise LeanError("This algorithm selects a dynamic universe — QuantConnect's coarse/fundamental data is not free, so "
                        "it runs on the Python layer (point-in-time S&P 500 + SEC fundamentals) instead.")
    if head.get("custom"):
        raise LeanError("Custom data uploads run on the Python layer (LEAN would fetch get_source itself, and the "
                        "container has no network).")
    tmp = Path(tempfile.mkdtemp(prefix="qlean_")).resolve()
    name = f"qlean-{uuid.uuid4().hex[:12]}"
    try:
        algo_dir, data_dir, results = tmp / "algo", tmp / "data", tmp / "results"
        for p in (algo_dir, data_dir, results):
            p.mkdir()
        os.chmod(results, 0o777)
        from api.quant.codelab import split_project
        main, files = split_project(code)
        (algo_dir / "main.py").write_text(main)
        for mod, src in files.items():                     # the project's other files, as real modules for LEAN
            path = algo_dir / (mod.replace(".", "/") + ".py")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(src)
            for parent in path.relative_to(algo_dir).parents:
                if str(parent) != ".":
                    (algo_dir / parent / "__init__.py").touch()
        prep = prepare(head["universe"], qc.get("start") or head["start"], data_dir, say)
        say(f"Running on LEAN ({IMAGE}) — {len(prep['tickers'])} tickers…")
        log_f = open(tmp / "lean.log", "w")
        p = subprocess.Popen(_docker_cmd(name, algo_dir, data_dir, results, qc["class"], timeout), stdout=log_f,
                             stderr=subprocess.STDOUT)
        t0 = time.time()
        while p.poll() is None:
            if job is not None and getattr(job, "cancelled", False):
                subprocess.run(["docker", "kill", name], capture_output=True, timeout=30)
                raise LeanError("Cancelled.")
            if time.time() - t0 > timeout:
                subprocess.run(["docker", "kill", name], capture_output=True, timeout=30)
                raise LeanError(f"LEAN ran longer than {timeout} s and was stopped.")
            time.sleep(0.5)
        log_f.close()
        console = (tmp / "lean.log").read_text(errors="replace")
        try:
            out = parse_results(results)
        except LeanError:
            err = [l for l in console.splitlines() if re.search(r"ERROR|Error|Exception|Traceback|Runtime Error", l)]
            raise LeanError("LEAN did not finish: " + (" | ".join(err[-4:]) or console[-800:]))
        rt_err = [l for l in console.splitlines() if "Runtime Error" in l or "PythonException" in l]
        out.update({"engine": "QuantConnect LEAN (unmodified)", "image": IMAGE, "image_date": st.get("image_date"),
                    "data": {**prep, "source": "platform daily prices (split- and dividend-adjusted) in LEAN format"},
                    "runtime_errors": rt_err[-5:], "console_tail": console[-3000:],
                    "isolation": "docker: no network, capabilities dropped, no privilege escalation, memory/CPU caps"})
        return out
    finally:
        try:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=20)
        except Exception:                                                     # noqa: BLE001
            pass
        shutil.rmtree(tmp, ignore_errors=True)
