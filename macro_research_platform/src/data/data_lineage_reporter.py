"""
Data Lineage Reporter

Tracks every metric from source to dashboard display.
"""

import pandas as pd
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent


def generate_data_lineage_report() -> pd.DataFrame:
    """
    Generate comprehensive data lineage report for all dashboard metrics.
    """
    lineage_records = []

    # Current timestamp for reference
    now = datetime.now()

    # ==========================================================================
    # 1. LOAD DATA SOURCES
    # ==========================================================================

    # Check model results
    model_results_path = PROJECT_ROOT / "outputs" / "latest_model_results.json"
    model_results = {}
    if model_results_path.exists():
        with open(model_results_path) as f:
            model_results = json.load(f)

    # Check data metadata
    metadata = {
        "is_sample": model_results.get("data_mode") == "sample",
        "source": model_results.get("data_mode", "unknown"),
    }

    # Check live data if exists
    live_processed = PROJECT_ROOT / "data" / "processed" / "live" / "macro_data.parquet"
    live_data_info = {
        "exists": live_processed.exists(),
        "latest_date": None,
        "series_count": 0,
    }
    if live_processed.exists():
        df_live = pd.read_parquet(live_processed)
        live_data_info["latest_date"] = df_live.index.max()
        live_data_info["series_count"] = len(df_live.columns)

    # ==========================================================================
    # 2. MACRO SCORES LINEAGE
    # ==========================================================================

    scores = model_results.get("scores", {})
    directions = model_results.get("directions", {})
    regime_class = model_results.get("regime_classification", {})

    # Growth Score
    growth_score = scores.get("growth", 0)
    lineage_records.append({
        "dashboard_metric_name": "Growth Score",
        "value_displayed": f"{growth_score:+.2f}",
        "source_module": "src/models/enhanced_macro_classifier.py",
        "source_file": "outputs/latest_model_results.json",
        "source_series_id": "ensemble_growth",
        "source_name": "Growth Ensemble",
        "raw_latest_observation_date": str(live_data_info["latest_date"]) if live_data_info["latest_date"] else "N/A",
        "raw_latest_value": "N/A (processed score)",
        "transformed_latest_date": model_results.get("timestamp", "N/A"),
        "transformed_latest_value": f"{growth_score:+.2f}",
        "transformation_used": "ensemble_weighted_average -> z_score_normalization",
        "is_live_data": not metadata["is_sample"] and live_data_info["exists"],
        "is_cached_live_data": not metadata["is_sample"] and live_data_info["exists"],
        "is_sample_data": metadata["is_sample"],
        "is_placeholder": False,
        "data_mode": model_results.get("data_mode", "unknown"),
        "confidence": regime_class.get("confidence", "unknown"),
        "status": "placeholder" if metadata["is_sample"] else "derived",
    })

    # Inflation Score
    inflation_score = scores.get("inflation", 0)
    inflation_state = regime_class.get("inflation_state", "unknown")
    lineage_records.append({
        "dashboard_metric_name": "Inflation Score",
        "value_displayed": f"{inflation_score:+.2f} ({inflation_state})",
        "source_module": "src/models/enhanced_macro_classifier.py",
        "source_file": "outputs/latest_model_results.json",
        "source_series_id": "ensemble_inflation",
        "source_name": "Inflation Ensemble (CPI, Core CPI, PPI)",
        "raw_latest_observation_date": str(live_data_info["latest_date"]) if live_data_info["latest_date"] else "N/A",
        "raw_latest_value": "N/A (processed score)",
        "transformed_latest_date": model_results.get("timestamp", "N/A"),
        "transformed_latest_value": f"{inflation_score:+.2f}",
        "transformation_used": "ensemble_weighted_average -> z_score_normalization",
        "is_live_data": not metadata["is_sample"] and live_data_info["exists"],
        "is_cached_live_data": not metadata["is_sample"] and live_data_info["exists"],
        "is_sample_data": metadata["is_sample"],
        "is_placeholder": False,
        "data_mode": model_results.get("data_mode", "unknown"),
        "confidence": regime_class.get("confidence", "unknown"),
        "status": "needs_audit" if inflation_score > 0.5 and inflation_state == "low" else "ok",
        "issue_flags": "SCORE_POSITIVE_BUT_STATE_LOW" if inflation_score > 0.5 and inflation_state == "low" else None,
    })

    # Financial Conditions Score
    liquidity_score = scores.get("liquidity", 0)
    fin_conditions = model_results.get("financial_conditions", {})
    lineage_records.append({
        "dashboard_metric_name": "Financial Conditions Ease",
        "value_displayed": f"{liquidity_score:+.2f}",
        "source_module": "src/models/enhanced_macro_classifier.py",
        "source_file": "outputs/latest_model_results.json",
        "source_series_id": "financial_conditions",
        "source_name": "Financial Conditions Index",
        "raw_latest_observation_date": str(live_data_info["latest_date"]) if live_data_info["latest_date"] else "N/A",
        "raw_latest_value": "N/A (composite score)",
        "transformed_latest_date": model_results.get("timestamp", "N/A"),
        "transformed_latest_value": f"{liquidity_score:+.2f}",
        "transformation_used": "yield_spread_calculation -> credit_conditions_composite",
        "is_live_data": not metadata["is_sample"] and live_data_info["exists"],
        "is_cached_live_data": not metadata["is_sample"] and live_data_info["exists"],
        "is_sample_data": metadata["is_sample"],
        "is_placeholder": False,
        "data_mode": model_results.get("data_mode", "unknown"),
        "confidence": regime_class.get("confidence", "unknown"),
        "status": "needs_clarification",
        "issue_flags": "NEEDS_LEVEL_VS_DIRECTION_SEPARATION",
        "notes": "Level shows easy/tight, direction shows easing/tightening. Both must be displayed.",
    })

    # Risk Appetite Score
    risk_score = scores.get("risk", 0)
    lineage_records.append({
        "dashboard_metric_name": "Risk Appetite",
        "value_displayed": f"{risk_score:+.2f}",
        "source_module": "src/models/enhanced_macro_classifier.py",
        "source_file": "outputs/latest_model_results.json",
        "source_series_id": "risk_appetite",
        "source_name": "Risk Appetite Composite (VIX, spreads, momentum)",
        "raw_latest_observation_date": str(live_data_info["latest_date"]) if live_data_info["latest_date"] else "N/A",
        "raw_latest_value": "N/A (composite score)",
        "transformed_latest_date": model_results.get("timestamp", "N/A"),
        "transformed_latest_value": f"{risk_score:+.2f}",
        "transformation_used": "vix_inversion -> spread_composite -> momentum_blend",
        "is_live_data": not metadata["is_sample"] and live_data_info["exists"],
        "is_cached_live_data": not metadata["is_sample"] and live_data_info["exists"],
        "is_sample_data": metadata["is_sample"],
        "is_placeholder": False,
        "data_mode": model_results.get("data_mode", "unknown"),
        "confidence": regime_class.get("confidence", "unknown"),
        "status": "needs_clarification",
        "issue_flags": "NEEDS_LEVEL_VS_DIRECTION_SEPARATION",
    })

    # ==========================================================================
    # 3. RECESSION RISK LINEAGE
    # ==========================================================================

    recession = model_results.get("recession_risk", {})
    rec_prob = recession.get("probability", 0)

    lineage_records.append({
        "dashboard_metric_name": "Recession Risk (Top Level)",
        "value_displayed": f"{rec_prob:.1f}%",
        "source_module": "src/models/enhanced_macro_classifier.py",
        "source_file": "outputs/latest_model_results.json",
        "source_series_id": "recession_probability",
        "source_name": "Recession Risk Model",
        "raw_latest_observation_date": str(live_data_info["latest_date"]) if live_data_info["latest_date"] else "N/A",
        "raw_latest_value": f"{rec_prob:.1f}%",
        "transformed_latest_date": model_results.get("timestamp", "N/A"),
        "transformed_latest_value": f"{rec_prob:.1f}%",
        "transformation_used": "yield_curve_inversion + unemployment_trend + leading_indicators",
        "is_live_data": not metadata["is_sample"] and live_data_info["exists"],
        "is_cached_live_data": not metadata["is_sample"] and live_data_info["exists"],
        "is_sample_data": metadata["is_sample"],
        "is_placeholder": False,
        "data_mode": model_results.get("data_mode", "unknown"),
        "confidence": "medium",
        "status": "needs_hierarchy_clarification",
        "issue_flags": "MISMATCH_WITH_US_RECESSION_RISK",
        "notes": "Top-level recession risk may differ from country-specific. Need clear separation.",
    })

    # ==========================================================================
    # 4. LATEST DATA DATE LINEAGE
    # ==========================================================================

    latest_data_date = live_data_info["latest_date"] if live_data_info["exists"] else None
    if latest_data_date:
        days_since = (now - latest_data_date).days
        is_future = latest_data_date > now
    else:
        days_since = None
        is_future = False

    lineage_records.append({
        "dashboard_metric_name": "Latest Data Date",
        "value_displayed": str(latest_data_date) if latest_data_date else "N/A",
        "source_module": "src/data/data_loader_live.py",
        "source_file": "data/processed/live/macro_data.parquet",
        "source_series_id": "index_max_date",
        "source_name": "Combined Live Data Index",
        "raw_latest_observation_date": str(latest_data_date) if latest_data_date else "N/A",
        "raw_latest_value": "N/A",
        "transformed_latest_date": str(latest_data_date) if latest_data_date else "N/A",
        "transformed_latest_value": str(latest_data_date) if latest_data_date else "N/A",
        "transformation_used": "resample('ME').last() -> forward_fill",
        "is_live_data": live_data_info["exists"],
        "is_cached_live_data": live_data_info["exists"],
        "is_sample_data": not live_data_info["exists"],
        "is_placeholder": False,
        "data_mode": "live" if live_data_info["exists"] else "sample",
        "confidence": "high",
        "status": "INVALID_FUTURE_DATE" if is_future else "ok",
        "issue_flags": "FUTURE_DATED" if is_future else None,
        "notes": f"Days since update: {days_since}. Current date: {now.date()}." if is_future else None,
    })

    # ==========================================================================
    # 5. LIVE SERIES COUNT LINEAGE
    # ==========================================================================

    lineage_records.append({
        "dashboard_metric_name": "Live Series Available",
        "value_displayed": str(live_data_info["series_count"]),
        "source_module": "src/data/data_loader_live.py",
        "source_file": "data/processed/live/macro_data.parquet",
        "source_series_id": "column_count",
        "source_name": "Available FRED Series",
        "raw_latest_observation_date": str(live_data_info["latest_date"]) if live_data_info["latest_date"] else "N/A",
        "raw_latest_value": str(live_data_info["series_count"]),
        "transformed_latest_date": model_results.get("timestamp", "N/A"),
        "transformed_latest_value": str(live_data_info["series_count"]),
        "transformation_used": "count_columns",
        "is_live_data": live_data_info["exists"],
        "is_cached_live_data": live_data_info["exists"],
        "is_sample_data": not live_data_info["exists"],
        "is_placeholder": False,
        "data_mode": "live" if live_data_info["exists"] else "sample",
        "confidence": "high",
        "status": "INSUFFICIENT_FOR_ALLOCATION" if live_data_info["series_count"] < 8 else "ok",
        "issue_flags": "BELOW_MINIMUM_THRESHOLD" if live_data_info["series_count"] < 8 else None,
        "notes": f"Minimum 8 series required for US macro view. Current: {live_data_info['series_count']}",
    })

    # ==========================================================================
    # 6. SECTOR SIGNALS LINEAGE
    # ==========================================================================

    sector_signals = model_results.get("sector_signals", {})
    for sector, signal in sector_signals.items():
        lineage_records.append({
            "dashboard_metric_name": f"Sector Signal: {sector}",
            "value_displayed": signal,
            "source_module": "src/models/enhanced_macro_classifier.py",
            "source_file": "outputs/latest_model_results.json",
            "source_series_id": f"sector_{sector.lower()}",
            "source_name": f"{sector} Sector Model",
            "raw_latest_observation_date": str(live_data_info["latest_date"]) if live_data_info["latest_date"] else "N/A",
            "raw_latest_value": signal,
            "transformed_latest_date": model_results.get("timestamp", "N/A"),
            "transformed_latest_value": signal,
            "transformation_used": "macro_regime_mapping -> sector_sensitivity",
            "is_live_data": not metadata["is_sample"] and live_data_info["exists"],
            "is_cached_live_data": not metadata["is_sample"] and live_data_info["exists"],
            "is_sample_data": metadata["is_sample"],
            "is_placeholder": signal == "Neutral",
            "data_mode": model_results.get("data_mode", "unknown"),
            "confidence": "low" if signal == "Neutral" else "medium",
            "status": "PLACEHOLDER" if signal == "Neutral" else "ok",
            "issue_flags": "DEFAULT_NEUTRAL_SIGNAL" if signal == "Neutral" else None,
        })

    # ==========================================================================
    # 7. BUSINESS LAYER METRICS
    # ==========================================================================

    # Check business outputs
    business_outputs = {
        "expected_returns": PROJECT_ROOT / "outputs" / "latest_expected_return_scores.csv",
        "position_sizing": PROJECT_ROOT / "outputs" / "latest_position_sizing.csv",
        "decision_log": PROJECT_ROOT / "outputs" / "latest_decision_log.csv",
    }

    for metric_name, file_path in business_outputs.items():
        if file_path.exists():
            lineage_records.append({
                "dashboard_metric_name": f"Business Layer: {metric_name}",
                "value_displayed": "Generated",
                "source_module": "src/business/",
                "source_file": str(file_path),
                "source_series_id": "business_layer",
                "source_name": f"Business Layer {metric_name.title()}",
                "raw_latest_observation_date": str(live_data_info["latest_date"]) if live_data_info["latest_date"] else "N/A",
                "raw_latest_value": "N/A",
                "transformed_latest_date": model_results.get("timestamp", "N/A"),
                "transformed_latest_value": "Generated",
                "transformation_used": f"signal_registry -> expected_return_engine -> {metric_name}",
                "is_live_data": not metadata["is_sample"],
                "is_cached_live_data": not metadata["is_sample"],
                "is_sample_data": metadata["is_sample"],
                "is_placeholder": metadata["is_sample"],
                "data_mode": model_results.get("data_mode", "unknown"),
                "confidence": "low" if metadata["is_sample"] else "medium",
                "status": "SAMPLE_MODE" if metadata["is_sample"] else "ok",
                "issue_flags": "SAMPLE_DATA_BUSINESS_LAYER" if metadata["is_sample"] else None,
            })

    # Create DataFrame
    df_lineage = pd.DataFrame(lineage_records)

    # Add report metadata
    report_meta = {
        "generated_at": now.isoformat(),
        "current_system_date": str(now.date()),
        "model_results_timestamp": model_results.get("timestamp", "N/A"),
        "data_mode": model_results.get("data_mode", "unknown"),
        "total_metrics_tracked": len(df_lineage),
        "issues_found": len(df_lineage[df_lineage["status"].str.contains("INVALID|INSUFFICIENT|PLACEHOLDER|needs", na=False)]),
    }

    return df_lineage, report_meta


def save_lineage_report():
    """Generate and save the data lineage report."""
    df_lineage, meta = generate_data_lineage_report()

    # Save CSV
    output_path = PROJECT_ROOT / "outputs" / "data_lineage_report.csv"
    df_lineage.to_csv(output_path, index=False)
    print(f"Saved CSV: {output_path}")

    # Generate Markdown report
    md_lines = [
        "# Data Lineage Report",
        "",
        f"**Generated:** {meta['generated_at']}",
        f"**System Date:** {meta['current_system_date']}",
        f"**Data Mode:** {meta['data_mode']}",
        f"**Total Metrics Tracked:** {meta['total_metrics_tracked']}",
        f"**Issues Found:** {meta['issues_found']}",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
    ]

    # Issues section
    issues = df_lineage[df_lineage["status"].str.contains("INVALID|INSUFFICIENT|PLACEHOLDER|needs", na=False)]
    if len(issues) > 0:
        md_lines.append("### ⚠️ Data Issues Requiring Attention")
        md_lines.append("")
        for _, row in issues.iterrows():
            md_lines.append(f"- **{row['dashboard_metric_name']}**: {row['status']}")
            if pd.notna(row.get('issue_flags')):
                md_lines.append(f"  - Flag: `{row['issue_flags']}`")
            if pd.notna(row.get('notes')):
                md_lines.append(f"  - Note: {row['notes']}")
        md_lines.append("")

    # Metrics by category
    md_lines.append("## Metrics by Category")
    md_lines.append("")

    categories = {
        "Macro Scores": ["Growth Score", "Inflation Score", "Financial Conditions", "Risk Appetite"],
        "Risk Metrics": ["Recession Risk"],
        "Data Quality": ["Latest Data Date", "Live Series Available"],
        "Sector Signals": ["Sector Signal"],
        "Business Layer": ["Business Layer"],
    }

    for cat_name, keywords in categories.items():
        cat_df = df_lineage[df_lineage["dashboard_metric_name"].apply(lambda x: any(k in x for k in keywords))]
        if len(cat_df) > 0:
            md_lines.append(f"### {cat_name}")
            md_lines.append("")
            md_lines.append("| Metric | Value | Source | Status |")
            md_lines.append("|--------|-------|--------|--------|")
            for _, row in cat_df.iterrows():
                status_icon = "✅" if row['status'] == 'ok' else "⚠️" if 'needs' in str(row['status']) else "❌"
                md_lines.append(f"| {row['dashboard_metric_name']} | {row['value_displayed']} | {row['source_module'].split('/')[-1]} | {status_icon} {row['status']} |")
            md_lines.append("")

    # Full details table
    md_lines.append("## Complete Lineage Details")
    md_lines.append("")
    md_lines.append("| Metric | Value | Transformation | Data Mode | Status |")
    md_lines.append("|--------|-------|----------------|-----------|--------|")
    for _, row in df_lineage.iterrows():
        md_lines.append(f"| {row['dashboard_metric_name']} | {row['value_displayed']} | {row['transformation_used'][:30]}... | {row['data_mode']} | {row['status']} |")
    md_lines.append("")

    # Save markdown
    md_path = PROJECT_ROOT / "outputs" / "data_lineage_report.md"
    with open(md_path, "w") as f:
        f.write("\n".join(md_lines))
    print(f"Saved Markdown: {md_path}")

    return df_lineage, meta


if __name__ == "__main__":
    df, meta = save_lineage_report()
    print(f"\nReport Summary:")
    print(f"  Total metrics: {meta['total_metrics_tracked']}")
    print(f"  Issues found: {meta['issues_found']}")
    print(f"  Data mode: {meta['data_mode']}")
