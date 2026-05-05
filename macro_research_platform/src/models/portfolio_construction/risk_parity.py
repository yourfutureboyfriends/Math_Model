"""
Risk Parity Allocator — Bridgewater All Weather Framework

Implements the equal risk contribution (ERC) portfolio from Qian (2005),
"Risk Parity Portfolios: Efficient Portfolios Through True Diversification"

ACADEMIC BASIS
==============
Edward Qian (PanAgora) showed that conventional 60/40 portfolios are NOT
balanced — equities account for ~90% of portfolio risk (not 60% of capital).
True diversification requires equal RISK contribution, not equal capital.

Bridgewater's All Weather portfolio achieves this across four "environments":

  ┌──────────────────┬─────────────────────────────────────┐
  │ Environment      │ Assets that do well                 │
  ├──────────────────┼─────────────────────────────────────┤
  │ Growth ↑         │ Equities, Credit                    │
  │ Growth ↓         │ Treasuries, Inflation-Linked bonds  │
  │ Inflation ↑      │ Commodities, TIPS, Gold             │
  │ Inflation ↓      │ Nominal Treasuries, Equities        │
  └──────────────────┴─────────────────────────────────────┘

The insight: hold something from EVERY environment.
Weight by how much risk each contributes, not by dollars.

FORMULAS
========
Naive Risk Parity (Inverse Volatility):
  w_i = (1 / σ_i) / Σ_j (1 / σ_j)

Full Equal Risk Contribution (ERC, Qian 2005):
  w_i = argmin Σ_i (RC_i - σ_p/N)²
  where RC_i = w_i × (Σw)_i / σ_p  [risk contribution of asset i]

This implementation provides both:
  1. Naive inverse-vol (fast, no optimisation)
  2. ERC (iterative Newton-Raphson convergence)

ASSET CLASS PROXIES (from available FRED data)
===============================================
  Equities:    S&P 500 (SP500) or equity_momentum_12m
  Bonds:       10Y Treasury yield inverse (price ↑ when yield ↓)
  Commodities: Oil price (proxy for broader commodity complex)
  Credit:      HY spread inverse (tighter = positive)
  Real Assets: Breakeven inflation (TIPS proxy)
  Cash:        Fed Funds rate (short-end rate)

REFERENCE
=========
Qian, E. (2005). "Risk Parity Portfolios: Efficient Portfolios Through True
Diversification." PanAgora Asset Management White Paper.

Dalio, R. (2004). "Engineering Targeted Returns and Risks." Bridgewater
Associates. (Foundation of All Weather strategy).

Ilmanen, A. (2011). "Expected Returns." Wiley Finance. Chapter 10.
"""

import logging
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class AssetClassProxy:
    """Definition of an All Weather asset class and how to proxy it from data."""
    name: str
    label: str
    environment: str           # "growth_up", "growth_down", "inflation_up", "inflation_down"
    columns: List[str]         # Column aliases to look for (first available wins)
    direction: int             # +1 = higher series value = positive return, -1 = inverse
    description: str


@dataclass
class RiskParityResult:
    """Result from risk parity computation."""
    weights: Dict[str, float]                  # Normalised allocation weights
    risk_contributions: Dict[str, float]       # % of portfolio risk from each asset
    volatilities: Dict[str, float]             # Annualised volatility per asset class
    portfolio_vol: float                       # Expected portfolio volatility (annualised %)
    diversification_ratio: float               # Weighted avg vol / portfolio vol (>1 = diversified)
    regime_positioning: str                    # Current regime interpretation
    description: str
    method: str                                # "inverse_vol" or "erc"


# =============================================================================
# All Weather Asset Class Definitions
# =============================================================================

ALL_WEATHER_ASSETS = [
    AssetClassProxy(
        name="equities",
        label="Global Equities",
        environment="growth_up / inflation_down",
        columns=["sp500", "equity_momentum_12m", "SP500"],
        direction=+1,
        description="Equities do best in growth-up / inflation-stable environments. "
                    "Key risk: recession and re-rating risk.",
    ),
    AssetClassProxy(
        name="nominal_bonds",
        label="Long-Term Treasuries",
        environment="growth_down / inflation_down",
        columns=["yield_10y", "us_10y_yield", "DGS10"],
        direction=-1,   # Bond PRICE moves inverse to yield
        description="Nominal Treasuries do best when growth and inflation are falling. "
                    "The classic 'risk-off' safe haven. Duration risk is the primary factor.",
    ),
    AssetClassProxy(
        name="commodities",
        label="Commodities / Real Assets",
        environment="inflation_up",
        columns=["oil_price", "ppi_yoy", "us_ppi"],
        direction=+1,
        description="Commodities protect in inflation-up environments. "
                    "Also positively correlated with growth acceleration.",
    ),
    AssetClassProxy(
        name="credit",
        label="Credit / High Yield",
        environment="growth_up",
        columns=["hy_spreads", "high_yield_spread", "bbb_spread"],
        direction=-1,   # Tighter spreads = positive credit return
        description="Credit (HY bonds) does well in growth-up environments. "
                    "Exposed to default cycles; spreads widen sharply in recessions.",
    ),
    AssetClassProxy(
        name="inflation_linked",
        label="Inflation-Linked / TIPS",
        environment="inflation_up",
        columns=["inflation_breakeven_10y", "T10YIE", "core_pce_yoy", "cpi_yoy"],
        direction=+1,
        description="TIPS / inflation-linked bonds outperform in inflation-up environments. "
                    "Real yield is the discount rate; nominal bonds lose purchasing power.",
    ),
]


# =============================================================================
# Risk Parity Model
# =============================================================================

class RiskParityAllocator:
    """
    Compute All Weather risk parity allocation from available macro data.

    The allocation represents how much risk each All Weather "bucket" should
    contribute to a balanced portfolio — equal risk from each environment.

    Two methods available:
      1. inverse_vol: w_i ∝ 1/σ_i  (naïve, fast, good approximation)
      2. erc: full equal risk contribution via iterative optimisation
    """

    def __init__(
        self,
        vol_window: int = 36,    # Months for rolling volatility estimate
        min_periods: int = 12,
        method: str = "inverse_vol",
    ):
        self.vol_window = vol_window
        self.min_periods = min_periods
        self.method = method

    def _get_return_proxy(self, df: pd.DataFrame, asset: AssetClassProxy) -> Optional[pd.Series]:
        """
        Extract a monthly return proxy for an asset class from available data.

        We approximate returns using:
        - Price series: pct_change(1) = 1-month return
        - Yield series (direction=-1): -diff(1) ≈ bond price return (duration-adjusted)
        - Flow series: pct_change(1)
        """
        for col in asset.columns:
            if col in df.columns:
                series = df[col].copy().ffill()
                if series.dropna().empty:
                    continue

                if asset.direction == +1:
                    # Return = month-on-month % change
                    returns = series.pct_change(1) * 100
                else:
                    # Inverse: e.g., bond PRICE up when yield down
                    # Approximate return: -1 × monthly change (level)
                    # Scale: for 10Y yield, 1bp change ≈ 0.10% price change (duration ~10)
                    if "yield" in col.lower() or "spread" in col.lower() or "rate" in col.lower():
                        # Duration-adjusted: 10Y duration ≈ 8-9 years for 10Y bond
                        returns = -series.diff(1) * 8.0
                    else:
                        returns = -series.pct_change(1) * 100

                if returns.dropna().shape[0] >= self.min_periods:
                    return returns.rename(asset.name)

        return None

    def _compute_volatilities(
        self, returns_dict: Dict[str, pd.Series]
    ) -> Dict[str, float]:
        """
        Compute annualised rolling volatility for each asset class.
        Uses the most recent vol_window months, annualised by √12.
        """
        vols = {}
        for name, ret in returns_dict.items():
            clean = ret.dropna()
            window = min(self.vol_window, len(clean))
            if window < self.min_periods:
                # Insufficient history — use a reasonable default
                vols[name] = 15.0   # 15% annualised default
            else:
                vol_monthly = clean.iloc[-window:].std()
                vols[name] = vol_monthly * np.sqrt(12)  # annualise

        return vols

    def _inverse_vol_weights(self, vols: Dict[str, float]) -> Dict[str, float]:
        """
        Naïve risk parity: weight inversely proportional to volatility.
        This is the fast approximation used when correlations are ~equal.
        """
        inv_vols = {k: 1.0 / max(v, 0.01) for k, v in vols.items()}
        total = sum(inv_vols.values())
        return {k: v / total for k, v in inv_vols.items()}

    def _erc_weights(
        self,
        returns_dict: Dict[str, pd.Series],
        vols: Dict[str, float],
        n_iter: int = 200,
    ) -> Dict[str, float]:
        """
        Full Equal Risk Contribution via iterative Spinu algorithm.

        Converges to weights where each asset contributes exactly 1/N
        of total portfolio risk.

        Reference: Spinu (2013) "An Algorithm for Computing Risk Parity Weights"
        (more numerically stable than Newton-Raphson for ERC).
        """
        names = list(returns_dict.keys())
        n = len(names)
        if n == 0:
            return {}

        # Build return matrix and covariance
        ret_df = pd.concat(list(returns_dict.values()), axis=1).dropna()
        if len(ret_df) < self.min_periods:
            logger.warning("Insufficient return history for ERC — falling back to inverse-vol")
            return self._inverse_vol_weights(vols)

        Sigma = ret_df.cov().values  # monthly covariance matrix

        # Initialise: inverse-vol starting weights
        inv_v = np.array([1.0 / max(vols[n], 0.01) for n in names])
        w = inv_v / inv_v.sum()

        # Iterative Spinu algorithm
        for _ in range(n_iter):
            Sw = Sigma @ w
            portfolio_var = w @ Sw
            if portfolio_var <= 0:
                break
            # Gradient: risk contribution of each asset
            rc = w * Sw / np.sqrt(portfolio_var)
            target_rc = np.sqrt(portfolio_var) / n

            # Update: move towards equal risk contribution
            w_new = w * (target_rc / (rc + 1e-10))
            w_new = np.maximum(w_new, 1e-6)   # no negative weights
            w_new /= w_new.sum()

            if np.max(np.abs(w_new - w)) < 1e-8:
                break
            w = w_new

        return dict(zip(names, w.tolist()))

    def _compute_risk_contributions(
        self,
        weights: Dict[str, float],
        returns_dict: Dict[str, pd.Series],
    ) -> Tuple[Dict[str, float], float]:
        """
        Compute actual risk contributions given final weights.

        Returns (risk_contributions_pct, portfolio_vol_annualised)
        """
        names = list(weights.keys())
        w = np.array([weights[n] for n in names])

        ret_df = pd.concat(
            [returns_dict[n] for n in names], axis=1
        ).dropna()

        if len(ret_df) < self.min_periods:
            equal_share = 100.0 / len(names)
            return {n: equal_share for n in names}, 10.0

        Sigma = ret_df.cov().values
        Sw = Sigma @ w
        port_var = w @ Sw
        port_vol_monthly = np.sqrt(port_var)
        port_vol_annual = port_vol_monthly * np.sqrt(12)

        rc = (w * Sw) / port_var  # fractional risk contribution
        rc_pct = {n: round(float(rc[i]) * 100, 1) for i, n in enumerate(names)}

        return rc_pct, round(float(port_vol_annual), 2)

    def _diversification_ratio(
        self,
        weights: Dict[str, float],
        vols: Dict[str, float],
        portfolio_vol: float,
    ) -> float:
        """
        Diversification Ratio = weighted avg vol / portfolio vol.
        > 1 means the portfolio benefits from diversification.
        """
        w_avg_vol = sum(weights[k] * vols[k] for k in weights)
        return round(w_avg_vol / max(portfolio_vol, 0.01), 3)

    def compute(self, df: pd.DataFrame) -> RiskParityResult:
        """
        Compute risk parity allocation from a raw macro DataFrame.

        Args:
            df: DataFrame with macro indicator columns

        Returns:
            RiskParityResult with weights, risk contributions, and descriptions
        """
        # ---- Build return proxies ----
        returns_dict = {}
        for asset in ALL_WEATHER_ASSETS:
            ret = self._get_return_proxy(df, asset)
            if ret is not None:
                returns_dict[asset.name] = ret
                logger.debug("Risk parity: using %s for %s", ret.name, asset.label)
            else:
                logger.debug("Risk parity: no data for %s", asset.name)

        if not returns_dict:
            logger.warning("No asset return proxies available for risk parity")
            equal_w = {a.name: 1.0 / len(ALL_WEATHER_ASSETS) for a in ALL_WEATHER_ASSETS}
            return RiskParityResult(
                weights=equal_w,
                risk_contributions={k: 100.0 / len(equal_w) for k in equal_w},
                volatilities={k: 10.0 for k in equal_w},
                portfolio_vol=10.0,
                diversification_ratio=1.0,
                regime_positioning="unknown",
                description="No return data available; using equal weights",
                method="equal_weight_fallback",
            )

        # ---- Compute volatilities ----
        vols = self._compute_volatilities(returns_dict)

        # ---- Compute weights ----
        if self.method == "erc" and len(returns_dict) >= 2:
            weights = self._erc_weights(returns_dict, vols)
        else:
            weights = self._inverse_vol_weights(vols)

        # ---- Risk contributions ----
        rc_pct, port_vol = self._compute_risk_contributions(weights, returns_dict)

        # ---- Diversification ratio ----
        div_ratio = self._diversification_ratio(weights, vols, port_vol)

        # ---- Regime positioning ----
        if "equities" in weights and "nominal_bonds" in weights:
            eq_w = weights.get("equities", 0)
            bond_w = weights.get("nominal_bonds", 0)
            comm_w = weights.get("commodities", 0)
            if eq_w > 0.35:
                positioning = "Growth-Overweight (equities dominant risk)"
            elif bond_w > 0.35:
                positioning = "Defensive (bonds dominant risk)"
            elif comm_w > 0.25:
                positioning = "Inflation-Hedged (real assets elevated)"
            else:
                positioning = "Balanced All Weather"
        else:
            positioning = "Balanced"

        # ---- Description ----
        top_asset = max(weights, key=weights.get)
        top_weight = weights[top_asset]
        description = (
            f"Risk Parity ({self.method}): "
            f"{len(weights)} asset classes, "
            f"portfolio vol {port_vol:.1f}% p.a., "
            f"diversification ratio {div_ratio:.2f}x. "
            f"Largest allocation: {top_asset} ({top_weight:.1%})."
        )

        return RiskParityResult(
            weights={k: round(v, 4) for k, v in weights.items()},
            risk_contributions=rc_pct,
            volatilities={k: round(v, 2) for k, v in vols.items()},
            portfolio_vol=port_vol,
            diversification_ratio=div_ratio,
            regime_positioning=positioning,
            description=description,
            method=self.method,
        )


# =============================================================================
# Convenience Functions
# =============================================================================

def get_risk_parity_allocation(
    df: pd.DataFrame,
    method: str = "inverse_vol",
) -> RiskParityResult:
    """
    Compute risk parity (All Weather) allocation.

    Args:
        df: DataFrame with macro indicator columns
        method: "inverse_vol" (fast) or "erc" (full equal risk contribution)

    Returns:
        RiskParityResult with weights and risk contributions
    """
    allocator = RiskParityAllocator(method=method)
    return allocator.compute(df)


def get_all_weather_summary(df: pd.DataFrame) -> dict:
    """Get All Weather allocation as a simple dict for dashboard display."""
    result = get_risk_parity_allocation(df)
    return {
        "weights": result.weights,
        "risk_contributions": result.risk_contributions,
        "portfolio_vol": result.portfolio_vol,
        "diversification_ratio": result.diversification_ratio,
        "positioning": result.regime_positioning,
        "description": result.description,
    }
