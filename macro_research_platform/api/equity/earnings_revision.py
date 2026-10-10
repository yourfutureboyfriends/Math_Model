"""
Earnings Revision Analyzer — Detecting Earnings Momentum

Implements earnings revision analysis for equity selection.
Tracks changes in analyst EPS estimates to identify:
1. Earnings surprise potential
2. Analyst conviction trends
3. Revision momentum (up/down grade ratio)

Academic Basis:
- Latane & Jones (1977) "Standardized Unexpected Earnings"
- Chan, Jegadeesh & Lakonishok (1996) "Momentum Strategies"
- Earnings revision effect: well-documented anomaly

Metrics:
- Revision ratio: # upgrades / # downgrades
- EPS momentum: % change in consensus EPS
- Surprise potential: std dev of estimates (high = uncertainty)
"""

import pandas as pd
from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class EarningsRevisionMetrics:
    """Earnings revision metrics for a single stock."""
    ticker: str
    current_eps: float
    prior_eps: float
    revision_pct: float
    revision_direction: str  # "upgrade", "downgrade", "stable"
    num_analysts: int
    std_dev: float  # Standard deviation of estimates
    surprise_potential: float  # 0-1 scale
    revision_momentum: float  # Trend of revisions
    signal: str  # "buy", "sell", "hold"


@dataclass
class EarningsRevisionModel:
    """Aggregate earnings revision analysis."""
    timestamp: datetime
    total_revisions: int
    upgrade_ratio: float
    sector_breakdown: Dict[str, Dict]
    top_upgrades: List[EarningsRevisionMetrics]
    top_downgrades: List[EarningsRevisionMetrics]
    broad_consensus: str  # "improving", "deteriorating", "stable"


class EarningsRevisionAnalyzer:
    """
    Analyze earnings revisions across universe.

    Identifies stocks with:
    - Positive revision momentum (analysts raising estimates)
    - High conviction (tight estimate dispersion)
    - Earnings surprise potential
    """

    def __init__(self):
        self.revision_history = {}

    def analyze_stock(
        self,
        ticker: str,
        current_estimates: Dict,
        prior_estimates: Optional[Dict] = None,
    ) -> EarningsRevisionMetrics:
        """
        Analyze earnings revisions for single stock.

        Args:
            ticker: Stock ticker
            current_estimates: Dict with keys [eps_consensus, num_analysts, std_dev]
            prior_estimates: Optional prior period estimates
        """
        current_eps = current_estimates.get("eps_consensus", 0)
        num_analysts = current_estimates.get("num_analysts", 0)
        std_dev = current_estimates.get("std_dev", 0)

        if prior_estimates:
            prior_eps = prior_estimates.get("eps_consensus", current_eps)
            revision_pct = (
                (current_eps - prior_eps) / abs(prior_eps) * 100
                if prior_eps != 0 else 0
            )
        else:
            prior_eps = current_eps
            revision_pct = 0

        # Determine direction
        if revision_pct > 5:
            direction = "upgrade"
        elif revision_pct < -5:
            direction = "downgrade"
        else:
            direction = "stable"

        # Surprise potential (higher std = more uncertainty = more surprise potential)
        surprise = min(std_dev / abs(current_eps) if current_eps != 0 else 0, 1.0)

        # Revision momentum (simplified: use revision_pct as proxy)
        momentum = revision_pct

        # Signal
        if direction == "upgrade" and num_analysts >= 5:
            signal = "buy"
        elif direction == "downgrade" and num_analysts >= 5:
            signal = "sell"
        else:
            signal = "hold"

        return EarningsRevisionMetrics(
            ticker=ticker,
            current_eps=round(current_eps, 2),
            prior_eps=round(prior_eps, 2),
            revision_pct=round(revision_pct, 2),
            revision_direction=direction,
            num_analysts=num_analysts,
            std_dev=round(std_dev, 2),
            surprise_potential=round(surprise, 3),
            revision_momentum=round(momentum, 2),
            signal=signal,
        )

    def analyze_universe(
        self,
        estimates_data: pd.DataFrame,
    ) -> EarningsRevisionModel:
        """
        Analyze earnings revisions across universe.

        Args:
            estimates_data: DataFrame with columns [ticker, eps_consensus, num_analysts, ...]
        """
        metrics_list = []

        for _, row in estimates_data.iterrows():
            try:
                ticker = row["ticker"]
                current = {
                    "eps_consensus": row.get("eps_consensus", 0),
                    "num_analysts": row.get("num_analysts", 0),
                    "std_dev": row.get("std_dev", 0),
                }
                prior = None
                if "prior_eps" in row:
                    prior = {"eps_consensus": row["prior_eps"]}

                metrics = self.analyze_stock(ticker, current, prior)
                metrics_list.append(metrics)
            except Exception as e:
                logger.warning(f"Failed to analyze {row.get('ticker', 'UNKNOWN')}: {e}")

        # Aggregate statistics
        upgrades = [m for m in metrics_list if m.revision_direction == "upgrade"]
        downgrades = [m for m in metrics_list if m.revision_direction == "downgrade"]
        total = len(metrics_list)

        upgrade_ratio = len(upgrades) / total if total > 0 else 0.5

        # Broad consensus
        if upgrade_ratio > 0.6:
            consensus = "improving"
        elif upgrade_ratio < 0.4:
            consensus = "deteriorating"
        else:
            consensus = "stable"

        # Sector breakdown
        sector_data = {}

        # Top upgrades/downgrades
        top_upgrades = sorted(
            upgrades,
            key=lambda x: x.revision_pct,
            reverse=True,
        )[:10]

        top_downgrades = sorted(
            downgrades,
            key=lambda x: x.revision_pct,
        )[:10]

        return EarningsRevisionModel(
            timestamp=datetime.now(),
            total_revisions=total,
            upgrade_ratio=round(upgrade_ratio, 3),
            sector_breakdown=sector_data,
            top_upgrades=top_upgrades,
            top_downgrades=top_downgrades,
            broad_consensus=consensus,
        )


def get_earnings_momentum_picks(
    model: EarningsRevisionModel,
    n: int = 5,
    min_analysts: int = 5,
) -> List[Dict]:
    """
    Get stocks with strongest positive earnings revision momentum.
    """
    qualified = [
        m for m in model.top_upgrades
        if m.num_analysts >= min_analysts
    ]

    return [
        {
            "ticker": m.ticker,
            "revision_pct": m.revision_pct,
            "revision_direction": m.revision_direction,
            "num_analysts": m.num_analysts,
            "surprise_potential": m.surprise_potential,
            "signal": m.signal,
        }
        for m in qualified[:n]
    ]


def detect_earnings_cycle_inflection(
    models: List[EarningsRevisionModel],
) -> Optional[Dict]:
    """
    Detect if earnings cycle is at inflection point.

    Args:
        models: Historical revision models
    """
    if len(models) < 3:
        return None

    recent = models[-3:]
    upgrade_ratios = [m.upgrade_ratio for m in recent]

    # Detect trend change
    if upgrade_ratios[-1] > 0.6 and upgrade_ratios[0] < 0.4:
        return {
            "inflection": True,
            "direction": "upturn",
            "confidence": upgrade_ratios[-1],
            "signal": "earnings_cycle_bottoming",
        }
    elif upgrade_ratios[-1] < 0.4 and upgrade_ratios[0] > 0.6:
        return {
            "inflection": True,
            "direction": "downturn",
            "confidence": 1 - upgrade_ratios[-1],
            "signal": "earnings_cycle_peaking",
        }

    return None
