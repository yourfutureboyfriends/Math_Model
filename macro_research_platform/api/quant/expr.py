"""
Signal formula language for the Quant Lab.

A strategy's signal is a formula over price data, e.g.

    rank(mom(252, 21)) + rank(-vol(252))          # momentum + low volatility
    sign(mom(21)) + sign(mom(63)) + sign(mom(252)) # multi-horizon trend
    where(close > sma(close, 200), -rsi(2), nan)   # buy dips in an up-trend

Formulas are parsed with Python's `ast` into a whitelist of node types and functions and
evaluated on (dates × symbols) DataFrames — no attribute access, indexing, imports or
arbitrary calls, so a formula cannot run code on the server. Every value is computed from
data up to and including the row's date (rolling windows, shifts); the engine trades on
the next bar, so a formula cannot look ahead.
"""
from __future__ import annotations

import ast
import difflib
import math
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

MAX_LEN = 1000
MAX_NODES = 300
MAX_WINDOW = 2520          # 10 years of trading days


class ExprError(ValueError):
    """A formula the user can fix: message says what and where."""


# ── Function library ─────────────────────────────────────────────────────────
# Each entry: (callable(ctx, *args), signature, description, category)
FUNCS: Dict[str, Dict[str, Any]] = {}


def _fn(name: str, sig: str, desc: str, cat: str):
    def deco(f: Callable):
        FUNCS[name] = {"f": f, "sig": sig, "desc": desc, "cat": cat}
        return f
    return deco


def _win(n: Any, name: str, lo: int = 1) -> int:
    if isinstance(n, (pd.DataFrame, pd.Series)) or not isinstance(n, (int, float)) or not math.isfinite(n):
        raise ExprError(f"{name}(): the window must be a number, e.g. {name}(..., 20)")
    k = int(round(n))
    if k < lo or k > MAX_WINDOW:
        raise ExprError(f"{name}(): window {k} is outside {lo}–{MAX_WINDOW} days")
    return k


def _df(x: Any, ctx: "Ctx") -> pd.DataFrame:
    if isinstance(x, pd.DataFrame):
        return x
    if isinstance(x, (int, float, bool, np.floating)):
        return pd.DataFrame(float(x), index=ctx.close.index, columns=ctx.close.columns)
    raise ExprError("expected a price series or a number")


# Price-based shortcuts
@_fn("ret", "ret(n=1)", "Return over the last n days (close to close).", "Returns & momentum")
def f_ret(ctx, n=1):
    n = _win(n, "ret")
    return ctx.close / ctx.close.shift(n) - 1


@_fn("mom", "mom(n, skip=0)", "Momentum: return from n days ago to `skip` days ago. mom(252, 21) is the classic 12-1 month momentum.", "Returns & momentum")
def f_mom(ctx, n, skip=0):
    n, s = _win(n, "mom"), int(skip)
    if s < 0 or s >= n:
        raise ExprError("mom(n, skip): skip must be between 0 and n-1")
    return ctx.close.shift(s) / ctx.close.shift(n) - 1


@_fn("vol", "vol(n=63)", "Annualised volatility of daily returns over n days.", "Risk")
def f_vol(ctx, n=63):
    n = _win(n, "vol", 2)
    lr = np.log(ctx.close / ctx.close.shift(1))
    return lr.rolling(n, min_periods=max(2, int(n * 0.8))).std() * math.sqrt(252)


@_fn("drawdown", "drawdown(n=252)", "Distance below the highest close of the last n days (0 = at the high, -0.2 = 20% below).", "Risk")
def f_drawdown(ctx, n=252):
    n = _win(n, "drawdown")
    return ctx.close / ctx.close.rolling(n, min_periods=1).max() - 1


@_fn("beta", "beta(n=252)", "Rolling beta of each asset's daily returns to the benchmark (mkt).", "Risk")
def f_beta(ctx, n=252):
    n = _win(n, "beta", 20)
    r = ctx.close.pct_change(fill_method=None)
    m = ctx.mkt_series.pct_change(fill_method=None)
    cov = r.rolling(n, min_periods=int(n * 0.8)).cov(m)
    var = m.rolling(n, min_periods=int(n * 0.8)).var()
    return cov.div(var, axis=0)


@_fn("rsi", "rsi(n=14)", "Wilder's Relative Strength Index (0–100). Below 30 = oversold, above 70 = overbought.", "Oscillators")
def f_rsi(ctx, n=14):
    n = _win(n, "rsi", 2)
    d = ctx.close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = up / dn.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.where(dn != 0, 100.0).where(up.notna())


@_fn("atr", "atr(n=14)", "Average True Range — the typical daily price range (uses high/low when available).", "Oscillators")
def f_atr(ctx, n=14):
    n = _win(n, "atr", 2)
    pc = ctx.close.shift(1)
    if ctx.high is not None and ctx.low is not None:
        tr = pd.concat([(ctx.high - ctx.low), (ctx.high - pc).abs(), (ctx.low - pc).abs()]).groupby(level=0).max()
        tr = tr.reindex(ctx.close.index)
    else:
        tr = (ctx.close - pc).abs()
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


# Rolling transforms
@_fn("sma", "sma(x, n)", "Simple moving average of x over n days.", "Smoothing")
def f_sma(ctx, x, n):
    n = _win(n, "sma")
    return _df(x, ctx).rolling(n, min_periods=n).mean()


@_fn("ema", "ema(x, n)", "Exponential moving average of x (span n).", "Smoothing")
def f_ema(ctx, x, n):
    n = _win(n, "ema")
    return _df(x, ctx).ewm(span=n, adjust=False, min_periods=n).mean()


@_fn("std", "std(x, n)", "Rolling standard deviation of x over n days.", "Smoothing")
def f_std(ctx, x, n):
    n = _win(n, "std", 2)
    return _df(x, ctx).rolling(n, min_periods=n).std()


@_fn("sum", "sum(x, n)", "Rolling sum of x over n days.", "Smoothing")
def f_sum(ctx, x, n):
    n = _win(n, "sum")
    return _df(x, ctx).rolling(n, min_periods=n).sum()


@_fn("highest", "highest(x, n)", "Highest value of x over the last n days (e.g. a breakout level).", "Smoothing")
def f_highest(ctx, x, n):
    n = _win(n, "highest")
    return _df(x, ctx).rolling(n, min_periods=n).max()


@_fn("lowest", "lowest(x, n)", "Lowest value of x over the last n days.", "Smoothing")
def f_lowest(ctx, x, n):
    n = _win(n, "lowest")
    return _df(x, ctx).rolling(n, min_periods=n).min()


@_fn("zscore", "zscore(x, n)", "How unusual x is vs its own last n days, in standard deviations.", "Smoothing")
def f_zscore(ctx, x, n):
    n = _win(n, "zscore", 5)
    x = _df(x, ctx)
    m, s = x.rolling(n, min_periods=n).mean(), x.rolling(n, min_periods=n).std()
    return (x - m) / s.replace(0, np.nan)


@_fn("delay", "delay(x, n)", "The value of x n days ago.", "Smoothing")
def f_delay(ctx, x, n):
    return _df(x, ctx).shift(_win(n, "delay"))


@_fn("delta", "delta(x, n)", "Change in x over n days.", "Smoothing")
def f_delta(ctx, x, n):
    x = _df(x, ctx)
    return x - x.shift(_win(n, "delta"))


@_fn("corr", "corr(x, y, n)", "Rolling correlation between x and y over n days.", "Smoothing")
def f_corr(ctx, x, y, n):
    n = _win(n, "corr", 5)
    x, y = _df(x, ctx), _df(y, ctx)
    return x.rolling(n, min_periods=n).corr(y)


# Cross-sectional (across the universe on each date)
@_fn("rank", "rank(x)", "Percentile rank of x across the universe each day (0 = lowest, 1 = highest).", "Cross-sectional")
def f_rank(ctx, x):
    return _df(x, ctx).rank(axis=1, pct=True)


@_fn("cs_zscore", "cs_zscore(x)", "x standardised across the universe each day.", "Cross-sectional")
def f_cs_zscore(ctx, x):
    x = _df(x, ctx)
    return x.sub(x.mean(axis=1), axis=0).div(x.std(axis=1).replace(0, np.nan), axis=0)


@_fn("demean", "demean(x)", "x minus its cross-sectional average each day (relative strength).", "Cross-sectional")
def f_demean(ctx, x):
    x = _df(x, ctx)
    return x.sub(x.mean(axis=1), axis=0)


# Element-wise math
@_fn("abs", "abs(x)", "Absolute value.", "Math")
def f_abs(ctx, x):
    return abs(x)


@_fn("sign", "sign(x)", "+1 if positive, -1 if negative, 0 if zero.", "Math")
def f_sign(ctx, x):
    return np.sign(_df(x, ctx))


@_fn("log", "log(x)", "Natural log (blank where x ≤ 0).", "Math")
def f_log(ctx, x):
    x = _df(x, ctx)
    return np.log(x.where(x > 0))


@_fn("sqrt", "sqrt(x)", "Square root (blank where x < 0).", "Math")
def f_sqrt(ctx, x):
    x = _df(x, ctx)
    return np.sqrt(x.where(x >= 0))


@_fn("clip", "clip(x, lo, hi)", "Limit x to the range [lo, hi].", "Math")
def f_clip(ctx, x, lo, hi):
    return _df(x, ctx).clip(lower=lo, upper=hi, axis=None) if not isinstance(lo, pd.DataFrame) else _df(x, ctx).clip(lo, hi)


@_fn("max", "max(a, b)", "Larger of a and b, element by element.", "Math")
def f_max(ctx, a, b):
    return np.fmax(_df(a, ctx), _df(b, ctx))


@_fn("min", "min(a, b)", "Smaller of a and b, element by element.", "Math")
def f_min(ctx, a, b):
    return np.fmin(_df(a, ctx), _df(b, ctx))


@_fn("where", "where(cond, a, b)", "a where cond is true, else b. Use nan for 'no position'.", "Logic")
def f_where(ctx, cond, a, b):
    c = _df(cond, ctx)
    return _df(a, ctx).where(c.fillna(0) > 0, _df(b, ctx))


VARIABLES: Dict[str, str] = {
    "close": "Adjusted closing price.",
    "open": "Adjusted opening price.",
    "high": "Adjusted daily high.",
    "low": "Adjusted daily low.",
    "volume": "Shares traded.",
    "mkt": "The benchmark's close (default SPY), the same for every asset — e.g. a market filter mkt > sma(mkt, 200).",
    "nan": "Missing value — means 'no position' in a signal.",
}

_BINOPS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
           ast.Div: lambda a, b: a / b, ast.Pow: lambda a, b: a ** b, ast.Mod: lambda a, b: a % b}
_CMPOPS = {ast.Gt: lambda a, b: a > b, ast.GtE: lambda a, b: a >= b, ast.Lt: lambda a, b: a < b,
           ast.LtE: lambda a, b: a <= b, ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b}
_ALLOWED = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Compare, ast.BoolOp, ast.Call, ast.Name,
            ast.Constant, ast.Load, ast.And, ast.Or, ast.Not, ast.USub, ast.UAdd, ast.Invert,
            ast.BitAnd, ast.BitOr, *(_BINOPS), *(_CMPOPS))


class Ctx:
    def __init__(self, close: pd.DataFrame, open_: Optional[pd.DataFrame] = None, high: Optional[pd.DataFrame] = None,
                 low: Optional[pd.DataFrame] = None, volume: Optional[pd.DataFrame] = None,
                 mkt: Optional[pd.Series] = None):
        self.close, self.open, self.high, self.low, self.volume = close, open_, high, low, volume
        self.mkt_series = mkt if mkt is not None else close.mean(axis=1)

    def var(self, name: str):
        if name == "nan":
            return float("nan")
        if name == "mkt":
            return pd.DataFrame(np.repeat(self.mkt_series.to_numpy()[:, None], self.close.shape[1], axis=1),
                                index=self.close.index, columns=self.close.columns)
        v = {"close": self.close, "open": self.open, "high": self.high, "low": self.low, "volume": self.volume}[name]
        if v is None:
            raise ExprError(f"'{name}' data is not available for this universe")
        return v


def _suggest(name: str, pool) -> str:
    m = difflib.get_close_matches(name, list(pool), n=1)
    return f" Did you mean '{m[0]}'?" if m else ""


def parse(text: str) -> ast.Expression:
    """Parse and validate a formula (structure only). Raises ExprError with a helpful message."""
    if not isinstance(text, str) or not text.strip():
        raise ExprError("The formula is empty.")
    if len(text) > MAX_LEN:
        raise ExprError(f"The formula is too long (max {MAX_LEN} characters).")
    src = text.strip().replace("\n", " ")
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError as e:
        col = (e.offset or 1) - 1
        raise ExprError(f"Syntax error at character {col + 1}: {src[max(0, col - 15):col + 15]!r}") from None
    n = 0
    for node in ast.walk(tree):
        n += 1
        if not isinstance(node, _ALLOWED):
            raise ExprError(f"'{type(node).__name__}' is not allowed in a formula — use numbers, variables, operators and the listed functions.")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ExprError("Only the listed functions can be called.")
            if node.func.id not in FUNCS:
                raise ExprError(f"Unknown function '{node.func.id}'.{_suggest(node.func.id, FUNCS)}")
            if node.keywords:
                raise ExprError(f"{node.func.id}(): pass arguments by position, e.g. mom(252, 21)")
        elif isinstance(node, ast.Name) and node.id not in VARIABLES and node.id not in FUNCS:
            raise ExprError(f"Unknown name '{node.id}'.{_suggest(node.id, list(VARIABLES) + list(FUNCS))}")
        elif isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)) or isinstance(node, ast.Constant) and isinstance(node.value, bool):
            raise ExprError("Only numbers are allowed as constants.")
    if n > MAX_NODES:
        raise ExprError(f"The formula is too complex (max {MAX_NODES} parts).")
    return tree


def _eval(node: ast.AST, ctx: Ctx):
    if isinstance(node, ast.Expression):
        return _eval(node.body, ctx)
    if isinstance(node, ast.Constant):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id in FUNCS:
            raise ExprError(f"'{node.id}' is a function — call it, e.g. {FUNCS[node.id]['sig']}")
        return ctx.var(node.id)
    if isinstance(node, ast.UnaryOp):
        v = _eval(node.operand, ctx)
        if isinstance(node.op, ast.USub):
            return -v
        if isinstance(node.op, ast.UAdd):
            return v
        return (_df(v, ctx).fillna(0) <= 0).astype(float)          # not / ~
    if isinstance(node, ast.BinOp):
        a, b = _eval(node.left, ctx), _eval(node.right, ctx)
        if isinstance(node.op, (ast.BitAnd, ast.BitOr)):
            a, b = _df(a, ctx).fillna(0) > 0, _df(b, ctx).fillna(0) > 0
            return ((a & b) if isinstance(node.op, ast.BitAnd) else (a | b)).astype(float)
        with np.errstate(all="ignore"):
            return _BINOPS[type(node.op)](a, b)
    if isinstance(node, ast.BoolOp):
        vals = [_df(_eval(v, ctx), ctx).fillna(0) > 0 for v in node.values]
        out = vals[0]
        for v in vals[1:]:
            out = (out & v) if isinstance(node.op, ast.And) else (out | v)
        return out.astype(float)
    if isinstance(node, ast.Compare):
        left = _eval(node.left, ctx)
        result = None
        for op, comp in zip(node.ops, node.comparators):
            right = _eval(comp, ctx)
            l_df, r_df = (_df(left, ctx), _df(right, ctx))
            c = _CMPOPS[type(op)](l_df, r_df) & l_df.notna() & r_df.notna()
            result = c if result is None else (result & c)
            left = right
        return result.astype(float)
    if isinstance(node, ast.Call):
        spec = FUNCS[node.func.id]
        args = [_eval(a, ctx) for a in node.args]
        try:
            return spec["f"](ctx, *args)
        except ExprError:
            raise
        except TypeError:
            raise ExprError(f"Wrong arguments for {node.func.id}: use {spec['sig']}") from None
    raise ExprError(f"Unsupported element: {type(node).__name__}")


def evaluate(text: str, ctx: Ctx) -> pd.DataFrame:
    """Evaluate a formula to a (dates × symbols) DataFrame; ±inf become missing."""
    out = _eval(parse(text), ctx)
    out = _df(out, ctx)
    return out.replace([np.inf, -np.inf], np.nan)


def catalogue() -> Dict[str, Any]:
    """Functions and variables for the UI's formula palette."""
    cats: Dict[str, List[Dict[str, str]]] = {}
    for name, f in FUNCS.items():
        cats.setdefault(f["cat"], []).append({"name": name, "sig": f["sig"], "desc": f["desc"]})
    return {"functions": cats, "variables": [{"name": k, "desc": v} for k, v in VARIABLES.items()],
            "operators": "+ - * / ** % · comparisons > >= < <= == != (give 1 or 0) · & | ~ (and, or, not)"}
