# Methodology — Phase 4: Signal Validation & Backtesting

_For a PM to read before trusting a signal._

## What it does
Gives every backtestable signal a **track record**: how often it was right, what returns
followed it, and the risk-adjusted performance of naively following it — so a signal's
confidence number is backed by history, not just asserted.

## Walk-forward, no look-ahead
The signal state at date *t* is reconstructed using **only data up to and including *t***,
then evaluated against the **strictly forward** return over the next `horizon` days
(default 21 ≈ 1 month). There is no peeking at future prices in the signal itself.

## Signals backtested (S&P 500, 5y daily)
- **Price Momentum (12-1m)** — sign of the 12-month-minus-1-month return; BULLISH/BEARISH.
- **Trend (200-day MA)** — price above/below its 200-day moving average.
- **VIX Vol-Regime** — VIX below/above its trailing 126-day median (risk-on/off).

## Metrics
- **Hit rate** — % of directional (non-neutral) signals whose sign matched the forward
  return sign.
- **Forward return by state** — average forward return (and sample count) when the
  signal was BULLISH / BEARISH / NEUTRAL.
- **Strategy Sharpe / Max Drawdown / Total Return** — of a naive strategy that goes long
  (+1) on BULLISH, short (−1) on BEARISH, flat (0) on NEUTRAL, earning the next-day return
  (annualized Sharpe, rf=0).
- **Confusion matrix** — signal state vs realized Up/Down.

## Assumptions & limitations
- **Only price-reconstructable signals are backtested.** Momentum/trend/vol-regime can be
  rebuilt from history with no look-ahead. The **composite regime classifier and ensemble**
  cannot be honestly backtested yet because the system does not persist their historical
  values — that requires the point-in-time signal store (Phase 9). Rather than fabricate a
  track record, those are intentionally omitted here.
- **No transaction costs / slippage** — the naive strategy is gross; real net Sharpe would
  be lower, especially for higher-turnover signals.
- **Single instrument (S&P 500)** and a single forward horizon — not a full cross-sectional
  or multi-horizon study.
- **In-sample parameters** — the signal thresholds (12-1m, 200d, 126d) are conventional,
  not optimized on this data, which limits (but does not eliminate) overfitting risk.

## Verification
12 known-answer unit tests (`api/tests/test_backtest.py`): a perfect predictor gives
hit rate 1.0; neutral signals are excluded from the base; max drawdown of a monotonic
up-series is 0 and captures a −50% path; a short earns when the market falls; the
momentum signal on a rising series is BULLISH. Verified live: momentum hit rate ~65%
with BULLISH forward returns (+1.6%) exceeding NEUTRAL (−0.3%) over 1,234 observations —
consistent with the known momentum premium.
