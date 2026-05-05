"""
report_generator.py — Professional report generation for macro research outputs.

Generates:
- HTML macro summary reports
- CSV exports for sector allocation
- Markdown investment memos
- Signal history exports
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime
import json

from src.reporting.hedge_fund_style import (
    generate_executive_summary,
    get_data_to_watch,
    get_research_backing,
    get_transmission_analysis,
)


# =============================================================================
# Output Paths
# =============================================================================

OUTPUT_DIR = Path(__file__).parent.parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)


# =============================================================================
# HTML Report Generator
# =============================================================================

def generate_html_summary(
    regime: str,
    scores: Dict[str, float],
    directions: Dict[str, str],
    sector_signals: Dict[str, str],
    sector_scores: Dict[str, float],
    sector_table: pd.DataFrame,
    recession_prob: float,
    nowcast: Optional[Dict],
    output_path: Optional[Path] = None,
) -> str:
    """
    Generate one-page HTML macro summary report.
    """
    if output_path is None:
        output_path = OUTPUT_DIR / f"macro_summary_{datetime.now().strftime('%Y%m%d')}.html"

    # Generate executive summary
    executive_summary = generate_executive_summary(regime, scores, directions, sector_signals)

    # Transmission analysis
    transmission = get_transmission_analysis(
        scores["growth"],
        scores["inflation"],
        scores["liquidity"],
        scores["risk"],
    )

    # Research backing
    research = get_research_backing("regime_classification")

    # Build sector table HTML
    sector_html = sector_table.to_html(index=False, classes="sector-table")

    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Macro Regime Summary - {datetime.now().strftime('%Y-%m-%d')}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            color: #333;
            background: #f8f9fa;
        }}
        .header {{
            background: #1a1a2e;
            color: white;
            padding: 30px;
            margin: -20px -20px 30px -20px;
        }}
        .header h1 {{
            margin: 0;
            font-size: 28px;
            font-weight: 400;
        }}
        .header .date {{
            opacity: 0.7;
            margin-top: 10px;
        }}
        .regime-badge {{
            display: inline-block;
            padding: 8px 16px;
            background: {'#2ecc71' if regime == 'Goldilocks' else '#e74c3c' if regime == 'Stagflation' else '#3498db' if regime == 'Slowdown' else '#f39c12'};
            color: white;
            border-radius: 4px;
            font-weight: 600;
            margin-top: 15px;
        }}
        .section {{
            background: white;
            padding: 25px;
            margin-bottom: 20px;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .section h2 {{
            margin-top: 0;
            color: #1a1a2e;
            font-size: 20px;
            border-bottom: 2px solid #eee;
            padding-bottom: 10px;
        }}
        .score-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }}
        .score-card {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 6px;
            border-left: 4px solid #3498db;
        }}
        .score-card.negative {{
            border-left-color: #e74c3c;
        }}
        .score-card.positive {{
            border-left-color: #2ecc71;
        }}
        .score-label {{
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #666;
            margin-bottom: 5px;
        }}
        .score-value {{
            font-size: 32px;
            font-weight: 600;
            color: #1a1a2e;
        }}
        .score-desc {{
            font-size: 13px;
            color: #666;
            margin-top: 5px;
        }}
        .executive-summary {{
            font-size: 16px;
            line-height: 1.8;
            color: #444;
        }}
        .transmission-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }}
        .transmission-card {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 6px;
        }}
        .transmission-card h4 {{
            margin-top: 0;
            color: #1a1a2e;
            font-size: 14px;
            text-transform: uppercase;
        }}
        .sector-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }}
        .sector-table th {{
            background: #1a1a2e;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 500;
        }}
        .sector-table td {{
            padding: 12px;
            border-bottom: 1px solid #eee;
        }}
        .sector-table tr:hover {{
            background: #f8f9fa;
        }}
        .signal-ow {{
            color: #2ecc71;
            font-weight: 600;
        }}
        .signal-uw {{
            color: #e74c3c;
            font-weight: 600;
        }}
        .signal-n {{
            color: #95a5a6;
        }}
        .disclaimer {{
            font-size: 11px;
            color: #888;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
        }}
        .research-note {{
            background: #f0f4f8;
            padding: 15px;
            border-radius: 6px;
            font-size: 13px;
            color: #555;
        }}
        .research-note ul {{
            margin: 10px 0;
            padding-left: 20px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Macro Regime Summary</h1>
        <div class="date">{datetime.now().strftime('%A, %B %d, %Y')}</div>
        <div class="regime-badge">Current Regime: {regime}</div>
    </div>

    <div class="section">
        <h2>Executive Summary</h2>
        <div class="executive-summary">
            {executive_summary.replace(chr(10), '<br>')}
        </div>
    </div>

    <div class="section">
        <h2>Macro Conditions</h2>
        <div class="score-grid">
            <div class="score-card {'positive' if scores['growth'] > 0.5 else 'negative' if scores['growth'] < -0.5 else ''}">
                <div class="score-label">Growth Momentum</div>
                <div class="score-value">{scores['growth']:+.2f}</div>
                <div class="score-desc">{directions['growth'].replace('_', ' ').title()}</div>
            </div>
            <div class="score-card {'positive' if scores['inflation'] > 0.5 else 'negative' if scores['inflation'] < -0.5 else ''}">
                <div class="score-label">Inflation Pressure</div>
                <div class="score-value">{scores['inflation']:+.2f}</div>
                <div class="score-desc">{directions['inflation'].replace('_', ' ').title()}</div>
            </div>
            <div class="score-card {'positive' if scores['liquidity'] > 0.5 else 'negative' if scores['liquidity'] < -0.5 else ''}">
                <div class="score-label">Financial Conditions</div>
                <div class="score-value">{scores['liquidity']:+.2f}</div>
                <div class="score-desc">{directions['liquidity'].replace('_', ' ').title()}</div>
            </div>
            <div class="score-card {'positive' if scores['risk'] > 0.5 else 'negative' if scores['risk'] < -0.5 else ''}">
                <div class="score-label">Risk Appetite</div>
                <div class="score-value">{scores['risk']:+.2f}</div>
                <div class="score-desc">{directions['risk'].replace('_', ' ').title()}</div>
            </div>
        </div>
    </div>

    <div class="section">
        <h2>Transmission Channels</h2>
        <div class="transmission-grid">
            <div class="transmission-card">
                <h4>Rates Channel</h4>
                <p>{transmission['rates']}</p>
            </div>
            <div class="transmission-card">
                <h4>Credit Channel</h4>
                <p>{transmission['credit']}</p>
            </div>
            <div class="transmission-card">
                <h4>Earnings Channel</h4>
                <p>{transmission['earnings']}</p>
            </div>
            <div class="transmission-card">
                <h4>Valuation Channel</h4>
                <p>{transmission['valuation']}</p>
            </div>
            <div class="transmission-card">
                <h4>Risk Appetite</h4>
                <p>{transmission['risk_appetite']}</p>
            </div>
        </div>
    </div>

    <div class="section">
        <h2>Sector Allocation View</h2>
        {sector_html}
    </div>

    <div class="section">
        <h2>Research Framework</h2>
        <div class="research-note">
            <strong>Model methodology based on:</strong>
            <ul>
                {''.join(f'<li>{paper}</li>' for paper in research)}
            </ul>
            <p>This is a decision support model, not an automatic trading system.</p>
        </div>
    </div>

    <div class="disclaimer">
        <strong>Disclaimer:</strong> This report is generated by a macro regime model for research and educational purposes.
        It is not investment advice. Past performance does not guarantee future results. The model has limitations
        including data lags, revision risk, and the inability to predict exogenous shocks.
    </div>
</body>
</html>
"""

    # Save to file
    output_path.write_text(html_content, encoding='utf-8')

    return str(output_path)


# =============================================================================
# CSV Export Generators
# =============================================================================

def export_sector_allocation(
    sector_table: pd.DataFrame,
    output_path: Optional[Path] = None,
) -> str:
    """
    Export sector allocation to CSV.
    """
    if output_path is None:
        output_path = OUTPUT_DIR / f"sector_allocation_{datetime.now().strftime('%Y%m%d')}.csv"

    # Add timestamp and metadata
    export_df = sector_table.copy()
    export_df['generated_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    export_df['data_source'] = 'macro_regime_model'

    export_df.to_csv(output_path, index=False)
    return str(output_path)


def export_signal_history(
    scores_df: pd.DataFrame,
    regime_series: pd.Series,
    output_path: Optional[Path] = None,
) -> str:
    """
    Export historical signals to CSV.
    """
    if output_path is None:
        output_path = OUTPUT_DIR / "signal_history.csv"

    # Combine scores and regime
    history = scores_df.copy()
    history['regime'] = regime_series

    # Add metadata
    history['exported'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    history.to_csv(output_path)
    return str(output_path)


def export_investment_memo(
    memo_text: str,
    metadata: Dict,
    output_path: Optional[Path] = None,
) -> str:
    """
    Export investment memo as Markdown.
    """
    if output_path is None:
        output_path = OUTPUT_DIR / f"investment_memo_{datetime.now().strftime('%Y%m%d')}.md"

    # Add header with metadata
    header = f"""# Investment Memo

**Generated:** {datetime.now().strftime('%A, %B %d, %Y at %H:%M')}
**Regime:** {metadata.get('regime', 'Unknown')}
**Data Source:** {metadata.get('source', 'Sample')}
**Data As Of:** {metadata.get('latest_date', 'Unknown')}

---

"""

    full_content = header + memo_text

    output_path.write_text(full_content, encoding='utf-8')
    return str(output_path)


def export_research_mapping(
    output_path: Optional[Path] = None,
) -> str:
    """
    Export research backing mapping.
    """
    if output_path is None:
        output_path = OUTPUT_DIR / "research_mapping.md"

    content = """# Research Framework Mapping

## Model Components and Academic Support

### Regime Classification
- Hamilton (1989) — Markov-switching model framework
- Ang & Bekaert (2002) — International regime-switching evidence

### Recession Probability
- Estrella & Mishkin (1998) — Yield curve recession prediction
- Campbell & Shiller (1991) — Term structure predictive power

### Factor Model
- Chen, Roll & Ross (1986) — APT macro factor framework
- Fama & French (1989) — Business cycle expected returns

### Inflation Nowcasting
- Stock & Watson (2002) — Dynamic factor nowcasting
- Bridge equation literature

### Sector Allocation
- Stangl, Jacobsen & Visaltanachoti (2008) — Sector rotation evidence
- Moskowitz, Ooi & Pedersen (2012) — Time-series momentum

### Cross-Asset Signals
- Ilmanen (2011) — Expected Returns (multi-asset framework)
- Cochrane & Piazzesi (2005) — Bond risk premia

## Implementation Notes

This model synthesizes academic research into a practical decision-support framework.
Each component has been selected for both theoretical soundness and empirical validity.

The model is designed to be:
- **Explainable**: Every signal traces to raw data and documented methodology
- **Testable**: Historical backtests validate signal efficacy
- **Modular**: Components can be improved independently
- **Consistent**: Framework aligns with institutional macro research workflows

---

*Last updated: {date}*
""".format(date=datetime.now().strftime('%Y-%m-%d'))

    output_path.write_text(content, encoding='utf-8')
    return str(output_path)


# =============================================================================
# Batch Export
# =============================================================================

def export_all_reports(
    regime: str,
    scores: Dict[str, float],
    directions: Dict[str, str],
    sector_signals: Dict[str, str],
    sector_scores: Dict[str, float],
    sector_table: pd.DataFrame,
    scores_df: pd.DataFrame,
    regime_series: pd.Series,
    memo_text: str,
    metadata: Dict,
    recession_prob: float = 0.0,
    nowcast: Optional[Dict] = None,
) -> Dict[str, str]:
    """
    Generate all report exports.

    Returns dict mapping report type to file path.
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    exports = {}

    # HTML Summary
    exports['html_summary'] = generate_html_summary(
        regime, scores, directions, sector_signals, sector_scores, sector_table,
        recession_prob, nowcast,
        output_path=OUTPUT_DIR / f"macro_summary_{timestamp}.html"
    )

    # Sector Allocation CSV
    exports['sector_csv'] = export_sector_allocation(
        sector_table,
        output_path=OUTPUT_DIR / f"sector_allocation_{timestamp}.csv"
    )

    # Signal History
    exports['signal_history'] = export_signal_history(
        scores_df, regime_series,
        output_path=OUTPUT_DIR / "signal_history.csv"
    )

    # Investment Memo
    exports['memo'] = export_investment_memo(
        memo_text, metadata,
        output_path=OUTPUT_DIR / f"investment_memo_{timestamp}.md"
    )

    # Research Mapping (once, not timestamped)
    research_path = OUTPUT_DIR / "research_mapping.md"
    if not research_path.exists():
        exports['research'] = export_research_mapping(research_path)

    return exports
