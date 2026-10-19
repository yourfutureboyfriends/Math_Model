"""
Code Lab engine — one file, numpy + pandas only, so the *same* code runs on the server and in the
browser (Pyodide). A strategy is plain Python:

    UNIVERSE = ["SPY", "TLT", "GLD"]          # tickers, any listing (VOD.L, 7203.T, 0700.HK …); ≤ UNIVERSE_LIMIT
                                              # run in the browser, up to LARGE_UNIVERSE_LIMIT as a server job
    TRADABLE_UNIVERSE = "GLOBAL"              # optional: trade a named universe instead (see codeserver)
    ACCOUNT_CURRENCY = "EUR"                  # optional (default USD): the account's currency — prices, NAV,
                                              # costs and cash interest are all in it
    FX_HEDGE = 1.0                            # optional (default 0): share of foreign-currency exposure hedged
    FUNDAMENTALS = ["book_to_price", "roe"]   # optional (or True): point-in-time SEC fundamentals in data.fund
    OPTIONS = [{"underlying": "SPY", "type": "put", "moneyness": 0.95}]   # optional: synthetic listed options,
                                              # each a column named like "SPY_P95_1M" (see api/quant/options.py)
        # An option column's weight is the UNDERLYING NOTIONAL it controls, as a fraction of NAV (-1.0 = write
        # options on 100% of NAV), converted to contracts at the execution price; data.opt has delta, iv, ...
    START = "2005-01-01"                      # optional
    PARAMS = {"lookback": [126, 252]}         # optional: grid for walk-forward optimisation
    HOLDOUT = "2023-01-01"                    # optional: data from here never takes part in selection

    def strategy(data, lookback=252):
        # data.close / open / high / low / volume: DataFrames (dates × tickers), adjusted prices
        # (prices converted to the account currency at as-of FX; data.account_currency names it)
        # data.rf: the account currency's daily cash rate (Series); data.vix: VIX close (Series)
        # data.instruments[t]: country, currency, sector, region, market_class; data.info: the same as a DataFrame
        # return target weights (dates × tickers): +long / −short, fraction of NAV.
        # A row with values is a decision taken at that day's close and traded at the next observed
        # open; a row left blank (all NaN) means "no decision — hold and let positions drift".
        ...

Costs (all charged, all configurable — defaults are research-calibrated):
  commission     per side, bps of traded notional (default 0.35 bp ≈ $0.0035/share at $100)
  spread         half the bid-ask spread per asset and day from its volatility and dollar volume
                 (see half_spread_bps), never below half a cent
  market impact  square-root law calibrated on $1.7tn of live institutional trades (Frazzini,
                 Israel & Moskowitz 2018, US): 11.2 bp × √(% of 63-day dollar volume traded)
  SEC fee        0.278 bp on sales (Section 31 rate)
  borrow         annual fee on short notional (default 0.30% general collateral)
  financing      cash earns the account currency's short rate (US T-bills for USD; api/quant/rates.py);
                 borrowing (gross long > 100%) pays that rate + spread (default 1.0%)
  venue taxes    stamp duties / FTTs by listing country (api/quant/instruments.py)
  FX conversion  2 bp of traded value on trades in a listing whose currency differs from the account's
Accounting: one self-financing account — units and cash, NAV = Σ units × mark + cash, costs settle
into cash. Fills only at observed opens of assets that traded; unfillable orders stay pending; stale
marks are flagged; explicitly dated delistings settle at their last observed mark; missing tails stay stale. Returns are total returns (Yahoo
adjusted prices include dividends). Units and assumptions: COST_SCHEMA.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

try:                                           # the QuantConnect-style API (api/quant/qcalgo.py; beside this file in Pyodide)
    from api.quant import qcalgo as _qc
except ImportError:                            # pragma: no cover — the browser engine
    try:
        import qcalgo as _qc
    except ImportError:
        _qc = None

ENGINE_VERSION = "2026.10-ledger.6"   # .6: walk-forward grid rows from each set's own account (no re-runs); share orders
UNIVERSE_LIMIT = 80                   # one capability limit, shared by the loader, the sandbox and the UI
LARGE_UNIVERSE_LIMIT = 4000           # server jobs (TRADABLE_UNIVERSE or a long UNIVERSE list) — one global cross-section
TRADING_DAYS = 252
COST_SCHEMA_VERSION = "2026.10"
COST_SCHEMA: Dict[str, Dict[str, str]] = {
    "capital": {"unit": "account currency (ACCOUNT_CURRENCY, default USD)", "meaning": "starting capital; impact depends on size"},
    "commission_bps": {"unit": "bp per side of traded notional", "meaning": "broker commission"},
    "spread_mult": {"unit": "multiplier (×), not bp", "meaning": "scales the modelled half-spread"},
    "impact_coef_bps": {"unit": "bp × √(% of 63-day traded value)", "meaning": "square-root market impact"},
    "sec_fee_bps": {"unit": "bp of sale notional", "meaning": "SEC Section 31 fee (US listings only)"},
    "venue_taxes": {"unit": "bp of traded value, per instrument", "meaning": "stamp duties / FTTs by listing country (api/quant/instruments.py)"},
    "fx_cost_bps": {"unit": "bp of traded value, cross-currency trades only", "meaning": "FX conversion cost when a listing's currency differs from the account's (broker fee + dealing spread)"},
    "fx_hedge": {"unit": "fraction (0–1) of foreign-currency exposure", "meaning": "hedged with daily-settled forwards: removes that share of each currency's moves and earns/pays the interest differential (account − foreign rate); currencies with no free rate history stay unhedged"},
    "fx_hedge_cost_bps": {"unit": "bp per year of hedged notional", "meaning": "forward roll dealing costs"},
    "dividend_wht": {"unit": "1 = on, 0 = off", "meaning": "tax withheld at source on dividends of listings in another currency than the account's (api/quant/market_rules.py)"},
    "wht_treaty_cap": {"unit": "decimal rate", "meaning": "withholding is the listing country's statutory non-resident rate capped at this treaty rate (1 = no treaty relief)"},
    "board_lots": {"unit": "1 = on, 0 = off", "meaning": "orders rounded to whole board lots (JP 100, HK per stock, TW 1,000 …), sized at `capital`"},
    "crypto_fee_bps": {"unit": "bp of traded value", "meaning": "crypto exchange taker fee (Coinbase Advanced / Kraken / Binance ≈ 10–40 bp)"},
    "commission_per_share": {"unit": "account currency per share", "meaning": "broker per-share commission (e.g. IBKR Pro Fixed $0.005)"},
    "commission_min": {"unit": "account currency per order", "meaning": "minimum commission per order (e.g. IBKR $1)"},
    "commission_max_pct": {"unit": "fraction of the order's value (0 = no cap)", "meaning": "commission cap (e.g. IBKR 1%)"},
    "exec_price": {"unit": "0 = next open, 1 = next day's VWAP (≈ (O+H+L+C)/4), 2 = next close (market-on-close)", "meaning": "where orders decided at a close are filled"},
    "max_participation": {"unit": "fraction of 63-day average daily traded value, per asset per day (0 = no cap)", "meaning": "volume limit: larger orders fill over several days (the rest stays pending)"},
    "borrow_tiers": {"unit": "1 = on, 0 = off", "meaning": "stock-borrow fee rises for less liquid names: ≥$100m/day the base fee, $20–100m 0.75%, $5–20m 2%, under $5m 5% a year"},
    "maintenance_margin": {"unit": "fraction of gross stock value (0.25 = Reg-T)", "meaning": "if NAV falls below this × gross stock value + option margin, the broker cuts every position (margin call)"},
    "option_margin": {"unit": "fraction of underlying notional", "meaning": "margin on written options (≈ CBOE 15–20% of underlying)"},
    "borrow_fee": {"unit": "annual decimal rate on short market value", "meaning": "stock-borrow fee"},
    "financing_spread": {"unit": "annual decimal rate over the cash rate", "meaning": "margin interest on negative cash"},
    "cash_spread": {"unit": "annual decimal rate under the cash rate", "meaning": "positive cash earns the account currency's short rate − this (0 = full rate)"},
    "no_trade_band": {"unit": "fraction of NAV", "meaning": "skip adjustments smaller than this to positions that stay open (entries and exits always trade)"},
    "max_gross": {"unit": "multiple of NAV", "meaning": "cap on gross target exposure"},
    "delist_haircut": {"unit": "fraction", "meaning": "loss applied when a held listing ends (settled at last close × (1 − this))"},
}
DEFAULT_COSTS: Dict[str, float] = {
    "capital": 1_000_000.0,
    "commission_bps": 0.35,
    "spread_mult": 1.0,
    "impact_coef_bps": 11.21,
    "sec_fee_bps": 0.278,
    "fx_cost_bps": 2.0,
    "fx_hedge": 0.0,
    "fx_hedge_cost_bps": 15.0,
    "dividend_wht": 1.0,
    "wht_treaty_cap": 0.15,
    "board_lots": 1.0,
    "exec_price": 0.0,
    "crypto_fee_bps": 10.0,
    "commission_per_share": 0.0,
    "commission_min": 0.0,
    "commission_max_pct": 0.0,
    "max_participation": 0.10,
    "borrow_tiers": 1.0,
    "maintenance_margin": 0.25,
    "option_margin": 0.15,
    "borrow_fee": 0.003,
    "financing_spread": 0.010,
    "cash_spread": 0.0,
    "no_trade_band": 0.0025,
    "max_gross": 4.0,
    "delist_haircut": 0.0,
}


class Data:
    """What a strategy sees. All frames share one date index; prices are split/dividend adjusted
    (total return). `close` is the *valuation mark*: the last observed close, carried forward inside each
    listing's history; `observed` says which days really have a bar. `open` holds only observed opens —
    it is the execution price, and NaN means no fill is possible that day."""

    def __init__(self, close, open_, high, low, volume, rf=None, vix=None, observed=None, rf_known=None,
                 provenance: Optional[Dict[str, Any]] = None, instruments: Optional[Dict[str, Dict[str, Any]]] = None,
                 account_currency: str = "USD", usd_per_unit=None, tick_bps=None, lot_value=None, div_yield=None,
                 fx=None, rf_ccy=None, settle=None, options=None, fundamentals=None, share_px=None):
        self.close, self.high, self.low = close, high, low
        idx = close.index
        self.observed = (observed.reindex(index=idx, columns=close.columns).fillna(False).astype(bool)
                         if observed is not None else close.notna())
        self.open = open_.reindex(index=idx, columns=close.columns).where(lambda x: x > 0)
        self.volume = volume.reindex(index=idx, columns=close.columns)
        self.rf_known = (rf is not None) if rf_known is None else bool(rf_known)
        self.rf = rf.reindex(idx).ffill().fillna(0.0) if rf is not None else pd.Series(0.0, index=idx)
        self.vix = vix.reindex(idx).ffill() if vix is not None else pd.Series(np.nan, index=idx)
        self.tickers = list(close.columns)
        self.provenance = dict(provenance or {})
        # per-instrument metadata: prices arrive already converted to the account currency; taxes in bp
        self.instruments = {c: dict((instruments or {}).get(c) or {"country": "US", "currency": "USD", "sec_fee": True})
                            for c in self.tickers}
        self.account_currency = account_currency
        # USD per unit of the account currency (as of each close) — scales the USD-calibrated spread model
        upu = 1.0 if usd_per_unit is None else usd_per_unit
        self.usd_per_unit = (upu.reindex(idx).ffill().bfill() if isinstance(upu, pd.Series)
                             else pd.Series(upu, index=idx, dtype=float)).fillna(1.0)
        self.members = None                                    # point-in-time index membership, when the universe has one
        # market microstructure and tax inputs (optional; absent = not modelled for that run):
        #   tick_bps   half the minimum tick in bp of price (floors the spread model)
        #   lot_value  account-currency value of one board lot (NaN = single shares)
        #   div_yield  cash dividend ÷ previous close on ex-dates (0 elsewhere) — for withholding tax
        #   fx         account units per 1 unit of each listing currency (as of each close) — for hedging
        #   rf_ccy     daily short rate of each listing currency (NaN = unknown) — the hedge's carry
        frame = lambda x: None if x is None else x.reindex(index=idx, columns=close.columns)
        self.tick_bps, self.lot_value, self.div_yield = frame(tick_bps), frame(lot_value), frame(div_yield)
        self.share_px = frame(share_px)                        # traded share price, account currency (per-share fees)
        self.fx = fx.reindex(idx) if fx is not None else None
        self.rf_ccy = rf_ccy.reindex(idx) if rf_ccy is not None else None
        # synthetic options (OPTIONS = [...]): `settle` holds each expiring contract's settlement value on its expiry
        # day; `opt` gives per-option analytics (dates × option names): delta (per share), elasticity (% move per 1%
        # of the underlying), notional (underlying value per 1 of premium), iv, strike, dte, roll (expiry days)
        self.settle = frame(settle)
        self.opt = {k: v.reindex(idx) for k, v in (options or {}).items()}
        self.option_names = list(self.opt["notional"].columns) if "notional" in self.opt else []
        # point-in-time fundamentals (FUNDAMENTALS = [...]): data.fund["book_to_price"] etc., dates × tickers
        self.fund = {k: v.reindex(index=idx, columns=close.columns) for k, v in (fundamentals or {}).items()}

    def __getattr__(self, name: str):
        # only reached for attributes that do not exist: explain live-trading fields instead of a bare AttributeError
        if name in LIVE_FIELDS:
            raise AttributeError(f"data.{name} does not exist in a backtest. " + LIVE_HINT.format(field=name))
        raise AttributeError(name)

    def truncate(self, n: int) -> "Data":
        """The same data as it stood after the first n rows — for checking that decisions never use later rows."""
        cut = lambda x: None if x is None else x.iloc[:n]
        d = Data(self.close.iloc[:n], self.open.iloc[:n], self.high.iloc[:n], self.low.iloc[:n], self.volume.iloc[:n],
                 rf=self.rf.iloc[:n] if self.rf_known else None, vix=self.vix.iloc[:n], observed=self.observed.iloc[:n],
                 rf_known=self.rf_known, provenance=self.provenance, instruments=self.instruments,
                 account_currency=self.account_currency, usd_per_unit=self.usd_per_unit.iloc[:n],
                 tick_bps=cut(self.tick_bps), lot_value=cut(self.lot_value), div_yield=cut(self.div_yield),
                 fx=cut(self.fx), rf_ccy=cut(self.rf_ccy), settle=cut(self.settle), share_px=cut(self.share_px),
                 options={k: v.iloc[:n] for k, v in self.opt.items()} or None,
                 fundamentals={k: v.iloc[:n] for k, v in self.fund.items()} or None)
        d.members = self.members.iloc[:n] if getattr(self, "members", None) is not None else None
        return d

    @property
    def info(self) -> pd.DataFrame:
        """Instrument metadata as a DataFrame (tickers × country, currency, sector, region, market_class, …):
        e.g. data.info["sector"] to neutralise by sector, data.info["currency"] to group by currency."""
        return pd.DataFrame.from_dict(self.instruments, orient="index").reindex(self.tickers)

    def returns(self) -> pd.DataFrame:
        return self.close.pct_change(fill_method=None)


# ── Helpers for strategy code ───────────────────────────────────────────────
def ewma_vol(close: pd.DataFrame, halflife: int = 42) -> pd.DataFrame:
    """Annualised exponentially weighted volatility of daily returns."""
    r = close.pct_change(fill_method=None)
    return r.ewm(halflife=halflife, min_periods=max(20, halflife)).std() * math.sqrt(TRADING_DAYS)


def momentum(close: pd.DataFrame, n: int, skip: int = 0) -> pd.DataFrame:
    return close.shift(skip) / close.shift(n) - 1


def on_rolls(weights: pd.DataFrame, data: "Data", name: str) -> pd.DataFrame:
    """Decide only on option `name`'s expiry days (the new contract is struck at that close and traded at the next
    open); other rows blank = hold."""
    roll = data.opt["roll"][name].reindex(weights.index).fillna(False).astype(bool)
    return weights.where(roll, np.nan, axis=0)


def hold_monthly(weights: pd.DataFrame) -> pd.DataFrame:
    """Decide once a month, on the first trading day observed in each month (knowable that day — no future
    rows needed), traded at the next open. Other rows are left blank (NaN) = no decision: hold and drift."""
    return _hold(weights, "M")


def hold_weekly(weights: pd.DataFrame) -> pd.DataFrame:
    """As hold_monthly, on the first trading day observed in each week."""
    return _hold(weights, "W")


def _hold(weights: pd.DataFrame, freq: str) -> pd.DataFrame:
    w = weights.copy()
    per = w.index.to_period(freq)
    first = np.r_[True, np.asarray(per[1:] != per[:-1])] if len(per) else np.zeros(0, bool)
    w.loc[~first] = np.nan
    return w


# ── Indicator library (vectorised over every ticker; causal: each value uses data up to that row) ──
def sma(x: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    """Simple moving average."""
    return x.rolling(n, min_periods=n).mean()


def ema(x: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    """Exponential moving average (span n)."""
    return x.ewm(span=n, min_periods=n, adjust=False).mean()


def wma(x: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    """Linearly weighted moving average."""
    w = np.arange(1, n + 1, dtype=float)
    return x.rolling(n, min_periods=n).apply(lambda a: float(np.dot(a, w) / w.sum()), raw=True)


def hma(x: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    """Hull moving average."""
    return wma(2 * wma(x, max(n // 2, 1)) - wma(x, n), max(int(math.sqrt(n)), 1))


def rsi(x: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    """Relative strength index (Wilder), 0–100."""
    d = x.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def macd(x: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, pd.DataFrame]:
    """MACD line, signal line and histogram."""
    line = ema(x, fast) - ema(x, slow)
    sig = line.ewm(span=signal, min_periods=signal, adjust=False).mean()
    return {"macd": line, "signal": sig, "hist": line - sig}


def bollinger(x: pd.DataFrame, n: int = 20, k: float = 2.0) -> Dict[str, pd.DataFrame]:
    """Bollinger bands: middle, upper, lower, %b and bandwidth."""
    mid = sma(x, n)
    sd = x.rolling(n, min_periods=n).std()
    up, lo = mid + k * sd, mid - k * sd
    return {"middle": mid, "upper": up, "lower": lo, "pct_b": (x - lo) / (up - lo), "width": (up - lo) / mid}


def true_range(data: "Data") -> pd.DataFrame:
    pc = data.close.shift(1)
    return np.fmax(np.fmax(data.high - data.low, (data.high - pc).abs()), (data.low - pc).abs())


def atr(data: "Data", n: int = 14) -> pd.DataFrame:
    """Average true range (Wilder)."""
    return true_range(data).ewm(alpha=1 / n, min_periods=n, adjust=False).mean()


def adx(data: "Data", n: int = 14) -> pd.DataFrame:
    """Average directional index (trend strength, 0–100)."""
    up, dn = data.high.diff(), -data.low.diff()
    plus = up.where((up > dn) & (up > 0), 0.0)
    minus = dn.where((dn > up) & (dn > 0), 0.0)
    tr = atr(data, n)
    pdi = 100 * plus.ewm(alpha=1 / n, adjust=False).mean() / tr
    mdi = 100 * minus.ewm(alpha=1 / n, adjust=False).mean() / tr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, min_periods=n, adjust=False).mean()


def stochastic(data: "Data", n: int = 14, d: int = 3) -> Dict[str, pd.DataFrame]:
    """Stochastic oscillator %K and %D (0–100)."""
    lo, hi = data.low.rolling(n, min_periods=n).min(), data.high.rolling(n, min_periods=n).max()
    k = 100 * (data.close - lo) / (hi - lo).replace(0, np.nan)
    return {"k": k, "d": k.rolling(d, min_periods=d).mean()}


def williams_r(data: "Data", n: int = 14) -> pd.DataFrame:
    """Williams %R (−100–0)."""
    lo, hi = data.low.rolling(n, min_periods=n).min(), data.high.rolling(n, min_periods=n).max()
    return -100 * (hi - data.close) / (hi - lo).replace(0, np.nan)


def cci(data: "Data", n: int = 20) -> pd.DataFrame:
    """Commodity channel index."""
    tp = (data.high + data.low + data.close) / 3
    m = tp.rolling(n, min_periods=n).mean()
    md = tp.rolling(n, min_periods=n).apply(lambda a: float(np.mean(np.abs(a - a.mean()))), raw=True)
    return (tp - m) / (0.015 * md.replace(0, np.nan))


def roc(x: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Rate of change over n rows."""
    return x / x.shift(n) - 1


def zscore(x: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    """Rolling z-score."""
    return (x - x.rolling(n, min_periods=n).mean()) / x.rolling(n, min_periods=n).std()


def donchian(data: "Data", n: int = 20) -> Dict[str, pd.DataFrame]:
    """Donchian channel of the previous n sessions (excludes today, so a breakout is today's close above it)."""
    return {"upper": data.high.rolling(n, min_periods=n).max().shift(1), "lower": data.low.rolling(n, min_periods=n).min().shift(1)}


def keltner(data: "Data", n: int = 20, k: float = 2.0) -> Dict[str, pd.DataFrame]:
    """Keltner channel: EMA ± k × ATR."""
    mid, a = ema(data.close, n), atr(data, n)
    return {"middle": mid, "upper": mid + k * a, "lower": mid - k * a}


def obv(data: "Data") -> pd.DataFrame:
    """On-balance volume."""
    return (np.sign(data.close.diff()).fillna(0.0) * data.volume.fillna(0.0)).cumsum()


def mfi(data: "Data", n: int = 14) -> pd.DataFrame:
    """Money flow index (volume-weighted RSI, 0–100)."""
    tp = (data.high + data.low + data.close) / 3
    flow = tp * data.volume
    pos = flow.where(tp.diff() > 0, 0.0).rolling(n, min_periods=n).sum()
    neg = flow.where(tp.diff() < 0, 0.0).rolling(n, min_periods=n).sum()
    return 100 - 100 / (1 + pos / neg.replace(0, np.nan))


def vwap(data: "Data", n: int = 20) -> pd.DataFrame:
    """Rolling volume-weighted average price over n sessions (typical price)."""
    tp = (data.high + data.low + data.close) / 3
    return (tp * data.volume).rolling(n, min_periods=n).sum() / data.volume.rolling(n, min_periods=n).sum().replace(0, np.nan)


def beta(x: pd.DataFrame, market: pd.Series, n: int = 252) -> pd.DataFrame:
    """Rolling beta of each column's returns to a market return series."""
    r, m = x.pct_change(fill_method=None), market.pct_change(fill_method=None)
    cov = r.rolling(n, min_periods=n // 2).cov(m)
    return cov.div(m.rolling(n, min_periods=n // 2).var(), axis=0)


def drawdown(x: pd.DataFrame) -> pd.DataFrame:
    """Distance below the running high (≤ 0)."""
    return x / x.cummax() - 1


# ── Scheduling and universe selection ────────────────────────────────────────
def rebalance(weights: pd.DataFrame, every: Any = "M") -> pd.DataFrame:
    """Decide on a schedule: "D", "W", "M", "Q", "Y" (first observed session of each period) or an integer n (every n
    sessions). Other rows blank = hold."""
    if isinstance(every, int):
        w = weights.copy()
        keep = np.zeros(len(w), bool)
        keep[::max(every, 1)] = True
        w.loc[~keep] = np.nan
        return w
    if str(every).upper() == "D":
        return weights
    return _hold(weights, {"W": "W", "M": "M", "Q": "Q", "Y": "Y", "A": "Y"}[str(every).upper()])


def top_liquid(data: "Data", n: int = 100, lookback: int = 63) -> pd.DataFrame:
    """True for the n most traded names each day (63-day average traded value in USD; known that day) — a dynamic
    universe like QuantConnect's coarse selection."""
    tv = (data.close.mul(data.usd_per_unit, axis=0) * data.volume).rolling(lookback, min_periods=lookback // 2).mean()
    return tv.rank(axis=1, ascending=False) <= n


# ── Custom charts (plot) ─────────────────────────────────────────────────────
_CHARTS: Dict[str, Dict[str, Dict[str, float]]] = {}
INDICATORS = ['sma', 'ema', 'wma', 'hma', 'rsi', 'macd', 'bollinger', 'true_range', 'atr', 'adx', 'stochastic', 'williams_r', 'cci', 'roc', 'zscore', 'donchian', 'keltner', 'obv', 'mfi', 'vwap', 'beta', 'drawdown', 'rebalance', 'top_liquid', 'plot']


def plot(chart: str, name: str, values: Any, date: Any = None) -> None:
    """Add a series to a custom chart in the results: plot("Signals", "SPY RSI", rsi(data.close)["SPY"]) for a whole
    series, or plot(chart, name, value, date) for one point (ctx.plot does that for you in on_bar)."""
    c = _CHARTS.setdefault(str(chart)[:60], {})
    s = c.setdefault(str(name)[:60], {})
    if len(c) > 12 or len(_CHARTS) > 12:
        return
    if isinstance(values, pd.Series):
        v = values.dropna()
        s.update({str(pd.Timestamp(k).date()): float(x) for k, x in v.items() if np.isfinite(x)})
    elif date is not None and values is not None and np.isfinite(float(values)):
        s[str(pd.Timestamp(date).date())] = float(values)


def _charts_out(max_points: int = 1000) -> Dict[str, Any]:
    out = {}
    for chart, series in _CHARTS.items():
        out[chart] = {}
        for name, pts in series.items():
            items = sorted(pts.items())
            step = max(1, len(items) // max_points)
            out[chart][name] = [[d, round(v, 6)] for d, v in items[::step]]
    return out


def decision_mask(weights: pd.DataFrame) -> np.ndarray:
    """Which rows are decisions. Rows left entirely blank (NaN) mean "no new decision"; any row with a value is
    a decision to rebalance to it — even if it equals the previous target. A frame with no blank rows is a
    decision every day."""
    blank = weights.isna().all(axis=1).to_numpy()
    return ~blank


def normalize_gross(weights: pd.DataFrame, gross: float = 1.0) -> pd.DataFrame:
    blank = weights.isna().all(axis=1)
    g = weights.abs().sum(axis=1).replace(0, np.nan)
    out = weights.div(g, axis=0).mul(gross).fillna(0.0)
    out.loc[blank] = np.nan                                 # keep "no decision" rows blank
    return out


def vol_target(weights: pd.DataFrame, close: pd.DataFrame, target: float = 0.10, lookback: int = 63,
               max_leverage: float = 2.0) -> pd.DataFrame:
    """Scale the book so its trailing realised volatility hits `target` (no look-ahead). Volatility is measured
    on the positions actually held (the latest decision carried forward)."""
    r = close.pct_change(fill_method=None).fillna(0.0)
    held = weights.ffill().fillna(0.0)
    port = (held.shift(1).fillna(0.0) * r).sum(axis=1)
    vol = port.rolling(lookback, min_periods=max(20, lookback // 2)).std() * math.sqrt(TRADING_DAYS)
    scale = (target / vol).clip(upper=max_leverage).fillna(1.0)
    return weights.mul(scale, axis=0)

# ── Transaction-cost inputs ─────────────────────────────────────────────────
def half_spread_bps(close: pd.DataFrame, volume: pd.DataFrame, window: int = 63,
                    usd_per_unit: Optional[pd.Series] = None, tick_bps: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Half the bid-ask spread in bps from liquidity and volatility, lagged one day:
         max(half a cent, 25.5 × daily vol (bp) × dollar volume^−0.43)
    calibrated to typical US quoted spreads — ≈0.1 bp for SPY ($30bn/day), ≈2–3 bp for a $50m/day
    mid-cap, ≈15 bp for a $2m/day small cap; wider in volatile markets. (Range-based estimators such as
    Corwin–Schultz or Abdi–Ranaldo are swamped by volatility for liquid names — they put SPY near 10 bp.)
    Adjusted prices are below the traded price in early years, so the half-cent floor is conservative.
    Prices in another account currency are scaled to USD first (`usd_per_unit`), so the calibration holds.
    `tick_bps` (half each exchange's tick, from its tick table) replaces the half-cent floor where known."""
    usd = close.mul(usd_per_unit, axis=0) if usd_per_unit is not None else close
    r = close.pct_change(fill_method=None)
    vol_bp = r.rolling(window, min_periods=20).std() * 1e4
    dv = (usd * volume).rolling(window, min_periods=10).mean()
    model = 25.5 * vol_bp * dv.where(dv > 0) ** -0.43
    tick = 0.005 / usd * 1e4
    if tick_bps is not None:
        tick = tick_bps.reindex(index=close.index, columns=close.columns).astype(float).fillna(tick)
    hs = np.maximum(model, tick).shift(1)
    return hs.clip(lower=0.05, upper=100.0).fillna(5.0)


def dollar_volume(close: pd.DataFrame, volume: pd.DataFrame, window: int = 63) -> pd.DataFrame:
    return (close * volume).rolling(window, min_periods=10).mean().shift(1)


# ── Backtest ────────────────────────────────────────────────────────────────
class Ctx:
    """What on_bar(ctx) sees after each close: data up to and including today only, the account as it really is,
    and order methods. Orders placed today act from the next session."""

    def __init__(self, data: Data, pre: Dict[str, Any]):
        self._data, self._pre = data, pre
        self.state: Dict[str, Any] = {}                     # yours: persists from bar to bar
        self.i, self.date = 0, None
        self.nav = self.cash = 1.0
        self.positions = pd.Series(dtype=float)              # fraction of NAV held per ticker (premium for options)
        self.units = pd.Series(dtype=float)
        self.fills: List[Dict[str, Any]] = []                # executions of the latest session
        self._targets: Dict[str, float] = {}
        self._cond: List[Dict[str, Any]] = []
        # share-quantity orders (the QuantConnect-style API, api/quant/qcalgo.py): deltas in shares per ticker, filled at
        # the next execution; with hold_by_default, names without an order keep their shares (no standing weights)
        self.capital = 1.0
        self.hold_by_default = False
        self._unit_orders: Dict[str, float] = {}
        self._unit_ids: Dict[str, List[int]] = {}
        self.executions: List[Dict[str, Any]] = []           # every fill since the previous bar (market and conditional)
        self._next_id = 1

    # data, causal
    def history(self, field: str = "close", n: Optional[int] = None) -> pd.DataFrame:
        """Rows up to today of data.close / open / high / low / volume / observed (last `n` rows if given)."""
        fr = getattr(self._data, field)
        a = 0 if n is None else max(0, self.i + 1 - n)
        return fr.iloc[a:self.i + 1]

    @property
    def close(self) -> pd.Series:
        return self._data.close.iloc[self.i]

    def pre(self, name: str) -> Any:
        """A series or frame computed by setup(data), up to today only."""
        v = self._pre[name]
        return v.iloc[:self.i + 1] if isinstance(v, (pd.Series, pd.DataFrame)) else v

    def opt(self, field: str) -> pd.DataFrame:
        return self._data.opt[field].iloc[:self.i + 1]

    def fund(self, name: str) -> pd.DataFrame:
        return self._data.fund[name].iloc[:self.i + 1]

    @property
    def info(self) -> pd.DataFrame:
        return self._data.info

    # orders
    def target(self, weights: Any, replace: bool = False) -> None:
        """Market orders: move these tickers to these weights at the next execution. replace=True: everything not
        listed goes to 0."""
        w = dict(weights) if not isinstance(weights, pd.Series) else weights.dropna().to_dict()
        if replace:
            self._targets = {"__replace__": 1.0}
        self._targets.update({str(k): float(v) for k, v in w.items()})

    def limit(self, ticker: str, weight: float, price: float, days: Optional[int] = None) -> None:
        """Move `ticker` to `weight` if the price trades at `price` or better (buy: low ≤ price; sell: high ≥ price);
        fills at the limit, or at the open if it opens through it. Good till cancelled, or `days` sessions."""
        self._cond.append({"ticker": ticker, "weight": float(weight), "price": float(price), "kind": "limit",
                           "days": days, "placed": str(self.date.date())})

    def stop(self, ticker: str, weight: float, price: float, days: Optional[int] = None) -> None:
        """Move `ticker` to `weight` once the price trades through `price` (a sell stop: low ≤ price; a buy stop:
        high ≥ price); fills at the stop, or at the open when it gaps through (worse)."""
        self._cond.append({"ticker": ticker, "weight": float(weight), "price": float(price), "kind": "stop",
                           "days": days, "placed": str(self.date.date())})

    def stop_limit(self, ticker: str, weight: float, stop: float, limit: float, days: Optional[int] = None) -> None:
        """Once the price trades through `stop`, becomes a limit order at `limit` (filled that day if the range reaches
        it, else stays as a limit order)."""
        self._cond.append({"ticker": ticker, "weight": float(weight), "price": float(stop), "limit": float(limit),
                           "kind": "stop_limit", "days": days, "placed": str(self.date.date())})

    def trailing_stop(self, ticker: str, weight: float, trail: float, days: Optional[int] = None) -> None:
        """A stop that follows the price: for a sell, `trail` (e.g. 0.10) below the highest high since it was placed;
        for a buy, that far above the lowest low. Fills at the stop, or at the open when it gaps through."""
        px = float(self.close.get(ticker, np.nan))
        self._cond.append({"ticker": ticker, "weight": float(weight), "trail": float(trail), "kind": "trailing",
                           "peak": px, "trough": px, "price": float("nan"), "days": days, "placed": str(self.date.date())})

    def bracket(self, ticker: str, weight: float, take_profit: float, stop_loss: float, days: Optional[int] = None) -> None:
        """Two linked exits — a limit at `take_profit` and a stop at `stop_loss`, both to `weight` (usually 0): whichever
        fills first cancels the other (one-cancels-other)."""
        g = f"oco{len(self._cond)}-{self.i}"
        self._cond.append({"ticker": ticker, "weight": float(weight), "price": float(take_profit), "kind": "limit",
                           "days": days, "placed": str(self.date.date()), "oco": g})
        self._cond.append({"ticker": ticker, "weight": float(weight), "price": float(stop_loss), "kind": "stop",
                           "days": days, "placed": str(self.date.date()), "oco": g})

    def plot(self, chart: str, name: str, value: float) -> None:
        """Add today's value to a custom chart in the results."""
        plot(chart, name, value, self.date)

    def cancel(self, ticker: Optional[str] = None) -> None:
        self._cond = [o for o in self._cond if ticker is not None and o["ticker"] != ticker]

    # share-quantity orders (used by the QuantConnect-style API; usable directly too)
    def order_shares(self, ticker: str, shares: float, kind: str = "market", price: Optional[float] = None,
                     limit: Optional[float] = None, trail: Optional[float] = None, days: Optional[int] = None) -> int:
        """Buy (+) or sell (−) `shares` of `ticker`. kind: market (next execution: the next open by default),
        moc (market-on-close: the next session's close), limit, stop, stop_limit (price = stop, limit = limit),
        trailing (trail = fraction). Returns an order id; fills appear in ctx.executions with that id."""
        if not shares:
            return 0
        oid = self._next_id
        self._next_id += 1
        du = float(shares) / self.capital                          # engine units (per 1 of starting capital)
        if kind == "market":
            self._unit_orders[ticker] = self._unit_orders.get(ticker, 0.0) + du
            self._unit_ids.setdefault(ticker, []).append(oid)
            return oid
        o = {"ticker": ticker, "du": du, "kind": kind, "days": days, "placed": str(self.date.date()), "id": oid,
             "weight": float("nan"), "price": float("nan") if price is None else float(price)}
        if kind == "stop_limit":
            o["limit"] = float(limit)
        if kind == "trailing":
            px = float(self.close.get(ticker, np.nan))
            o.update({"trail": float(trail), "peak": px, "trough": px, "buy": shares > 0})
        self._cond.append(o)
        return oid

    def cancel_order(self, oid: int) -> bool:
        n = len(self._cond)
        self._cond = [o for o in self._cond if o.get("id") != oid]
        if len(self._cond) < n:
            return True
        for t, ids in self._unit_ids.items():                      # a market order not yet sent to the market
            if oid in ids and t in self._unit_orders:
                ids.remove(oid)
                if not ids:
                    self._unit_orders.pop(t, None)
                return True
        return False

    @property
    def orders(self) -> List[Dict[str, Any]]:
        return list(self._cond)


def backtest(weights: Optional[pd.DataFrame], data: Data, costs: Optional[Dict[str, float]] = None,
             start: Optional[str] = None, decisions: Optional[np.ndarray] = None,
             on_bar: Optional[Callable] = None, params: Optional[Dict[str, Any]] = None,
             pre: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Simulate target weights as one self-financing account.

    Ledger: holdings in units and a cash balance; NAV = Σ units × mark + cash every day. A decision row
    decided at the close of day t places orders filled at the observed OPEN of t+1, only where that open
    exists and the asset traded (volume > 0); orders that cannot fill stay pending until filled or
    replaced by the next decision. Event-driven mode (on_bar): instead of a weight table, on_bar(ctx, **params) is
    called after every close with the account's real state and places market, limit and stop orders.
    Trading costs, fees, borrow and interest settle into cash. Marks are the
    last observed close (stale days are counted, never treated as tradable). An explicitly dated, already-known delisting
    is settled at its last observed mark × (1 − delist_haircut); missing tails remain stale holdings. Returns are NAV changes."""
    cfg = {**DEFAULT_COSTS, **(costs or {})}
    close = data.close
    idx, cols = close.index, list(close.columns)
    if on_bar is None:
        w = weights.reindex(index=idx, columns=cols).astype(float)
        D = decision_mask(w) if decisions is None else np.asarray(decisions, bool)
        W = w.fillna(0.0).to_numpy()
        g = np.abs(W).sum(axis=1)
        W = W * np.where(g > cfg["max_gross"], cfg["max_gross"] / np.where(g > 0, g, 1.0), 1.0)[:, None]
    else:                                                      # decisions arrive bar by bar
        D = np.zeros(len(idx), bool)
        W = np.zeros((len(idx), len(cols)))
        ctx = Ctx(data, pre or {})
        ctx.capital = float(cfg["capital"])
        col_of = {c: j for j, c in enumerate(cols)}
        Hh_, Ll_ = data.high.to_numpy(float), data.low.to_numpy(float)
        cond_fills = 0
    M = close.to_numpy(float)
    OBS = data.observed.to_numpy(bool) & np.isfinite(M)
    O = data.open.to_numpy(float)
    # execution price: next open (default), next day's VWAP (≈ (O+H+L+C)/4), or next close (market-on-close)
    xmode = int(cfg["exec_price"])
    if xmode == 2:
        EXP = np.where(OBS, M, np.nan)
    elif xmode == 1:
        Hh, Ll = data.high.to_numpy(float), data.low.to_numpy(float)
        vw = (O + Hh + Ll + M) / 4
        EXP = np.where(OBS & np.isfinite(vw) & (vw > 0), vw, O)
    else:
        EXP = O
    V = np.nan_to_num(data.volume.to_numpy(float))
    hs = half_spread_bps(close, data.volume, usd_per_unit=data.usd_per_unit, tick_bps=data.tick_bps).to_numpy() * cfg["spread_mult"] / 1e4
    LOT = data.lot_value.to_numpy(float) if (data.lot_value is not None and cfg["board_lots"]) else None
    SET = data.settle.to_numpy(float) if data.settle is not None else None
    NOTL = (data.opt["notional"].reindex(columns=cols).to_numpy(float) if "notional" in data.opt else None)
    # option targets are underlying notional (fraction of NAV): contracts = notional / the underlying's price
    SPOT_O = data.opt["spot_open"].reindex(columns=cols).to_numpy(float) if "spot_open" in data.opt else None
    SPOT_C = data.opt["spot"].reindex(columns=cols).to_numpy(float) if "spot" in data.opt else None
    if SPOT_O is not None and xmode:                      # options sized on the underlying at the execution time
        SPOT_O = SPOT_C if xmode == 2 else (SPOT_O + SPOT_C) / 2
    with np.errstate(divide="ignore", invalid="ignore"):
        LU = LOT / (cfg["capital"] * M) if LOT is not None else None     # account units (of NAV = 1) per board lot
    DY = data.div_yield.to_numpy(float) if (data.div_yield is not None and cfg["dividend_wht"]) else None
    adv = dollar_volume(close, data.volume).to_numpy()
    usd_unit = data.usd_per_unit.to_numpy(float)
    rf = data.rf.to_numpy(float)
    T, N = M.shape
    # A missing tail is not evidence of delisting; future observations must not change history.
    listing_events = data.provenance.get("delisting_events", {})
    if not isinstance(listing_events, dict):
        raise ValueError("delisting_events must map tickers to effective_date and known_at")
    settlement_dates = {}
    for symbol, event in listing_events.items():
        if symbol not in cols or not isinstance(event, dict) or not event.get("effective_date") or not event.get("known_at"):
            raise ValueError("Invalid explicit delisting event")
        effective, known = pd.Timestamp(event["effective_date"]), pd.Timestamp(event["known_at"])
        if effective.tzinfo is not None or known.tzinfo is not None:
            raise ValueError("Delisting dates use timezone-naive exchange session dates")
        settlement_dates[cols.index(symbol)] = max(effective, known)
    settled = np.zeros(N, dtype=bool)
    first = int(np.searchsorted(idx.values, np.datetime64(pd.Timestamp(start)))) if start else 0
    first = max(first, 1)
    last_dec = np.where(D, np.arange(T), -1)
    last_dec = np.maximum.accumulate(last_dec)
    band, cap = cfg["no_trade_band"], cfg["capital"]
    inst = [data.instruments.get(c, {}) for c in cols]
    sec_mask = np.array([1.0 if i.get("sec_fee", True) else 0.0 for i in inst])        # SEC fee: US listings only
    tax_buy = np.array([float(i.get("tax_buy_bps") or 0.0) for i in inst])             # venue transaction taxes
    tax_sell = np.array([float(i.get("tax_sell_bps") or 0.0) for i in inst])
    # converting currency to buy (or back after selling) a listing in another currency
    fx_cost = np.array([cfg["fx_cost_bps"] if (i.get("currency") or "USD") != data.account_currency else 0.0 for i in inst])
    fx_cost = fx_cost + np.array([cfg["crypto_fee_bps"] if i.get("asset_class") == "crypto" else 0.0 for i in inst])
    is_fx = np.array([i.get("asset_class") == "fx" for i in inst])
    # dividend withholding: statutory non-resident rate capped at the treaty rate; listings in the account currency
    # are domestic (nothing withheld)
    wht = np.array([min(float(i.get("wht") or 0.0), cfg["wht_treaty_cap"])
                    if (i.get("currency") or "USD") != data.account_currency else 0.0 for i in inst])
    # FX hedge: per-currency exposure at the previous close, hedged with daily-settled forwards
    ccy_of = [(i.get("currency") or "USD") for i in inst]
    hedge_ccys = []
    if cfg["fx_hedge"] > 0 and data.fx is not None and data.rf_ccy is not None:
        for c in sorted(set(ccy_of) - {data.account_currency}):
            if c in data.fx.columns and c in data.rf_ccy.columns and data.rf_ccy[c].notna().any():
                hedge_ccys.append(c)
    unhedged = sorted(set(ccy_of) - {data.account_currency} - set(hedge_ccys)) if cfg["fx_hedge"] > 0 else []
    HFX = data.fx[hedge_ccys].to_numpy(float) if hedge_ccys else None
    HRF = data.rf_ccy[hedge_ccys].to_numpy(float) if hedge_ccys else None
    hmask = np.array([[ccy_of[j] == c for j in range(len(cols))] for c in hedge_ccys], float) if hedge_ccys else None
    # attribution: each asset's P&L (price and, separately, the currency move on foreign listings)
    fx_cols = [c for c in (data.fx.columns if data.fx is not None else [])]
    FXA = data.fx.to_numpy(float) if data.fx is not None else None
    ccy_pos = np.array([fx_cols.index(c) if c in fx_cols and c != data.account_currency else -1 for c in ccy_of])
    maxp = float(cfg["max_participation"])
    # Brinson–Fachler against the equal-weight universe, by sector (or listing country when sectors are unknown)
    gkey = "sector" if any(i.get("sector") for i in inst) else "country"
    gname = [str(i.get(gkey) or "Other") for i in inst]
    glabels = sorted(set(g for g, o in zip(gname, [c in data.option_names for c in cols]) if not o))
    G = np.array([[gname[j] == g and cols[j] not in data.option_names for j in range(len(cols))] for g in glabels], float)
    br = {k: np.zeros(len(glabels)) for k in ("alloc", "select", "inter")}
    br_cash = 0.0
    MEM = data.members.reindex(index=idx, columns=cols).fillna(False).to_numpy(bool) if getattr(data, "members", None) is not None else None
    mark_prev_close = None
    units = np.zeros(N)
    per_share, cmin, cmax = float(cfg["commission_per_share"]), float(cfg["commission_min"]), float(cfg["commission_max_pct"])
    SH = (data.share_px.to_numpy(float) if data.share_px is not None else M)
    SH = np.where(np.isfinite(SH) & (SH > 0), SH, M)
    # order log and round-trip trades (average-cost accounting per asset; quantities at `capital`)
    fills: List[tuple] = []
    fill_ids: List[Optional[tuple]] = []                        # order ids behind each fill (share-quantity orders)
    trades: List[Dict[str, Any]] = []
    tpos, tavg, tentry, treal, tcost, tmax = (np.zeros(N), np.zeros(N), [None] * N, np.zeros(N), np.zeros(N), np.zeros(N))

    def _fill(t_, j, dq, price, cost, kind, ids=None):
        fills.append((t_, j, dq, price, cost, kind))
        fill_ids.append(ids)
        pos = tpos[j]
        if pos == 0 or np.sign(pos) == np.sign(dq):
            if pos == 0:
                tentry[j], treal[j], tcost[j], tmax[j] = t_, 0.0, 0.0, 0.0
            tavg[j] = (tavg[j] * abs(pos) + price * abs(dq)) / (abs(pos) + abs(dq))
            tpos[j] = pos + dq
            tcost[j] += cost
            tmax[j] = max(tmax[j], abs(tpos[j]) * tavg[j])
            return
        close = min(abs(dq), abs(pos))
        treal[j] += close * (price - tavg[j]) * np.sign(pos)
        tcost[j] += cost
        tpos[j] = pos + dq
        if abs(tpos[j]) < 1e-12 or np.sign(tpos[j]) != np.sign(pos):
            trades.append({"ticker": cols[j], "side": "long" if pos > 0 else "short", "entry": str(idx[tentry[j]].date()),
                           "exit": str(idx[t_].date()), "days": int((idx[t_] - idx[tentry[j]]).days),
                           "pnl": (treal[j] - tcost[j]) * cap, "return": (treal[j] - tcost[j]) / tmax[j] if tmax[j] > 0 else 0.0,
                           "costs": tcost[j] * cap})
            rest = tpos[j] if abs(tpos[j]) > 1e-12 else 0.0
            tpos[j], treal[j], tcost[j], tmax[j] = 0.0, 0.0, 0.0, 0.0
            if rest:                                          # flipped: the remainder opens a new trade
                tentry[j], tavg[j], tpos[j], tmax[j] = t_, price, rest, abs(rest) * price

    pnl_asset = np.zeros(N)
    fx_asset = np.zeros(N)
    margin_calls = 0
    opt_notional = np.zeros(T)
    is_opt = np.array([c in data.option_names for c in cols])
    cash = 1.0
    mark = np.where(OBS[first - 1], M[first - 1], np.nan)
    lv = mark.copy()                                           # price each holding was last valued at (attribution)
    target: Optional[np.ndarray] = None if on_bar is None else np.zeros(N)
    pending = np.zeros(N, bool)
    nav_prev = 1.0
    mv_prev = np.zeros(N)
    keys = ("ret", "gross", "commission", "spread", "impact", "fees", "borrow", "financing", "turnover", "long", "short",
            "cash", "nav", "unfilled", "stale_held", "dividend_tax", "hedge", "lot_residual", "capped")
    out = {k: np.zeros(T) for k in keys}
    events: List[Dict[str, Any]] = []
    UT = np.full((T, N), np.nan) if on_bar is not None else None  # absolute unit targets from share orders, by decision day
    UID: Dict[int, Dict[int, List[int]]] = defaultdict(dict)    # order ids behind them
    ut_active = np.full(N, np.nan)                               # unit targets still being worked
    ut_ids: Dict[int, List[int]] = {}
    seen, hold = [0], [False]
    def _bar(t, nav, cash, mv):
        """Event mode: give on_bar the account after day t's close; record its market orders as a decision on t."""
        ctx.i, ctx.date, ctx.nav, ctx.cash = t, idx[t], nav, cash
        ctx.units = pd.Series(units, index=cols)
        ctx.positions = pd.Series(mv / nav if nav > 0 else mv * 0, index=cols)
        ctx._targets = {}
        ctx._unit_orders, ctx._unit_ids = {}, {}
        ctx.executions = [{"ids": list(fill_ids[k] or ()), "date": str(idx[f[0]].date()), "ticker": cols[f[1]],
                           "shares": f[2] * cap, "price": f[3], "cost": f[4] * cap, "kind": f[5]}
                          for k, f in enumerate(fills[seen[0]:], start=seen[0])]
        seen[0] = len(fills)
        on_bar(ctx, **(params or {}))
        if ctx.hold_by_default and not hold[0]:
            hold[0] = True
            target[:] = np.nan                                  # QuantConnect semantics: no standing weights
        if ctx._targets or ctx._unit_orders:
            row = np.zeros(N) if ctx._targets.pop("__replace__", None) else target.copy()
            for k, v in ctx._targets.items():
                if k not in col_of:
                    raise ValueError(f"ctx.target: unknown ticker {k}")
                row[col_of[k]] = v
            for k, du in ctx._unit_orders.items():
                if k not in col_of:
                    raise ValueError(f"order: unknown ticker {k}")
                j = col_of[k]
                base = UT[t, j] if np.isfinite(UT[t, j]) else (ut_active[j] if np.isfinite(ut_active[j]) else units[j])
                UT[t, j] = base + du
                UID[t][j] = list(ctx._unit_ids.get(k, []))
                row[j] = np.nan
            gr = np.nansum(np.abs(row))
            if gr > cfg["max_gross"]:
                row = row * cfg["max_gross"] / gr
            W[t], D[t] = row, True

    if on_bar is not None:
        _bar(first - 1, 1.0, cash, np.zeros(N))             # the starting account, before the first session
    for t in range(first, T):
        day_pnl = np.zeros(N)
        if FXA is not None and (ccy_pos >= 0).any():
            with np.errstate(divide="ignore", invalid="ignore"):
                fr_c = FXA[t] / FXA[t - 1] - 1
            fr_a = np.where(ccy_pos >= 0, np.nan_to_num(fr_c[np.maximum(ccy_pos, 0)]), 0.0)
            fx_asset += np.where(units != 0, units * np.nan_to_num(mark) * fr_a, 0.0) / nav_prev
        # 1) the decision taken at yesterday's close becomes today's orders
        if D[t - 1] or (t == first and last_dec[t - 1] >= 0):
            target = W[t - 1] if D[t - 1] else W[last_dec[t - 1]]
            pending = np.ones(N, bool)
            if on_bar is not None and D[t - 1]:
                fresh = np.isfinite(UT[t - 1])
                ut_active = np.where(fresh, UT[t - 1], ut_active)
                for j_, ids_ in UID.get(t - 1, {}).items():
                    ut_ids[j_] = ut_ids.get(j_, []) + ids_
        # 2) only an explicitly dated, already-known listing event permits settlement.
        # Missing observations retain stale valuation marks and pending orders, never free cash.
        for j, settlement in settlement_dates.items():
            if not settled[j] and idx[t] >= settlement:
                if units[j] != 0:
                    value = units[j] * float(mark[j]) * (1 - cfg["delist_haircut"])
                    _fill(t, j, float(-units[j]), float(mark[j]) * (1 - cfg["delist_haircut"]), 0.0, "delisted")
                    day_pnl[j] += value - units[j] * float(np.nan_to_num(lv[j]))
                    cash += value
                    events.append({"date": str(idx[t].date()), "ticker": cols[j],
                                   "event": "listing ended — explicit event settled at last observed mark",
                                   "value": round(float(value), 6)})
                units[j] = 0.0
                pending[j] = False
                settled[j] = True
        # 2b) ex-dividend: tax withheld at source on long holdings' dividends (gross dividends are in the prices)
        dtax = 0.0
        if DY is not None:
            dy = DY[t]
            if np.any(dy > 0):
                dtax = float(np.nansum(np.where((units > 0) & (dy > 0), units * np.nan_to_num(mark) * dy * wht, 0.0)))
                cash -= dtax
        # 3) the opening market: only observed opens of assets that traded are executable
        exe = np.isfinite(EXP[t]) & (EXP[t] > 0) & OBS[t] & (V[t] > 0) & ~settled
        mark_open = np.where(exe, EXP[t], mark)
        held_val = np.where(units != 0, units * np.nan_to_num(mark_open), 0.0)
        nav_open = float(held_val.sum() + cash)
        comm = spr = imp = fee = turn = 0.0
        if nav_open <= 0:
            out["ret"][t] = -1.0
            events.append({"date": str(idx[t].date()), "ticker": None, "event": "insolvent: NAV ≤ 0, simulation stopped"})
            for k in keys:
                out[k][t + 1:] = np.nan
            break
        ids_now: Dict[int, tuple] = {}
        if target is not None and pending.any():
            px = np.where(exe, EXP[t], np.nan)
            # 63-day average traded value; a listing too new for one uses yesterday's (never "unlimited")
            dv = np.where(np.isfinite(adv[t]), adv[t], V[t - 1] * np.nan_to_num(M[t - 1]))
            okdv = np.isfinite(dv) & (dv > 0)

            # share-quantity orders and "hold" targets exist only in event mode; weight strategies keep the plain path
            u_ord = np.isfinite(ut_active) if on_bar is not None else None
            t_hold = np.isnan(target) if on_bar is not None else None
            mixed = on_bar is not None and (u_ord.any() or t_hold.any())

            def order(nav_eff):
                per_unit = np.where(exe, EXP[t], 1.0)
                if SPOT_O is not None:
                    per_unit = np.where(is_opt & np.isfinite(SPOT_O[t]), SPOT_O[t], per_unit)
                if mixed:
                    want = np.where(u_ord, ut_active, np.where(t_hold, units, np.nan_to_num(target) * nav_eff / per_unit))
                else:
                    want = target * nav_eff / per_unit
                dl = np.where(pending & exe, want - units, 0.0)
                nt = np.abs(dl) * np.nan_to_num(px)
                # the band suppresses small *adjustments* to positions held and kept; opening a new position or
                # closing one always trades (otherwise a 700-name book of 0.14% positions could never be bought);
                # share-quantity orders are never suppressed
                sm = (nt <= band * nav_open) & (units != 0) & (target != 0)
                if mixed:
                    sm &= ~u_ord
                dl, nt = np.where(sm, 0.0, dl), np.where(sm, 0.0, nt)
                if maxp > 0:
                    # volume limit: at most max_participation of the asset's average daily traded value today
                    lim = np.where(okdv, maxp * np.where(okdv, dv, 0.0) / cap, np.inf)
                    over = nt > lim
                    dl = np.where(over, dl * lim / np.where(nt > 0, nt, 1.0), dl)
                    nt = np.where(over, lim, nt)
                    capped[0] = over
                if LU is not None:
                    # whole board lots only (sized at `capital`); a full exit may sell an odd lot
                    lu = LU[t - 1]
                    lot = np.isfinite(lu) & (lu > 0) & (dl != 0) & (target != 0)
                    req = nt
                    dl = np.where(lot, np.round(dl / np.where(lot, lu, 1.0)) * np.where(lot, lu, 1.0), dl)
                    nt = np.abs(dl) * np.nan_to_num(px)
                    resid[0] = float(np.abs(req - nt).sum())
                cv = cfg["commission_bps"] / 1e4 * nt
                if per_share or cmin:
                    # broker model: per share with a minimum and a cap per order (share counts at `capital`)
                    traded = nt > 0
                    shares = np.where(traded, nt * cap / np.where(traded & (SH[t] > 0), SH[t], np.inf), 0.0)
                    fee_ps = np.where(traded, np.maximum(shares * per_share, cmin) / cap, 0.0)
                    if cmax > 0:
                        fee_ps = np.minimum(fee_ps, cmax * nt)
                    cv = cv + fee_ps
                sv = nt * np.nan_to_num(hs[t], nan=5e-4)
                fr = np.where(okdv, nt * cap / np.where(okdv, dv, 1.0), 0.0)
                iv = nt * cfg["impact_coef_bps"] / 1e4 * np.sqrt(100 * fr)
                sells, buys = np.where(dl < 0, nt, 0.0), np.where(dl > 0, nt, 0.0)
                fv = (sells * (cfg["sec_fee_bps"] * sec_mask + tax_sell) + buys * tax_buy + nt * fx_cost) / 1e4
                per_asset[0] = cv + sv + iv + fv
                return dl, nt, float(cv.sum()), float(sv.sum()), float(iv.sum()), float(fv.sum())
            # size orders against NAV *after* this rebalance's costs, so fees come out of what is bought rather
            # than leaving an unintended margin loan (fixed point; converges in a few steps for realistic costs)
            nav_eff = nav_open
            per_asset = [np.zeros(N)]
            resid = [0.0]
            capped = [np.zeros(N, bool)]
            for _ in range(30):
                delta, notional, comm, spr, imp, fee = order(nav_eff)
                nxt = nav_open - (comm + spr + imp + fee)
                if abs(nxt - nav_eff) < 1e-13:
                    break
                nav_eff = nxt
            pending &= ~exe                                    # executable orders are done (filled or within band)
            pending |= capped[0]                               # …except what the volume limit held back
            if on_bar is not None and u_ord.any():                  # share orders (or a share-mode margin cut) working
                ids_now = {j_: tuple(v) for j_, v in ut_ids.items() if np.isfinite(ut_active[j_])}   # before clearing
                done_u = exe & ~capped[0] & np.isfinite(ut_active)  # share orders fully worked
                for j_ in np.nonzero(done_u)[0]:
                    ut_ids.pop(int(j_), None)
                ut_active = np.where(done_u, np.nan, ut_active)
            out["capped"][t] = float(capped[0].sum())
            day_pnl += np.where(exe & (units != 0), units * (np.nan_to_num(px) - np.nan_to_num(lv)), 0.0)
            lv = np.where(exe, px, lv)
            if notional.any():
                for j in np.nonzero(delta)[0]:
                    _fill(t, j, float(delta[j]), float(px[j]), float(per_asset[0][j]), "order", ids_now.get(int(j)))
                units = units + delta
                cash -= float(np.nansum(delta * px)) + comm + spr + imp + fee
                turn = float(notional.sum() / nav_open)
            out["lot_residual"][t] = resid[0] / nav_open
            # orders still open: assets whose target differs from what is held and cannot trade today
            cur_w = np.where(units != 0, units * np.nan_to_num(mark_open), 0.0) / nav_open
            if SPOT_O is not None:
                cur_w = np.where(is_opt, units * np.nan_to_num(SPOT_O[t]) / nav_open, cur_w)
            out["unfilled"][t] = float((pending & (np.abs(target - cur_w) > band)).sum())
        # 3b) event mode: limit and stop orders against today's range (fill at the order price, or the open if it
        # gapped through); each fill moves that one holding to the order's weight, with its trading costs
        if on_bar is not None and ctx._cond:
            keep = []
            fills_today = []
            for o in ctx._cond:
                j = col_of.get(o["ticker"])
                if j is None or is_opt[j]:
                    continue
                ok_t = OBS[t] & (V[t] > 0)
                if not ok_t[j] or not np.isfinite(O[t, j]) or settled[j]:
                    keep.append(o)
                    continue
                nav_now = float(np.where(units != 0, units * np.nan_to_num(np.where(OBS[t], M[t], mark)), 0.0).sum() + cash)
                cur_w = units[j] * O[t, j] / nav_now if nav_now > 0 else 0.0
                buy = (o["du"] > 0) if "du" in o else o["weight"] > cur_w
                if o["kind"] == "moc":                            # market-on-close: the next session's close
                    fpx = M[t, j]
                    if not np.isfinite(fpx):
                        keep.append(o)
                        continue
                    o["price"] = float(fpx)
                op_, hi_, lo_ = O[t, j], Hh_[t, j], Ll_[t, j]
                if o["kind"] == "trailing":                       # the stop level from the extreme up to yesterday
                    o["price"] = o["trough"] * (1 + o["trail"]) if buy else o["peak"] * (1 - o["trail"])
                k_ = o["price"]
                if o["kind"] == "moc":
                    hit = True
                elif o["kind"] == "limit":
                    hit = (lo_ <= k_) if buy else (hi_ >= k_)
                elif o["kind"] == "stop_limit" and not o.get("armed"):
                    hit = (hi_ >= k_) if buy else (lo_ <= k_)
                    if hit:                                       # triggered: now a limit order at its limit price
                        o["armed"], o["armed_at"] = True, t
                        lim = o["limit"]
                        hit = (lo_ <= lim) if buy else (hi_ >= lim)
                elif o["kind"] == "stop_limit":
                    lim = o["limit"]
                    hit = (lo_ <= lim) if buy else (hi_ >= lim)
                else:                                             # stop, trailing
                    hit = (hi_ >= k_) if buy else (lo_ <= k_)
                if o["kind"] == "trailing" and not hit:
                    o["peak"], o["trough"] = max(o["peak"], hi_), min(o["trough"], lo_)
                if not hit:
                    if o["days"] is not None:
                        o["days"] -= 1
                        if o["days"] <= 0:
                            continue
                    keep.append(o)
                    continue
                if o["kind"] == "moc":
                    fpx = float(M[t, j])
                elif o["kind"] == "limit":
                    fpx = min(op_, k_) if buy else max(op_, k_)
                elif o["kind"] == "stop_limit":
                    lim = o["limit"]
                    if o.get("armed_at") == t:                   # triggered today: filled around the stop, within the limit
                        fpx = min(max(op_, k_), lim) if buy else max(min(op_, k_), lim)
                    else:                                         # an armed limit from an earlier day
                        fpx = min(op_, lim) if buy else max(op_, lim)
                else:
                    fpx = max(op_, k_) if buy else min(op_, k_)
                dl_j = o["du"] if "du" in o else o["weight"] * nav_now / fpx - units[j]
                nt_j = abs(dl_j) * fpx
                dv_j = adv[t, j] if np.isfinite(adv[t, j]) else V[t - 1, j] * np.nan_to_num(M[t - 1, j])
                c1 = cfg["commission_bps"] / 1e4 * nt_j
                s1 = nt_j * float(np.nan_to_num(hs[t, j], nan=5e-4))
                i1 = nt_j * cfg["impact_coef_bps"] / 1e4 * math.sqrt(100 * nt_j * cap / dv_j) if dv_j and dv_j > 0 else 0.0
                f1 = nt_j * ((cfg["sec_fee_bps"] * sec_mask[j] + tax_sell[j]) if dl_j < 0 else tax_buy[j]) / 1e4 + nt_j * fx_cost[j] / 1e4
                day_pnl[j] += units[j] * (fpx - float(np.nan_to_num(lv[j])))
                lv[j] = fpx
                _fill(t, j, float(dl_j), float(fpx), float(c1 + s1 + i1 + f1), o["kind"], (o["id"],) if "id" in o else None)
                units[j] += dl_j
                cash -= dl_j * fpx + c1 + s1 + i1 + f1
                comm += c1
                spr += s1
                imp += i1
                fee += f1
                turn += nt_j / nav_now if nav_now > 0 else 0.0
                target[j] = o["weight"]                           # NaN for share orders: hold the new position
                if "du" in o and np.isfinite(ut_active[j]):
                    ut_active[j] += dl_j                         # a working market order still aims at the same change
                else:
                    pending[j] = False
                cond_fills += 1
                fills_today.append({"date": str(idx[t].date()), "ticker": o["ticker"], "kind": o["kind"], "price": round(float(fpx), 6),
                                    "weight": o["weight"], "placed": o["placed"], **({"oco": o["oco"]} if o.get("oco") else {})})
            filled_groups = {f.get("oco") for f in fills_today if f.get("oco")}
            ctx._cond = [o for o in keep if not o.get("oco") or o["oco"] not in filled_groups]   # one cancels other
            ctx.fills = fills_today
            events.extend({**f, "event": f"{f['kind']} order filled"} for f in fills_today)
        elif on_bar is not None:
            ctx.fills = []
        # 4) the close: observed closes update marks; others stay stale
        if SET is not None:
            # option expiry: the expiring contract settles at intrinsic value into cash; the column continues as the
            # next contract, and a standing target is re-established in it at the next open (the roll)
            ex_ = np.isfinite(SET[t])
            if ex_.any():
                for j in np.where(ex_ & (units != 0))[0]:
                    _fill(t, j, float(-units[j]), float(SET[t, j]), 0.0, "expiry")
                    day_pnl[j] += units[j] * (SET[t, j] - float(np.nan_to_num(lv[j])))
                    cash += units[j] * SET[t, j]
                    events.append({"date": str(idx[t].date()), "ticker": cols[j], "event": "option expired — settled",
                                   "value": round(float(units[j] * SET[t, j]), 6)})
                units = np.where(ex_, 0.0, units)
                if target is not None:
                    pending |= ex_ & (target != 0)
        mark = np.where(OBS[t], M[t], mark)
        day_pnl += np.where(OBS[t] & (units != 0), units * (np.nan_to_num(M[t]) - np.nan_to_num(lv)), 0.0)
        lv = np.where(OBS[t], M[t], lv)
        out["stale_held"][t] = float(((units != 0) & ~OBS[t]).sum())
        mv = np.where(units != 0, units * np.nan_to_num(mark), 0.0)
        short_vec = np.where((mv < 0) & ~is_opt & ~is_fx, -mv, 0.0)   # stock borrow: options are written, FX is a forward
        short_mv = float(short_vec.sum())
        if NOTL is not None:                                   # underlying value controlled by option positions
            opt_notional[t] = float(np.nansum(np.abs(mv) * np.nan_to_num(NOTL[t])))
        # 5) one trading day of interest on cash and borrow on shorts
        rf_d = rf[t] if np.isfinite(rf[t]) else 0.0
        fin = cash * (rf_d - cfg["cash_spread"] / TRADING_DAYS) if cash >= 0 else cash * (rf_d + cfg["financing_spread"] / TRADING_DAYS)
        spread_part = (cash * cfg["financing_spread"] / TRADING_DAYS if cash < 0 else -cash * cfg["cash_spread"] / TRADING_DAYS)
        if cfg["borrow_tiers"] and short_mv > 0:
            # hard-to-borrow: thinly traded names cost more to borrow (tiers by average daily traded value in USD)
            a_usd = np.nan_to_num(adv[t]) * (usd_unit[t] if np.isfinite(usd_unit[t]) else 1.0)
            fee_y = np.maximum(cfg["borrow_fee"], np.where(a_usd >= 1e8, 0.0, np.where(a_usd >= 2e7, 0.0075,
                                                                                  np.where(a_usd >= 5e6, 0.02, 0.05))))
            bor = float((short_vec * fee_y).sum()) / TRADING_DAYS
        else:
            bor = short_mv * cfg["borrow_fee"] / TRADING_DAYS
        cash += fin - bor
        # 6) FX hedge: forwards on yesterday's closing exposure per currency, settled daily — the hedged share of
        # each currency's move is given back and the interest differential (account − foreign) is earned or paid
        hpl = 0.0
        if HFX is not None:
            e = hmask @ mv_prev
            with np.errstate(divide="ignore", invalid="ignore"):
                fxr = HFX[t] / HFX[t - 1] - 1
            ok = np.isfinite(fxr) & np.isfinite(HRF[t]) & (e != 0)
            h = cfg["fx_hedge"]
            hpl = float(np.sum(np.where(ok, h * e * (-np.nan_to_num(fxr) + rf_d - np.nan_to_num(HRF[t])), 0.0))
                        - h * np.sum(np.where(ok, np.abs(e), 0.0)) * cfg["fx_hedge_cost_bps"] / 1e4 / TRADING_DAYS)
            cash += hpl
        if mark_prev_close is not None and len(glabels):
            with np.errstate(divide="ignore", invalid="ignore"):
                ra = np.where(OBS[t] & np.isfinite(mark_prev_close) & (mark_prev_close > 0), M[t] / mark_prev_close - 1, np.nan)
            okb = np.isfinite(ra) & np.array([not o for o in is_opt])
            if MEM is not None:
                okb &= MEM[t]
            if okb.sum() >= 2:
                r0 = np.nan_to_num(ra)
                wb = okb / okb.sum()
                wp = np.where(np.isfinite(ra) & ~is_opt, mv_prev / nav_prev, 0.0)
                rb = float(wb @ r0)
                Wb, Wp = G @ wb, G @ wp
                Rb = np.divide(G @ (wb * r0), Wb, out=np.zeros_like(Wb), where=Wb > 0)
                Rb = np.where(Wb > 0, Rb, rb)
                Rp = np.divide(G @ (wp * r0), Wp, out=Rb.copy(), where=np.abs(Wp) > 1e-12)
                br["alloc"] += (Wp - Wb) * (Rb - rb)
                br["select"] += Wb * (Rp - Rb)
                br["inter"] += (Wp - Wb) * (Rp - Rb)
                wcash = 1.0 - float(wp.sum())                       # everything not in a priced holding
                br_cash += wcash * (0.0 - rb)
        mark_prev_close = mark.copy()
        mv_prev = mv
        nav = float(mv.sum() + cash)
        pnl_asset += day_pnl / nav_prev
        # margin: NAV must cover maintenance on gross stock value plus margin on written options; otherwise the broker
        # cuts every position at the next execution to bring the requirement back to 80% of NAV
        req = cfg["maintenance_margin"] * float(np.abs(mv[~is_opt & ~is_fx]).sum()) + 0.05 * float(np.abs(mv[is_fx]).sum())
        if NOTL is not None:
            req += cfg["option_margin"] * float(np.nansum(np.where(is_opt & (mv < 0), -mv * np.nan_to_num(NOTL[t]), 0.0)))
        if req > 0 and nav < req and nav > 0:
            k = 0.8 * nav / req
            cur = mv / nav
            if SPOT_C is not None:
                cur = np.where(is_opt, units * np.nan_to_num(SPOT_C[t]) / nav, cur)
            if hold[0]:
                ut_active = np.where(units != 0, units * k, ut_active)    # share mode: cut the holdings themselves
            else:
                target = cur * k
            pending = units != 0
            margin_calls += 1
            events.append({"date": str(idx[t].date()), "ticker": None,
                           "event": f"margin call — NAV {nav:.3f} below requirement {req:.3f}; every position cut to {k:.0%}"})
        trading = comm + spr + imp + fee
        out["ret"][t] = nav / nav_prev - 1
        out["gross"][t] = (nav + trading + bor + dtax - spread_part) / nav_prev - 1   # before costs, borrow, tax, rate spreads
        for k, v in (("commission", comm), ("spread", spr), ("impact", imp), ("fees", fee), ("borrow", bor), ("financing", fin),
                     ("dividend_tax", dtax), ("hedge", hpl)):
            out[k][t] = v / nav_prev
        out["turnover"][t] = turn
        out["long"][t] = float(mv[mv > 0].sum() / nav) if nav > 0 else np.nan
        out["short"][t] = short_mv / nav if nav > 0 else np.nan
        out["cash"][t], out["nav"][t] = cash, nav
        opt_notional[t] = opt_notional[t] / nav if nav > 0 else np.nan
        nav_prev = nav
        if on_bar is not None and t < T - 1:
            _bar(t, nav, cash, mv)
    sl = slice(first, T)
    last_dec = np.maximum.accumulate(np.where(D, np.arange(T), -1))
    res: Dict[str, Any] = {k: pd.Series(v[sl], index=idx[sl]).dropna() for k, v in out.items()}
    ld = int(last_dec[-1]) if len(last_dec) and last_dec[-1] >= 0 else None
    res["weights_last"] = ({c: round(float(x), 4) for c, x in zip(cols, W[ld]) if abs(x) > 1e-4} if ld is not None else {})
    navf = float(out["nav"][T - 1]) if T else 1.0
    held = np.where(units != 0, units * np.nan_to_num(mark), 0.0)
    res["holdings_last"] = {c: round(float(x / navf), 4) for c, x in zip(cols, held) if navf > 0 and abs(x / navf) > 1e-4}
    res["ledger"] = {"units": {c: float(u) for c, u in zip(cols, units) if u}, "cash": float(cash), "nav": navf,
                     "securities": float(held.sum()), "reconciles": bool(abs(held.sum() + cash - navf) < 1e-9)}
    res["events"] = events[-200:]
    open_trades = [{"ticker": cols[j], "side": "long" if tpos[j] > 0 else "short", "entry": str(idx[tentry[j]].date()),
                    "unrealised": round(float((tpos[j] * (float(np.nan_to_num(mark[j])) - tavg[j]) + treal[j] - tcost[j]) * cap), 2)}
                   for j in np.nonzero(tpos)[0] if tentry[j] is not None]
    res["fills"] = fills
    res["trades"] = trades
    res["open_trades"] = open_trades
    res["brinson"] = {"by": gkey, "groups": glabels, **{k: v.tolist() for k, v in br.items()}, "cash": br_cash}
    res["attribution"] = {"pnl": {c: float(x) for c, x in zip(cols, pnl_asset) if x},
                          "fx": {c: float(x) for c, x in zip(cols, fx_asset) if x}}
    res["execution"] = {"unfilled_order_days": int((out["unfilled"][sl] > 0).sum()),
                        "stale_position_days": int(out["stale_held"][sl].sum()), "listings_ended": sum(e["event"].startswith("listing ended") for e in events),
                        "delisting_policy": "explicit effective_date and known_at only; missing tails retain stale marks",
                        "rf_known": bool(data.rf_known),
                        "board_lots": LU is not None, "lot_residual_avg": round(float(out["lot_residual"][sl].mean()), 6) if T > first else 0.0,
                        "fx_hedged": hedge_ccys, "fx_unhedged": unhedged,
                        "tick_table": data.tick_bps is not None, "dividend_withholding": DY is not None,
                        "exec_price": ["next open", "next-day VWAP", "next close"][xmode],
                        "max_participation": maxp, "participation_capped_days": int((out["capped"][sl] > 0).sum()),
                        "margin_calls": margin_calls,
                        **({"mode": "event-driven", "conditional_fills": cond_fills, "open_orders": len(ctx._cond),
                            **({"algorithm": ctx.report} if getattr(ctx, "report", None) else {})}
                           if on_bar is not None else {}),
                        **({"option_notional_avg": round(float(np.nanmean(opt_notional[sl])), 3),
                            "option_notional_max": round(float(np.nanmax(opt_notional[sl])), 3),
                            "options_expired": sum(e["event"].startswith("option expired") for e in events)}
                           if NOTL is not None and T > first else {})}
    return res


# ── Statistics (one definition, mirrored exactly by api/quant/robust.py) ────
def years_between(first: pd.Timestamp, last: pd.Timestamp) -> float:
    """Calendar years spanned by a return series (first to last return date), at least one day."""
    return max((pd.Timestamp(last) - pd.Timestamp(first)).days, 1) / 365.25


def metrics(ret: pd.Series, rf: Optional[pd.Series] = None) -> Dict[str, Optional[float]]:
    """Return statistics. Sharpe and Sortino use returns above the reference rate (`rf`, daily, decimal);
    std with ddof=1, annualised by √(periods a year) — 252, or the calendar's own count when it differs by more than 5%
    (crypto trades every day; a global union calendar has ~260 sessions). Max drawdown includes the starting capital.
    CAGR uses calendar years."""
    r = ret.dropna()
    if len(r) < 20:
        return {}
    eq = (1 + r).cumprod()
    yrs = years_between(r.index[0], r.index[-1])
    ppy = periods_per_year(r.index)
    ex = r - (rf.reindex(r.index).fillna(0.0) if rf is not None else 0.0)
    sd = float(ex.std(ddof=1))
    peak = np.maximum.accumulate(np.r_[1.0, eq.to_numpy()])[1:]
    dd = eq.to_numpy() / peak - 1
    down = ex[ex < 0]
    mdd = float(dd.min())
    cagr = float(eq.iloc[-1] ** (1 / yrs) - 1) if eq.iloc[-1] > 0 else -1.0
    return {"cagr": round(cagr, 4), "vol": round(float(r.std(ddof=1) * math.sqrt(ppy)), 4),
            "sharpe": round(float(ex.mean() / sd * math.sqrt(ppy)), 3) if sd > 0 else None,
            "sortino": round(float(ex.mean() / down.std(ddof=1) * math.sqrt(ppy)), 3) if len(down) > 5 and down.std(ddof=1) > 0 else None,
            "max_drawdown": round(mdd, 4),
            "calmar": round(cagr / abs(mdd), 3) if mdd < 0 else None,
            "log_growth": round(float(np.log1p(r.clip(lower=-0.999)).mean() * ppy), 4),
            "hit_rate": round(float((r > 0).mean()), 3), "years": round(yrs, 1),
            "total_return": round(float(eq.iloc[-1] - 1), 4),
            "cash_rate": round(float((r - ex).mean() * ppy), 4)}


def periods_per_year(index: pd.DatetimeIndex) -> float:
    """Rows a year: 252 unless the calendar itself differs by more than 5% (the same rule as the deep report)."""
    if len(index) < 2:
        return float(TRADING_DAYS)
    actual = (len(index) - 1) / years_between(index[0], index[-1])
    return actual if abs(actual / TRADING_DAYS - 1) > 0.05 else float(TRADING_DAYS)


def cost_summary(res: Dict[str, Any]) -> Dict[str, float]:
    """Average annual drag of each cost item (fraction of NAV per year)."""
    r = res["ret"]
    yr = 1.0 / years_between(r.index[0], r.index[-1]) if len(r) > 1 else 1.0      # totals per calendar year
    out = {k: round(float(res[k].sum()) * yr, 5) for k in ("commission", "spread", "impact", "fees", "borrow")}
    out["dividend_tax"] = round(float(res["dividend_tax"].sum()) * yr, 5) if "dividend_tax" in res else 0.0
    out["hedge_pnl"] = round(float(res["hedge"].sum()) * yr, 5) if "hedge" in res else 0.0
    out["financing_net"] = round(float(res["financing"].sum()) * yr, 5)
    out["turnover"] = round(float(res["turnover"].sum()) * yr, 2)
    out["avg_long"] = round(float(res["long"].mean()), 3)
    out["avg_short"] = round(float(res["short"].mean()), 3)
    out["total_trading"] = round(sum(out[k] for k in ("commission", "spread", "impact", "fees")), 5)
    return out

# ── Walk-forward optimisation ───────────────────────────────────────────────
def grid(params: Dict[str, Sequence[Any]]) -> List[Dict[str, Any]]:
    combos: List[Dict[str, Any]] = [{}]
    for k, vals in (params or {}).items():
        combos = [{**c, k: v} for c in combos for v in vals]
    return combos


def select_walk_forward(series: List[pd.Series], combos: List[Dict[str, Any]], warmup_years: int = 5,
                        objective: str = "log_growth", rf: Optional[pd.Series] = None) -> List[Dict[str, Any]]:
    """For each calendar year after the warm-up, the parameter set with the best `objective` on returns
    strictly before 1 January of that year. Standalone return paths are used only for this scoring (they
    depend only on data up to the scoring date); the account itself is simulated once, continuously."""
    idx = series[0].index
    years = sorted(set(idx.year))
    if not years:
        return []
    out = []
    for y in years:
        if y < years[0] + warmup_years:
            continue
        cut = pd.Timestamp(f"{y}-01-01")
        scores = []
        for s in series:
            m = metrics(s[s.index < cut], rf)
            v = m.get(objective)
            scores.append(v if v is not None else -1e9)
        b = int(np.argmax(scores))
        out.append({"year": y, "params": combos[b], "trailing": round(float(scores[b]), 4)})
    return out


def walk_forward(run: Callable[[Dict[str, Any]], pd.Series], params: Dict[str, Sequence[Any]],
                 warmup_years: int = 5, objective: str = "log_growth") -> Dict[str, Any]:
    """Selection only (kept for callers that combine return streams, not accounts)."""
    combos = grid(params)
    series = [run(p) for p in combos]
    chosen = select_walk_forward(series, combos, warmup_years, objective)
    return {"chosen": chosen, "combos": combos}


def _standing(W: pd.DataFrame, D: np.ndarray) -> pd.DataFrame:
    """The target in force on each day: the latest decision carried forward (zeros before the first)."""
    Wt = W.copy()
    Wt.loc[~np.asarray(D, bool)] = np.nan
    return Wt.ffill().fillna(0.0)


def continuous_walk_forward(weight_sets: List[pd.DataFrame], chosen: List[Dict[str, Any]], combos: List[Dict[str, Any]],
                            idx: pd.DatetimeIndex) -> tuple:
    """One target/decision schedule following the chosen parameters year by year. On the first trading day
    of a year whose choice differs from the last one, a decision to the new set's standing target is forced,
    so the account trades from what it holds to what the new set wants — and pays for it."""
    key = [repr(sorted(c.items())) for c in combos]
    cols = weight_sets[0].columns
    Wc = pd.DataFrame(np.nan, index=idx, columns=cols)
    Dc = np.zeros(len(idx), bool)
    prev = None
    switches = []
    for ch in chosen:
        j = key.index(repr(sorted(ch["params"].items())))
        Wj = weight_sets[j].reindex(index=idx, columns=cols)
        Dj = decision_mask(Wj)
        rows = np.flatnonzero(idx.year == ch["year"])
        if not len(rows):
            continue
        Wc.iloc[rows] = Wj.iloc[rows].to_numpy()
        Dc[rows] = Dj[rows]
        if prev != j:
            r0 = rows[0]
            Wc.iloc[r0] = _standing(Wj, Dj).iloc[r0].to_numpy()
            Dc[r0] = True
            if prev is not None:
                switches.append({"date": str(idx[r0].date()), "to": ch["params"]})
        prev = j
    return Wc, Dc, switches


# ── Monte Carlo ─────────────────────────────────────────────────────────────

def _stationary_bootstrap_idx(n: int, length: int, paths: int, mean_block: int, rng) -> np.ndarray:
    """Politis & Romano (1994): blocks of geometric length (mean `mean_block`), random starts, wrapping."""
    idx = np.empty((paths, length), dtype=np.int64)
    idx[:, 0] = rng.integers(0, n, paths)
    new_block = rng.random((paths, length)) < 1.0 / mean_block
    starts = rng.integers(0, n, (paths, length))
    for t in range(1, length):
        idx[:, t] = np.where(new_block[:, t], starts[:, t], (idx[:, t - 1] + 1) % n)
    return idx


def monte_carlo(ret: pd.Series, rf: Optional[pd.Series] = None, years: float = 10.0, paths: int = 2000,
                mean_block: int = 21, seed: int = 7, leverage_grid: Sequence[float] = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0),
                financing_spread: float = 0.01, dd_limit: float = 0.5, dd_prob: float = 0.05,
                max_leverage: float = 2.0) -> Dict[str, Any]:
    """Resample the strategy's daily (net) returns in blocks to simulate `paths` futures of `years`.
    Also scales the excess return by leverage L (financing at T-bill + spread above 1×) to find the
    growth-optimal (Kelly) leverage and the largest leverage keeping P(drawdown > dd_limit) ≤ dd_prob."""
    r = ret.dropna().to_numpy(float)
    rfv = (rf.reindex(ret.dropna().index).fillna(0.0).to_numpy(float) if rf is not None else np.zeros_like(r))
    if r.size < 250:
        raise ValueError("Need at least a year of returns for a Monte Carlo.")
    rng = np.random.default_rng(seed)
    H = int(round(years * TRADING_DAYS))
    paths = int(min(max(paths, 200), 5000))
    idx = _stationary_bootstrap_idx(r.size, H, paths, mean_block, rng)
    ex = r - rfv

    def sim(L: float):
        rr = rfv[idx] + L * ex[idx] - (max(L - 1, 0) * financing_spread / TRADING_DAYS)
        rr = np.clip(rr, -0.99, None)
        logw = np.cumsum(np.log1p(rr), axis=1)
        dd = logw - np.maximum.accumulate(logw, axis=1)
        return logw, 1 - np.exp(dd.min(axis=1))
    logw, mdd = sim(1.0)
    term = np.exp(logw[:, -1])
    cagr = term ** (1 / years) - 1
    step = max(1, H // 120)
    pts = list(range(step - 1, H, step))
    if pts[-1] != H - 1:
        pts.append(H - 1)
    q = np.percentile(np.exp(logw[:, pts]), [5, 25, 50, 75, 95], axis=0)
    fan = [{"year": round((t + 1) / TRADING_DAYS, 2), "p5": round(float(q[0, i]), 4), "p25": round(float(q[1, i]), 4),
            "p50": round(float(q[2, i]), 4), "p75": round(float(q[3, i]), 4), "p95": round(float(q[4, i]), 4)} for i, t in enumerate(pts)]
    hist_edges = np.linspace(np.percentile(cagr, 0.5), np.percentile(cagr, 99.5), 31)
    counts, edges = np.histogram(np.clip(cagr, hist_edges[0], hist_edges[-1]), bins=hist_edges)
    lev = []
    for L in leverage_grid:
        lw, md = sim(float(L))
        g = lw[:, -1] / years
        lev.append({"leverage": L, "median_cagr": round(float(np.expm1(np.median(g))), 4),
                    "p5_cagr": round(float(np.expm1(np.percentile(g, 5))), 4),
                    "p_dd": round(float((md > dd_limit).mean()), 4), "median_max_dd": round(float(np.median(md)), 4),
                    "p_loss": round(float((lw[:, -1] < 0).mean()), 4)})
    mu, var = float(ex.mean()), float(ex.var())
    kelly = mu / var if var > 0 else None
    safe = [x["leverage"] for x in lev if x["p_dd"] <= dd_prob and x["leverage"] <= max_leverage]
    best_g = max(lev, key=lambda x: x["median_cagr"])
    sharpe_ex = float(ex.mean() / ex.std(ddof=1) * math.sqrt(TRADING_DAYS)) if ex.std(ddof=1) > 0 else 0.0
    weak = False
    if kelly is None or kelly <= 0:
        rec = 0.0                                                # no positive excess return to lever
    else:
        rec = max(safe) if safe else min(leverage_grid)
        rec = min(rec, max(0.25, math.floor(kelly / 2 * 4) / 4))   # never above half-Kelly (estimation error)
        if sharpe_ex < 0.3:                                      # Kelly on a near-zero edge is mostly noise
            rec, weak = min(rec, 1.0), True
    return {
        "years": years, "paths": paths, "mean_block_days": mean_block, "based_on_days": int(r.size),
        "fan": fan,
        "cagr_pct": {p: round(float(np.percentile(cagr, p)), 4) for p in (5, 25, 50, 75, 95)},
        "max_dd_pct": {p: round(float(np.percentile(mdd, p)), 4) for p in (5, 50, 95)},
        "p_loss": round(float((term < 1).mean()), 4),
        "p_dd": {f"{int(x * 100)}": round(float((mdd > x).mean()), 4) for x in (0.1, 0.2, 0.3, 0.5)},
        "hist": [{"cagr": round(float((edges[i] + edges[i + 1]) / 2), 4), "count": int(counts[i])} for i in range(len(counts))],
        "leverage": lev, "kelly_full": None if kelly is None else round(kelly, 2),
        "growth_optimal_leverage": best_g["leverage"], "recommended_leverage": rec,
        "rule": (f"Largest leverage with P(drawdown > {dd_limit:.0%}) ≤ {dd_prob:.0%}, capped at {max_leverage}× and at half-Kelly"
                 + ("; capped at 1× because the excess-return Sharpe is below 0.3 — too weak an edge to lever." if weak else ".")),
        "sharpe_excess": round(sharpe_ex, 3),
    }


# ── Running user code ───────────────────────────────────────────────────────
LIVE_FIELDS = ("asof", "options", "equity", "available_cash", "reserved_risk", "option_positions",
               "pending_option_orders", "positions", "orders", "quotes", "equity_high_watermark", "variance_forecasts")
LIVE_HINT = ("This looks like a live order generator: it reads a market snapshot (data.{field}) and returns orders. "
             "The Quant Lab backtests instead: strategy(data) returns target weights for every date, from daily data "
             "and modelled options (OPTIONS = [...], data.opt). Live option quotes are not available from free data. "
             "See 'Index put credit spreads' in the Strategy library for a backtestable version of a spread strategy.")


def universe_error(code: str) -> str:
    """Why a strategy has no usable UNIVERSE — with the live-snapshot case explained."""
    import re
    m = re.search(r"\bdata\.(" + "|".join(LIVE_FIELDS) + r")\b", code or "")
    if m:
        return "UNIVERSE is missing. " + LIVE_HINT.format(field=m.group(1))
    return (f"UNIVERSE is missing or empty: add UNIVERSE = [\"SPY\", …] (up to {LARGE_UNIVERSE_LIMIT} tickers; more than "
            f"{UNIVERSE_LIMIT} run as a server job), or TRADABLE_UNIVERSE = \"GLOBAL\", or OPTIONS = [...] (their "
            "underlyings become the universe).")


FUNDAMENTAL_NAMES = ("eps_ttm", "sales_ttm", "net_income_ttm", "gross_profit_ttm", "fcf_ttm", "book_value",
                     "total_assets", "total_liabilities", "shares", "market_cap", "earnings_yield", "book_to_price",
                     "sales_to_price", "fcf_yield", "roe", "gross_profitability", "leverage")


def fundamentals_spec(x: Any) -> List[str]:
    """FUNDAMENTALS = True (all) or a list of names → the names to load."""
    if x is True:
        return list(FUNDAMENTAL_NAMES)
    if not x:
        return []
    if isinstance(x, str):
        x = [x]
    return [str(n) for n in x]


def run_costs(st: Dict[str, Any], costs: Optional[Dict[str, float]]) -> Dict[str, float]:
    """Execution settings for a run: the strategy's own FX_HEDGE unless the caller sets fx_hedge explicitly."""
    out = dict(costs or {})
    if st.get("fx_hedge") is not None and "fx_hedge" not in out:
        out["fx_hedge"] = st["fx_hedge"]
    qc = st.get("qc") or {}
    if qc.get("capital") and "capital" not in out:                   # set_cash(...)
        out["capital"] = qc["capital"]
    if qc.get("broker") == "ibkr" and "commission_per_share" not in out:   # set_brokerage_model(InteractiveBrokers…)
        out.update({"commission_bps": 0.0, "commission_per_share": 0.005, "commission_min": 1.0, "commission_max_pct": 0.01})
    elif qc.get("broker") == "alpaca" and "commission_per_share" not in out:
        out.update({"commission_bps": 0.0, "commission_per_share": 0.0, "commission_min": 0.0, "spread_mult": 1.15})
    return out


def until(data: "Data", end: Optional[str]) -> "Data":
    """The data up to and including `end` (set_end_date) — nothing after it is visible."""
    if not end:
        return data
    n = int(data.close.index.searchsorted(pd.Timestamp(end), side="right"))
    return data if n >= len(data.close) else data.truncate(n)


def tradable_spec(x: Any) -> Optional[str]:
    """Canonical TRADABLE_UNIVERSE: a name, or several joined with '+' ("JP+HK"; a list works too)."""
    if not x:
        return None
    parts = x if isinstance(x, (list, tuple)) else str(x).split("+")
    toks = sorted({str(t).strip().upper().replace(" ", "_").replace("-", "_") for t in parts if str(t).strip()})
    return "+".join(toks) or None


def load_strategy(code: str, namespace: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Execute strategy source and return its UNIVERSE / START / PARAMS / HOLDOUT / strategy. (The server
    never calls this on user code outside the sandbox; the browser runs it in Pyodide.)"""
    import hashlib
    ns: Dict[str, Any] = {"np": np, "pd": pd, "math": math, "ewma_vol": ewma_vol, "momentum": momentum,
                          "hold_monthly": hold_monthly, "hold_weekly": hold_weekly, "normalize_gross": normalize_gross,
                          "vol_target": vol_target, "on_rolls": on_rolls, "cov_shrink": cov_shrink, "optimize": optimize,
                          "min_variance": min_variance, "risk_parity": risk_parity, "style_exposures": style_exposures,
                          **{k: globals()[k] for k in INDICATORS}}
    if namespace:
        ns.update(namespace)
    qc = None
    if _qc is not None and "QCAlgorithm" in code:
        import ast as _ast
        if _qc.find_class(_ast.parse(code)) is not None:
            qc = _qc.static_header(code)
            ns.update(_qc.NAMES)
            code = _qc.prepare_source(code)
    exec(compile(code, "<strategy>", "exec"), ns)                    # noqa: S102 — see docstring
    fn = ns.get("strategy")
    ob = ns.get("on_bar")
    if qc is not None:                                               # a QuantConnect-style algorithm class
        fn, ob = None, _qc.adapter(ns[qc["class"]], qc)
        ns.setdefault("UNIVERSE", qc["universe"] or [qc.get("benchmark") or "SPY"])
        ns.setdefault("START", qc.get("start") or "2015-01-01")
        ns.setdefault("BENCHMARK", qc.get("benchmark") or "SPY")
        if qc["dynamic_universe"]:
            ns.setdefault("TRADABLE_UNIVERSE", "SP500_PIT")
        if qc.get("fundamentals"):
            ns.setdefault("FUNDAMENTALS", qc["fundamentals"])
    if not callable(fn) and not callable(ob):
        raise ValueError("Define strategy(data, **params) returning target weights, or on_bar(ctx, **params) for an "
                         "event-driven strategy.")
    uni = ns.get("UNIVERSE")
    if isinstance(uni, str):
        uni = [uni]
    if not uni and ns.get("OPTIONS"):                           # an options-only strategy: trade its underlyings
        uni = list(dict.fromkeys(str(o.get("underlying", "")).upper() for o in ns["OPTIONS"] if isinstance(o, dict)))
    if not uni:
        raise ValueError(universe_error(code))
    if not isinstance(uni, (list, tuple)) or len(uni) > LARGE_UNIVERSE_LIMIT:
        raise ValueError(f"Set UNIVERSE to a list of 1–{LARGE_UNIVERSE_LIMIT} tickers (more than {UNIVERSE_LIMIT} run "
                         "as a server job).")
    holdout = ns.get("HOLDOUT")
    tradable = ns.get("TRADABLE_UNIVERSE")
    account = str(ns.get("ACCOUNT_CURRENCY") or "USD").strip().upper()
    hedge = ns.get("FX_HEDGE")
    return {"strategy": fn if callable(fn) else None, "on_bar": ob if callable(ob) else None,
            "setup": ns.get("setup") if callable(ns.get("setup")) else None,
            "tradable": tradable_spec(tradable), "account": account,
            "fx_hedge": float(hedge) if isinstance(hedge, (int, float)) and not isinstance(hedge, bool) else None,
            "options": list(ns.get("OPTIONS") or []),
            "fundamentals": fundamentals_spec(ns.get("FUNDAMENTALS")),
            "signal": ns.get("signal") if callable(ns.get("signal")) else None,
            "universe": [str(u).upper() for u in uni], "start": str(ns.get("START") or "2005-01-01")[:10],
            "params": ns.get("PARAMS") or {}, "benchmark": str(ns.get("BENCHMARK") or "SPY").upper(),
            "holdout": str(holdout)[:10] if holdout else None,
            "code_hash": hashlib.sha256(code.encode()).hexdigest()[:16],
            "qc": qc, "end": (qc or {}).get("end")}


def run_weights(fn: Callable, data: Data, params: Dict[str, Any]) -> pd.DataFrame:
    w = fn(data, **params)
    if isinstance(w, pd.Series):
        w = w.to_frame()
    if not isinstance(w, pd.DataFrame):
        raise ValueError("strategy() must return a DataFrame of weights (dates × tickers).")
    unknown = [c for c in w.columns if c not in data.close.columns]
    if unknown:
        raise ValueError(f"Weights for tickers not in UNIVERSE: {', '.join(map(str, unknown[:5]))}")
    if not w.index.equals(data.close.index):
        w = w.reindex(data.close.index)
    return w.replace([np.inf, -np.inf], np.nan)


def exposure_breakdown(holdings: Dict[str, float], instruments: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """Net weight (fraction of NAV) of the current holdings by listing currency, country and sector — the
    currency line is the account's FX exposure."""
    out: Dict[str, Dict[str, float]] = {"currency": {}, "country": {}, "sector": {}}
    for t, w in (holdings or {}).items():
        i = instruments.get(t) or {}
        for k in out:
            g = i.get(k) or "—"
            out[k][g] = out[k].get(g, 0.0) + float(w)
    return {k: {g: round(v, 4) for g, v in sorted(d.items(), key=lambda x: -abs(x[1]))} for k, d in out.items()}


def _data_hash(data: Data) -> str:
    import hashlib
    h = hashlib.sha256()
    h.update(np.ascontiguousarray(np.round(np.nan_to_num(data.close.to_numpy(float)), 6)).tobytes())
    h.update(",".join(data.tickers).encode())
    h.update(str(data.close.index[0]).encode() + str(data.close.index[-1]).encode())
    return h.hexdigest()[:16]


def _segment(ret: pd.Series, rf: pd.Series, a: Optional[str], b: Optional[str]) -> Dict[str, Any]:
    s = ret
    if a:
        s = s[s.index >= pd.Timestamp(a)]
    if b:
        s = s[s.index < pd.Timestamp(b)]
    return metrics(s, rf)


# ── Portfolio construction helpers for strategy code ─────────────────────────
def cov_shrink(returns: pd.DataFrame) -> pd.DataFrame:
    """Ledoit–Wolf (2004) shrinkage covariance of daily returns (towards a scaled identity) — the sample
    covariance of many assets over few days is too noisy to optimise on. Missing returns count as 0."""
    X = returns.fillna(0.0).to_numpy(float)
    n, p = X.shape
    if n < 2:
        return pd.DataFrame(np.eye(p) * 1e-4, index=returns.columns, columns=returns.columns)
    X = X - X.mean(axis=0)
    S = X.T @ X / n
    mu = np.trace(S) / p
    d2 = ((S - mu * np.eye(p)) ** 2).sum() / p
    b2 = ((np.einsum("ij,ij->i", X, X) ** 2).sum() - n * (S ** 2).sum()) / (n * n * p)
    shrink = float(min(max(b2, 0.0), d2) / d2) if d2 > 0 else 1.0
    return pd.DataFrame(shrink * mu * np.eye(p) + (1 - shrink) * S, index=returns.columns, columns=returns.columns)


def _capped_simplex(v: np.ndarray, total: float, cap: float) -> np.ndarray:  # noqa: D401 — kept for callers
    """Euclidean projection onto {0 ≤ w ≤ cap, Σw = total}."""
    cap = max(cap, total / len(v) + 1e-12)
    lo, hi = v.min() - cap, v.max()
    for _ in range(100):
        th = (lo + hi) / 2
        if np.clip(v - th, 0, cap).sum() > total:
            lo = th
        else:
            hi = th
    return np.clip(v - (lo + hi) / 2, 0, cap)


def _qp(P: np.ndarray, q: np.ndarray, A: np.ndarray, lo: np.ndarray, hi: np.ndarray, iterations: int = 4000,
        rho: float = 0.1, sigma: float = 1e-6, alpha: float = 1.6, tol: float = 1e-7) -> np.ndarray:
    """min ½x'Px + q'x subject to lo ≤ Ax ≤ hi — ADMM as in OSQP (Stellato et al. 2020), numpy only. Equality rows
    (lo = hi) get a 1000× penalty, as OSQP does."""
    n = P.shape[0]
    r = np.where(np.isclose(lo, hi), rho * 1e3, rho)
    K = P + sigma * np.eye(n) + A.T @ (r[:, None] * A)
    Kinv = np.linalg.inv(K)
    x, z, y = np.zeros(n), np.clip(np.zeros(A.shape[0]), lo, hi), np.zeros(A.shape[0])
    for _ in range(iterations):
        xt = Kinv @ (sigma * x - q + A.T @ (r * z - y))
        zt = A @ xt
        x_new = alpha * xt + (1 - alpha) * x
        z_new = np.clip(alpha * zt + (1 - alpha) * z + y / r, lo, hi)
        y = y + r * (alpha * zt + (1 - alpha) * z - z_new)
        prim = np.abs(A @ x_new - z_new).max()
        dual = np.abs(x_new - x).max()
        x, z = x_new, z_new
        if prim < tol and dual < tol:
            break
    return x


def optimize(expected: pd.Series, cov: pd.DataFrame, risk_aversion: float = 5.0, max_weight: float = 0.10,
             long_only: bool = True, gross: float = 1.0, net: float = 0.0, prev: Optional[pd.Series] = None,
             turnover_penalty: float = 0.0, groups: Optional[pd.Series] = None, group_max: Optional[float] = None,
             exposures: Optional[pd.DataFrame] = None, factor_bounds: Optional[Dict[str, Sequence[float]]] = None) -> pd.Series:
    """Mean–variance weights: maximise expected'w − risk_aversion/2 · w'Σw − turnover_penalty/2 · ‖w − prev‖²
    (quadratic trading-cost proxy). Long-only: 0 ≤ w ≤ max_weight, Σw = gross. Long–short: |w| ≤ max_weight,
    Σ|w| ≤ gross, Σw = net. `groups` (e.g. data.info["sector"]) with `group_max` caps each group's net weight in
    absolute value; `exposures` (tickers × factors, e.g. style_exposures(data, date)) with `factor_bounds`
    {"momentum": (-0.1, 0.1)} keeps the book's factor exposures in those bands. Solved exactly as a quadratic
    programme (ADMM, numpy only — runs in the browser and the sandbox)."""
    names = [c for c in expected.index if c in cov.index]
    n = len(names)
    if n == 0:
        return pd.Series(dtype=float)
    mu = expected.reindex(names).fillna(0.0).to_numpy(float)
    C = cov.loc[names, names].to_numpy(float)
    w0 = prev.reindex(names).fillna(0.0).to_numpy(float) if prev is not None else np.zeros(n)
    Pw = risk_aversion * C + turnover_penalty * np.eye(n)
    qw = -(mu + turnover_penalty * w0)
    lin = []                                                    # (row on w, lo, hi)
    if groups is not None and group_max is not None:
        g = groups.reindex(names).fillna("—").to_numpy()
        for k in sorted(set(g)):
            lin.append(((g == k).astype(float), -group_max, group_max))
    if exposures is not None and factor_bounds:
        ex = exposures.reindex(names)
        for k, (lo_, hi_) in factor_bounds.items():
            lin.append((ex[k].fillna(0.0).to_numpy(float), float(lo_), float(hi_)))
    if long_only:
        rows = [np.eye(n), np.ones((1, n))] + [r_[None, :] for r_, _, _ in lin]
        lo = np.concatenate([np.zeros(n), [gross], [l_ for _, l_, _ in lin]])
        hi = np.concatenate([np.full(n, max_weight), [gross], [h_ for _, _, h_ in lin]])
        x = _qp(Pw, qw, np.vstack(rows), lo, hi)
        w = np.clip(x, 0.0, max_weight)
    else:                                                       # w = p − m with p, m ≥ 0
        P2 = np.block([[Pw, -Pw], [-Pw, Pw]])
        q2 = np.concatenate([qw, -qw])
        D = np.hstack([np.eye(n), -np.eye(n)])
        rows = [np.eye(2 * n), np.hstack([np.ones(n), -np.ones(n)])[None, :], np.ones((1, 2 * n))]
        rows += [(r_ @ D)[None, :] for r_, _, _ in lin]
        lo = np.concatenate([np.zeros(2 * n), [net], [0.0], [l_ for _, l_, _ in lin]])
        hi = np.concatenate([np.full(2 * n, max_weight), [net], [gross], [h_ for _, _, h_ in lin]])
        x = _qp(P2, q2, np.vstack(rows), lo, hi)
        w = np.clip(x[:n] - x[n:], -max_weight, max_weight)
    return pd.Series(w, index=names)


def min_variance(cov: pd.DataFrame, max_weight: float = 1.0, long_only: bool = True) -> pd.Series:
    """Minimum-variance weights (fully invested)."""
    return optimize(pd.Series(0.0, index=cov.index), cov, risk_aversion=1.0, max_weight=max_weight,
                    long_only=long_only, gross=1.0, net=1.0)


def risk_parity(cov: pd.DataFrame, iterations: int = 500) -> pd.Series:
    """Equal risk contribution weights, long-only, summing to 1 (Maillard, Roncalli & Teïletche 2010)."""
    C = cov.to_numpy(float)
    w = 1 / np.sqrt(np.maximum(np.diag(C), 1e-12))
    w /= w.sum()
    for _ in range(iterations):
        rc = w * (C @ w)
        tgt = rc.sum() / len(w)
        w_new = w * np.sqrt(tgt / np.maximum(rc, 1e-18))
        w_new /= w_new.sum()
        if np.abs(w_new - w).max() < 1e-10:
            w = w_new
            break
        w = w_new
    return pd.Series(w, index=cov.index)


# ── Validation ───────────────────────────────────────────────────────────────
class _Mute:
    def write(self, s):
        return len(s)

    def flush(self):
        pass


def _quiet(f: Callable, *a, **k):
    """Run a check without repeating the strategy's print() output."""
    import contextlib
    with contextlib.redirect_stdout(_Mute()):
        return f(*a, **k)


def causality_check(fn: Callable, data: Data, params: Dict[str, Any], full: pd.DataFrame,
                    cuts: Sequence[float] = (0.6, 0.85), runner: Optional[Callable] = None) -> Dict[str, Any]:
    """Look-ahead detector: re-run the strategy on the data as it stood at earlier dates and compare its decisions
    with the full-history run. A causal strategy makes exactly the same decisions on the dates both runs share; any
    difference means a decision used data from after its date (e.g. a full-sample mean, shift(-1), or bfill)."""
    T = len(data.close)
    out: Dict[str, Any] = {"passed": True, "cuts": []}
    for f in cuts:
        n = int(T * f)
        if n < 260:
            continue
        cut_date = str(data.close.index[n - 1].date())
        try:
            part = (runner or run_weights)(fn, data.truncate(n), params)
        except Exception as e:                                  # noqa: BLE001 — cannot check; say so
            out["cuts"].append({"as_of": cut_date, "checked": False, "error": f"{type(e).__name__}: {str(e)[:160]}"})
            continue
        a = full.iloc[:n].reindex(columns=part.columns.union(full.columns))
        b = part.reindex(index=a.index, columns=a.columns)
        A, B = a.to_numpy(float), b.to_numpy(float)
        both_nan = np.isnan(A) & np.isnan(B)
        diff = ~both_nan & ~(np.isclose(np.nan_to_num(A, nan=1e300), np.nan_to_num(B, nan=1e300), rtol=1e-6, atol=1e-9))
        item = {"as_of": cut_date, "checked": True, "differences": int(diff.sum())}
        if diff.any():
            r, c = np.argwhere(diff)[0]
            item["first"] = {"date": str(a.index[r].date()), "ticker": str(a.columns[c]),
                             "full_history": None if np.isnan(A[r, c]) else round(float(A[r, c]), 6),
                             "data_to_date": None if np.isnan(B[r, c]) else round(float(B[r, c]), 6)}
            out["passed"] = False
        out["cuts"].append(item)
    if not any(c.get("checked") for c in out["cuts"]):
        out["passed"] = None
    out["note"] = ("Decisions were recomputed from the data available at each check date and matched the full-history "
                   "run." if out["passed"] else
                   "Decisions changed when later data was removed: the backtest uses information from the future "
                   "(look-ahead bias). Unseeded randomness also shows up here." if out["passed"] is False else
                   "Not enough history to check.")
    return out


def pbo(series: List[pd.Series], splits: int = 10) -> Optional[Dict[str, Any]]:
    """Probability of backtest overfitting by combinatorially symmetric cross-validation (Bailey, Borwein, López de
    Prado & Zhu 2017): split the history into `splits` blocks; for every half/half split, pick the parameter set
    with the best in-sample Sharpe and see where it ranks out of sample. PBO = share of splits where the in-sample
    winner lands in the bottom half out of sample."""
    import itertools
    R = pd.concat(series, axis=1).dropna()
    N = R.shape[1]
    if N < 2 or len(R) < splits * 21:
        return None
    X = R.to_numpy(float)
    if np.allclose(X, X[:, :1], atol=1e-12):
        return {"pbo": None, "candidates": N, "note": "Every parameter set gives the same returns — nothing to overfit."}
    blocks = np.array_split(np.arange(len(R)), splits)
    lam, omegas, oos_loss = [], [], []
    for comb in itertools.combinations(range(splits), splits // 2):
        ins = np.concatenate([blocks[i] for i in comb])
        oos = np.concatenate([blocks[i] for i in range(splits) if i not in comb])
        sh = lambda x: x.mean(axis=0) / np.where(x.std(axis=0) > 0, x.std(axis=0), np.inf)
        s_in, s_out = sh(X[ins]), sh(X[oos])
        best = int(np.argmax(s_in))
        rank = (s_out < s_out[best]).sum() + 0.5 * ((s_out == s_out[best]).sum() - 1) + 1
        omega = rank / (N + 1)
        lam.append(math.log(omega / (1 - omega)))
        omegas.append(omega)
        oos_loss.append(float(s_out[best]) < 0)
    lam = np.array(lam)
    p = float((lam <= 0).mean())
    return {"pbo": round(p, 3), "splits": int(len(lam)), "candidates": N,
            "median_oos_percentile": round(float(np.median(omegas)), 3),
            "prob_oos_loss": round(float(np.mean(oos_loss)), 3),
            "note": ("Low risk of overfitting the parameter choice" if p < 0.2 else
                     "Moderate: the best in-sample choice is often mediocre out of sample" if p < 0.5 else
                     "High: picking the best backtest is no better than picking at random")}


def cpcv(series: List[pd.Series], groups: int = 6, test_groups: int = 2, embargo: int = 5) -> Optional[Dict[str, Any]]:
    """Combinatorial purged cross-validation of the parameter choice (López de Prado 2018, ch. 12): split the history
    into `groups` blocks; for every choice of `test_groups` blocks, pick the best parameter set on the remaining
    blocks (dropping `embargo` days next to each test block), and record its returns on the test blocks. Stitching
    those test blocks gives C(groups−1, test_groups−1) full out-of-sample paths — a distribution, not one number."""
    import itertools
    R = pd.concat(series, axis=1).dropna()
    N = R.shape[1]
    if N < 2 or len(R) < groups * 60:
        return None
    X = R.to_numpy(float)
    blocks = np.array_split(np.arange(len(R)), groups)
    splits = list(itertools.combinations(range(groups), test_groups))
    n_paths = math.comb(groups - 1, test_groups - 1)
    seen = {g: 0 for g in range(groups)}
    paths = [np.full(len(R), np.nan) for _ in range(n_paths)]
    for comb in splits:
        test = np.concatenate([blocks[g] for g in comb])
        ban = set()
        for g in comb:
            a, z = blocks[g][0], blocks[g][-1]
            ban |= set(range(max(0, a - embargo), min(len(R), z + embargo + 1)))
        train = np.array([i for i in range(len(R)) if i not in ban])
        sd = X[train].std(axis=0)
        best = int(np.argmax(X[train].mean(axis=0) / np.where(sd > 0, sd, np.inf)))
        for g in comb:
            paths[seen[g]][blocks[g]] = X[blocks[g], best]
            seen[g] += 1
    sh = [float(np.nanmean(p) / np.nanstd(p, ddof=1) * math.sqrt(TRADING_DAYS)) for p in paths if np.nanstd(p) > 0]
    if not sh:
        return None
    return {"paths": len(sh), "sharpe_mean": round(float(np.mean(sh)), 3), "sharpe_std": round(float(np.std(sh)), 3),
            "sharpe_min": round(float(np.min(sh)), 3), "sharpe_max": round(float(np.max(sh)), 3),
            "share_positive": round(float(np.mean(np.array(sh) > 0)), 3), "groups": groups, "test_groups": test_groups,
            "embargo_days": embargo, "path_sharpes": [round(x, 3) for x in sh],
            "note": "Each path is a full out-of-sample history built from parameter choices made without its test blocks "
                    "(and with an embargo next to them); the spread of their Sharpe ratios is the honest range."}


def capacity_curve(rerun: Callable[[Dict[str, float]], Dict[str, Any]], data: Data, costs: Optional[Dict[str, float]],
                   levels: Sequence[float] = (1e6, 1e7, 1e8, 1e9)) -> Dict[str, Any]:
    """Net results of the same decisions at different account sizes: impact, volume limits and board lots grow with
    capital. Capacity ≈ the largest size that keeps at least half the smallest size's Sharpe ratio."""
    rows = []
    for cap in levels:
        r = rerun({**(costs or {}), "capital": float(cap)})
        m = metrics(r["ret"], data.rf)
        cs = cost_summary(r)
        rows.append({"capital": cap, "cagr": m.get("cagr"), "sharpe": m.get("sharpe"), "trading_costs": cs["total_trading"],
                     "impact": cs["impact"], "capped_days": r["execution"]["participation_capped_days"],
                     "lot_residual": r["execution"]["lot_residual_avg"]})
    base = rows[0]["sharpe"]
    ok = [r["capital"] for r in rows if base and base > 0 and r["sharpe"] is not None and r["sharpe"] >= 0.5 * base]
    return {"levels": rows, "capacity": max(ok) if ok else None,
            "note": "Same decisions re-simulated at each size; capacity = largest tested size keeping ≥ half the Sharpe "
                    "ratio of the smallest (a lower bound when every size passes)."}


# ── Attribution and risk ─────────────────────────────────────────────────────
def trade_report(res: Dict[str, Any], data: Data, capital: float) -> Dict[str, Any]:
    """Order log and round-trip trade statistics (QuantConnect-style): every fill with its quantity at `capital`,
    price and costs; closed trades by average-cost accounting; win rate, profit-loss ratio, expectancy, holding time."""
    idx, cols = data.close.index, data.tickers
    fills = res.get("fills") or []
    tr = res.get("trades") or []
    pnl = np.array([x["pnl"] for x in tr], float)
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    stats = {"orders": len(fills), "closed_trades": len(tr), "open_trades": len(res.get("open_trades") or []),
             "win_rate": round(float((pnl > 0).mean()), 4) if len(pnl) else None,
             "avg_win": round(float(wins.mean()), 2) if len(wins) else None,
             "avg_loss": round(float(losses.mean()), 2) if len(losses) else None,
             "profit_loss_ratio": round(float(wins.mean() / -losses.mean()), 3) if len(wins) and len(losses) else None,
             "profit_factor": round(float(wins.sum() / -losses.sum()), 3) if len(wins) and len(losses) and losses.sum() else None,
             "expectancy": round(float(pnl.mean()), 2) if len(pnl) else None,
             "avg_days_held": round(float(np.mean([x["days"] for x in tr])), 1) if tr else None,
             "largest_win": round(float(pnl.max()), 2) if len(pnl) else None, "largest_loss": round(float(pnl.min()), 2) if len(pnl) else None,
             "total_costs": round(float(sum(f[4] for f in fills) * capital), 2),
             "long_trades": sum(1 for x in tr if x["side"] == "long"), "short_trades": sum(1 for x in tr if x["side"] == "short")}
    orders = [{"date": str(idx[t].date()), "ticker": cols[j], "side": "buy" if dq > 0 else "sell",
               "quantity": round(abs(dq) * capital, 4), "price": round(price, 6), "value": round(abs(dq) * price * capital, 2),
               "costs": round(cost * capital, 2), "type": kind} for t, j, dq, price, cost, kind in fills[-2000:]]
    recent = [{**x, "pnl": round(x["pnl"], 2), "return": round(x["return"], 4), "costs": round(x["costs"], 2)} for x in tr[-300:]]
    return {"stats": stats, "orders": orders, "orders_total": len(fills), "closed": recent, "open": (res.get("open_trades") or [])[:100],
            "note": f"Quantities and money at the run's capital ({capital:,.0f} {data.account_currency}); prices are adjusted "
                    "(dividends reinvested), so quantities are adjusted shares. Trades: average-cost, closed when the position "
                    "returns to zero or flips; P&L after that trade's costs."}


def attribution(res: Dict[str, Any], data: Data) -> Dict[str, Any]:
    """Where the return came from: each holding's P&L (and, for foreign listings, how much of it was the currency),
    grouped by sector, country and currency, next to costs, financing, taxes and the FX hedge. Sums of daily
    contributions (arithmetic, fraction of NAV), shown per year."""
    pnl, fx = res["attribution"]["pnl"], res["attribution"]["fx"]
    rr = res["ret"]
    yr = 1.0 / years_between(rr.index[0], rr.index[-1]) if len(rr) > 1 else 1.0
    info = data.instruments
    groups: Dict[str, Dict[str, float]] = {"sector": {}, "country": {}, "currency": {}}
    for t, v in pnl.items():
        i = info.get(t) or {}
        for k in groups:
            g = i.get(k) or "—"
            groups[k][g] = groups[k].get(g, 0.0) + v * yr
    srt = sorted(pnl.items(), key=lambda x: -x[1])
    row = lambda t, v: {"ticker": t, "name": (info.get(t) or {}).get("name"), "per_year": round(v * yr, 5),
                        "currency_part": round(fx.get(t, 0.0) * yr, 5)}
    sec, fxt = sum(pnl.values()) * yr, sum(fx.values()) * yr
    tot = lambda k: round(float(res[k].sum()) * yr, 5) if k in res else 0.0
    b = res.get("brinson") or {}
    brinson = None
    if b.get("groups"):
        rows = [{"group": g, "allocation": round(a * yr, 5), "selection": round(sl * yr, 5), "interaction": round(it * yr, 5)}
                for g, a, sl, it in zip(b["groups"], b["alloc"], b["select"], b["inter"])]
        rows.sort(key=lambda r: -abs(r["allocation"] + r["selection"] + r["interaction"]))
        btot = {k: round(sum(r[k] for r in rows), 5) for k in ("allocation", "selection", "interaction")}
        brinson = {"by": b["by"], "rows": rows[:15], "total": {**btot, "cash": round(b["cash"] * yr, 5)},
                   "note": "Brinson–Fachler against the equal-weight universe (same names), before costs: allocation = "
                           "over/underweighting groups that beat/lagged the universe; selection = picking better names "
                           "inside each group; cash = not being invested. Arithmetic, per year."}
    return {"brinson": brinson, "per_year": {"securities": round(sec, 5), "of_which_currency": round(fxt, 5), "of_which_local": round(sec - fxt, 5),
                         "trading_costs": -round(sum(tot(k) for k in ("commission", "spread", "impact", "fees")), 5),
                         "borrow": -tot("borrow"), "cash_interest": tot("financing"), "dividend_tax": -tot("dividend_tax"),
                         "fx_hedge": tot("hedge"), "total": round(float(res["ret"].sum()) * yr, 5)},
            "top": [row(t, v) for t, v in srt[:10] if v > 0], "bottom": [row(t, v) for t, v in srt[::-1][:10] if v < 0],
            "by": {k: {g: round(v, 5) for g, v in sorted(d.items(), key=lambda x: -abs(x[1]))[:12]} for k, d in groups.items()},
            "note": "Sums of daily contributions (fraction of NAV, arithmetic) per year — they add up to the average daily "
                    "return × 252, not to CAGR. Currency part: each foreign holding's value × its currency's daily move."}


STRESS = [("Global financial crisis", "2008-09-01", "2009-03-09"), ("Euro debt crisis", "2011-07-22", "2011-10-03"),
          ("China deval / oil crash", "2015-08-10", "2016-02-11"), ("Volmageddon", "2018-01-26", "2018-02-08"),
          ("Q4 2018 sell-off", "2018-09-20", "2018-12-24"), ("Covid crash", "2020-02-19", "2020-03-23"),
          ("2022 rate shock", "2022-01-03", "2022-10-12"), ("Yen carry unwind", "2024-07-16", "2024-08-05")]


def risk_model(data: Data, holdings: Dict[str, float], benchmark: Optional[pd.Series] = None,
               lookback: int = 252) -> Optional[Dict[str, Any]]:
    """Ex-ante risk of today's book: shrinkage covariance of the last year of daily returns (options as their
    delta-equivalent stock exposure), volatility, beta, 99% VaR / expected shortfall (parametric and historical),
    each position's and group's share of risk, concentration, and today's book replayed through past crises."""
    h = pd.Series({k: float(v) for k, v in (holdings or {}).items()})
    if h.empty:
        return None
    if "elasticity" in data.opt:
        for name in [x for x in h.index if x in data.option_names]:
            u = (data.instruments.get(name) or {}).get("underlying")
            el = data.opt["elasticity"][name].dropna()
            if u and len(el):
                h[u] = h.get(u, 0.0) + h[name] * float(el.iloc[-1])
            h = h.drop(name)
    names = [x for x in h.index if x in data.close.columns and abs(h[x]) > 1e-6]
    if not names:
        return None
    px = data.close[names]
    R = px.pct_change(fill_method=None).where(data.observed[names])
    Rl = R.iloc[-lookback:]
    C = cov_shrink(Rl).to_numpy()
    w = h[names].to_numpy(float)
    var_d = float(w @ C @ w)
    sd = math.sqrt(max(var_d, 0.0))
    mrc = C @ w / sd if sd > 0 else np.zeros(len(w))
    share = w * mrc / sd if sd > 0 else np.zeros(len(w))
    info = data.instruments
    grp = {k: {} for k in ("sector", "country", "currency")}
    for t, s_ in zip(names, share):
        for k in grp:
            g = (info.get(t) or {}).get(k) or "—"
            grp[k][g] = grp[k].get(g, 0.0) + float(s_)
    hist = (R.fillna(0.0).iloc[-500:] @ w)
    q = float(np.quantile(hist, 0.01)) if len(hist) > 50 else None
    es = float(hist[hist <= q].mean()) if q is not None else None
    beta = None
    if benchmark is not None:
        b = benchmark.reindex(R.index).pct_change(fill_method=None).iloc[-lookback:]
        port = Rl.fillna(0.0) @ w
        ok = b.notna()
        if ok.sum() > 60 and b[ok].var() > 0:
            beta = float(np.cov(port[ok], b[ok])[0, 1] / b[ok].var())
    stress = []
    allr = data.close.pct_change(fill_method=None).where(data.observed)
    for nm, a, z in STRESS:
        win = allr.loc[a:z]
        if len(win) < 3:
            continue
        cum = (1 + win.fillna(0.0)).prod() - 1
        have = [t for t in names if win[t].notna().sum() >= 0.8 * len(win)]
        proxy = float(cum[have].mean()) if have else (float(cum.mean()) if len(cum) else 0.0)
        ret = float(sum(h[t] * (cum[t] if t in have else proxy) for t in names))
        bm = None
        if benchmark is not None:
            bw = benchmark.loc[a:z].dropna()
            bm = float(bw.iloc[-1] / bw.iloc[0] - 1) if len(bw) > 1 else None
        stress.append({"scenario": nm, "start": a, "end": z, "book": round(ret, 4), "benchmark": None if bm is None else round(bm, 4),
                       "coverage": round(float(np.abs(h[have]).sum() / np.abs(h[names]).sum()), 3) if have else 0.0})
    top = sorted(zip(names, w, share), key=lambda x: -abs(x[2]))[:12]
    return {"vol": round(sd * math.sqrt(TRADING_DAYS), 4), "beta": None if beta is None else round(beta, 3),
            "var99_1d": round(2.326 * sd, 4), "es99_1d": round(2.665 * sd, 4),
            "hist_var99_1d": None if q is None else round(-q, 4), "hist_es99_1d": None if es is None else round(-es, 4),
            "gross": round(float(np.abs(w).sum()), 3), "net": round(float(w.sum()), 3),
            "effective_positions": round(float(1 / (np.square(w / np.abs(w).sum())).sum()), 1) if np.abs(w).sum() > 0 else None,
            "positions": [{"ticker": t, "weight": round(float(x), 4), "risk_share": round(float(s_), 4)} for t, x, s_ in top],
            "risk_by": {k: {g: round(v, 4) for g, v in sorted(d.items(), key=lambda x: -abs(x[1]))[:12]} for k, d in grp.items()},
            "stress": stress, "lookback_days": int(min(lookback, len(Rl))),
            "note": "Ex-ante: today's holdings with a Ledoit–Wolf covariance of the last year's daily returns. Options enter "
                    "as delta-equivalent stock (first-order). Stress: today's book through each episode with the returns "
                    "its holdings had then; holdings without history then take the average mover (coverage shows how much "
                    "of the book had its own history)."}


# ── Fundamental factor risk model (Barra-style) ──────────────────────────────
STYLE_FACTORS = ("momentum", "volatility", "size", "value", "quality")


def _z(x: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional z-score per date, winsorised at ±3."""
    z = x.sub(x.mean(axis=1), axis=0).div(x.std(axis=1).replace(0, np.nan), axis=0)
    return z.clip(-3, 3)


def style_frames(data: Data) -> Dict[str, pd.DataFrame]:
    """Daily style exposures (z-scores, causal): momentum (12–1 month return), volatility (63-day), size (log market
    value — or log traded value without fundamentals), value (book ÷ price) and quality (gross profit ÷ assets) when
    FUNDAMENTALS are loaded."""
    px = data.close.where(data.observed).ffill()
    r = px.pct_change(fill_method=None)
    out = {"momentum": _z(px.shift(21) / px.shift(252) - 1),
           "volatility": _z(r.rolling(63, min_periods=40).std())}
    usd = data.close.mul(data.usd_per_unit, axis=0)
    if "market_cap" in data.fund:
        size = np.log(data.fund["market_cap"].where(data.fund["market_cap"] > 0))
    elif "shares" in data.fund:
        size = np.log((data.fund["shares"] * usd).where(lambda x: x > 0))
    else:
        size = np.log((usd * data.volume).rolling(63, min_periods=20).mean().where(lambda x: x > 0))
    out["size"] = _z(size)
    if "book_to_price" in data.fund:
        out["value"] = _z(data.fund["book_to_price"])
    if "gross_profitability" in data.fund:
        out["quality"] = _z(data.fund["gross_profitability"])
    if data.option_names:
        out = {k: v.drop(columns=[c for c in data.option_names if c in v.columns]) for k, v in out.items()}
    return out


def style_exposures(data: Data, date: Any = None) -> pd.DataFrame:
    """Tickers × style factors on `date` (default: the last date) — e.g. for optimize(..., exposures=…)."""
    fr = style_frames(data)
    pos = len(data.close) - 1 if date is None else int(data.close.index.get_indexer([pd.Timestamp(date)], method="pad")[0])
    # each name's latest exposure within the last 5 sessions (a market holiday leaves a date's row blank)
    return pd.DataFrame({k: v.iloc[max(0, pos - 5):pos + 1].ffill().iloc[-1] for k, v in fr.items()})


def factor_risk(data: Data, holdings: Dict[str, float], lookback: int = 252, max_names: int = 600) -> Optional[Dict[str, Any]]:
    """Ex-ante risk from a factor model: each day, regress the cross-section of next-day returns on sector dummies
    and style exposures (OLS); factor covariance from those factor returns, specific risk from the residuals.
    Risk = h'XFX'h + h'Dh. Reports the factor/specific split, the book's style exposures and each factor's share."""
    h = pd.Series({k: float(v) for k, v in (holdings or {}).items() if k not in data.option_names})
    if h.empty or len(data.close) < lookback + 260:
        return None
    styles = style_frames(data)
    sectors = data.info["sector"].fillna("Other") if "sector" in data.info.columns else pd.Series("All", index=data.tickers)
    sectors = sectors.drop([c for c in data.option_names if c in sectors.index])
    liq = (data.close * data.volume).iloc[-63:].mean().reindex(sectors.index)
    est = list(liq.sort_values(ascending=False).index[:max_names])
    est = list(dict.fromkeys(est + [t for t in h.index if t in sectors.index]))
    secs = sorted(set(sectors[est]))
    S = pd.get_dummies(sectors[est]).reindex(columns=secs).astype(float)
    R = data.close[est].pct_change(fill_method=None).where(data.observed[est])
    T = len(data.close)
    names_f = secs + list(styles)
    fr_rows, resid = [], []
    for t in range(T - lookback - 1, T - 1):
        X = np.column_stack([S.to_numpy()] + [styles[k][est].iloc[t].fillna(0.0).to_numpy() for k in styles])
        y = R.iloc[t + 1].to_numpy()
        ok = np.isfinite(y)
        if ok.sum() < X.shape[1] + 5:
            continue
        f, *_ = np.linalg.lstsq(X[ok], y[ok], rcond=None)
        e = np.full(len(est), np.nan)
        e[ok] = y[ok] - X[ok] @ f
        fr_rows.append(f)
        resid.append(e)
    if len(fr_rows) < 60:
        return None
    Fr = np.array(fr_rows)
    F = np.cov(Fr.T) * TRADING_DAYS
    E = pd.DataFrame(resid, columns=est)
    spec = E.var().fillna(E.var().median())
    spec = (0.7 * spec + 0.3 * spec.median()) * TRADING_DAYS                   # shrink specific risk to the median
    held = [t for t in h.index if t in est]
    w = h[held]
    Xh = np.column_stack([S.loc[held].to_numpy()] + [styles[k][held].iloc[-6:].ffill().iloc[-1].fillna(0.0).to_numpy()
                                                      for k in styles])
    b = w.to_numpy() @ Xh                                                       # the book's factor exposures
    fvar = float(b @ F @ b)
    svar = float((w.to_numpy() ** 2 * spec[held].to_numpy()).sum())
    tot = fvar + svar
    contrib = b * (F @ b) / tot if tot > 0 else np.zeros(len(b))
    by = dict(zip(names_f, contrib))
    sector_share = sum(by[s] for s in secs)
    return {"vol": round(math.sqrt(max(tot, 0)), 4), "factor_share": round(fvar / tot, 3) if tot else None,
            "specific_share": round(svar / tot, 3) if tot else None,
            "style_exposures": {k: round(float(x), 3) for k, x in zip(list(styles), b[len(secs):])},
            "risk_share": {**{k: round(float(by[k]), 4) for k in styles}, "sectors (industry)": round(float(sector_share), 4)},
            "factor_vol": {k: round(float(math.sqrt(max(F[i, i], 0))), 4) for i, k in enumerate(names_f) if k in styles},
            "estimation_universe": len(est), "days": len(fr_rows),
            "note": "Cross-sectional regression each day of next-day returns on sector dummies and z-scored styles "
                    "(momentum, volatility, size" + (", value, quality" if "value" in styles else "") + "); "
                    "exposures are the book's weighted z-scores (0 = like the average stock)."}


# ── Signal research (Alphalens-style) ────────────────────────────────────────
def signal_report(sig: pd.DataFrame, data: Data, start: Optional[str] = None, horizons: Sequence[int] = (1, 5, 21, 63),
                  quantiles: int = 5) -> Dict[str, Any]:
    """Information coefficient (Spearman rank correlation of today's scores with returns from the next open),
    its decay by horizon, quantile returns and turnover — whether a signal predicts before costs and weights."""
    idx, cols = data.close.index, data.close.columns
    S = sig.reindex(index=idx, columns=cols).astype(float)
    if getattr(data, "members", None) is not None:
        S = S.where(data.members.reindex(index=idx, columns=cols).fillna(False).astype(bool))
    o = data.open.where(data.observed)
    first = int(np.searchsorted(idx.values, np.datetime64(pd.Timestamp(start)))) if start else 0

    def rank_ic(a: pd.DataFrame, b: pd.DataFrame) -> pd.Series:
        m = a.notna() & b.notna()
        ra, rb = a.where(m).rank(axis=1), b.where(m).rank(axis=1)
        ra, rb = ra.sub(ra.mean(axis=1), axis=0), rb.sub(rb.mean(axis=1), axis=0)
        num = (ra * rb).sum(axis=1)
        den = np.sqrt((ra ** 2).sum(axis=1) * (rb ** 2).sum(axis=1))
        ic = num / den.where(den > 0)
        return ic.where(m.sum(axis=1) >= 10).iloc[first:].dropna()

    rows = []
    fwd_cache = {}
    for hz in horizons:
        fwd = o.shift(-(1 + hz)) / o.shift(-1) - 1             # score at close t → from open t+1 to open t+1+h
        fwd_cache[hz] = fwd
        ic = rank_ic(S, fwd)
        if len(ic) < 20:
            continue
        sample = ic.iloc[::hz]                                  # non-overlapping for the t-statistic
        t_stat = float(sample.mean() / sample.std(ddof=1) * math.sqrt(len(sample))) if len(sample) > 2 and sample.std() > 0 else None
        rows.append({"horizon": hz, "mean_ic": round(float(ic.mean()), 4), "ic_std": round(float(ic.std()), 4),
                     "ic_ir": round(float(ic.mean() / ic.std() * math.sqrt(TRADING_DAYS / hz)), 3) if ic.std() > 0 else None,
                     "t_stat": None if t_stat is None else round(t_stat, 2), "positive": round(float((ic > 0).mean()), 3),
                     "days": int(len(ic))})
    out: Dict[str, Any] = {"ic": rows, "coverage": round(float(S.iloc[first:].notna().sum(axis=1).mean()), 1)}
    hz = 21 if 21 in fwd_cache else (horizons[0] if horizons else 1)
    fwd = fwd_cache.get(hz)
    if fwd is not None:
        pct = S.rank(axis=1, pct=True)
        q = np.ceil(pct * quantiles).clip(1, quantiles)
        ex = fwd.sub(fwd.where(S.notna()).mean(axis=1), axis=0)
        qr = []
        for k in range(1, quantiles + 1):
            v = ex.where(q == k).iloc[first:].stack()
            qr.append(round(float(v.mean() / hz * TRADING_DAYS), 4) if len(v) else None)
        out["quantiles"] = {"horizon": hz, "annualised_excess": qr,
                            "spread": None if None in (qr[0], qr[-1]) else round(qr[-1] - qr[0], 4),
                            "monotonic": bool(all(a is not None and b is not None and b >= a for a, b in zip(qr, qr[1:])))}
        top = (q == quantiles).iloc[first:]
        chg = (top & ~top.shift(1, fill_value=False)).sum(axis=1) / top.sum(axis=1).where(top.sum(axis=1) > 0)
        out["top_quantile_turnover"] = round(float(chg.mean()), 4) if chg.notna().any() else None
    ac = [S.iloc[first:].rank(axis=1).corrwith(S.iloc[first:].rank(axis=1).shift(l), axis=1).mean() for l in (1, 5, 21)]
    out["rank_autocorrelation"] = {str(l): (None if pd.isna(a) else round(float(a), 3)) for l, a in zip((1, 5, 21), ac)}
    out["note"] = ("Spearman IC of each day's scores with returns from the next open; t-statistics on non-overlapping "
                   "samples. Quantile returns are annualised excess over the scored universe's average, before costs.")
    return out


_LAST_RUN: Dict[str, Any] = {}


def research_checks() -> Dict[str, Any]:
    """The slower checks for the run evaluate(checks=False) just made: look-ahead re-runs, capacity, the factor risk
    model and signal research — so a result can be shown first and completed a moment later."""
    L = _LAST_RUN
    if not L:
        raise ValueError("No run to check — run the strategy first.")
    data, combos = L["data"], L["combos"]
    out: Dict[str, Any] = {}
    if L["on_bar"] is not None:
        setup = L["setup"]
        raw = lambda f, d, p: f(d, **p)
        out["causality"] = (_quiet(causality_check, _setup_table(setup), data, combos[0], _setup_table(setup)(data, **combos[0]),
                                   runner=raw) if setup is not None else
                            {"passed": True, "cuts": [], "note": "Event-driven: on_bar only sees data up to each bar (causal by construction)."})
    else:
        out["causality"] = _quiet(causality_check, L["fn"], data, combos[0], L["weight_sets"][0])
    if L["n"] <= 400:
        out["capacity"] = capacity_curve(L["rerun"], data, L["costs"])
    try:
        out["factor_model"] = factor_risk(data, L["holdings"])
    except Exception as e:                                      # noqa: BLE001
        out["factor_model"] = {"error": f"{type(e).__name__}: {str(e)[:160]}"}
    if L["signal"] is not None:
        try:
            out["signal"] = signal_report(_quiet(run_weights, L["signal"], data, combos[0]), data, L["first_day"])
        except Exception as e:                                  # noqa: BLE001
            out["signal"] = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
    return out


def _setup_table(setup: Callable) -> Callable:
    """setup(data) → {name: Series/DataFrame}, as one wide table (for the look-ahead check)."""
    def f(data, **p):
        out = setup(data, **p) or {}
        parts = {k: (v.to_frame(k) if isinstance(v, pd.Series) else v) for k, v in out.items()
                 if isinstance(v, (pd.Series, pd.DataFrame))}
        out_ = pd.concat(parts, axis=1).astype(float) if parts else pd.DataFrame(index=data.close.index)
        out_.columns = [" ".join(map(str, c)) if isinstance(c, tuple) else str(c) for c in out_.columns]
        return out_
    return f


def _run_events(on_bar: Callable, setup: Optional[Callable], data: Data, combos: List[Dict[str, Any]], start: str,
                costs: Optional[Dict[str, float]], holdout: Optional[str]):
    """Event-driven run(s): one per parameter set; with several, walk-forward — each January the set with the best
    growth on data up to then takes over the same continuing account (state and positions carry on)."""
    pres = [(setup(data, **p) or {}) if setup is not None else {} for p in combos]
    runs = [_quiet(backtest, None, data, costs, start, on_bar=on_bar, params=p, pre=pr) for p, pr in zip(combos, pres)]
    if len(combos) == 1:
        rr = lambda c: backtest(None, data, c, start, on_bar=on_bar, params=combos[0], pre=pres[0])
        return runs[0], {"walk_forward": False, "params": combos[0], "mode": "event-driven"}, [], rr
    sel_end = pd.Timestamp(holdout) if holdout else None
    standalone = [r["ret"][r["ret"].index < sel_end] if sel_end is not None else r["ret"] for r in runs]
    chosen = select_walk_forward(standalone, combos, rf=data.rf)
    if not chosen:
        raise ValueError("Not enough history for walk-forward selection (needs more than the 5-year warm-up).")
    by_year = {c["year"]: combos.index(c["params"]) for c in chosen}
    first_year = min(by_year)

    def dispatch(ctx, **_):
        y = ctx.date.year
        k = by_year.get(y, by_year[max([yy for yy in by_year if yy <= y], default=first_year)])
        ctx._pre = pres[k]
        on_bar(ctx, **combos[k])
    oos = str(pd.Timestamp(f"{first_year}-01-01").date())
    rr = lambda c: backtest(None, data, c, oos, on_bar=dispatch)
    res = rr(costs)
    full_ins = [metrics(r["ret"][r["ret"].index >= pd.Timestamp(oos)], data.rf) for r in runs]
    b = int(np.argmax([f.get("log_growth") if f.get("log_growth") is not None else -1e9 for f in full_ins]))
    opt = {"walk_forward": True, "mode": "event-driven", "chosen": chosen, "switches": [], "oos_start": oos,
           "in_sample_best": {"params": combos[b], **full_ins[b]}, "grid": [{"params": c, **f} for c, f in zip(combos, full_ins)],
           "note": "Event-driven walk-forward: one continuing account; each January the parameter set chosen on data up "
                   "to then drives on_bar."}
    return res, opt, standalone, rr


def evaluate(fn: Optional[Callable], data: Data, params: Dict[str, Sequence[Any]], start: str,
             costs: Optional[Dict[str, float]] = None, benchmark: Optional[pd.Series] = None,
             holdout: Optional[str] = None, code_hash: Optional[str] = None, signal: Optional[Callable] = None,
             checks: bool = True, on_bar: Optional[Callable] = None, setup: Optional[Callable] = None,
             light: bool = False) -> Dict[str, Any]:
    """Backtest as one account (walk-forward when PARAMS has several combinations). Also returns the
    universe-matched equal-weight baseline under the same costs, the benchmark, segment statistics for an
    untouched holdout (if HOLDOUT is set), validation (look-ahead check, PBO), capacity, attribution, ex-ante risk,
    the signal's information coefficients (if the code defines signal()) and a provenance record."""
    _CHARTS.clear()
    combos = grid(params)
    if len(combos) > 48:
        raise ValueError(f"{len(combos)} parameter combinations — keep the grid to 48 or fewer.")
    if on_bar is not None:
        res, opt, standalone, rerun = _run_events(on_bar, setup, data, combos, start, costs, holdout)
        weight_sets = None
    else:
        weight_sets = [run_weights(fn, data, p) for p in combos]
    if on_bar is not None:
        pass                                                   # ran above
    elif len(combos) > 1:
        # holdout years never take part in selection
        sel_end = pd.Timestamp(holdout) if holdout else None
        standalone, own = [], []
        for Wp in weight_sets:
            r = backtest(Wp, data, costs, start)["ret"]
            own.append(r)
            standalone.append(r[r.index < sel_end] if sel_end is not None else r)
        chosen = select_walk_forward(standalone, combos, rf=data.rf)
        if holdout:                                            # keep the last pre-holdout choice through the holdout
            last = chosen[-1] if chosen else None
            for y in sorted(set(data.close.index.year)):
                if pd.Timestamp(f"{y}-01-01") >= sel_end and last and all(c["year"] != y for c in chosen):
                    chosen.append({"year": y, "params": last["params"], "trailing": None})
        if not chosen:
            raise ValueError("Not enough history for walk-forward selection (needs more than the 5-year warm-up).")
        Wc, Dc, switches = continuous_walk_forward(weight_sets, chosen, combos, data.close.index)
        oos_start = str(pd.Timestamp(f"{chosen[0]['year']}-01-01").date())
        res = backtest(Wc, data, costs, oos_start, decisions=Dc)
        rerun = lambda c: backtest(Wc, data, c, oos_start, decisions=Dc)
        # each parameter set's own account (the run that scored it), measured over the out-of-sample years — no extra
        # fresh-start backtests (they cost one full ledger run per set)
        full_ins = [metrics(r[r.index >= pd.Timestamp(oos_start)], data.rf) for r in own]
        ins_obj = [f.get("log_growth") if f.get("log_growth") is not None else -1e9 for f in full_ins]
        b = int(np.argmax(ins_obj))
        opt = {"walk_forward": True, "chosen": chosen, "switches": switches, "oos_start": oos_start,
               "in_sample_best": {"params": combos[b], **full_ins[b]},
               "grid": [{"params": c, **f} for c, f in zip(combos, full_ins)],
               "note": "One continuous account: switching parameter sets trades from current holdings to the new "
                       "targets and pays those costs. Grid rows: each set's own account (started with the data) over "
                       "the out-of-sample years."}
    else:
        res = backtest(weight_sets[0], data, costs, start)
        opt = {"walk_forward": False, "params": combos[0]}
        rerun = lambda c: backtest(weight_sets[0], data, c, start)
        standalone = []
    ret = res["ret"]
    first_day = str(ret.index[0].date()) if len(ret) else start
    if light:
        # what a paper book needs each day — returns, today's targets and holdings — without the research extras
        # (baseline, look-ahead re-runs, capacity, attribution, risk models), which cost several backtests each
        return {"metrics": metrics(ret, data.rf), "costs": cost_summary(res), "optimisation": opt,
                "weights_last": res["weights_last"], "holdings_last": res["holdings_last"], "execution": res["execution"],
                "dates": [d.strftime("%Y-%m-%d") for d in ret.index], "returns": [round(float(x), 8) for x in ret.values],
                "account_currency": data.account_currency,
                **({"benchmark": [round(float(x), 8) for x in
                                  benchmark.reindex(ret.index).pct_change(fill_method=None).fillna(0.0).values]}
                   if benchmark is not None else {}),
                "provenance": {"engine_version": ENGINE_VERSION, "code_hash": code_hash, "account_currency": data.account_currency,
                               "data_last": str(data.close.index[-1].date()), "light": True}}
    # universe-matched baseline: equal weight of every listed name, rebalanced monthly, same costs and start
    listed = data.observed.astype(float).where(data.observed)
    ew = hold_monthly(listed.div(listed.sum(axis=1), axis=0).fillna(0.0))
    base = backtest(ew, data, costs, first_day)["ret"]
    out = {"metrics": metrics(ret, data.rf), "metrics_gross": metrics(res["gross"], data.rf), "costs": cost_summary(res),
           "optimisation": opt, "weights_last": res["weights_last"], "holdings_last": res["holdings_last"],
           "ledger": res["ledger"], "execution": res["execution"], "events": res["events"][-50:],
           "baseline_equal_weight": metrics(base.reindex(ret.index).fillna(0.0), data.rf),
           "dates": [d.strftime("%Y-%m-%d") for d in ret.index], "returns": [round(float(x), 8) for x in ret.values],
           "gross": [round(float(x), 8) for x in res["gross"].reindex(ret.index).fillna(0).values],
           "baseline_returns": [round(float(x), 8) for x in base.reindex(ret.index).fillna(0).values],
           "account_currency": data.account_currency,
           "exposure": exposure_breakdown(res["holdings_last"], data.instruments)}
    if benchmark is not None:
        bm = benchmark.reindex(ret.index).pct_change(fill_method=None).fillna(0.0)
        out["benchmark"] = [round(float(x), 8) for x in bm.values]
        out["benchmark_metrics"] = metrics(bm, data.rf)
        out["benchmark_definition"] = ("frictionless total return (adjusted close), 100% invested from the first "
                                       "record day; no costs, no cash")
    # research-grade checks: does any decision use the future, how likely is the parameter choice overfit, how much
    # money can it run, where did the return come from, how risky is today's book, does the signal predict
    if on_bar is not None:
        raw = lambda f, d, p: f(d, **p)
        caus = (_quiet(causality_check, _setup_table(setup), data, combos[0], _setup_table(setup)(data, **combos[0]),
                       runner=raw)
                if setup is not None and checks else
                {"passed": True, "cuts": [], "note": "Event-driven: on_bar only sees data up to each bar (causal by "
                                                      "construction)" + ("; setup() was not checked." if setup else ".")})
    else:
        caus = _quiet(causality_check, fn, data, combos[0], weight_sets[0]) if checks else None
    out["validation"] = {"causality": caus,
                         "pbo": pbo(standalone) if len(standalone) > 1 else None,
                         "cpcv": cpcv(standalone) if len(standalone) > 1 else None}
    out["trades"] = trade_report(res, data, (costs or {}).get("capital", DEFAULT_COSTS["capital"]))
    out["charts"] = _charts_out()
    out["attribution"] = attribution(res, data)
    out["risk"] = risk_model(data, res["holdings_last"], benchmark)
    if out["risk"] is not None and checks:
        try:
            out["risk"]["factor_model"] = factor_risk(data, res["holdings_last"])
        except Exception as e:                                  # noqa: BLE001 — the statistical model stands alone
            out["risk"]["factor_model"] = {"error": f"{type(e).__name__}: {str(e)[:160]}"}
    if checks and len(data.tickers) <= 400:
        out["capacity"] = capacity_curve(rerun, data, costs)
    if signal is not None and checks:
        try:
            out["signal"] = signal_report(_quiet(run_weights, signal, data, combos[0]), data, first_day)
        except Exception as e:                                  # noqa: BLE001 — the backtest stands without it
            out["signal"] = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
    if not checks:
        # keep what the slower checks need, so research_checks() can add them afterwards without re-running the strategy
        _LAST_RUN.clear()
        _LAST_RUN.update(fn=fn, data=data, combos=combos, weight_sets=weight_sets, rerun=rerun, costs=costs,
                         holdings=res["holdings_last"], signal=signal, setup=setup, on_bar=on_bar, first_day=first_day,
                         n=len(data.tickers))
        out["checks_pending"] = True
    if holdout:
        out["holdout"] = {"start": holdout, "in_sample": _segment(ret, data.rf, None, holdout),
                          "holdout": _segment(ret, data.rf, holdout, None),
                          "baseline_holdout": _segment(base.reindex(ret.index).fillna(0.0), data.rf, holdout, None)}
    out["provenance"] = {"engine_version": ENGINE_VERSION, "cost_schema_version": COST_SCHEMA_VERSION,
                         "costs": {**DEFAULT_COSTS, **(costs or {})}, "params": params, "universe": data.tickers,
                         "data_first": str(data.close.index[0].date()), "data_last": str(data.close.index[-1].date()),
                         "data_hash": _data_hash(data), "code_hash": code_hash, "rf_known": data.rf_known,
                         "record_type": ("walk-forward (selection out-of-sample)" if opt["walk_forward"] else
                                         "exploratory backtest (single specification, full history)"),
                         **data.provenance}
    return out
