"""
Workbench functions:

  formula_chart(exprs)   G     — chart formulas over any instruments and FRED series: AAPL/SPY, {^TNX}-{FRED:DGS2},
                                 log(XOM)-log(CVX), ma(SPY,200), yoy(FRED:CPIAUCSL) …
  data_grid(syms, flds)  BDP   — any fields for a list of instruments, for a table or a spreadsheet
  history_grid(syms)     BDH   — closing prices (or returns / volume) for a list of instruments side by side
  vol_surface(sym)       OVDV  — implied volatility by strike and expiry, term structure, skew, IV vs realised, IV history
  exchanges()            CDR   — trading hours, open / closed now, next session and holidays for 22 exchanges
"""
from __future__ import annotations

import ast
import concurrent.futures as cf
import json
import logging
import math
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from api.marketdata.core import NotFound, _cached, _f, _info, yahoo_call, yahoo_download

logger = logging.getLogger(__name__)


# ── G: formula charts ────────────────────────────────────────────────────────
FUNCS = {"log", "exp", "abs", "sqrt", "ma", "ema", "yoy", "pct", "diff", "rebase", "z", "lag", "vol"}
PERIODS = {"1y": 365, "2y": 730, "5y": 1826, "10y": 3652, "20y": 7305, "max": 36500}
TOKEN = re.compile(r"\{([^}]+)\}|(FRED:[A-Za-z0-9_]+)|(\^?[A-Za-z][A-Za-z0-9.=_]*)")


def _parse(expr: str) -> (str, Dict[str, str]):
    """Replace each instrument / FRED id with a variable name so the expression is plain Python."""
    names: Dict[str, str] = {}
    out, pos = [], 0
    for m in TOKEN.finditer(expr):
        raw = m.group(1) or m.group(2) or m.group(3)
        after = expr[m.end():].lstrip()
        if m.group(3) and raw.lower() in FUNCS and after.startswith("("):
            continue                                              # a function name
        out.append(expr[pos:m.start()])
        key = raw.strip().upper()
        var = names.setdefault(key, f"v{len(names)}")
        out.append(var)
        pos = m.end()
    out.append(expr[pos:])
    return "".join(out), {v: k for k, v in names.items()}


def _series(key: str, start: date) -> pd.Series:
    if key.startswith("FRED:"):
        from api.marketdata.toolkit import fred_series
        d = fred_series(key[5:])
        s = pd.Series({pd.Timestamp(r["date"]): r["value"] for r in d["rows"]}, dtype=float)
        return s[s.index >= pd.Timestamp(start)]

    def fetch():
        df = yahoo_download([key], start=start.isoformat(), auto_adjust=True)
        if df is None or df.empty:
            raise NotFound(f"No price history for {key}.")
        c = df["Close"]
        if isinstance(c, pd.DataFrame):
            c = c.iloc[:, 0]
        c = c.dropna()
        c.index = pd.to_datetime(c.index).tz_localize(None).normalize()
        return c
    return _cached(f"gser:{key}:{start}", 1800, fetch)


def _eval(node, env: Dict[str, pd.Series]):
    if isinstance(node, ast.Expression):
        return _eval(node.body, env)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id not in env:
            raise NotFound(f"Unknown name '{node.id}'.")
        return env[node.id]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = _eval(node.operand, env)
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
        a, b = _eval(node.left, env), _eval(node.right, env)
        if isinstance(node.op, ast.Add):
            return a + b
        if isinstance(node.op, ast.Sub):
            return a - b
        if isinstance(node.op, ast.Mult):
            return a * b
        if isinstance(node.op, ast.Div):
            return a / (b.replace(0, np.nan) if isinstance(b, pd.Series) else (b or np.nan))
        return a ** b
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id.lower() in FUNCS and not node.keywords:
        f = node.func.id.lower()
        args = [_eval(a, env) for a in node.args]
        x = args[0] if args else None
        n = int(args[1]) if len(args) > 1 and not isinstance(args[1], pd.Series) else None
        if not isinstance(x, pd.Series):
            raise NotFound(f"{f}() needs a series as its first argument.")
        if f == "log":
            return np.log(x.where(x > 0))
        if f == "exp":
            return np.exp(x)
        if f == "abs":
            return x.abs()
        if f == "sqrt":
            return np.sqrt(x.where(x >= 0))
        if f == "ma":
            return x.rolling(n or 50).mean()
        if f == "ema":
            return x.ewm(span=n or 20, adjust=False).mean()
        if f == "pct":
            return x.pct_change(n or 1) * 100
        if f == "diff":
            return x.diff(n or 1)
        if f == "lag":
            return x.shift(n or 1)
        if f == "rebase":
            first = x.dropna()
            return x / first.iloc[0] * 100 if len(first) else x
        if f == "z":
            w = n or 252
            return (x - x.rolling(w).mean()) / x.rolling(w).std()
        if f == "vol":
            return np.log(x).diff().rolling(n or 21).std() * math.sqrt(252) * 100
        if f == "yoy":                                          # by date, whatever the frequency
            prev = x.reindex(x.index - pd.Timedelta(days=365), method="ffill")
            prev.index = x.index
            return (x / prev - 1) * 100
    raise NotFound("Use + − × ÷ ^, numbers, instruments and the functions " + ", ".join(sorted(FUNCS)) + ".")


def formula_chart(exprs: List[str], period: str = "5y") -> Dict[str, Any]:
    exprs = [e.strip() for e in exprs if e and e.strip()][:6]
    if not exprs:
        raise NotFound("Enter a formula, e.g. AAPL/SPY or {^TNX}-{FRED:DGS2}.")
    days = PERIODS.get(period, 1826)
    start = date.today() - timedelta(days=days + 400)            # extra history for moving averages / y/y
    parsed = []
    keys: Dict[str, str] = {}
    for e in exprs:
        if re.search(r"__|['\"\[\];\\@`]|\blambda\b", e) or len(e) > 300:
            raise NotFound(f"'{e[:40]}' isn't a formula — use instruments, numbers, + − × ÷ ^ and the listed functions.")
        code, names = _parse(e.replace("×", "*").replace("÷", "/").replace("−", "-").replace("^(", "**("))
        code = re.sub(r"(?<=[\w)])\s*\^\s*(?=[\d(])", "**", code)  # x^2 → x**2 (instrument names keep their ^)
        try:
            tree = ast.parse(code, mode="eval")
        except SyntaxError:
            raise NotFound(f"Couldn't read '{e}'. Wrap symbols with - or = in braces: {{BTC-USD}}, {{EURUSD=X}}.")
        parsed.append((e, tree, names))
        keys.update({k: k for k in names.values()})
    with cf.ThreadPoolExecutor(4) as ex:
        fut = {k: ex.submit(_series, k, start) for k in keys}
        data = {}
        for k, f in fut.items():
            try:
                data[k] = f.result()
            except NotFound as err:
                raise NotFound(f"{k}: {err}")
    lines, cols = [], {}
    for i, (e, tree, names) in enumerate(parsed):
        # each formula on its own calendar: the trading days its instruments share (a weekend-trading coin must not
        # forward-fill a stock across Saturdays), with FRED series carried forward onto those days
        mk = [k for k in names.values() if not k.startswith("FRED:")]
        if mk:
            idx = data[mk[0]].index
            for k in mk[1:]:
                idx = idx.intersection(data[k].index)
        else:
            idx = pd.DatetimeIndex(sorted(set().union(*[set(data[k].index) for k in names.values()])))
        env = {v: (data[k].reindex(data[k].index.union(idx)).ffill().reindex(idx) if k.startswith("FRED:") else data[k].reindex(idx))
               for v, k in names.items()}
        try:
            val = _eval(tree, env)
        except ZeroDivisionError:
            raise NotFound(f"Division by zero in '{e}'.")
        if not isinstance(val, pd.Series):                  # a constant or a scalar (e.g. "2", "mean(x)")
            val = pd.Series(val, index=idx)
        val = val.replace([np.inf, -np.inf], np.nan)
        val = val[val.index >= pd.Timestamp(date.today() - timedelta(days=days))].dropna()
        if val.empty:
            raise NotFound(f"'{e}' has no values over this period.")
        key = f"f{i}"
        cols[key] = val
        last = float(val.iloc[-1])

        def ago(d):
            p = val[val.index <= val.index[-1] - pd.Timedelta(days=d)]
            return float(p.iloc[-1]) if len(p) else None
        lines.append({"key": key, "expr": e, "last": last, "date": val.index[-1].strftime("%Y-%m-%d"), "m1": ago(30), "y1": ago(365),
                      "min": float(val.min()), "max": float(val.max()), "percentile": float((val < last).mean()), "inputs": list(names.values())})
    out = pd.DataFrame(cols)
    step = max(1, len(out) // 1500)
    rows = [{"date": d.strftime("%Y-%m-%d"), **{k: (round(float(v), 6) if pd.notna(v) else None) for k, v in r.items()}}
            for j, (d, r) in enumerate(out.iterrows()) if j % step == 0 or j == len(out) - 1]
    return {"lines": lines, "rows": rows, "period": period, "functions": sorted(FUNCS),
            "note": "Instruments use adjusted daily closes (Yahoo); FRED series as published (forward-filled between releases). "
                    "Series are aligned on calendar dates.", "source": "Yahoo Finance; FRED"}


# ── BDP / BDH: data grid ─────────────────────────────────────────────────────
FIELDS: Dict[str, tuple] = {
    "name": ("Name", lambda i: i.get("shortName") or i.get("longName")), "price": ("Price", lambda i: _f(i.get("regularMarketPrice"))),
    "change_pct": ("Change %", lambda i: _f(i.get("regularMarketChangePercent"))), "currency": ("Currency", lambda i: i.get("currency")),
    "market_cap": ("Market cap", lambda i: _f(i.get("marketCap"))), "pe": ("P/E", lambda i: _f(i.get("trailingPE"))),
    "forward_pe": ("Forward P/E", lambda i: _f(i.get("forwardPE"))), "pb": ("P/B", lambda i: _f(i.get("priceToBook"))),
    "ps": ("P/S", lambda i: _f(i.get("priceToSalesTrailing12Months"))), "ev_ebitda": ("EV/EBITDA", lambda i: _f(i.get("enterpriseToEbitda"))),
    "div_yield": ("Dividend yield %", lambda i: _f(i.get("dividendYield"))), "beta": ("Beta", lambda i: _f(i.get("beta"))),
    "high_52w": ("52w high", lambda i: _f(i.get("fiftyTwoWeekHigh"))), "low_52w": ("52w low", lambda i: _f(i.get("fiftyTwoWeekLow"))),
    "ma50": ("50-day avg", lambda i: _f(i.get("fiftyDayAverage"))), "ma200": ("200-day avg", lambda i: _f(i.get("twoHundredDayAverage"))),
    "volume": ("Avg volume", lambda i: _f(i.get("averageVolume"))), "short_float": ("Short % float", lambda i: (_f(i.get("shortPercentOfFloat")) or 0) * 100 if i.get("shortPercentOfFloat") is not None else None),
    "target": ("Target price", lambda i: _f(i.get("targetMeanPrice"))), "rating": ("Rating", lambda i: i.get("recommendationKey")),
    "eps": ("EPS (TTM)", lambda i: _f(i.get("trailingEps"))), "revenue": ("Revenue", lambda i: _f(i.get("totalRevenue"))),
    "gross_margin": ("Gross margin %", lambda i: (_f(i.get("grossMargins")) or 0) * 100 if i.get("grossMargins") is not None else None),
    "op_margin": ("Operating margin %", lambda i: (_f(i.get("operatingMargins")) or 0) * 100 if i.get("operatingMargins") is not None else None),
    "roe": ("ROE %", lambda i: (_f(i.get("returnOnEquity")) or 0) * 100 if i.get("returnOnEquity") is not None else None),
    "debt_equity": ("Debt/equity", lambda i: _f(i.get("debtToEquity"))), "rev_growth": ("Revenue growth %", lambda i: (_f(i.get("revenueGrowth")) or 0) * 100 if i.get("revenueGrowth") is not None else None),
    "sector": ("Sector", lambda i: i.get("sector")), "industry": ("Industry", lambda i: i.get("industry")), "country": ("Country", lambda i: i.get("country")),
    "exchange": ("Exchange", lambda i: i.get("fullExchangeName") or i.get("exchange")), "employees": ("Employees", lambda i: _f(i.get("fullTimeEmployees"))),
    "type": ("Type", lambda i: i.get("quoteType")), "expense": ("Expense ratio %", lambda i: _f(i.get("netExpenseRatio"))),
}


def data_grid(symbols: List[str], fields: List[str]) -> Dict[str, Any]:
    syms = [s.strip().upper() for s in symbols if s.strip()][:100]
    flds = [f for f in fields if f in FIELDS] or ["name", "price", "change_pct", "market_cap", "pe"]
    if not syms:
        raise NotFound("Add some symbols.")

    def one(s):
        try:
            i = _info(s)
            return {"symbol": s, **{f: FIELDS[f][1](i) for f in flds}}
        except Exception as e:
            return {"symbol": s, "error": str(e)[:80]}
    with cf.ThreadPoolExecutor(6) as ex:
        rows = list(ex.map(one, syms))
    return {"fields": [{"key": f, "label": FIELDS[f][0]} for f in flds], "rows": rows,
            "catalogue": [{"key": k, "label": v[0]} for k, v in FIELDS.items()], "source": "Yahoo Finance"}


def history_grid(symbols: List[str], period: str = "1y", interval: str = "1d", field: str = "close") -> Dict[str, Any]:
    syms = [s.strip().upper() for s in symbols if s.strip()][:50]
    if not syms:
        raise NotFound("Add some symbols.")
    if interval not in ("1d", "1wk", "1mo") or period not in ("1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "max"):
        raise NotFound("period 1mo…max, interval 1d/1wk/1mo")
    df = yahoo_download(syms, period=period, interval=interval, auto_adjust=field in ("close", "return"), group_by="ticker", threads=True)
    cols = {}
    for s in syms:
        try:
            sub = df[s] if isinstance(df.columns, pd.MultiIndex) else df
            c = sub["Volume" if field == "volume" else "Close"].dropna()
            cols[s] = c.pct_change() * 100 if field == "return" else c
        except Exception:
            continue
    if not cols:
        raise NotFound("No history for those symbols.")
    out = pd.DataFrame(cols)
    out.index = pd.to_datetime(out.index).tz_localize(None)
    rows = [{"date": d.strftime("%Y-%m-%d"), **{k: (round(float(v), 6) if pd.notna(v) else None) for k, v in r.items()}} for d, r in out.iterrows()]
    return {"symbols": list(cols), "missing": [s for s in syms if s not in cols], "field": field, "rows": rows[::-1],
            "note": "Close = dividend- and split-adjusted; return = daily % change of the adjusted close.", "source": "Yahoo Finance"}


# ── OVDV: implied volatility surface ─────────────────────────────────────────
def _bs_price(S, K, T, r, q, sig, call):
    if sig <= 0 or T <= 0:
        return max(0.0, (S - K) if call else (K - S))
    d1 = (math.log(S / K) + (r - q + 0.5 * sig * sig) * T) / (sig * math.sqrt(T))
    d2 = d1 - sig * math.sqrt(T)
    N = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))
    if call:
        return S * math.exp(-q * T) * N(d1) - K * math.exp(-r * T) * N(d2)
    return K * math.exp(-r * T) * N(-d2) - S * math.exp(-q * T) * N(-d1)


def _implied_vol(price, S, K, T, r, q, call) -> Optional[float]:
    """Black–Scholes implied volatility by bisection (None if the price is below intrinsic or above the bound)."""
    intrinsic = max(0.0, (S * math.exp(-q * T) - K * math.exp(-r * T)) if call else (K * math.exp(-r * T) - S * math.exp(-q * T)))
    if price <= intrinsic + 1e-6 or price >= (S if call else K):
        return None
    lo, hi = 1e-4, 5.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if _bs_price(S, K, T, r, q, mid, call) > price:
            hi = mid
        else:
            lo = mid
    v = (lo + hi) / 2
    return v if 1e-3 < v < 4.9 else None


IV_DIR = Path(__file__).resolve().parents[2] / "data" / "processed" / "iv_history"
MONEYNESS = [0.80, 0.85, 0.90, 0.95, 0.975, 1.0, 1.025, 1.05, 1.10, 1.15, 1.20]


def vol_surface(symbol: str, max_expiries: int = 10) -> Dict[str, Any]:
    from api.marketdata.security import OPTION_ROOT, _tk
    s0 = symbol.strip().upper()
    s = OPTION_ROOT.get(s0, s0)

    def build():
        t = _tk(s)
        exps = list(t.options or [])
        if not exps:
            raise NotFound(f"No listed options for {s0} on Yahoo (options are mainly US-listed).")
        hist = yahoo_call(lambda: t.history(period="1y", auto_adjust=True))
        if hist is None or hist.empty:
            raise NotFound(f"No price history for {s0}.")
        spot = float(hist["Close"].iloc[-1])
        lr = np.log(hist["Close"]).diff().dropna()
        rv20, rv60 = float(lr.iloc[-20:].std() * math.sqrt(252)), float(lr.iloc[-60:].std() * math.sqrt(252))
        today = date.today()
        try:
            rf = (_f(_info("^IRX").get("regularMarketPrice")) or 4.0) / 100       # 13-week T-bill
        except Exception:
            rf = 0.04
        try:
            from api.marketdata.core import div_yield
            dy = div_yield(_info(s0)) or 0.0
        except Exception:
            dy = 0.0
        chosen = [e for e in exps if (date.fromisoformat(e) - today).days >= 5][:max_expiries]
        surface, term, smiles = [], [], []
        for e in chosen:
            try:
                ch = t.option_chain(e)
            except Exception:
                continue
            dte = (date.fromisoformat(e) - today).days
            # out-of-the-money side for each strike (liquid and clean): puts below spot, calls above
            pts = []
            T = max(dte, 0.5) / 365.0
            for side, df in (("put", ch.puts), ("call", ch.calls)):
                for r in df.itertuples():
                    k = float(r.strike)
                    if not ((side == "put" and k <= spot * 1.0) or (side == "call" and k >= spot)) or not (0.6 * spot <= k <= 1.4 * spot):
                        continue
                    bid, ask = float(getattr(r, "bid", 0) or 0), float(getattr(r, "ask", 0) or 0)
                    last = float(getattr(r, "lastPrice", 0) or 0)
                    if bid > 0 and ask > 0 and (ask - bid) / ((ask + bid) / 2) < 0.6:
                        px = (bid + ask) / 2                            # a live two-sided quote
                    elif bid <= 0 and ask <= 0 and last > 0 and float(getattr(r, "volume", 0) or 0) > 0:
                        px = last                                      # market closed: the last trade, if it traded
                    else:
                        continue
                    iv = _implied_vol(px, spot, k, T, rf, dy, side == "call")
                    if iv:
                        pts.append((k / spot, iv))
            if len(pts) < 5:
                continue
            pts.sort()
            m, v = np.array([p[0] for p in pts]), np.array([p[1] for p in pts])
            row = {"expiry": e, "dte": dte}
            for mm in MONEYNESS:
                row[f"{mm:.3f}"] = float(np.interp(mm, m, v)) if m[0] <= mm <= m[-1] else None
            surface.append(row)
            atm = row.get("1.000")
            term.append({"expiry": e, "dte": dte, "atm": atm, "skew": (row["0.900"] - row["1.100"]) if row.get("0.900") and row.get("1.100") else None,
                         "put_wing": row.get("0.900"), "call_wing": row.get("1.100")})
            if len(smiles) < 4:
                smiles.append({"expiry": e, "dte": dte, "points": [{"m": round(float(a), 4), "iv": round(float(b), 4)} for a, b in pts if 0.7 <= a <= 1.3]})
        if not term:
            raise NotFound(f"The option chains for {s0} are too thin to build a surface.")
        # 30-day ATM vol by interpolating the term structure
        tt = [x for x in term if x["atm"]]
        iv30 = float(np.interp(30, [x["dte"] for x in tt], [x["atm"] for x in tt])) if tt else None
        sk = [x for x in term if x["skew"] is not None]
        skew30 = float(np.interp(30, [x["dte"] for x in sk], [x["skew"] for x in sk])) if sk else None
        # keep a daily record so IV rank / percentile build up over time
        hist_rows = []
        try:
            IV_DIR.mkdir(parents=True, exist_ok=True)
            fp = IV_DIR / f"{re.sub(r'[^A-Z0-9]', '_', s0)}.json"
            h = json.loads(fp.read_text()) if fp.exists() else {}
            if iv30:
                h[today.isoformat()] = {"iv30": iv30, "skew30": skew30, "rv20": rv20}
                fp.write_text(json.dumps(h))
            hist_rows = [{"date": k, **v} for k, v in sorted(h.items())]
        except Exception as e:
            logger.info("[ovdv] history: %s", e)
        ivs = [r["iv30"] for r in hist_rows if r.get("iv30")]
        rank = pct = None
        if len(ivs) >= 20 and iv30:
            rank = (iv30 - min(ivs)) / (max(ivs) - min(ivs)) if max(ivs) > min(ivs) else None
            pct = float(np.mean([x < iv30 for x in ivs]))
        contango = term[-1]["atm"] - term[0]["atm"] if term[0]["atm"] and term[-1]["atm"] else None
        return {"symbol": s0, "option_root": s, "spot": spot, "iv30": iv30, "skew30": skew30, "rv20": rv20, "rv60": rv60,
                "vrp": (iv30 - rv20) if iv30 else None, "term": term, "surface": surface, "moneyness": [f"{m:.3f}" for m in MONEYNESS],
                "smiles": smiles, "contango": contango, "history": hist_rows[-260:], "iv_rank": rank, "iv_percentile": pct, "history_days": len(ivs),
                "note": "Implied vols solved here with Black–Scholes from bid/ask midpoints of out-of-the-money options (puts below spot, calls above; "
                        "T-bill rate and dividend yield included), interpolated to fixed moneyness. Skew = "
                        "90% minus 110% moneyness vol. IV rank needs a history: this terminal records one point a day from the first time "
                        "you open a symbol (no free source publishes IV history).", "source": "Yahoo Finance option chains"}
    return _cached(f"ovdv2:{s0}", 900, build)


# ── CDR: exchange hours and holidays ─────────────────────────────────────────
EXCHANGES = [
    # code, name, city, tz, sessions [(open, close)], holiday calendar, weekend days
    ("XNYS", "NYSE / Nasdaq", "New York", "America/New_York", [("09:30", "16:00")], "XNYS", (5, 6)),
    ("XTSE", "Toronto Stock Exchange", "Toronto", "America/Toronto", [("09:30", "16:00")], "XTSE", (5, 6)),
    ("XMEX", "Bolsa Mexicana", "Mexico City", "America/Mexico_City", [("08:30", "15:00")], "XMEX", (5, 6)),
    ("BVMF", "B3", "São Paulo", "America/Sao_Paulo", [("10:00", "17:00")], "BVMF", (5, 6)),
    ("XLON", "London Stock Exchange", "London", "Europe/London", [("08:00", "16:30")], "XLON", (5, 6)),
    ("XETR", "Xetra (Deutsche Börse)", "Frankfurt", "Europe/Berlin", [("09:00", "17:30")], "XETR", (5, 6)),
    ("XPAR", "Euronext Paris", "Paris", "Europe/Paris", [("09:00", "17:30")], "XECB", (5, 6)),
    ("XAMS", "Euronext Amsterdam", "Amsterdam", "Europe/Amsterdam", [("09:00", "17:30")], "XECB", (5, 6)),
    ("XMAD", "Bolsa de Madrid", "Madrid", "Europe/Madrid", [("09:00", "17:30")], "XMAD", (5, 6)),
    ("XSWX", "SIX Swiss Exchange", "Zurich", "Europe/Zurich", [("09:00", "17:30")], "XSWX", (5, 6)),
    ("XJSE", "Johannesburg SE", "Johannesburg", "Africa/Johannesburg", [("09:00", "17:00")], "XJSE", (5, 6)),
    ("XSAU", "Saudi Exchange (Tadawul)", "Riyadh", "Asia/Riyadh", [("10:00", "15:00")], None, (4, 5)),
    ("XNSE", "NSE India", "Mumbai", "Asia/Kolkata", [("09:15", "15:30")], "XNSE", (5, 6)),
    ("XSES", "Singapore Exchange", "Singapore", "Asia/Singapore", [("09:00", "12:00"), ("13:00", "17:00")], "XSES", (5, 6)),
    ("XHKG", "Hong Kong Exchanges", "Hong Kong", "Asia/Hong_Kong", [("09:30", "12:00"), ("13:00", "16:00")], "XHKG", (5, 6)),
    ("XSHG", "Shanghai Stock Exchange", "Shanghai", "Asia/Shanghai", [("09:30", "11:30"), ("13:00", "15:00")], "XSHG", (5, 6)),
    ("XSHE", "Shenzhen Stock Exchange", "Shenzhen", "Asia/Shanghai", [("09:30", "11:30"), ("13:00", "15:00")], "XSHE", (5, 6)),
    ("XTAI", "Taiwan Stock Exchange", "Taipei", "Asia/Taipei", [("09:00", "13:30")], "XTAI", (5, 6)),
    ("XKRX", "Korea Exchange", "Seoul", "Asia/Seoul", [("09:00", "15:30")], "XKRX", (5, 6)),
    ("XJPX", "Japan Exchange (Tokyo)", "Tokyo", "Asia/Tokyo", [("09:00", "11:30"), ("12:30", "15:30")], "XJPX", (5, 6)),
    ("XASX", "ASX", "Sydney", "Australia/Sydney", [("10:00", "16:00")], "XASX", (5, 6)),
    ("XNZE", "NZX", "Wellington", "Pacific/Auckland", [("10:00", "16:45")], "XNZE", (5, 6)),
]


def exchanges() -> Dict[str, Any]:
    import holidays as hol
    now_utc = datetime.now(ZoneInfo("UTC"))
    out = []
    for code, name, city, tzname, sessions, cal, weekend in EXCHANGES:
        tz = ZoneInfo(tzname)
        now = now_utc.astimezone(tz)
        years = [now.year, now.year + 1]
        try:
            hd = hol.financial_holidays(cal, years=years) if cal else {}
        except Exception:
            hd = {}

        def trading_day(d: date) -> bool:
            return d.weekday() not in weekend and d not in hd

        def at(d: date, hm: str) -> datetime:
            h, m = map(int, hm.split(":"))
            return datetime(d.year, d.month, d.day, h, m, tzinfo=tz)
        status, closes_at, next_open = "closed", None, None
        if trading_day(now.date()):
            for i, (o, c) in enumerate(sessions):
                if at(now.date(), o) <= now < at(now.date(), c):
                    status, closes_at = "open", at(now.date(), c)
                    break
                if i + 1 < len(sessions) and at(now.date(), c) <= now < at(now.date(), sessions[i + 1][0]):
                    status, next_open = "lunch break", at(now.date(), sessions[i + 1][0])
                    break
        if status == "closed":
            d = now.date()
            for k in range(0, 15):
                dd = d + timedelta(days=k)
                if trading_day(dd) and at(dd, sessions[0][0]) > now:
                    next_open = at(dd, sessions[0][0])
                    break
        upcoming = sorted((d, n) for d, n in hd.items() if now.date() <= d <= now.date() + timedelta(days=60))
        out.append({"code": code, "name": name, "city": city, "tz": tzname, "local_time": now.strftime("%a %H:%M"),
                    "sessions": [f"{o}–{c}" for o, c in sessions], "status": status,
                    "closes_in_min": int((closes_at - now).total_seconds() // 60) if closes_at else None,
                    "next_open_utc": next_open.astimezone(ZoneInfo("UTC")).isoformat() if next_open else None,
                    "opens_in_min": int((next_open - now).total_seconds() // 60) if next_open else None,
                    "holidays": [{"date": d.isoformat(), "name": n} for d, n in upcoming][:6],
                    "utc_offset_h": now.utcoffset().total_seconds() / 3600 if now.utcoffset() else 0,
                    "holiday_calendar": bool(cal)})
    return {"now_utc": now_utc.isoformat(timespec="minutes"), "exchanges": out,
            "note": "Regular continuous-trading sessions (auctions and extended hours excluded). Holidays from exchange calendars in the "
                    "open-source 'holidays' library; Tadawul trades Sunday–Thursday (its holiday calendar isn't covered).",
            "source": "Exchange schedules; python-holidays financial calendars"}
