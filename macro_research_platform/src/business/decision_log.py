"""
Decision Log

Tracks every model recommendation with full context for audit trail and postmortem analysis.
Each recommendation is logged with:
- Timestamp and data context
- Recommendation details
- Supporting and opposing signals
- Actual outcome (filled in later)
- Postmortem status

Philosophy:
- Every recommendation must be traceable
- Decisions without logging didn't happen
- Outcomes are only known with hindsight
- The log is for learning, not blame
"""

import logging
import csv
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import pandas as pd

from .business_objectives import Recommendation, ConvictionLevel, PositionSize

logger = logging.getLogger(__name__)


@dataclass
class DecisionLogEntry:
    """A single decision log entry."""

    # Identification
    decision_id: str
    timestamp: datetime
    data_mode: str  # live, cached, sample

    # Recommendation details
    recommendation_type: str
    headline: str
    detail: str
    conviction: str
    suggested_position_size: str

    # Supporting analysis
    supporting_signals: List[str] = field(default_factory=list)
    opposing_signals: List[str] = field(default_factory=list)
    risk_to_view: str = ""
    data_to_watch: List[str] = field(default_factory=list)

    # Business context
    business_relevance: str = ""
    suggested_action: str = ""

    # Model context
    model_version: str = "1.0.0"
    global_regime: str = ""
    growth_momentum: Optional[float] = None
    inflation_pressure: Optional[float] = None
    recession_probability: Optional[float] = None

    # Outcome tracking (filled in later)
    actual_outcome: Optional[str] = None  # "correct", "incorrect", "early", "late", "ongoing"
    outcome_notes: str = ""
    outcome_timestamp: Optional[datetime] = None

    # Postmortem tracking
    postmortem_status: str = "pending"  # pending, completed, skipped
    postmortem_date: Optional[datetime] = None
    postmortem_findings: str = ""
    model_improvement_suggested: bool = False
    improvement_description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "decision_id": self.decision_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "data_mode": self.data_mode,
            "recommendation_type": self.recommendation_type,
            "headline": self.headline,
            "detail": self.detail,
            "conviction": self.conviction,
            "suggested_position_size": self.suggested_position_size,
            "supporting_signals": json.dumps(self.supporting_signals),
            "opposing_signals": json.dumps(self.opposing_signals),
            "risk_to_view": self.risk_to_view,
            "data_to_watch": json.dumps(self.data_to_watch),
            "business_relevance": self.business_relevance,
            "suggested_action": self.suggested_action,
            "model_version": self.model_version,
            "global_regime": self.global_regime,
            "growth_momentum": self.growth_momentum,
            "inflation_pressure": self.inflation_pressure,
            "recession_probability": self.recession_probability,
            "actual_outcome": self.actual_outcome,
            "outcome_notes": self.outcome_notes,
            "outcome_timestamp": self.outcome_timestamp.isoformat() if self.outcome_timestamp else None,
            "postmortem_status": self.postmortem_status,
            "postmortem_date": self.postmortem_date.isoformat() if self.postmortem_date else None,
            "postmortem_findings": self.postmortem_findings,
            "model_improvement_suggested": self.model_improvement_suggested,
            "improvement_description": self.improvement_description,
        }

    @classmethod
    def from_recommendation(
        cls,
        recommendation: Recommendation,
        decision_id: str,
        global_regime: str = "",
        growth_momentum: Optional[float] = None,
        inflation_pressure: Optional[float] = None,
        recession_probability: Optional[float] = None,
    ) -> "DecisionLogEntry":
        """Create a log entry from a recommendation."""
        return cls(
            decision_id=decision_id,
            timestamp=recommendation.timestamp,
            data_mode=recommendation.data_mode,
            recommendation_type=recommendation.recommendation_type,
            headline=recommendation.headline,
            detail=recommendation.detail,
            conviction=recommendation.conviction.value,
            suggested_position_size=recommendation.suggested_position_size.value,
            supporting_signals=recommendation.supporting_signals,
            opposing_signals=recommendation.opposing_signals,
            risk_to_view=recommendation.risk_to_view,
            data_to_watch=recommendation.data_to_watch,
            business_relevance=recommendation.business_relevance,
            suggested_action=recommendation.suggested_action,
            model_version=recommendation.model_version,
            global_regime=global_regime,
            growth_momentum=growth_momentum,
            inflation_pressure=inflation_pressure,
            recession_probability=recession_probability,
        )


class DecisionLog:
    """Manages the decision log."""

    def __init__(self, output_dir: str = "outputs"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.output_dir / "decision_log.csv"
        self.entries: List[DecisionLogEntry] = []
        self._load_existing()

    def _load_existing(self) -> None:
        """Load existing log entries from file."""
        if not self.log_file.exists():
            return

        try:
            df = pd.read_csv(self.log_file)
            for _, row in df.iterrows():
                entry = DecisionLogEntry(
                    decision_id=row["decision_id"],
                    timestamp=datetime.fromisoformat(row["timestamp"]) if pd.notna(row["timestamp"]) else None,
                    data_mode=row["data_mode"],
                    recommendation_type=row["recommendation_type"],
                    headline=row["headline"],
                    detail=row["detail"],
                    conviction=row["conviction"],
                    suggested_position_size=row["suggested_position_size"],
                    supporting_signals=json.loads(row["supporting_signals"]) if pd.notna(row["supporting_signals"]) else [],
                    opposing_signals=json.loads(row["opposing_signals"]) if pd.notna(row["opposing_signals"]) else [],
                    risk_to_view=row.get("risk_to_view", ""),
                    data_to_watch=json.loads(row["data_to_watch"]) if pd.notna(row["data_to_watch"]) else [],
                    business_relevance=row.get("business_relevance", ""),
                    suggested_action=row.get("suggested_action", ""),
                    model_version=row.get("model_version", "1.0.0"),
                    global_regime=row.get("global_regime", ""),
                    growth_momentum=row.get("growth_momentum"),
                    inflation_pressure=row.get("inflation_pressure"),
                    recession_probability=row.get("recession_probability"),
                    actual_outcome=row.get("actual_outcome"),
                    outcome_notes=row.get("outcome_notes", ""),
                    outcome_timestamp=datetime.fromisoformat(row["outcome_timestamp"]) if pd.notna(row.get("outcome_timestamp")) else None,
                    postmortem_status=row.get("postmortem_status", "pending"),
                    postmortem_date=datetime.fromisoformat(row["postmortem_date"]) if pd.notna(row.get("postmortem_date")) else None,
                    postmortem_findings=row.get("postmortem_findings", ""),
                    model_improvement_suggested=row.get("model_improvement_suggested", False),
                    improvement_description=row.get("improvement_description", ""),
                )
                self.entries.append(entry)
            logger.info(f"Loaded {len(self.entries)} existing log entries")
        except Exception as e:
            logger.error(f"Error loading decision log: {e}")

    def log_decision(
        self,
        recommendation: Recommendation,
        global_regime: str = "",
        growth_momentum: Optional[float] = None,
        inflation_pressure: Optional[float] = None,
        recession_probability: Optional[float] = None,
    ) -> str:
        """
        Log a new decision.

        Returns:
            decision_id for later reference
        """
        decision_id = f"DEC_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.entries):04d}"

        entry = DecisionLogEntry.from_recommendation(
            recommendation=recommendation,
            decision_id=decision_id,
            global_regime=global_regime,
            growth_momentum=growth_momentum,
            inflation_pressure=inflation_pressure,
            recession_probability=recession_probability,
        )

        self.entries.append(entry)
        self._append_to_file(entry)

        logger.info(f"Logged decision {decision_id}: {recommendation.headline}")
        return decision_id

    def _append_to_file(self, entry: DecisionLogEntry) -> None:
        """Append a single entry to the CSV file."""
        dict_row = entry.to_dict()

        file_exists = self.log_file.exists()
        with open(self.log_file, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=dict_row.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(dict_row)

    def update_outcome(
        self,
        decision_id: str,
        actual_outcome: str,
        outcome_notes: str = "",
    ) -> bool:
        """Update the outcome of a decision."""
        for entry in self.entries:
            if entry.decision_id == decision_id:
                entry.actual_outcome = actual_outcome
                entry.outcome_notes = outcome_notes
                entry.outcome_timestamp = datetime.now()
                self._rewrite_file()
                logger.info(f"Updated outcome for {decision_id}: {actual_outcome}")
                return True
        logger.warning(f"Decision {decision_id} not found")
        return False

    def mark_postmortem_complete(
        self,
        decision_id: str,
        findings: str,
        improvement_suggested: bool = False,
        improvement_description: str = "",
    ) -> bool:
        """Mark a decision as having completed postmortem."""
        for entry in self.entries:
            if entry.decision_id == decision_id:
                entry.postmortem_status = "completed"
                entry.postmortem_date = datetime.now()
                entry.postmortem_findings = findings
                entry.model_improvement_suggested = improvement_suggested
                entry.improvement_description = improvement_description
                self._rewrite_file()
                logger.info(f"Completed postmortem for {decision_id}")
                return True
        return False

    def _rewrite_file(self) -> None:
        """Rewrite the entire log file."""
        if not self.entries:
            return

        dict_rows = [e.to_dict() for e in self.entries]
        with open(self.log_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=dict_rows[0].keys())
            writer.writeheader()
            writer.writerows(dict_rows)

    def get_entries(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        recommendation_type: Optional[str] = None,
        conviction: Optional[str] = None,
        postmortem_status: Optional[str] = None,
    ) -> List[DecisionLogEntry]:
        """Get filtered entries."""
        filtered = self.entries

        if start_date:
            filtered = [e for e in filtered if e.timestamp and e.timestamp >= start_date]
        if end_date:
            filtered = [e for e in filtered if e.timestamp and e.timestamp <= end_date]
        if recommendation_type:
            filtered = [e for e in filtered if e.recommendation_type == recommendation_type]
        if conviction:
            filtered = [e for e in filtered if e.conviction == conviction]
        if postmortem_status:
            filtered = [e for e in filtered if e.postmortem_status == postmortem_status]

        return filtered

    def get_pending_postmortems(self) -> List[DecisionLogEntry]:
        """Get entries pending postmortem review."""
        return [e for e in self.entries
                if e.postmortem_status == "pending"
                and e.timestamp
                and (datetime.now() - e.timestamp).days >= 30]

    def get_accuracy_stats(self) -> Dict:
        """Get recommendation accuracy statistics."""
        completed = [e for e in self.entries if e.actual_outcome]

        if not completed:
            return {"message": "No completed outcomes yet"}

        total = len(completed)
        correct = sum(1 for e in completed if e.actual_outcome == "correct")
        incorrect = sum(1 for e in completed if e.actual_outcome == "incorrect")
        early = sum(1 for e in completed if e.actual_outcome == "early")
        late = sum(1 for e in completed if e.actual_outcome == "late")

        return {
            "total_completed": total,
            "correct": correct,
            "incorrect": incorrect,
            "early": early,
            "late": late,
            "accuracy_rate": correct / total if total > 0 else 0,
            "timing_issues": (early + late) / total if total > 0 else 0,
        }

    def to_dataframe(self) -> pd.DataFrame:
        """Convert log to DataFrame."""
        if not self.entries:
            return pd.DataFrame()
        return pd.DataFrame([e.to_dict() for e in self.entries])

    def export_for_review(self, output_path: Optional[str] = None) -> str:
        """Export log for review."""
        if output_path is None:
            output_path = self.output_dir / f"decision_log_export_{datetime.now().strftime('%Y%m%d')}.csv"

        df = self.to_dataframe()
        df.to_csv(output_path, index=False)
        logger.info(f"Exported decision log to {output_path}")
        return str(output_path)


# Convenience functions
def create_decision_log(output_dir: str = "outputs") -> DecisionLog:
    """Create a new decision log."""
    return DecisionLog(output_dir)
