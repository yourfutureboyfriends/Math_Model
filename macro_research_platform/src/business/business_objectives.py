"""
Business Objectives Layer

Defines what the macro research platform produces for the investment fund.
Each output has a clear business purpose, target audience, and decision support role.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from enum import Enum


class BusinessOutputType(Enum):
    """Types of business outputs the platform generates."""
    WEEKLY_MACRO_VIEW = "weekly_macro_view"
    SECTOR_ALLOCATION_VIEW = "sector_allocation_view"
    CROSS_ASSET_VIEW = "cross_asset_view"
    RISK_SIZING_VIEW = "risk_sizing_view"
    INVESTMENT_MEMO = "investment_memo"
    IC_PACK = "investment_committee_pack"
    SIGNAL_SCORECARD = "signal_scorecard"
    DECISION_LOG = "decision_log"
    POSTMORTEM = "model_postmortem"


class ConvictionLevel(Enum):
    """Conviction levels for recommendations."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PositionSize(Enum):
    """Suggested position sizes."""
    NO_POSITION = "no_position"
    WATCHLIST = "watchlist"
    SMALL = "small"
    NORMAL = "normal"
    HIGH_CONVICTION = "high_conviction"


@dataclass
class BusinessObjective:
    """Definition of a business output."""
    output_type: BusinessOutputType
    purpose: str
    target_audience: str
    output_format: str
    decision_supported: str
    frequency: str
    sla_minutes: int  # Expected generation time


# Define all business objectives
BUSINESS_OBJECTIVES = {
    BusinessOutputType.WEEKLY_MACRO_VIEW: BusinessObjective(
        output_type=BusinessOutputType.WEEKLY_MACRO_VIEW,
        purpose="Summarize current macro conditions for the investment committee",
        target_audience="Investment Committee",
        output_format="Markdown memo and dashboard section",
        decision_supported="Portfolio tilt and sector allocation",
        frequency="Weekly (Monday morning)",
        sla_minutes=5
    ),

    BusinessOutputType.SECTOR_ALLOCATION_VIEW: BusinessObjective(
        output_type=BusinessOutputType.SECTOR_ALLOCATION_VIEW,
        purpose="Rank sectors by macro attractiveness",
        target_audience="Portfolio Manager",
        output_format="Table with OW/NW/UW ratings and rationale",
        decision_supported="Sector overweight/neutral/underweight positioning",
        frequency="Weekly or on regime change",
        sla_minutes=3
    ),

    BusinessOutputType.CROSS_ASSET_VIEW: BusinessObjective(
        output_type=BusinessOutputType.CROSS_ASSET_VIEW,
        purpose="Translate macro signals into asset class views",
        target_audience="Investment Committee",
        output_format="Table and memo section with equities, rates, FX, credit, commodities",
        decision_supported="Broad asset allocation decisions",
        frequency="Weekly",
        sla_minutes=3
    ),

    BusinessOutputType.RISK_SIZING_VIEW: BusinessObjective(
        output_type=BusinessOutputType.RISK_SIZING_VIEW,
        purpose="Convert conviction into suggested risk size",
        target_audience="Portfolio Manager",
        output_format="Position sizing table with caps and constraints",
        decision_supported="Watchlist, small position, normal position, high conviction sizing",
        frequency="Weekly or on signal change",
        sla_minutes=2
    ),

    BusinessOutputType.INVESTMENT_MEMO: BusinessObjective(
        output_type=BusinessOutputType.INVESTMENT_MEMO,
        purpose="Research-backed explanation of current view",
        target_audience="Investment Committee and stakeholders",
        output_format="Markdown document with narrative sections",
        decision_supported="Understanding the 'why' behind positioning",
        frequency="Weekly or on significant change",
        sla_minutes=5
    ),

    BusinessOutputType.IC_PACK: BusinessObjective(
        output_type=BusinessOutputType.IC_PACK,
        purpose="Complete investment committee briefing pack",
        target_audience="Investment Committee",
        output_format="Multi-section markdown document",
        decision_supported="IC decision-making process",
        frequency="Weekly",
        sla_minutes=10
    ),

    BusinessOutputType.SIGNAL_SCORECARD: BusinessObjective(
        output_type=BusinessOutputType.SIGNAL_SCORECARD,
        purpose="Track all signals, their confidence, and performance",
        target_audience="Research Team and PM",
        output_format="Table with metrics and status",
        decision_supported="Signal validation and model improvement",
        frequency="Real-time / Weekly",
        sla_minutes=2
    ),

    BusinessOutputType.DECISION_LOG: BusinessObjective(
        output_type=BusinessOutputType.DECISION_LOG,
        purpose="Track model recommendations and actual outcomes",
        target_audience="Research Team and Compliance",
        output_format="CSV/JSON log with audit trail",
        decision_supported="Postmortem analysis and model improvement",
        frequency="Real-time",
        sla_minutes=1
    ),

    BusinessOutputType.POSTMORTEM: BusinessObjective(
        output_type=BusinessOutputType.POSTMORTEM,
        purpose="Compare previous recommendations with actual outcomes",
        target_audience="Research Team",
        output_format="Monthly markdown report",
        decision_supported="Model improvement and research prioritization",
        frequency="Monthly",
        sla_minutes=30
    ),
}


@dataclass
class Recommendation:
    """A structured recommendation from the platform."""
    timestamp: datetime
    recommendation_type: str  # "research_view", "portfolio_view", "action_view"

    # The recommendation itself
    headline: str
    detail: str

    # Confidence and sizing
    conviction: ConvictionLevel
    suggested_position_size: PositionSize

    # Supporting analysis
    supporting_signals: List[str] = field(default_factory=list)
    opposing_signals: List[str] = field(default_factory=list)
    risk_to_view: str = ""
    data_to_watch: List[str] = field(default_factory=list)

    # Business context
    business_relevance: str = ""  # Why this matters for the fund
    suggested_action: str = ""  # What to actually do

    # Metadata
    data_mode: str = "sample"  # live, cached, sample
    data_freshness_score: float = 0.0  # 0-1
    model_version: str = "1.0.0"

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "recommendation_type": self.recommendation_type,
            "headline": self.headline,
            "detail": self.detail,
            "conviction": self.conviction.value,
            "suggested_position_size": self.suggested_position_size.value,
            "supporting_signals": self.supporting_signals,
            "opposing_signals": self.opposing_signals,
            "risk_to_view": self.risk_to_view,
            "data_to_watch": self.data_to_watch,
            "business_relevance": self.business_relevance,
            "suggested_action": self.suggested_action,
            "data_mode": self.data_mode,
            "data_freshness_score": self.data_freshness_score,
            "model_version": self.model_version,
        }


@dataclass
class PlatformEffectiveness:
    """Track platform effectiveness metrics."""
    timestamp: datetime

    # Signal metrics
    active_signals: int
    high_conviction_signals: int
    conflicting_signals: int

    # Data quality metrics
    data_freshness_pct: float  # Percentage of data fresh
    live_data_pct: float  # Percentage from live sources

    # Postmortem metrics
    postmortems_completed: int

    # Recommendation metrics (optional)
    recommendation_hit_rate: Optional[float] = None
    avg_signal_decay_days: Optional[float] = None

    # Portfolio stance (with default)
    current_portfolio_risk_stance: str = "neutral"

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "active_signals": self.active_signals,
            "high_conviction_signals": self.high_conviction_signals,
            "conflicting_signals": self.conflicting_signals,
            "data_freshness_pct": self.data_freshness_pct,
            "live_data_pct": self.live_data_pct,
            "recommendation_hit_rate": self.recommendation_hit_rate,
            "avg_signal_decay_days": self.avg_signal_decay_days,
            "postmortems_completed": self.postmortems_completed,
            "current_portfolio_risk_stance": self.current_portfolio_risk_stance,
        }


class BusinessObjectivesManager:
    """Manager for business objectives and their generation."""

    def __init__(self):
        self.objectives = BUSINESS_OBJECTIVES
        self.generation_log: List[Dict] = []

    def get_objective(self, output_type: BusinessOutputType) -> BusinessObjective:
        """Get a specific business objective."""
        return self.objectives.get(output_type)

    def get_all_objectives(self) -> Dict[BusinessOutputType, BusinessObjective]:
        """Get all business objectives."""
        return self.objectives

    def log_generation(self, output_type: BusinessOutputType,
                      success: bool, duration_seconds: float,
                      output_path: Optional[str] = None):
        """Log a generation event."""
        self.generation_log.append({
            "timestamp": datetime.now().isoformat(),
            "output_type": output_type.value,
            "success": success,
            "duration_seconds": duration_seconds,
            "output_path": output_path,
        })

    def get_generation_stats(self, days: int = 7) -> Dict:
        """Get generation statistics for the last N days."""
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=days)

        recent_logs = [
            log for log in self.generation_log
            if datetime.fromisoformat(log["timestamp"]) > cutoff
        ]

        if not recent_logs:
            return {"message": "No generation events in the specified period"}

        total = len(recent_logs)
        successful = sum(1 for log in recent_logs if log["success"])
        avg_duration = sum(log["duration_seconds"] for log in recent_logs) / total

        return {
            "total_generations": total,
            "successful": successful,
            "failed": total - successful,
            "success_rate": successful / total,
            "avg_duration_seconds": avg_duration,
        }


# Convenience functions
def get_business_objective(output_type: str) -> Optional[BusinessObjective]:
    """Get a business objective by string name."""
    try:
        enum_type = BusinessOutputType(output_type)
        return BUSINESS_OBJECTIVES.get(enum_type)
    except ValueError:
        return None


def list_all_outputs() -> List[str]:
    """List all available output types."""
    return [output.value for output in BusinessOutputType]
