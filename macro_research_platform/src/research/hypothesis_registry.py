"""
Hypothesis Registry

Tracks research hypotheses, their validation status, and performance.

Research process:
1. Form hypothesis
2. Document assumptions
3. Test against data
4. Track in production
5. Postmortem analysis
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class HypothesisStatus(Enum):
    """Status of a hypothesis in the research pipeline."""
    PROPOSED = "proposed"
    UNDER_TEST = "under_test"
    VALIDATED = "validated"
    REJECTED = "rejected"
    IN_PRODUCTION = "in_production"
    DEPRECATED = "deprecated"


class HypothesisType(Enum):
    """Type of hypothesis."""
    MACRO_RELATIONSHIP = "macro_relationship"  # X causes Y
    SIGNAL_EFFECTIVENESS = "signal_effectiveness"  # Signal generates alpha
    REGIME_DEPENDENCE = "regime_dependence"  # Works in certain regimes
    CROSS_ASSET = "cross_asset"  # Relationship between assets


@dataclass
class Hypothesis:
    """A research hypothesis."""
    id: str
    name: str
    description: str
    hypothesis_type: HypothesisType
    statement: str  # The actual hypothesis statement
    assumptions: List[str]
    testable_predictions: List[str]
    status: HypothesisStatus
    created_at: datetime
    author: str

    # Data requirements
    required_data: List[str]
    minimum_observations: int
    test_period: tuple  # (start, end) dates

    # Results
    validation_results: Dict = field(default_factory=dict)
    performance_metrics: Dict = field(default_factory=dict)
    status_changed_at: Optional[datetime] = None
    status_reason: str = ""


class HypothesisRegistry:
    """
    Central registry for research hypotheses.

    Manages the lifecycle of research ideas from
    conception to production to deprecation.
    """

    def __init__(self):
        self.hypotheses: Dict[str, Hypothesis] = {}
        self.tag_index: Dict[str, List[str]] = {}  # tag -> hypothesis_ids

    def register_hypothesis(
        self,
        hypothesis_id: str,
        name: str,
        description: str,
        hypothesis_type: HypothesisType,
        statement: str,
        assumptions: List[str],
        testable_predictions: List[str],
        required_data: List[str],
        author: str,
        tags: Optional[List[str]] = None,
    ) -> Hypothesis:
        """
        Register a new hypothesis.

        Args:
            hypothesis_id: Unique identifier
            name: Short name
            description: Full description
            hypothesis_type: Type of hypothesis
            statement: The actual hypothesis
            assumptions: List of assumptions
            testable_predictions: Predictions that can be tested
            required_data: Data needed for testing
            author: Researcher name
            tags: Optional tags for categorization

        Returns:
            Created Hypothesis
        """
        hypothesis = Hypothesis(
            id=hypothesis_id,
            name=name,
            description=description,
            hypothesis_type=hypothesis_type,
            statement=statement,
            assumptions=assumptions,
            testable_predictions=testable_predictions,
            status=HypothesisStatus.PROPOSED,
            created_at=datetime.now(),
            author=author,
            required_data=required_data,
            minimum_observations=60,  # Default
            test_period=(None, None),
        )

        self.hypotheses[hypothesis_id] = hypothesis

        # Add to tag index
        if tags:
            for tag in tags:
                if tag not in self.tag_index:
                    self.tag_index[tag] = []
                self.tag_index[tag].append(hypothesis_id)

        logger.info(f"Registered hypothesis: {name} ({hypothesis_id})")
        return hypothesis

    def update_status(
        self,
        hypothesis_id: str,
        new_status: HypothesisStatus,
        reason: str = "",
    ) -> bool:
        """
        Update hypothesis status.

        Args:
            hypothesis_id: Hypothesis ID
            new_status: New status
            reason: Reason for change

        Returns:
            True if updated successfully
        """
        if hypothesis_id not in self.hypotheses:
            logger.error(f"Hypothesis not found: {hypothesis_id}")
            return False

        hypothesis = self.hypotheses[hypothesis_id]
        old_status = hypothesis.status

        hypothesis.status = new_status
        hypothesis.status_changed_at = datetime.now()
        hypothesis.status_reason = reason

        logger.info(
            f"Updated hypothesis {hypothesis_id} status: "
            f"{old_status.value} -> {new_status.value}: {reason}"
        )
        return True

    def record_validation_results(
        self,
        hypothesis_id: str,
        results: Dict,
    ) -> bool:
        """
        Record validation test results.

        Args:
            hypothesis_id: Hypothesis ID
            results: Test results dict

        Returns:
            True if recorded successfully
        """
        if hypothesis_id not in self.hypotheses:
            return False

        self.hypotheses[hypothesis_id].validation_results = results

        # Update status based on results
        if results.get("validated", False):
            self.update_status(
                hypothesis_id,
                HypothesisStatus.VALIDATED,
                "Validation tests passed",
            )
        else:
            self.update_status(
                hypothesis_id,
                HypothesisStatus.REJECTED,
                results.get("failure_reason", "Validation failed"),
            )

        return True

    def record_production_metrics(
        self,
        hypothesis_id: str,
        metrics: Dict,
    ) -> bool:
        """Record production performance metrics."""
        if hypothesis_id not in self.hypotheses:
            return False

        self.hypotheses[hypothesis_id].performance_metrics = metrics
        return True

    def get_hypothesis(self, hypothesis_id: str) -> Optional[Hypothesis]:
        """Get hypothesis by ID."""
        return self.hypotheses.get(hypothesis_id)

    def list_hypotheses(
        self,
        status: Optional[HypothesisStatus] = None,
        hypothesis_type: Optional[HypothesisType] = None,
        author: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> List[Hypothesis]:
        """
        List hypotheses with optional filters.

        Args:
            status: Filter by status
            hypothesis_type: Filter by type
            author: Filter by author
            tag: Filter by tag

        Returns:
            List of matching hypotheses
        """
        results = list(self.hypotheses.values())

        if status:
            results = [h for h in results if h.status == status]

        if hypothesis_type:
            results = [h for h in results if h.hypothesis_type == hypothesis_type]

        if author:
            results = [h for h in results if h.author == author]

        if tag:
            ids = self.tag_index.get(tag, [])
            results = [h for h in results if h.id in ids]

        return results

    def get_validation_summary(self, hypothesis_id: str) -> Dict:
        """Get validation summary for a hypothesis."""
        h = self.hypotheses.get(hypothesis_id)
        if not h:
            return {}

        return {
            "hypothesis": h.name,
            "statement": h.statement,
            "status": h.status.value,
            "testable_predictions": h.testable_predictions,
            "validation_results": h.validation_results,
            "production_metrics": h.performance_metrics,
            "days_in_current_status": (
                (datetime.now() - h.status_changed_at).days
                if h.status_changed_at else None
            ),
        }

    def generate_hypothesis_report(self) -> Dict:
        """Generate comprehensive hypothesis report."""
        # Group by status
        by_status = {}
        for status in HypothesisStatus:
            by_status[status.value] = len([
                h for h in self.hypotheses.values() if h.status == status
            ])

        # Group by type
        by_type = {}
        for htype in HypothesisType:
            by_type[htype.value] = len([
                h for h in self.hypotheses.values() if h.hypothesis_type == htype
            ])

        # Recent validations
        recent_validated = [
            {
                "id": h.id,
                "name": h.name,
                "validated_at": h.status_changed_at,
                "sharpe": h.validation_results.get("sharpe_ratio"),
            }
            for h in self.hypotheses.values()
            if h.status == HypothesisStatus.VALIDATED and h.status_changed_at
        ]

        # Production performance
        production_performance = [
            {
                "id": h.id,
                "name": h.name,
                "current_pnl": h.performance_metrics.get("total_pnl"),
                "sharpe": h.performance_metrics.get("sharpe_ratio"),
            }
            for h in self.hypotheses.values()
            if h.status == HypothesisStatus.IN_PRODUCTION
        ]

        return {
            "summary": {
                "total_hypotheses": len(self.hypotheses),
                "by_status": by_status,
                "by_type": by_type,
            },
            "recent_validations": sorted(
                recent_validated,
                key=lambda x: x["validated_at"] or datetime.min,
                reverse=True,
            )[:10],
            "production_performance": production_performance,
        }

    def archive_hypothesis(self, hypothesis_id: str, reason: str = "") -> bool:
        """Archive a hypothesis."""
        return self.update_status(
            hypothesis_id,
            HypothesisStatus.DEPRECATED,
            reason or "Archived",
        )


def create_macro_hypothesis(
    name: str,
    cause_variable: str,
    effect_variable: str,
    expected_lag_months: int,
    transmission_mechanism: str,
) -> Dict:
    """
    Create a macro relationship hypothesis template.

    Args:
        name: Hypothesis name
        cause_variable: Independent variable
        effect_variable: Dependent variable
        expected_lag_months: Expected time lag
        transmission_mechanism: How the effect works

    Returns:
        Hypothesis template dict
    """
    return {
        "name": name,
        "type": HypothesisType.MACRO_RELATIONSHIP,
        "statement": f"{cause_variable} causes {effect_variable} with {expected_lag_months} month lag",
        "assumptions": [
            "Causal relationship exists",
            f"Lag is approximately {expected_lag_months} months",
            "No confounding variables dominate",
        ],
        "testable_predictions": [
            f"Correlation between {cause_variable} and future {effect_variable}",
            f"Granger causality test significant at 5%",
        ],
        "required_data": [cause_variable, effect_variable],
        "transmission_mechanism": transmission_mechanism,
    }


def create_signal_hypothesis(
    name: str,
    signal_description: str,
    expected_return: float,
    expected_volatility: float,
    expected_sharpe: float,
) -> Dict:
    """
    Create a signal effectiveness hypothesis template.

    Args:
        name: Hypothesis name
        signal_description: Description of the signal
        expected_return: Expected annual return
        expected_volatility: Expected volatility
        expected_sharpe: Expected Sharpe ratio

    Returns:
        Hypothesis template dict
    """
    return {
        "name": name,
        "type": HypothesisType.SIGNAL_EFFECTIVENESS,
        "statement": f"Signal '{signal_description}' generates alpha with Sharpe > {expected_sharpe}",
        "assumptions": [
            "Signal is not arbitraged away",
            "Transaction costs don't eliminate alpha",
            "Relationship is stable over time",
        ],
        "testable_predictions": [
            f"Backtest Sharpe ratio > {expected_sharpe}",
            "Positive information coefficient",
            "Works in different market regimes",
        ],
        "expected_performance": {
            "return": expected_return,
            "volatility": expected_volatility,
            "sharpe": expected_sharpe,
        },
    }
