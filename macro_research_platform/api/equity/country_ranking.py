"""
Country/Market Ranking Engine — Macro-Driven Market Selection

Ranks countries/markets by macro attractiveness.
Integrates:
1. Growth differential vs US/global
2. Inflation stability
3. Real rates
4. FX valuation
5. Liquidity conditions

Academic Basis:
- Interest rate differentials and FX (Uncovered Interest Parity)
- Relative growth strength
- Terms of trade effects
"""

import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class CountryScore:
    """Macro score for a single country/market."""
    country: str
    ticker: str  # ETF or index ticker
    growth_score: float
    inflation_score: float
    rates_score: float
    fx_score: float
    liquidity_score: float
    composite_score: float
    rank: int
    regime_alignment: str
    signal: str


@dataclass
class CountryRankingModel:
    """Complete country ranking model."""
    timestamp: datetime
    global_regime: str
    rankings: List[CountryScore]
    top_picks: List[CountryScore]
    bottom_avoid: List[CountryScore]
    regional_breakdown: Dict[str, Dict]


# Major markets and their characteristics
MARKETS = [
    {"name": "United States", "ticker": "SPY", "region": "Americas"},
    {"name": "China", "ticker": "MCHI", "region": "Asia"},
    {"name": "Europe", "ticker": "VGK", "region": "Europe"},
    {"name": "Japan", "ticker": "EWJ", "region": "Asia"},
    {"name": "Emerging Markets", "ticker": "EEM", "region": "EM"},
    {"name": "India", "ticker": "INDA", "region": "Asia"},
    {"name": "Brazil", "ticker": "EWZ", "region": "Americas"},
    {"name": "UK", "ticker": "EWU", "region": "Europe"},
    {"name": "Germany", "ticker": "EWG", "region": "Europe"},
]


class CountryRankingEngine:
    """
    Rank countries by macro attractiveness.

    Higher score = more attractive for equity allocation.
    """

    def __init__(self):
        self.country_data = {}

    def calculate_scores(
        self,
        macro_data: Dict[str, Dict],
        global_regime: str,
    ) -> CountryRankingModel:
        """
        Calculate country scores from macro data.

        Args:
            macro_data: Dict of {country: {gdp_growth, inflation, real_rate, ...}}
            global_regime: Current global regime
        """
        scores = []

        for market in MARKETS:
            country = market["name"]
            data = macro_data.get(country, {})

            if not data:
                continue

            # Component scores (0-1 scale, higher = better)
            # Growth score: higher growth = better
            growth = data.get("gdp_growth", 0)
            growth_score = min(max((growth + 2) / 6, 0), 1)  # -2% to 4% range

            # Inflation score: stable inflation (1-3%) = best
            inflation = data.get("inflation", 0)
            inflation_score = 1 - abs(inflation - 2) / 4  # Peak at 2%
            inflation_score = max(0, inflation_score)

            # Rates score: positive real rates = good
            real_rate = data.get("real_rate", 0)
            rates_score = min(max((real_rate + 2) / 4, 0), 1)

            # FX score: undervalued = potential appreciation
            fx_valuation = data.get("fx_valuation", 0)
            fx_score = min(max((fx_valuation + 20) / 40, 0), 1)

            # Liquidity score: central bank dovish = supportive
            cb_stance = data.get("cb_stance", 0)  # -1 hawkish to +1 dovish
            liquidity_score = (cb_stance + 1) / 2

            # Composite score (weighted average)
            weights = [0.30, 0.20, 0.20, 0.15, 0.15]
            composite = (
                growth_score * weights[0] +
                inflation_score * weights[1] +
                rates_score * weights[2] +
                fx_score * weights[3] +
                liquidity_score * weights[4]
            )

            # Regime alignment
            if global_regime in ["Goldilocks", "Reflation"]:
                regime_align = "favorable" if growth_score > 0.5 else "unfavorable"
            else:
                regime_align = "favorable" if liquidity_score > 0.5 else "unfavorable"

            # Signal
            if composite > 0.7:
                signal = "overweight"
            elif composite < 0.4:
                signal = "underweight"
            else:
                signal = "neutral"

            score = CountryScore(
                country=country,
                ticker=market["ticker"],
                growth_score=round(growth_score, 3),
                inflation_score=round(inflation_score, 3),
                rates_score=round(rates_score, 3),
                fx_score=round(fx_score, 3),
                liquidity_score=round(liquidity_score, 3),
                composite_score=round(composite, 3),
                rank=0,  # Set after sorting
                regime_alignment=regime_align,
                signal=signal,
            )
            scores.append(score)

        # Sort by composite score and assign ranks
        scores.sort(key=lambda x: x.composite_score, reverse=True)
        for i, s in enumerate(scores):
            s.rank = i + 1

        # Top and bottom
        top = [s for s in scores if s.signal == "overweight"][:5]
        bottom = [s for s in scores if s.signal == "underweight"][-5:]

        # Regional breakdown
        regions = {}
        for s in scores:
            region = MARKETS[[m["name"] for m in MARKETS].index(s.country)]["region"]
            if region not in regions:
                regions[region] = {"scores": [], "countries": []}
            regions[region]["scores"].append(s.composite_score)
            regions[region]["countries"].append(s.country)

        regional = {
            r: {
                "avg_score": round(np.mean(data["scores"]), 3),
                "countries": data["countries"],
            }
            for r, data in regions.items()
        }

        return CountryRankingModel(
            timestamp=datetime.now(),
            global_regime=global_regime,
            rankings=scores,
            top_picks=top,
            bottom_avoid=bottom,
            regional_breakdown=regional,
        )


def get_country_allocation(
    model: CountryRankingModel,
    total_weight: float = 1.0,
) -> Dict[str, float]:
    """
    Generate country allocation weights based on rankings.
    """
    allocations = {}
    total_score = sum(s.composite_score for s in model.top_picks)

    if total_score > 0 and model.top_picks:
        for s in model.top_picks:
            allocations[s.ticker] = round(
                (s.composite_score / total_score) * total_weight, 3
            )
    else:
        # Equal weight fallback
        n = len(model.top_picks) if model.top_picks else 1
        for s in model.top_picks:
            allocations[s.ticker] = round(total_weight / n, 3)

    return allocations


def detect_country_inflection(
    current_model: CountryRankingModel,
    previous_model: Optional[CountryRankingModel],
) -> Optional[Dict]:
    """
    Detect if a country has had significant rank change.
    """
    if not previous_model:
        return None

    big_moves = []
    prev_ranks = {s.country: s.rank for s in previous_model.rankings}

    for s in current_model.rankings:
        if s.country in prev_ranks:
            change = prev_ranks[s.country] - s.rank  # Positive = moved up
            if abs(change) >= 3:
                big_moves.append({
                    "country": s.country,
                    "rank_change": change,
                    "new_rank": s.rank,
                    "old_rank": prev_ranks[s.country],
                })

    if big_moves:
        return {
            "inflection": True,
            "moves": big_moves,
            "signal": "review_country_allocations",
        }

    return None
