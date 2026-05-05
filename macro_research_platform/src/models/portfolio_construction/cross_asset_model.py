"""
Cross-Asset Allocation Model - Upgraded

Professional cross-asset allocation using:
- Regime-based weights
- Factor sensitivities
- Financial conditions impulse
- Credit stress signals
- Market momentum

Asset classes:
- Rates (duration, curve)
- Credit (IG, HY)
- Equities (beta, cyclicals vs defensives)
- Commodities (energy, metals)
- FX (dollar bias)
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class AssetSignal:
    """Asset class signal result."""
    asset_class: str
    category: str
    signal: str  # Overweight, Neutral, Underweight
    score: float
    conviction: str  # Low, Medium, High
    rationale: str


class CrossAssetModel:
    """
    Cross-Asset Allocation Model

    Generates signals across major asset classes based on macro regime,
    financial conditions, and market indicators.
    """

    def __init__(self):
        # Asset class configurations
        self.assets = {
            # Rates
            "duration": {
                "name": "Duration / Government Bonds",
                "category": "rates",
                "regime_weights": {
                    "Goldilocks": -0.2,
                    "Reflation": -0.6,
                    "Slowdown": 0.8,
                    "Stagflation": 0.0,
                },
                "factor_sensitivities": {
                    "growth": -0.4,
                    "inflation": -0.7,
                    "liquidity": 0.6,
                    "risk": -0.3,
                },
                "fc_sensitivities": {
                    "easing": 0.5,
                    "neutral": 0.0,
                    "tightening": -0.5,
                },
                "description": "Interest rate sensitivity through government bond duration",
            },
            "curve_steepener": {
                "name": "Curve Steepener",
                "category": "rates",
                "regime_weights": {
                    "Goldilocks": 0.3,
                    "Reflation": 0.6,
                    "Slowdown": -0.3,
                    "Stagflation": -0.5,
                },
                "factor_sensitivities": {
                    "growth": 0.3,
                    "inflation": 0.4,
                    "liquidity": 0.2,
                    "risk": -0.1,
                },
                "fc_sensitivities": {
                    "easing": 0.3,
                    "neutral": 0.0,
                    "tightening": -0.2,
                },
                "description": "Yield curve positioning - steepener vs flattener bias",
            },

            # Credit
            "high_yield": {
                "name": "High Yield Credit",
                "category": "credit",
                "regime_weights": {
                    "Goldilocks": 0.7,
                    "Reflation": 0.4,
                    "Slowdown": -0.6,
                    "Stagflation": -0.8,
                },
                "factor_sensitivities": {
                    "growth": 0.6,
                    "inflation": -0.2,
                    "liquidity": 0.5,
                    "risk": 0.7,
                },
                "fc_sensitivities": {
                    "easing": 0.6,
                    "neutral": 0.0,
                    "tightening": -0.7,
                },
                "description": "Credit risk exposure through high-yield bonds",
            },
            "investment_grade": {
                "name": "Investment Grade Credit",
                "category": "credit",
                "regime_weights": {
                    "Goldilocks": 0.4,
                    "Reflation": 0.2,
                    "Slowdown": 0.3,
                    "Stagflation": -0.2,
                },
                "factor_sensitivities": {
                    "growth": 0.3,
                    "inflation": -0.4,
                    "liquidity": 0.4,
                    "risk": 0.3,
                },
                "fc_sensitivities": {
                    "easing": 0.3,
                    "neutral": 0.0,
                    "tightening": -0.3,
                },
                "description": "Investment grade credit exposure - hybrid of rates and equity",
            },

            # Equities
            "equity_beta": {
                "name": "Equity Beta",
                "category": "equities",
                "regime_weights": {
                    "Goldilocks": 0.8,
                    "Reflation": 0.6,
                    "Slowdown": -0.4,
                    "Stagflation": -0.6,
                },
                "factor_sensitivities": {
                    "growth": 0.8,
                    "inflation": -0.3,
                    "liquidity": 0.6,
                    "risk": 0.8,
                },
                "fc_sensitivities": {
                    "easing": 0.5,
                    "neutral": 0.0,
                    "tightening": -0.5,
                },
                "description": "Broad equity market exposure",
            },
            "cyclicals_vs_defensives": {
                "name": "Cyclicals vs Defensives",
                "category": "equities",
                "regime_weights": {
                    "Goldilocks": 0.6,
                    "Reflation": 0.5,
                    "Slowdown": -0.5,
                    "Stagflation": -0.3,
                },
                "factor_sensitivities": {
                    "growth": 0.7,
                    "inflation": 0.2,
                    "liquidity": 0.4,
                    "risk": 0.5,
                },
                "fc_sensitivities": {
                    "easing": 0.4,
                    "neutral": 0.0,
                    "tightening": -0.4,
                },
                "description": "Tilt toward cyclical sectors vs defensive sectors",
            },
            "growth_vs_value": {
                "name": "Growth vs Value",
                "category": "equities",
                "regime_weights": {
                    "Goldilocks": 0.2,
                    "Reflation": -0.3,
                    "Slowdown": 0.3,
                    "Stagflation": -0.4,
                },
                "factor_sensitivities": {
                    "growth": 0.2,
                    "inflation": -0.6,
                    "liquidity": 0.7,
                    "risk": 0.3,
                },
                "fc_sensitivities": {
                    "easing": 0.4,
                    "neutral": 0.0,
                    "tightening": -0.4,
                },
                "description": "Tilt toward growth vs value factors",
            },

            # Commodities
            "energy": {
                "name": "Energy Commodities",
                "category": "commodities",
                "regime_weights": {
                    "Goldilocks": 0.3,
                    "Reflation": 0.8,
                    "Slowdown": -0.4,
                    "Stagflation": 0.6,
                },
                "factor_sensitivities": {
                    "growth": 0.4,
                    "inflation": 0.7,
                    "liquidity": 0.1,
                    "risk": 0.2,
                },
                "fc_sensitivities": {
                    "easing": 0.2,
                    "neutral": 0.0,
                    "tightening": -0.1,
                },
                "description": "Crude oil, natural gas, and refined products exposure",
            },
            "industrial_metals": {
                "name": "Industrial Metals",
                "category": "commodities",
                "regime_weights": {
                    "Goldilocks": 0.4,
                    "Reflation": 0.7,
                    "Slowdown": -0.5,
                    "Stagflation": 0.3,
                },
                "factor_sensitivities": {
                    "growth": 0.7,
                    "inflation": 0.5,
                    "liquidity": 0.2,
                    "risk": 0.3,
                },
                "fc_sensitivities": {
                    "easing": 0.3,
                    "neutral": 0.0,
                    "tightening": -0.2,
                },
                "description": "Copper, aluminum, and industrial metals",
            },
            "gold": {
                "name": "Gold",
                "category": "commodities",
                "regime_weights": {
                    "Goldilocks": -0.2,
                    "Reflation": -0.3,
                    "Slowdown": 0.4,
                    "Stagflation": 0.7,
                },
                "factor_sensitivities": {
                    "growth": -0.1,
                    "inflation": 0.5,
                    "liquidity": -0.4,
                    "risk": -0.5,
                },
                "fc_sensitivities": {
                    "easing": 0.3,
                    "neutral": 0.0,
                    "tightening": 0.1,
                },
                "description": "Gold as inflation hedge and risk-off asset",
            },

            # FX
            "dollar_bias": {
                "name": "US Dollar",
                "category": "fx",
                "regime_weights": {
                    "Goldilocks": -0.2,
                    "Reflation": 0.3,
                    "Slowdown": 0.5,
                    "Stagflation": 0.4,
                },
                "factor_sensitivities": {
                    "growth": 0.2,
                    "inflation": -0.2,
                    "liquidity": 0.5,
                    "risk": -0.6,
                },
                "fc_sensitivities": {
                    "easing": -0.2,
                    "neutral": 0.0,
                    "tightening": 0.4,
                },
                "description": "US dollar exposure through DXY or individual currency pairs",
            },
            "safe_haven_fx": {
                "name": "Safe Haven FX",
                "category": "fx",
                "regime_weights": {
                    "Goldilocks": -0.3,
                    "Reflation": -0.2,
                    "Slowdown": 0.6,
                    "Stagflation": 0.3,
                },
                "factor_sensitivities": {
                    "growth": -0.3,
                    "inflation": 0.0,
                    "liquidity": -0.3,
                    "risk": -0.7,
                },
                "fc_sensitivities": {
                    "easing": -0.3,
                    "neutral": 0.0,
                    "tightening": 0.5,
                },
                "description": "JPY, CHF, and other safe haven currencies",
            },
        }

    def compute_asset_score(
        self,
        asset_key: str,
        regime: str,
        scores: Dict[str, float],
        financial_conditions: str = "neutral",
        credit_stress: float = 0.0,
    ) -> AssetSignal:
        """
        Calculate score for a single asset class.

        Formula:
            score = regime_weight * 0.5 + factor_score * 0.3 + fc_score * 0.2
        """
        config = self.assets.get(asset_key, {})

        # 1. Regime component (50%)
        regime_weight = config.get("regime_weights", {}).get(regime, 0.0)

        # 2. Factor component (30%)
        factor_sens = config.get("factor_sensitivities", {})
        factor_score = sum(
            factor_sens.get(f, 0) * scores.get(f, 0)
            for f in ["growth", "inflation", "liquidity", "risk"]
        )

        # 3. Financial conditions component (20%)
        fc_sens = config.get("fc_sensitivities", {}).get(financial_conditions, 0.0)

        # Combine
        total_score = (
            regime_weight * 0.50 +
            factor_score * 0.30 +
            fc_sens * 0.20
        )

        # Adjust for credit stress
        if config.get("category") in ["credit", "equities"]:
            total_score -= credit_stress * 0.3

        # Determine signal
        if total_score > 0.3:
            signal = "Overweight"
        elif total_score < -0.3:
            signal = "Underweight"
        else:
            signal = "Neutral"

        # Determine conviction
        abs_score = abs(total_score)
        if abs_score > 0.6:
            conviction = "High"
        elif abs_score > 0.3:
            conviction = "Medium"
        else:
            conviction = "Low"

        # Build rationale
        category = config.get("category", "")
        if signal == "Overweight":
            rationale = f"Constructive {category} view given {regime} regime"
        elif signal == "Underweight":
            rationale = f"Defensive {category} positioning warranted"
        else:
            rationale = f"Neutral {category} exposure appropriate"

        return AssetSignal(
            asset_class=config.get("name", asset_key),
            category=category,
            signal=signal,
            score=round(total_score, 2),
            conviction=conviction,
            rationale=rationale,
        )

    def compute_all_signals(
        self,
        regime: str,
        growth_score: float,
        inflation_score: float,
        liquidity_score: float,
        risk_score: float,
        financial_conditions: str = "neutral",
        credit_stress: float = 0.0,
    ) -> pd.DataFrame:
        """
        Compute signals for all asset classes.

        Returns:
            DataFrame with asset allocation view
        """
        scores = {
            "growth": growth_score,
            "inflation": inflation_score,
            "liquidity": liquidity_score,
            "risk": risk_score,
        }

        results = []

        for asset_key in self.assets.keys():
            signal = self.compute_asset_score(
                asset_key=asset_key,
                regime=regime,
                scores=scores,
                financial_conditions=financial_conditions,
                credit_stress=credit_stress,
            )

            results.append({
                "Asset Class": signal.asset_class,
                "Category": signal.category,
                "Signal": signal.signal,
                "Score": signal.score,
                "Conviction": signal.conviction,
                "Rationale": signal.rationale,
            })

        return pd.DataFrame(results)

    def get_implementation_view(
        self,
        asset_signals: pd.DataFrame,
    ) -> Dict[str, str]:
        """
        Generate practical implementation guidance.

        Returns:
            Dict mapping asset category to implementation suggestion
        """
        views = {}

        # Rates view
        rates = asset_signals[asset_signals["Category"] == "rates"]
        if not rates.empty:
            ow = len(rates[rates["Signal"] == "Overweight"])
            uw = len(rates[rates["Signal"] == "Underweight"])
            if ow > uw:
                views["rates"] = "Increase duration through long-dated Treasuries"
            elif uw > ow:
                views["rates"] = "Reduce duration, favor floating rate"
            else:
                views["rates"] = "Neutral duration, barbell strategy"

        # Credit view
        credit = asset_signals[asset_signals["Category"] == "credit"]
        if not credit.empty:
            ow = len(credit[credit["Signal"] == "Overweight"])
            uw = len(credit[credit["Signal"] == "Underweight"])
            if ow > uw:
                views["credit"] = "Add credit exposure through HY ETFs"
            elif uw > ow:
                views["credit"] = "Reduce credit beta, favor quality"
            else:
                views["credit"] = "Maintain current credit allocation"

        # Equity view
        equity = asset_signals[asset_signals["Category"] == "equities"]
        if not equity.empty:
            avg_score = equity["Score"].mean()
            if avg_score > 0.2:
                views["equity"] = "Overweight equity beta"
            elif avg_score < -0.2:
                views["equity"] = "Underweight equity beta"
            else:
                views["equity"] = "Neutral equity beta"

        return views


def get_cross_asset_signals(
    regime: str,
    growth_score: float,
    inflation_score: float,
    liquidity_score: float,
    risk_score: float,
    financial_conditions: str = "neutral",
    credit_stress: float = 0.0,
) -> pd.DataFrame:
    """
    Convenience function to get cross-asset signals.
    """
    model = CrossAssetModel()
    return model.compute_all_signals(
        regime=regime,
        growth_score=growth_score,
        inflation_score=inflation_score,
        liquidity_score=liquidity_score,
        risk_score=risk_score,
        financial_conditions=financial_conditions,
        credit_stress=credit_stress,
    )
