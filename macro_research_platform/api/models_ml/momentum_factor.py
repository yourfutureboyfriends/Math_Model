"""
Cross-sectional and time-series momentum factor model.

Academic basis:
  Jegadeesh, N. & Titman, S. (1993). Returns to Buying
  Winners and Selling Losers: Implications for Stock
  Market Efficiency. Journal of Finance, 48(1), 65-91.

  Moskowitz, T.J., Ooi, Y.H. & Pedersen, L.H. (2012).
  Time Series Momentum. Journal of Financial Economics,
  104(2), 228-250.

  Asness, C.S., Moskowitz, T.J. & Pedersen, L.H. (2013).
  Value and Momentum Everywhere. Journal of Finance,
  68(3), 929-985.

  Barroso, P. & Santa-Clara, P. (2015). Momentum Has
  Its Moments. Journal of Financial Economics,
  116(1), 111-120.

Key findings:
  Jegadeesh & Titman (1993):
    12-1 month return predicts next month return.
    Skip last month to avoid short-term reversal.
    Long winners short losers: 1.23% monthly alpha.

  Moskowitz et al. (2012):
    Time-series momentum works across ALL asset classes.
    12-month lookback optimal for macro assets.
    Sharpe ~1.0 across equities, bonds, FX, commodities.

  Barroso & Santa-Clara (2015):
    Scale by ex-ante volatility to manage crash risk.
    Target 12% annual volatility exposure.

Implementation steps:
  1. Fetch monthly prices for 16-asset universe
  2. Cross-sectional rank by 12-1M return
  3. Time-series signal per asset (sign of return)
  4. Scale each asset by inverse realised vol
  5. Suppress in crash regime (vol > 25%)
  6. Combine CS + TS into composite signal
"""

import numpy as np
import pandas as pd
import yfinance as yf
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


# ── Asset universe ─────────────────────────────────────────

MOMENTUM_UNIVERSE = {
    'SPY':  {'class': 'equity',     'name': 'S&P 500'},
    'QQQ':  {'class': 'equity',     'name': 'Nasdaq 100'},
    'IWM':  {'class': 'equity',     'name': 'US Small Cap'},
    'EEM':  {'class': 'equity',     'name': 'Emerging Markets'},
    'EFA':  {'class': 'equity',     'name': 'Developed ex-US'},
    'VNQ':  {'class': 'real_estate','name': 'Real Estate'},
    'TLT':  {'class': 'bonds',      'name': '20Y Treasury'},
    'IEF':  {'class': 'bonds',      'name': '7-10Y Treasury'},
    'TIP':  {'class': 'bonds',      'name': 'TIPS'},
    'HYG':  {'class': 'credit',     'name': 'High Yield'},
    'GLD':  {'class': 'commodity',  'name': 'Gold'},
    'DBC':  {'class': 'commodity',  'name': 'Commodities'},
    'USO':  {'class': 'commodity',  'name': 'Crude Oil'},
    'UUP':  {'class': 'fx',         'name': 'US Dollar'},
    'FXE':  {'class': 'fx',         'name': 'Euro'},
    'FXY':  {'class': 'fx',         'name': 'Yen'},
}

# Risk management constants per Barroso & Santa-Clara (2015)
VOL_LOOKBACK_MONTHS = 3     # 3-month rolling vol window
VOL_TARGET_ANNUAL   = 0.12  # 12% annual volatility target
VOL_CRASH_THRESHOLD = 0.25  # suppress above 25% annual vol
MAX_LEVERAGE        = 2.0   # cap risk-managed scaling at 2x


class MomentumFactorModel:
    """
    Multi-asset momentum model combining:
      - Cross-sectional ranking (Jegadeesh & Titman 1993)
      - Time-series signals (Moskowitz et al. 2012)
      - Risk-managed scaling (Barroso & Santa-Clara 2015)
    """

    def __init__(
        self,
        lookback_months: int   = 12,
        skip_months:     int   = 1,
        vol_target:      float = VOL_TARGET_ANNUAL,
    ):
        """
        Args:
          lookback_months: Return lookback window.
                           12 months per literature.
          skip_months:     Skip most recent N months.
                           1 month per J&T to avoid
                           short-term reversal.
          vol_target:      Annual vol target for
                           risk-managed momentum.
        """
        self.lookback    = lookback_months
        self.skip        = skip_months
        self.vol_target  = vol_target
        self.prices:     pd.DataFrame | None = None
        self.returns:    pd.DataFrame | None = None
        self.last_fetch: str | None = None

    # ── Data fetching ──────────────────────────────────

    def fetch_prices(
        self,
        tickers: list[str] | None = None,
        period:  str = '2y',
    ) -> pd.DataFrame:
        """
        Fetch monthly adjusted close prices.
        Drops tickers with insufficient history.
        Minimum required: lookback + skip + 2 months.
        """
        if tickers is None:
            tickers = list(MOMENTUM_UNIVERSE.keys())

        logger.info(
            f'[MOMENTUM] Fetching {len(tickers)} tickers'
        )

        try:
            raw = yf.download(
                tickers,
                period=period,
                interval='1mo',
                progress=False,
                auto_adjust=True,
            )

            # Handle single vs multi-ticker response
            if isinstance(raw.columns, pd.MultiIndex):
                prices = raw['Close'].copy()
            else:
                prices = raw[['Close']].copy()
                prices.columns = [tickers[0]]

            # Drop tickers with insufficient history
            min_obs = self.lookback + self.skip + 2
            valid   = [
                c for c in prices.columns
                if prices[c].dropna().__len__() >= min_obs
            ]
            prices = prices[valid]

            if prices.empty:
                raise ValueError(
                    f'No tickers have >= {min_obs} months'
                )

            self.prices     = prices
            self.returns    = prices.pct_change()
            self.last_fetch = datetime.utcnow().isoformat()

            logger.info(
                f'[MOMENTUM] Loaded '
                f'{len(prices.columns)} assets '
                f'x {len(prices)} months'
            )
            return prices

        except Exception as e:
            logger.error(f'[MOMENTUM] Fetch failed: {e}')
            raise

    # ── Cross-sectional momentum ───────────────────────

    def cross_sectional_momentum(
        self,
        prices: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        """
        12-1 month cross-sectional momentum ranking.

        Per Jegadeesh & Titman (1993):
          Return = P(t-1) / P(t-13) - 1
          Skip t-1 to t to avoid reversal effect.
          Rank all assets by this return.
          Top third = BUY, bottom third = SELL.

        Returns DataFrame with columns:
          ticker, return_12_1, z_score, rank, cs_signal
        Sorted by rank ascending (1 = best).
        """
        if prices is None:
            prices = self.prices
        if prices is None:
            raise ValueError('No price data. Call fetch_prices() first.')

        n_needed = self.lookback + self.skip + 1
        if len(prices) < n_needed:
            raise ValueError(
                f'Need {n_needed} months, '
                f'only have {len(prices)}'
            )

        # Price at t-1 (skip end) and t-13 (lookback start)
        p_t1  = prices.iloc[-(1 + self.skip)]
        p_t13 = prices.iloc[-(self.lookback + self.skip)]

        results = []
        for ticker in prices.columns:
            try:
                p_now  = float(p_t1[ticker])
                p_then = float(p_t13[ticker])

                if (p_then <= 0 or
                        np.isnan(p_then) or
                        np.isnan(p_now)):
                    continue

                ret_12_1 = p_now / p_then - 1.0

                results.append({
                    'ticker':      ticker,
                    'return_12_1': round(ret_12_1, 4),
                    'asset_class': MOMENTUM_UNIVERSE.get(
                        ticker, {}
                    ).get('class', 'other'),
                    'name': MOMENTUM_UNIVERSE.get(
                        ticker, {}
                    ).get('name', ticker),
                })

            except (KeyError, TypeError, ZeroDivisionError):
                continue

        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results)

        # Cross-sectional z-score
        mu  = df['return_12_1'].mean()
        std = df['return_12_1'].std()
        df['z_score'] = (
            (df['return_12_1'] - mu) / std
            if std > 1e-8 else 0.0
        )

        # Rank: 1 = highest 12-1M return
        df['rank'] = (
            df['return_12_1']
            .rank(ascending=False)
            .astype(int)
        )

        # Signal: top/bottom third
        n             = len(df)
        cutoff_top    = n // 3
        cutoff_bottom = 2 * n // 3
        df['cs_signal'] = df['rank'].apply(
            lambda r:
                'BUY'     if r <= cutoff_top    else
                'SELL'    if r >  cutoff_bottom  else
                'NEUTRAL'
        )

        return df.sort_values('rank').reset_index(drop=True)

    # ── Time-series momentum ───────────────────────────

    def time_series_momentum(
        self,
        ticker:  str,
        prices:  pd.DataFrame | None = None,
    ) -> dict:
        """
        Time-series momentum for a single asset.

        Per Moskowitz, Ooi & Pedersen (2012):
          Signal direction = sign(12M own return).
          Scaled by inverse realised volatility
          to target constant 12% annual vol.

        Per Barroso & Santa-Clara (2015):
          Use rolling 3M realised vol as estimate.
          Cap scaling at 2x to limit leverage.
          Suppress heavily if vol > crash threshold.

        Returns signal dict with score, vol, scaling.
        """
        if prices is None:
            prices = self.prices
        if prices is None or ticker not in prices.columns:
            return {
                'signal':     'NEUTRAL',
                'score':       0.0,
                'return_12m':  None,
                'vol_ann':     None,
                'vol_scalar':  1.0,
                'in_crash':    False,
            }

        col      = prices[ticker].dropna()
        n_needed = self.lookback + self.skip + 1
        if len(col) < n_needed:
            return {
                'signal':     'NEUTRAL',
                'score':       0.0,
                'return_12m':  None,
                'vol_ann':     None,
                'vol_scalar':  1.0,
                'in_crash':    False,
            }

        # 12-1M return for this asset
        p_t1  = float(col.iloc[-(1 + self.skip)])
        p_t13 = float(
            col.iloc[-(self.lookback + self.skip)]
        )
        if p_t13 <= 0:
            return {
                'signal':     'NEUTRAL',
                'score':       0.0,
                'return_12m':  None,
                'vol_ann':     None,
                'vol_scalar':  1.0,
                'in_crash':    False,
            }
        ret_12 = p_t1 / p_t13 - 1.0

        # Realised volatility: rolling 3-month
        monthly_rets = col.pct_change().dropna()
        n_vol = min(VOL_LOOKBACK_MONTHS, len(monthly_rets))
        if n_vol >= 2:
            vol_m   = float(
                monthly_rets.iloc[-n_vol:].std()
            )
            vol_ann = vol_m * np.sqrt(12)
        else:
            vol_ann = 0.15  # default 15%

        # Risk-managed scaling: target vol / realised vol
        if vol_ann > 1e-6:
            vol_scalar = min(
                self.vol_target / vol_ann,
                MAX_LEVERAGE,
            )
        else:
            vol_scalar = 1.0

        # Crash regime detection
        in_crash = vol_ann > VOL_CRASH_THRESHOLD

        # Signal and score
        raw_sign = float(np.sign(ret_12))
        score    = raw_sign * vol_scalar

        if in_crash:
            score    *= 0.25     # 75% suppression in crash
            ts_signal = 'CAUTION'
        elif raw_sign > 0:
            ts_signal = 'UPTREND'
        elif raw_sign < 0:
            ts_signal = 'DOWNTREND'
        else:
            ts_signal = 'NEUTRAL'

        return {
            'signal':     ts_signal,
            'score':       round(float(score), 4),
            'return_12m':  round(ret_12, 4),
            'vol_ann':     round(vol_ann, 4),
            'vol_scalar':  round(vol_scalar, 4),
            'in_crash':    in_crash,
        }

    # ── Short-term returns ─────────────────────────────

    def _get_short_returns(
        self,
        prices: pd.DataFrame,
    ) -> dict[str, dict]:
        """
        Compute 1M and 3M returns for display in CTA table.
        Returns dict of ticker -> {return_1m, return_3m}.
        """
        out = {}
        for ticker in prices.columns:
            col = prices[ticker].dropna()
            r   = {}
            try:
                if len(col) >= 2:
                    r['return_1m'] = float(
                        col.iloc[-1] / col.iloc[-2] - 1
                    )
                if len(col) >= 4:
                    r['return_3m'] = float(
                        col.iloc[-1] / col.iloc[-4] - 1
                    )
            except Exception:
                pass
            out[ticker] = r
        return out

    # ── Asset results builder ──────────────────────────

    def _build_asset_results(
        self,
        cs_df:      pd.DataFrame,
        ts_signals: dict,
    ) -> list[dict]:
        """
        Combine CS and TS results per asset.
        Includes 1M, 3M, 12M returns as percentages.
        Sorted by z-score descending (best momentum first).
        """
        cs_lookup = (
            cs_df.set_index('ticker').to_dict('index')
            if not cs_df.empty else {}
        )

        short_rets = (
            self._get_short_returns(self.prices)
            if self.prices is not None else {}
        )

        results = []
        for ticker, ts in ts_signals.items():
            cs  = cs_lookup.get(ticker, {})
            srs = short_rets.get(ticker, {})

            def pct(val):
                return round(val * 100, 1) \
                    if val is not None else None

            results.append({
                'ticker':      ticker,
                'name':        MOMENTUM_UNIVERSE.get(
                    ticker, {}
                ).get('name', ticker),
                'asset_class': MOMENTUM_UNIVERSE.get(
                    ticker, {}
                ).get('class', 'other'),
                'return_1m':   pct(srs.get('return_1m')),
                'return_3m':   pct(srs.get('return_3m')),
                'return_12m':  pct(ts.get('return_12m')),
                'ts_signal':   ts.get('signal', 'NEUTRAL'),
                'ts_score':    round(
                    ts.get('score', 0.0), 4
                ),
                'cs_rank':     cs.get('rank'),
                'cs_signal':   cs.get('cs_signal', 'NEUTRAL'),
                'z_score':     round(
                    cs.get('z_score', 0.0), 3
                ),
                'vol_ann_pct': pct(ts.get('vol_ann')),
                'vol_scalar':  round(
                    ts.get('vol_scalar', 1.0), 3
                ),
                'in_crash':    ts.get('in_crash', False),
            })

        return sorted(
            results,
            key=lambda x: x.get('z_score') or 0.0,
            reverse=True,
        )

    # ── Composite signal ───────────────────────────────

    def _composite_signal(
        self,
        cs_df:      pd.DataFrame,
        ts_signals: dict,
    ) -> dict:
        """
        Combine CS and TS momentum into composite signal.
        Equal weighting: 50% CS, 50% TS.

        CS contribution: mean cross-sectional z-score.
        TS contribution: mean of risk-managed TS scores.
        Both clipped to [-1, +1] before combining.
        """
        components = []

        # CS contribution
        if (not cs_df.empty and
                'z_score' in cs_df.columns):
            cs_mean  = float(cs_df['z_score'].mean())
            cs_score = float(np.clip(cs_mean, -1.0, 1.0))
            components.append(('cs', cs_score, 0.50))

        # TS contribution
        ts_scores = [
            t['score']
            for t in ts_signals.values()
            if isinstance(t.get('score'), (int, float))
        ]
        if ts_scores:
            ts_mean  = float(np.mean(ts_scores))
            ts_score = float(np.clip(ts_mean, -1.0, 1.0))
            components.append(('ts', ts_score, 0.50))

        if not components:
            return {
                'score':       0.0,
                'direction':   'NEUTRAL',
                'conviction':  'LOW',
                'n_uptrend':    0,
                'n_downtrend':  0,
                'breadth_pct':  0.5,
                'cs_score':     0.0,
                'ts_score':     0.0,
            }

        # Weighted average
        total_w   = sum(c[2] for c in components)
        composite = sum(
            c[1] * c[2] for c in components
        ) / total_w
        composite = float(np.clip(composite, -1.0, 1.0))

        # Direction from score level
        if   composite >  0.15: direction = 'RISK_ON'
        elif composite < -0.15: direction = 'RISK_OFF'
        else:                   direction = 'NEUTRAL'

        # Conviction from magnitude
        abs_c      = abs(composite)
        conviction = (
            'HIGH'   if abs_c >= 0.50 else
            'MEDIUM' if abs_c >= 0.25 else
            'LOW'
        )

        # Breadth: fraction of assets in uptrend
        n_up   = sum(
            1 for t in ts_signals.values()
            if t.get('signal') == 'UPTREND'
        )
        n_down = sum(
            1 for t in ts_signals.values()
            if t.get('signal') == 'DOWNTREND'
        )
        n_total = n_up + n_down

        return {
            'score':       round(composite, 4),
            'direction':   direction,
            'conviction':  conviction,
            'n_uptrend':   n_up,
            'n_downtrend': n_down,
            'breadth_pct': round(
                n_up / n_total if n_total > 0 else 0.5,
                3
            ),
            'cs_score':    round(
                components[0][1]
                if components else 0.0,
                4
            ),
            'ts_score':    round(
                components[1][1]
                if len(components) > 1 else 0.0,
                4
            ),
        }

    # ── Staleness check ────────────────────────────────

    def _is_stale(self, hours: int = 4) -> bool:
        """Return True if cached prices are older than hours."""
        if not self.last_fetch:
            return True
        fetched = datetime.fromisoformat(self.last_fetch)
        return (
            datetime.utcnow() - fetched >
            timedelta(hours=hours)
        )

    # ── Empty result ───────────────────────────────────

    def _empty_result(self) -> dict:
        """Return safe empty result when model cannot run."""
        return {
            'composite': {
                'score':       0.0,
                'direction':   'NEUTRAL',
                'conviction':  'LOW',
                'n_uptrend':    0,
                'n_downtrend':  0,
                'breadth_pct':  0.5,
            },
            'assets':        [],
            'crash_pct':     0.0,
            'n_assets':      0,
            'last_updated':  None,
            'papers': [
                'Jegadeesh & Titman (1993) JF 48(1)',
                'Moskowitz et al. (2012) JFE 104(2)',
                'Barroso & Santa-Clara (2015) JFE 116(1)',
            ],
        }

    # ── Full model run ─────────────────────────────────

    def run(self) -> dict:
        """
        Run the complete momentum model pipeline:
          1. Use cached prices or fetch fresh
          2. Cross-sectional momentum ranking
          3. Time-series momentum per asset
          4. Build composite signal
          5. Apply crash regime filter
          6. Return full result dict

        Called every time the CTA endpoint is hit.
        Prices cached for 4 hours to avoid rate limits.
        """
        # Fetch if needed
        if self.prices is None or self._is_stale(hours=4):
            try:
                self.fetch_prices()
            except Exception as e:
                logger.error(
                    f'[MOMENTUM] Price fetch failed: {e}'
                )
                return self._empty_result()

        if self.prices is None:
            return self._empty_result()

        # Step 1: Cross-sectional momentum
        try:
            cs_df = self.cross_sectional_momentum()
        except Exception as e:
            logger.error(
                f'[MOMENTUM] CS momentum failed: {e}'
            )
            cs_df = pd.DataFrame()

        # Step 2: Time-series momentum per asset
        ts_signals: dict = {}
        for ticker in self.prices.columns:
            try:
                ts_signals[ticker] = \
                    self.time_series_momentum(ticker)
            except Exception as e:
                logger.warning(
                    f'[MOMENTUM] TS failed {ticker}: {e}'
                )
                continue

        if not ts_signals:
            logger.error('[MOMENTUM] No TS signals computed')
            return self._empty_result()

        # Step 3: Composite signal
        composite = self._composite_signal(
            cs_df, ts_signals
        )

        # Step 4: Crash regime filter
        # Per Barroso & Santa-Clara (2015):
        # If > 50% of assets in crash vol regime,
        # reduce composite score by 75%
        n_crash  = sum(
            1 for t in ts_signals.values()
            if t.get('in_crash', False)
        )
        crash_pct = n_crash / max(len(ts_signals), 1)

        if crash_pct > 0.50:
            composite['score']    *= 0.25
            composite['score']     = round(
                composite['score'], 4
            )
            composite['direction'] = 'CAUTION'
            composite['conviction'] = 'LOW'
            composite['regime_filter_active'] = True
            logger.warning(
                f'[MOMENTUM] Crash filter active: '
                f'{n_crash}/{len(ts_signals)} assets '
                f'in crash vol regime'
            )
        else:
            composite['regime_filter_active'] = False

        # Step 5: Asset-level results for display
        assets = self._build_asset_results(
            cs_df, ts_signals
        )

        return {
            'composite':    composite,
            'assets':       assets,
            'crash_pct':    round(crash_pct, 3),
            'n_assets':     len(ts_signals),
            'last_updated': self.last_fetch,
            'papers': [
                'Jegadeesh & Titman (1993) JF 48(1)',
                'Moskowitz et al. (2012) JFE 104(2)',
                'Barroso & Santa-Clara (2015) JFE 116(1)',
            ],
        }


# ── Module-level singleton ────────────────────────────────

_momentum_model: MomentumFactorModel | None = None


def get_momentum_model() -> MomentumFactorModel:
    """
    Return the singleton MomentumFactorModel.
    Fetches prices on first call.
    """
    global _momentum_model
    if _momentum_model is None:
        _momentum_model = MomentumFactorModel()
        try:
            _momentum_model.fetch_prices()
            logger.info('[MOMENTUM] Model initialised')
        except Exception as e:
            logger.error(
                f'[MOMENTUM] Init failed: {e}'
            )
    return _momentum_model


def get_momentum_signal() -> dict:
    """
    Get current composite momentum signal.
    Used by the Bayesian ensemble collector.

    Returns:
      score:      float in [-1, +1]
      direction:  'RISK_ON' | 'RISK_OFF' | 'NEUTRAL'
      confidence: float in [0, 1]
      conviction: 'HIGH' | 'MEDIUM' | 'LOW'
    """
    try:
        model  = get_momentum_model()
        result = model.run()
        comp   = result['composite']

        return {
            'score':      comp['score'],
            'direction':  comp['direction'],
            'confidence': (
                0.80 if comp['conviction'] == 'HIGH'
                else 0.60 if comp['conviction'] == 'MEDIUM'
                else 0.40
            ),
            'conviction':  comp['conviction'],
            'n_uptrend':   comp.get('n_uptrend',  0),
            'n_downtrend': comp.get('n_downtrend', 0),
            'breadth_pct': comp.get('breadth_pct', 0.5),
            'method':      'Cross-Sectional + TS Momentum',
            'papers': [
                'Jegadeesh & Titman (1993) JF 48(1)',
                'Moskowitz et al. (2012) JFE 104(2)',
            ],
        }

    except Exception as e:
        logger.error(f'[MOMENTUM] Signal failed: {e}')
        return {
            'score':      0.0,
            'direction':  'NEUTRAL',
            'confidence': 0.40,
            'conviction': 'LOW',
            'method':     'fallback',
        }


def refresh_momentum_prices() -> dict:
    """
    Force refresh of price data.
    Called by hourly Celery/APScheduler task.
    """
    global _momentum_model
    if _momentum_model is None:
        _momentum_model = MomentumFactorModel()

    try:
        _momentum_model.fetch_prices()
        return {
            'status':   'ok',
            'n_assets': len(
                _momentum_model.prices.columns
            ) if _momentum_model.prices is not None
              else 0,
            'updated':  _momentum_model.last_fetch,
        }
    except Exception as e:
        logger.error(f'[MOMENTUM] Refresh failed: {e}')
        return {'status': 'error', 'message': str(e)}
