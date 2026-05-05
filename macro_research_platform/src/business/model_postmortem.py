"""
Model Postmortem Engine

Each month, compare:
- Previous model recommendation
- Actual asset performance
- Whether thesis was right
- Whether timing was early
- Whether signal failed
- Whether data was stale
- What should be improved

Output: Monthly markdown report
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import pandas as pd

from .decision_log import DecisionLog, DecisionLogEntry

logger = logging.getLogger(__name__)


@dataclass
class PostmortemAnalysis:
    """Analysis of a single recommendation outcome."""
    decision_id: str
    recommendation_type: str
    original_headline: str
    original_conviction: str

    # Outcome assessment
    outcome_assessment: str  # correct, incorrect, early, late, ongoing
    accuracy_score: float  # 0-1
    timing_score: float  # 0-1

    # Analysis
    thesis_accuracy: str  # Was the thesis right?
    timing_assessment: str  # Was timing right?
    signal_performance: str  # Did signals work?
    data_quality_impact: str  # Did data issues affect outcome?

    # Learning
    key_lessons: List[str] = field(default_factory=list)
    improvement_suggestions: List[str] = field(default_factory=list)
    model_changes_recommended: bool = False


def analyze_outcome(
    entry: DecisionLogEntry,
    actual_performance: Optional[Dict] = None
) -> PostmortemAnalysis:
    """
    Analyze a single recommendation outcome.

    Args:
        entry: The decision log entry
        actual_performance: Dict with actual performance metrics

    Returns:
        PostmortemAnalysis
    """
    # Determine outcome assessment
    if entry.actual_outcome:
        outcome = entry.actual_outcome
    else:
        outcome = "ongoing"

    # Calculate accuracy score
    accuracy_map = {
        "correct": 1.0,
        "incorrect": 0.0,
        "early": 0.5,  # Right thesis, wrong timing
        "late": 0.5,
        "ongoing": 0.5,
    }
    accuracy = accuracy_map.get(outcome, 0.5)

    # Determine timing score
    if outcome in ["early", "late"]:
        timing = 0.3
    elif outcome == "correct":
        timing = 1.0
    else:
        timing = 0.5

    # Generate analysis text
    thesis_accuracy = _assess_thesis_accuracy(entry, actual_performance)
    timing_assessment = _assess_timing(entry, actual_performance)
    signal_performance = _assess_signals(entry, actual_performance)
    data_quality_impact = _assess_data_quality(entry)

    # Extract lessons
    lessons = _extract_lessons(entry, outcome)
    suggestions = _suggest_improvements(entry, outcome)

    return PostmortemAnalysis(
        decision_id=entry.decision_id,
        recommendation_type=entry.recommendation_type,
        original_headline=entry.headline,
        original_conviction=entry.conviction,
        outcome_assessment=outcome,
        accuracy_score=accuracy,
        timing_score=timing,
        thesis_accuracy=thesis_accuracy,
        timing_assessment=timing_assessment,
        signal_performance=signal_performance,
        data_quality_impact=data_quality_impact,
        key_lessons=lessons,
        improvement_suggestions=suggestions,
        model_changes_recommended=len(suggestions) > 0,
    )


def _assess_thesis_accuracy(entry: DecisionLogEntry, performance: Optional[Dict]) -> str:
    """Assess if the thesis was accurate."""
    if not performance:
        return "Unable to assess - no performance data available"

    # Compare predicted vs actual
    return "Assessment requires manual review"


def _assess_timing(entry: DecisionLogEntry, performance: Optional[Dict]) -> str:
    """Assess timing of recommendation."""
    if entry.actual_outcome == "early":
        return "Recommendation was directionally correct but premature"
    elif entry.actual_outcome == "late":
        return "Recommendation was directionally correct but late"
    elif entry.actual_outcome == "correct":
        return "Timing was appropriate"
    else:
        return "Timing assessment pending"


def _assess_signals(entry: DecisionLogEntry, performance: Optional[Dict]) -> str:
    """Assess signal performance."""
    supporting = len(entry.supporting_signals)
    opposing = len(entry.opposing_signals)

    if supporting > opposing:
        return f"Majority of signals ({supporting}) supported the view"
    elif opposing > supporting:
        return f"More signals opposed ({opposing}) than supported"
    else:
        return "Signals were evenly split"


def _assess_data_quality(entry: DecisionLogEntry) -> str:
    """Assess impact of data quality."""
    if entry.data_mode == "sample":
        return "WARNING: Decision based on sample data"
    elif entry.data_freshness_score < 0.5:
        return f"Data freshness was low ({entry.data_freshness_score:.0%})"
    else:
        return f"Data quality acceptable ({entry.data_freshness_score:.0%})"


def _extract_lessons(entry: DecisionLogEntry, outcome: str) -> List[str]:
    """Extract key lessons from the outcome."""
    lessons = []

    if outcome == "incorrect":
        lessons.append("Review signal weights and model logic")
        if entry.opposing_signals:
            lessons.append(f"Consider why {len(entry.opposing_signals)} opposing signals were overridden")

    if outcome in ["early", "late"]:
        lessons.append("Review timing indicators and catalyst assumptions")

    if entry.data_mode == "sample":
        lessons.append("Avoid making real decisions with sample data")

    return lessons


def _suggest_improvements(entry: DecisionLogEntry, outcome: str) -> List[str]:
    """Suggest model improvements."""
    suggestions = []

    if outcome == "incorrect":
        suggestions.append("Recalibrate signal weights")
        suggestions.append("Add new validation rules")

    if entry.opposing_signals and outcome == "incorrect":
        suggestions.append("Implement opposing signal veto logic")

    if outcome == "early":
        suggestions.append("Add timing confirmation rules")

    return suggestions


class ModelPostmortemEngine:
    """Engine for generating monthly model postmortems."""

    def __init__(self, output_dir: str = "outputs"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.decision_log = DecisionLog(output_dir)

    def generate_monthly_report(
        self,
        year: Optional[int] = None,
        month: Optional[int] = None
    ) -> str:
        """
        Generate monthly postmortem report.

        Args:
            year: Report year (default: previous month)
            month: Report month (default: previous month)

        Returns:
            Path to generated markdown file
        """
        # Determine report period
        if year is None or month is None:
            today = datetime.now()
            if today.month == 1:
                year = today.year - 1
                month = 12
            else:
                year = today.year
                month = today.month - 1

        # Get entries for the month
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)

        entries = self.decision_log.get_entries(
            start_date=start_date,
            end_date=end_date
        )

        # Filter to completed entries
        completed = [e for e in entries if e.actual_outcome]

        # Generate report
        filename = f"model_postmortem_{year}{month:02d}.md"
        output_path = self.output_dir / filename

        sections = [
            self._generate_header(year, month),
            self._generate_summary(completed),
            self._generate_accuracy_stats(completed),
            self._generate_detailed_analysis(completed),
            self._generate_lessons_learned(completed),
            self._generate_improvement_recommendations(completed),
            self._generate_action_items(completed),
        ]

        content = "\n\n".join(sections)

        with open(output_path, "w") as f:
            f.write(content)

        logger.info(f"Generated postmortem report: {output_path}")
        return str(output_path)

    def _generate_header(self, year: int, month: int) -> str:
        """Generate report header."""
        month_name = datetime(year, month, 1).strftime("%B")
        return f"""# Model Postmortem Report

**Period:** {month_name} {year}
**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}
**Prepared by:** Macro Research Platform

---

## Executive Summary

This report reviews model recommendations from {month_name} {year} and assesses their accuracy, timing, and lessons learned.

"""

    def _generate_summary(self, entries: List[DecisionLogEntry]) -> str:
        """Generate summary section."""
        total = len(entries)
        by_type = {}
        for e in entries:
            by_type[e.recommendation_type] = by_type.get(e.recommendation_type, 0) + 1

        type_summary = "\n".join([f"- {t}: {c}" for t, c in by_type.items()])

        return f"""## Recommendation Summary

**Total Recommendations:** {total}

### By Type
{type_summary if type_summary else "_No recommendations in period_"}

### Outcome Status
- Completed assessments: {sum(1 for e in entries if e.actual_outcome)}
- Pending assessment: {sum(1 for e in entries if not e.actual_outcome)}

"""

    def _generate_accuracy_stats(self, entries: List[DecisionLogEntry]) -> str:
        """Generate accuracy statistics."""
        if not entries:
            return "## Accuracy Statistics\n\n_No data available_\n\n"

        completed = [e for e in entries if e.actual_outcome]
        if not completed:
            return "## Accuracy Statistics\n\n_No completed outcomes yet_\n\n"

        outcomes = {}
        for e in completed:
            outcomes[e.actual_outcome] = outcomes.get(e.actual_outcome, 0) + 1

        # Calculate rates
        total = len(completed)
        correct_rate = outcomes.get("correct", 0) / total
        timing_issue_rate = (outcomes.get("early", 0) + outcomes.get("late", 0)) / total

        return f"""## Accuracy Statistics

| Metric | Value |
|--------|-------|
| Total Assessed | {total} |
| Correct | {outcomes.get('correct', 0)} ({correct_rate:.0%}) |
| Incorrect | {outcomes.get('incorrect', 0)} ({outcomes.get('incorrect', 0)/total:.0%}) |
| Early | {outcomes.get('early', 0)} |
| Late | {outcomes.get('late', 0)} |
| Timing Issues | {timing_issue_rate:.0%} |

### By Conviction Level

| Conviction | Count | Correct Rate |
|------------|-------|--------------|
| High | {sum(1 for e in completed if e.original_conviction == 'high')} | _TBD_ |
| Medium | {sum(1 for e in completed if e.original_conviction == 'medium')} | _TBD_ |
| Low | {sum(1 for e in completed if e.original_convidence == 'low')} | _TBD_ |

"""

    def _generate_detailed_analysis(self, entries: List[DecisionLogEntry]) -> str:
        """Generate detailed analysis section."""
        if not entries:
            return "## Detailed Analysis\n\n_No entries to analyze_\n\n"

        lines = ["## Detailed Analysis\n"]

        for entry in entries[:10]:  # Limit to first 10
            lines.append(f"""### {entry.recommendation_type}: {entry.original_headline}

- **Decision ID:** {entry.decision_id}
- **Outcome:** {entry.actual_outcome or "Pending"}
- **Thesis Accuracy:** {entry.outcome_notes or "Not assessed"}
- **Data Quality:** {entry.data_mode} ({entry.data_freshness_score:.0%} freshness)

""")

        return "".join(lines)

    def _generate_lessons_learned(self, entries: List[DecisionLogEntry]) -> str:
        """Generate lessons learned section."""
        # Collect all lessons
        all_lessons = []
        for entry in entries:
            if entry.outcome_notes:
                all_lessons.append(entry.outcome_notes)

        lessons_text = "\n".join([f"- {l}" for l in all_lessons[:10]]) if all_lessons else "_No specific lessons recorded_"

        return f"""## Lessons Learned

### Key Insights
{lessons_text}

### Patterns Observed
1. *Pattern TBD*

### Data Quality Observations
- Sample data usage: {sum(1 for e in entries if e.data_mode == 'sample')} decisions
- Low freshness (<50%): {sum(1 for e in entries if e.data_freshness_score < 0.5)} decisions

"""

    def _generate_improvement_recommendations(self, entries: List[DecisionLogEntry]) -> str:
        """Generate improvement recommendations."""
        suggestions = []
        for entry in entries:
            if entry.model_improvement_suggested:
                suggestions.append(entry.improvement_description)

        suggestions_text = "\n".join([f"- {s}" for s in set(suggestions)]) if suggestions else "_No improvements suggested_"

        return f"""## Improvement Recommendations

{suggestions_text}

### Recommended Model Changes
| Priority | Change | Expected Impact |
|----------|--------|-----------------|
| *TBD* | *TBD* | *TBD* |

"""

    def _generate_action_items(self, entries: List[DecisionLogEntry]) -> str:
        """Generate action items."""
        return f"""## Action Items

### Immediate (This Week)
- [ ] Review all incorrect recommendations
- [ ] Assess signal calibration needs

### Short Term (This Month)
- [ ] Implement agreed model changes
- [ ] Update documentation

### Ongoing
- [ ] Continue tracking outcomes
- [ ] Update postmortem monthly

---

*Report generated by Model Postmortem Engine*
*Next report due: {(datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')}*
"""


# Convenience function
def generate_monthly_postmortem(
    output_dir: str = "outputs",
    year: Optional[int] = None,
    month: Optional[int] = None
) -> str:
    """Generate monthly postmortem report."""
    engine = ModelPostmortemEngine(output_dir)
    return engine.generate_monthly_report(year, month)
