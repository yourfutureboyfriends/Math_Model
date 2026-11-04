// Starter templates for the Code Lab — one per way of writing a strategy. Each runs as-is.

export const TEMPLATES: { id: string; name: string; about: string; code: string }[] = [
  {
    id: 'weights',
    name: 'Cross-sectional momentum (weights)',
    about: 'The basic form: strategy(data) returns target weights for every date; decisions monthly.',
    code: `UNIVERSE = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC", "VNQ"]
START = "2010-01-04"
PARAMS = {"lookback": [126, 252]}          # walk-forward: each January the best set so far is used


def signal(data, lookback=252):
    # optional: scores for the information-coefficient report
    return momentum(data.close, lookback, 21)


def strategy(data, lookback=252, top=3):
    score = signal(data, lookback)
    pick = score.rank(axis=1, ascending=False) <= top
    w = pick.astype(float) / top
    return hold_monthly(w)                     # decide on the first session of each month
`,
  },
  {
    id: 'event',
    name: 'Trend with limit entries and stops (event-driven)',
    about: 'on_bar(ctx) runs after every close with the real account: market, limit and stop orders.',
    code: `UNIVERSE = ["SPY", "TLT", "GLD"]
START = "2012-01-03"


def setup(data, fast=50, slow=200):
    # indicators computed once (checked for look-ahead); read them with ctx.pre(name)
    return {"fast": data.close.rolling(fast).mean(), "slow": data.close.rolling(slow).mean()}


def on_bar(ctx, fast=50, slow=200):
    f, s, px = ctx.pre("fast").iloc[-1], ctx.pre("slow").iloc[-1], ctx.close
    for t in UNIVERSE:
        held = ctx.positions.get(t, 0.0)
        waiting = any(o["ticker"] == t for o in ctx.orders)
        if f[t] > s[t] and held < 0.01 and not waiting:
            ctx.limit(t, 1 / 3, px[t] * 0.99, days=5)     # buy a 1% dip within a week
        elif f[t] < s[t] and held > 0.01:
            ctx.cancel(t)
            ctx.target({t: 0.0})                          # trend over: sell at the next open
        elif held > 0.01 and not waiting:
            ctx.stop(t, 0.0, px[t] * 0.90)                # 10% protective stop
`,
  },
  {
    id: 'options',
    name: 'Covered calls with a protective put (options)',
    about: 'OPTIONS adds modelled listed options; their weights are underlying notional.',
    code: `UNIVERSE = ["SPY"]
START = "2010-01-04"
OPTIONS = [
    {"underlying": "SPY", "type": "call", "moneyness": 1.03},                       # monthly 3% OTM call
    {"underlying": "SPY", "type": "put", "moneyness": 0.90, "expiry": "quarterly"},  # quarterly 10% OTM put
]


def strategy(data):
    w = data.close * 0
    w["SPY"] = 1.0
    w["SPY_C103_1M"] = -1.0        # sell calls on 100% of NAV
    w["SPY_P90_Q"] = 1.0           # buy puts on 100% of NAV
    expiry = data.opt["roll"].any(axis=1)
    return w.where(expiry, np.nan, axis=0)     # re-strike at each expiry
`,
  },
  {
    id: 'fundamentals',
    name: 'Value + quality, sector- and momentum-neutral (fundamentals + optimiser)',
    about: 'Point-in-time SEC fundamentals, a shrinkage covariance and a constrained optimiser.',
    code: `UNIVERSE = ["AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "JPM", "BAC", "WFC", "XOM", "CVX", "JNJ", "PFE",
            "MRK", "PG", "KO", "PEP", "WMT", "HD", "MCD", "CSCO", "INTC", "ORCL", "IBM", "T", "VZ", "DIS", "NKE",
            "CAT", "MMM"]
START = "2014-01-02"
FUNDAMENTALS = ["book_to_price", "gross_profitability"]


def signal(data):
    f = data.fund
    return f["book_to_price"].rank(axis=1, pct=True) + f["gross_profitability"].rank(axis=1, pct=True)


def strategy(data, risk_aversion=10.0):
    score, rets = signal(data), data.close.pct_change()
    w = pd.DataFrame(np.nan, index=data.close.index, columns=data.close.columns)
    month = data.close.index.to_series().dt.to_period("M")
    for t in np.where((month != month.shift(1)).to_numpy())[0]:
        s = score.iloc[t].dropna()
        if t < 300 or len(s) < 15:
            continue
        cov = cov_shrink(rets.iloc[t - 252:t])
        x = style_exposures(data, data.close.index[t])
        w.iloc[t] = optimize((s - s.mean()) * 0.0004, cov, risk_aversion=risk_aversion, max_weight=0.08,
                             groups=data.info["sector"], group_max=0.30,
                             exposures=x, factor_bounds={"momentum": (-0.05, 0.05)}).reindex(w.columns).fillna(0).values
    return w
`,
  },
  {
    id: 'global',
    name: 'Global momentum in euros, currency-hedged (any market, any currency)',
    about: 'A whole region from the tradable universe, an EUR account and an FX hedge (runs on the server).',
    code: `UNIVERSE = ["EZU"]
TRADABLE_UNIVERSE = "EUROPE+JP"              # a region, countries ("JP+HK") or "GLOBAL"
ACCOUNT_CURRENCY = "EUR"
FX_HEDGE = 1.0                               # hedge foreign-currency exposure back to euros
START = "2012-01-02"


def strategy(data, picks=30):
    px = data.close
    traded = (px * data.volume * data.usd_per_unit.values[:, None]).rolling(63, min_periods=40).mean()
    liquid = traded > 20e6                     # at least $20m a day
    mom = momentum(px, 252, 21).where(liquid)
    pick = mom.rank(axis=1, ascending=False) <= picks
    w = pick.astype(float).div(pick.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    return hold_monthly(w)
`,
  },
];
