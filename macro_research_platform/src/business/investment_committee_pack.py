"""
Investment Committee Pack Generator

Generates the weekly Investment Committee pack with all required sections.

Structure:
1. Executive Summary
2. World Macro View
3. What Changed This Week
4. Key Macro Regime Changes
5. Regional Divergence
6. Cross-Asset Implications
7. Sector Allocation View
8. Risk and Portfolio Sizing
9. Signals with Highest Conviction
10. Signals with Most Disagreement
11. What Would Prove Us Wrong
12. Data to Watch Next
13. Appendix: Model Diagnostics and Data Status

Philosophy:
- Lead with the conclusion
- Show the reasoning, not just the result
- Be specific about risks and what would invalidate the view
- Data quality is part of the story
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from .business_objectives import Recommendation
from .recommendation_engine import RecommendationEngine

logger = logging.getLogger(__name__)


class InvestmentCommitteePackGenerator:
    """Generates the weekly Investment Committee pack."""

    def __init__(self, output_dir: str = "outputs"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.recommendation_engine = RecommendationEngine()

    def generate(
        self,
        global_view: Dict,
        recommendations: Dict[str, Recommendation],
        signal_scorecard: Dict,
        data_status: Dict,
        sector_allocation: Dict,
        cross_asset_signals: Dict,
    ) -> str:
        """
        Generate the complete IC pack.

        Returns:
            Path to the generated markdown file
        """
        timestamp = datetime.now()
        filename = f"investment_committee_pack_{timestamp.strftime('%Y%m%d')}.md"
        output_path = self.output_dir / filename

        sections = [
            self._generate_header(timestamp),
            self._generate_executive_summary(recommendations),
            self._generate_world_macro_view(global_view),
            self._generate_what_changed(global_view),
            self._generate_regime_changes(global_view),
            self._generate_regional_divergence(global_view),
            self._generate_cross_asset_implications(cross_asset_signals),
            self._generate_sector_allocation(sector_allocation),
            self._generate_risk_sizing(recommendations, data_status),
            self._generate_high_conviction_signals(signal_scorecard),
            self._generate_signal_disagreements(signal_scorecard),
            self._generate_risk_to_view(recommendations),
            self._generate_data_to_watch(recommendations),
            self._generate_appendix(data_status),
        ]

        content = "\n\n".join(sections)

        with open(output_path, "w") as f:
            f.write(content)

        logger.info(f"Generated Investment Committee Pack: {output_path}")
        return str(output_path)

    def _generate_header(self, timestamp: datetime) -> str:
        """Generate the document header."""
        return f"""# Investment Committee Pack

**Date:** {timestamp.strftime('%Y-%m-%d %H:%M')}
**Prepared by:** Macro Research Platform
**Classification:** Internal Use Only

---
"""

    def _generate_executive_summary(self, recommendations: Dict[str, Recommendation]) -> str:
        """Generate executive summary section."""
        research = recommendations.get("research_view")
        portfolio = recommendations.get("portfolio_view")
        action = recommendations.get("action_view")

        if not research or not portfolio:
            return """## 1. Executive Summary

*Error: Could not generate recommendations.*
"""

        return f"""## 1. Executive Summary

### Macro View
{research.headline}

{research.detail}

### Portfolio Positioning
{portfolio.headline}

{portfolio.detail}

### Recommended Actions
{action.headline if action else "No specific actions recommended"}

{action.detail if action else ""}

**Conviction Level:** {portfolio.conviction.value.upper() if portfolio else "N/A"}
**Data Mode:** {research.data_mode if research else "N/A"}
**Data Freshness:** {f"{research.data_freshness_score:.0%}" if research and hasattr(research, 'data_freshness_score') else "N/A"}
"""

    def _generate_world_macro_view(self, global_view: Dict) -> str:
        """Generate world macro view section."""
        regime = global_view.get("global_regime", "unknown")
        growth = global_view.get("global_growth_momentum", 0)
        inflation = global_view.get("global_inflation_pressure", 0)
        divergence = global_view.get("regional_divergence", 0)

        return f"""## 2. World Macro View

| Metric | Value | Interpretation |
|--------|-------|------------------|
| Global Regime | {regime.replace('_', ' ').title()} | Current macro environment |
| Growth Momentum | {growth:+.1f} | {'Positive' if growth > 0 else 'Negative'} deviation from trend |
| Inflation Pressure | {inflation:+.1f} | {'Elevated' if inflation > 0.5 else 'Contained' if abs(inflation) < 0.5 else 'Below target'} |
| Regional Divergence | {divergence:.2f} | {'High' if divergence > 0.4 else 'Moderate' if divergence > 0.2 else 'Low'} synchronization |

### Key Countries/Regions
"""

    def _generate_what_changed(self, global_view: Dict) -> str:
        """Generate what changed section."""
        return """## 3. What Changed This Week

### Growth
- [ ] Accelerating
- [ ] Stable
- [ ] Decelerating
- [ ] Significant change in trajectory

### Inflation
- [ ] Rising pressure
- [ ] Stable
- [ ] Falling pressure
- [ ] Significant regime shift

### Policy
- [ ] Hawkish shift
- [ ] Dovish shift
- [ ] Neutral stance maintained
- [ ] Policy uncertainty increased

### Liquidity
- [ ] Tightening
- [ ] Easing
- [ ] Stable conditions
- [ ] Market stress emerging

### Credit
- [ ] Spreads widening
- [ ] Spreads narrowing
- [ ] Credit stress contained
- [ ] Credit deterioration

*Note: This section is populated by comparing current readings to previous week.*
"""

    def _generate_regime_changes(self, global_view: Dict) -> str:
        """Generate regime changes section."""
        narrative = global_view.get("narrative", "N/A")

        return f"""## 4. Key Macro Regime Changes

### Current Narrative
{narrative}

### Regime Stability
- Probability of regime persistence: *TBD*
- Risk of regime transition: *TBD*
- Key variables to watch: Growth momentum, inflation prints, central bank communication

### Historical Context
*How does current regime compare to historical analogs?*
"""

    def _generate_regional_divergence(self, global_view: Dict) -> str:
        """Generate regional divergence section."""
        divergence = global_view.get("regional_divergence", 0)
        growth_dispersion = global_view.get("growth_dispersion", 0)
        inflation_dispersion = global_view.get("inflation_dispersion", 0)

        return f"""## 5. Regional Divergence

| Divergence Metric | Value | Interpretation |
|-------------------|-------|----------------|
| Overall Divergence | {divergence:.2f} | {'High' if divergence > 0.4 else 'Moderate' if divergence > 0.2 else 'Low'} |
| Growth Dispersion | {growth_dispersion:.2f} | Variance in growth across regions |
| Inflation Dispersion | {inflation_dispersion:.2f} | Variance in inflation across regions |

### Implications
{'Regional divergence is elevated. This argues for selective regional allocation rather than a single global risk-on or risk-off stance.' if divergence > 0.3 else 'Regional divergence is moderate. Some regional selectivity warranted.' if divergence > 0.2 else 'Regions are broadly synchronized. Global risk-on/risk-off positioning appropriate.'}

### Country Summary
"""

    def _generate_cross_asset_implications(self, cross_asset_signals: Dict) -> str:
        """Generate cross-asset implications section."""
        lines = ["## 6. Cross-Asset Implications\n"]
        lines.append("| Asset Class | Signal | Confidence | Rationale |")
        lines.append("|-------------|--------|------------|-----------|")

        for asset, signal_data in cross_asset_signals.items():
            signal = signal_data.get("signal", "neutral")
            conf = signal_data.get("confidence", 0)
            rationale = signal_data.get("rationale", "N/A")
            lines.append(f"| {asset.title()} | {signal.replace('_', ' ').title()} | {conf:.0%} | {rationale} |")

        return "\n".join(lines)

    def _generate_sector_allocation(self, sector_allocation: Dict) -> str:
        """Generate sector allocation section."""
        lines = ["## 7. Sector Allocation View\n"]
        lines.append("| Sector | Score | Signal | Expected Return |")
        lines.append("|--------|-------|--------|-----------------|")

        for sector, data in sector_allocation.items():
            score = data.get("score", 0) if isinstance(data, dict) else data
            signal = data.get("signal", "neutral") if isinstance(data, dict) else "neutral"
            exp_ret = data.get("expected_return", 0) if isinstance(data, dict) else 0
            lines.append(f"| {sector} | {score:+.2f} | {signal.title()} | {exp_ret:+.2f} |")

        return "\n".join(lines)

    def _generate_risk_sizing(self, recommendations: Dict, data_status: Dict) -> str:
        """Generate risk and sizing section."""
        portfolio = recommendations.get("portfolio_view")

        data_mode = data_status.get("mode", "unknown")
        freshness = data_status.get("freshness", "unknown")

        return f"""## 8. Risk and Portfolio Sizing

### Current Risk Stance
- Recommended position size: {portfolio.suggested_position_size.value if portfolio else "N/A"}
- Conviction level: {portfolio.conviction.value if portfolio else "N/A"}

### Data Quality Constraints
- Data mode: {data_mode}
- Data freshness: {freshness}
{'⚠️ WARNING: Using sample data. Sizing recommendations are illustrative only.' if data_mode == 'sample' else '✓ Data quality acceptable for sizing decisions.' if data_mode == 'live' else '⚠️ Data may be stale. Consider validating before sizing.'}

### Risk Budget Allocation
*Based on conviction and expected returns*
"""

    def _generate_high_conviction_signals(self, signal_scorecard: Dict) -> str:
        """Generate high conviction signals section."""
        lines = ["## 9. Signals with Highest Conviction\n"]
        lines.append("| Signal | Category | Reading | Confidence | Research Support |")
        lines.append("|--------|----------|---------|------------|------------------|")

        # Sort by confidence if available
        signals = []
        for name, data in signal_scorecard.items():
            conf = data.get("confidence", 0) if isinstance(data, dict) else 0
            if conf > 0.6:
                signals.append((name, data))

        signals.sort(key=lambda x: x[1].get("confidence", 0) if isinstance(x[1], dict) else 0, reverse=True)

        for name, data in signals[:5]:
            if isinstance(data, dict):
                cat = data.get("category", "N/A")
                reading = data.get("current_reading", "N/A")
                conf = data.get("confidence", 0)
                research = data.get("research_support", "N/A")
                lines.append(f"| {name} | {cat} | {reading} | {conf:.0%} | {research} |")

        if len(signals) == 0:
            lines.append("\n_No high-conviction signals currently._")

        return "\n".join(lines)

    def _generate_signal_disagreements(self, signal_scorecard: Dict) -> str:
        """Generate signal disagreements section."""
        return """## 10. Signals with Most Disagreement

*Signals where models or data sources conflict*

| Signal | Conflict | Resolution | Impact on View |
|--------|----------|------------|----------------|
| *TBD* | *TBD* | *TBD* | *TBD* |

### Model Disagreement Assessment
- Level of disagreement: *Low / Medium / High*
- Impact on conviction: *Reduces conviction by X%*
- Recommended action: *Wait for clarity / Average signals / Trust primary model*
"""

    def _generate_risk_to_view(self, recommendations: Dict) -> str:
        """Generate risk to view section."""
        lines = ["## 11. What Would Prove Us Wrong\n\n"]

        for rec_type, rec in recommendations.items():
            if rec and rec.risk_to_view:
                lines.append(f"### {rec_type.replace('_', ' ').title()}\n")
                lines.append(f"**Risk:** {rec.risk_to_view}\n")
                lines.append(f"**Monitoring:** {', '.join(rec.data_to_watch) if rec.data_to_watch else 'See data to watch section'}\n\n")

        return "".join(lines)

    def _generate_data_to_watch(self, recommendations: Dict) -> str:
        """Generate data to watch section."""
        all_data = set()
        for rec in recommendations.values():
            if rec and rec.data_to_watch:
                all_data.update(rec.data_to_watch)

        data_list = "\n".join([f"- {d}" for d in sorted(all_data)]) if all_data else "- *TBD*"

        return f"""## 12. Data to Watch Next

### Critical Releases
{data_list}

### Calendar
*Next week's key data releases:*

| Date | Release | Importance | Expected | Previous |
|------|---------|------------|----------|----------|
| *TBD* | *TBD* | *TBD* | *TBD* | *TBD* |
"""

    def _generate_appendix(self, data_status: Dict) -> str:
        """Generate appendix section."""
        return f"""## 13. Appendix: Model Diagnostics and Data Status

### Data Status
- Data mode: {data_status.get('mode', 'unknown')}
- Last update: {data_status.get('last_update', 'unknown')}
- Series available: {data_status.get('series_count', 'unknown')}
- Stale series: {data_status.get('stale_count', 'unknown')}

### Model Diagnostics
- Model version: {data_status.get('model_version', '1.0.0')}
- Last calibration: {data_status.get('last_calibration', 'unknown')}
- Active signals: {data_status.get('active_signals', 'unknown')}
- Signal validation rate: {data_status.get('validation_rate', 'unknown')}

### Known Issues
- *None reported*

### Next Scheduled Maintenance
- *TBD*

---

*Generated by Macro Research Platform v1.0.0*
*For questions, contact: research@fund.com*
"""


# Convenience function
def generate_ic_pack(
    global_view: Dict,
    recommendations: Dict[str, Recommendation],
    signal_scorecard: Dict,
    data_status: Dict,
    sector_allocation: Dict,
    cross_asset_signals: Dict,
    output_dir: str = "outputs",
) -> str:
    """Generate the IC pack with all required inputs."""
    generator = InvestmentCommitteePackGenerator(output_dir)
    return generator.generate(
        global_view, recommendations, signal_scorecard,
        data_status, sector_allocation, cross_asset_signals
    )
