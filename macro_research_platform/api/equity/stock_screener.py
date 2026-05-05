"""
Macro-Aware Stock Screener — Filter Universe by Regime

Combines multiple signals to filter stock universe:
1. Sector rotation alignment
2. Factor exposure match
3. Earnings revision momentum
4. Valuation thresholds
5. Technical signals

Provides ranked list of actionable ideas.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Dict, List, Optional, Callable
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class ScreenedStock:
    """Stock that passed screening criteria."""
    ticker: str
    name: str
    sector: str
    market_cap: float
    composite_score: float
    rank: int
    criteria_passed: List[str]
    red_flags: List[str]
    key_metrics: Dict[str, float]


@dataclass
class ScreenerResult:
    """Result of screening operation."""
    timestamp: datetime
    regime: str
    total_universe: int
    passed_count: int
    pass_rate: float
    top_picks: List[ScreenedStock]
    criteria_breakdown: Dict[str, int]


class MacroStockScreener:
    """
    Screen stock universe using macro-aware criteria.

    Filters applied sequentially (AND logic):
    1. Sector alignment with regime
    2. Factor exposure match
    3. Minimum quality score
    4. Valuation thresholds
    5. Earnings momentum
    """

    def __init__(self):
        self.criteria: Dict[str, Callable] = {}

    def add_criterion(self, name: str, func: Callable):
        """Add a screening criterion."""
        self.criteria[name] = func

    def screen(
        self,
        universe: pd.DataFrame,
        regime: str,
        min_market_cap: float = 1e9,  # $1B
    ) -> ScreenerResult:
        """
        Screen universe based on macro criteria.

        Args:
            universe: DataFrame with stock data
            regime: Current macro regime
            min_market_cap: Minimum market cap in USD
        """
        passed_stocks = []
        criteria_counts = {name: 0 for name in self.criteria}
        criteria_counts["market_cap"] = 0

        for _, row in universe.iterrows():
            # Market cap filter
            if row.get("market_cap", 0) < min_market_cap:
                continue
            criteria_counts["market_cap"] += 1

            passed_criteria = []
            red_flags = []

            # Apply each criterion
            for name, criterion in self.criteria.items():
                try:
                    result = criterion(row, regime)
                    if result["pass"]:
                        passed_criteria.append(name)
                        criteria_counts[name] += 1
                    else:
                        red_flags.append(result.get("reason", name))
                except Exception as e:
                    logger.debug(f"Criterion {name} failed for {row.get('ticker')}: {e}")
                    continue

            # Must pass all criteria
            if len(passed_criteria) == len(self.criteria):
                # Calculate composite score
                composite = self._calculate_composite_score(row, regime)

                stock = ScreenedStock(
                    ticker=row.get("ticker", "UNKNOWN"),
                    name=row.get("name", ""),
                    sector=row.get("sector", "Unknown"),
                    market_cap=row.get("market_cap", 0),
                    composite_score=round(composite, 3),
                    rank=0,  # Set after sorting
                    criteria_passed=passed_criteria,
                    red_flags=red_flags,
                    key_metrics={
                        "pe": row.get("pe_ratio", 0),
                        "peg": row.get("peg_ratio", 0),
                        "eps_growth": row.get("eps_growth", 0),
                        "roa": row.get("roa", 0),
                    },
                )
                passed_stocks.append(stock)

        # Sort by composite score
        passed_stocks.sort(key=lambda x: x.composite_score, reverse=True)
        for i, s in enumerate(passed_stocks):
            s.rank = i + 1

        total = len(universe)
        passed = len(passed_stocks)
        pass_rate = passed / total if total > 0 else 0

        return ScreenerResult(
            timestamp=datetime.now(),
            regime=regime,
            total_universe=total,
            passed_count=passed,
            pass_rate=round(pass_rate, 3),
            top_picks=passed_stocks[:20],
            criteria_breakdown=criteria_counts,
        )

    def _calculate_composite_score(self, row: pd.Series, regime: str) -> float:
        """Calculate composite quality score for a stock."""
        scores = []

        # Valuation score (lower P/E = better)
        pe = row.get("pe_ratio", 0)
        if 5 < pe < 25:
            scores.append(1 - (pe - 5) / 20)

        # Growth score
        growth = row.get("eps_growth", 0)
        scores.append(min(max(growth / 0.2, 0), 1))  # 20% growth = max score

        # Quality score
        roa = row.get("roa", 0)
        scores.append(min(max(roa / 0.15, 0), 1))  # 15% ROA = max score

        # Momentum score
        momentum = row.get("price_momentum_12m", 0)
        scores.append((momentum + 0.5) / 1.0)  # Normalize

        return np.mean(scores) if scores else 0.5


# Pre-built criteria functions
def sector_alignment_criterion(sector_scores: Dict[str, float]):
    """Factory for sector alignment criterion."""
    def criterion(row: pd.Series, regime: str) -> Dict:
        sector = row.get("sector", "Unknown")
        score = sector_scores.get(sector, 0)
        return {
            "pass": score > 0.2,
            "reason": f"{sector} not aligned with {regime}" if score <= 0.2 else None,
        }
    return criterion


def quality_criterion(min_roa: float = 0.05):
    """Factory for quality criterion."""
    def criterion(row: pd.Series, regime: str) -> Dict:
        roa = row.get("roa", 0)
        return {
            "pass": roa >= min_roa,
            "reason": f"ROA {roa:.1%} < {min_roa:.1%}" if roa < min_roa else None,
        }
    return criterion


def valuation_criterion(max_pe: float = 30.0, max_peg: float = 2.0):
    """Factory for valuation criterion."""
    def criterion(row: pd.Series, regime: str) -> Dict:
        pe = row.get("pe_ratio", 0)
        peg = row.get("peg_ratio", 0)
        if pe <= 0 or pe > max_pe:
            return {"pass": False, "reason": f"P/E {pe:.1f} > {max_pe}"}
        if peg > max_peg:
            return {"pass": False, "reason": f"PEG {peg:.1f} > {max_peg}"}
        return {"pass": True}
    return criterion


def earnings_momentum_criterion(min_revision: float = 0.05):
    """Factory for earnings momentum criterion."""
    def criterion(row: pd.Series, regime: str) -> Dict:
        revision = row.get("eps_revision", 0)
        return {
            "pass": revision >= min_revision,
            "reason": f"EPS revision {revision:.1%} < {min_revision:.1%}" if revision < min_revision else None,
        }
    return criterion


def create_default_screener(
    sector_scores: Dict[str, float],
) -> MacroStockScreener:
    """
    Create screener with default criteria.
    """
    screener = MacroStockScreener()
    screener.add_criterion("sector_alignment", sector_alignment_criterion(sector_scores))
    screener.add_criterion("quality", quality_criterion(min_roa=0.05))
    screener.add_criterion("valuation", valuation_criterion(max_pe=30, max_peg=2))
    screener.add_criterion("earnings_momentum", earnings_momentum_criterion(min_revision=0.03))

    return screener


def get_screening_summary(result: ScreenerResult) -> Dict:
    """
    Generate human-readable summary of screening results.
    """
    return {
        "regime": result.regime,
        "universe_size": result.total_universe,
        "passed": result.passed_count,
        "pass_rate": f"{result.pass_rate:.1%}",
        "top_picks": [
            {
                "rank": s.rank,
                "ticker": s.ticker,
                "sector": s.sector,
                "score": s.composite_score,
                "metrics": s.key_metrics,
            }
            for s in result.top_picks[:10]
        ],
        "criteria_breakdown": result.criteria_breakdown,
    }
