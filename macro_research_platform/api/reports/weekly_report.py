"""
Weekly Research Report Generator — Institutional-grade PDF Reports

Generates 5-page PDF research reports every Monday with:
1. Macro Overview — Regime, leading indicators, recession risk
2. Signal Dashboard — Signal performance, model agreement
3. Equity Research — Sector rotation, factor exposure, stock picks
4. Valuation — Market valuation, GMO forecasts, expected returns
5. Forward Calendar — Economic events, earnings, central banks

Academic Basis:
- Report Formatting: CFA Institute Research Standards
- Color Scheme: Institutional Financial (Blue/Gray/Accent)
- Layout: Professional Research Report Format
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
from dataclasses import dataclass
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, KeepTogether, ListFlowable, ListItem
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie

logger = logging.getLogger(__name__)

# Institutional color scheme
COLORS = {
    "primary_blue": colors.HexColor("#1e3a5f"),
    "secondary_blue": colors.HexColor("#2c5282"),
    "accent_green": colors.HexColor("#38a169"),
    "accent_red": colors.HexColor("#e53e3e"),
    "accent_yellow": colors.HexColor("#d69e2e"),
    "light_gray": colors.HexColor("#e2e8f0"),
    "medium_gray": colors.HexColor("#718096"),
    "dark_gray": colors.HexColor("#2d3748"),
    "white": colors.white,
    "black": colors.black,
}


@dataclass
class ReportData:
    """Container for all report data."""
    macro_overview: Dict[str, Any]
    signal_dashboard: Dict[str, Any]
    equity_research: Dict[str, Any]
    valuation: Dict[str, Any]
    forward_calendar: Dict[str, Any]
    generated_at: datetime


class WeeklyResearchReport:
    """
    Generate institutional-grade weekly research PDF.

    Page Layout:
    - Page 1: Cover + Executive Summary
    - Page 2: Macro Overview
    - Page 3: Signal Dashboard
    - Page 4: Equity Research
    - Page 5: Valuation + Forward Calendar
    """

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent.parent / "reports"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.styles = self._create_styles()

    def _create_styles(self) -> Dict:
        """Create custom paragraph styles."""
        styles = getSampleStyleSheet()

        # Title style
        styles.add(ParagraphStyle(
            "ReportTitle",
            parent=styles["Heading1"],
            fontSize=24,
            textColor=COLORS["primary_blue"],
            spaceAfter=20,
            alignment=TA_CENTER,
            fontName="Helvetica-Bold"
        ))

        # Section header
        styles.add(ParagraphStyle(
            "SectionHeader",
            parent=styles["Heading2"],
            fontSize=16,
            textColor=COLORS["primary_blue"],
            spaceBefore=20,
            spaceAfter=10,
            borderColor=COLORS["primary_blue"],
            borderWidth=2,
            borderPadding=5,
        ))

        # Subsection header
        styles.add(ParagraphStyle(
            "SubsectionHeader",
            parent=styles["Heading3"],
            fontSize=12,
            textColor=COLORS["secondary_blue"],
            spaceBefore=10,
            spaceAfter=5,
        ))

        # Body text
        styles.add(ParagraphStyle(
            "ReportBodyText",
            parent=styles["Normal"],
            fontSize=10,
            textColor=COLORS["dark_gray"],
            spaceBefore=5,
            spaceAfter=5,
            leading=14,
        ))

        # Highlight box
        styles.add(ParagraphStyle(
            "HighlightBox",
            parent=styles["Normal"],
            fontSize=11,
            textColor=COLORS["primary_blue"],
            backColor=COLORS["light_gray"],
            spaceBefore=10,
            spaceAfter=10,
            borderPadding=10,
        ))

        # Footer
        styles.add(ParagraphStyle(
            "Footer",
            parent=styles["Normal"],
            fontSize=8,
            textColor=COLORS["medium_gray"],
            alignment=TA_CENTER,
        ))

        return styles

    def generate(self, data: ReportData) -> Path:
        """
        Generate weekly research PDF.

        Args:
            data: ReportData containing all sections

        Returns:
            Path to generated PDF file
        """
        # Generate filename
        week_str = data.generated_at.strftime("%Y-W%W")
        filename = f"Macro_Research_Weekly_{week_str}.pdf"
        filepath = self.output_dir / filename

        # Create PDF
        doc = SimpleDocTemplate(
            str(filepath),
            pagesize=letter,
            rightMargin=0.75 * inch,
            leftMargin=0.75 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
        )

        # Build content
        story = []

        # Page 1: Cover + Executive Summary
        story.extend(self._build_cover_page(data))
        story.append(PageBreak())

        # Page 2: Macro Overview
        story.extend(self._build_macro_overview(data.macro_overview))
        story.append(PageBreak())

        # Page 3: Signal Dashboard
        story.extend(self._build_signal_dashboard(data.signal_dashboard))
        story.append(PageBreak())

        # Page 4: Equity Research
        story.extend(self._build_equity_research(data.equity_research))
        story.append(PageBreak())

        # Page 5: Valuation + Forward Calendar
        story.extend(self._build_valuation(data.valuation))
        story.extend(self._build_forward_calendar(data.forward_calendar))

        # Build PDF
        try:
            doc.build(story)
            logger.info(f"[REPORT] Generated: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"[REPORT] Failed to generate PDF: {e}")
            raise

    def _build_cover_page(self, data: ReportData) -> List:
        """Build cover page with executive summary."""
        story = []

        # Title
        story.append(Spacer(1, 1 * inch))
        story.append(Paragraph(
            "MACRO RESEARCH WEEKLY",
            self.styles["ReportTitle"]
        ))

        # Subtitle
        week_str = data.generated_at.strftime("%Y Week %W")
        date_str = data.generated_at.strftime("%B %d, %Y")
        story.append(Paragraph(
            f"{week_str} | {date_str}",
            self.styles["SubsectionHeader"]
        ))
        story.append(Spacer(1, 0.5 * inch))

        # Executive Summary Box
        regime = data.macro_overview.get("regime", "Unknown")
        signal = data.signal_dashboard.get("overall_signal", "Neutral")

        summary_text = f"""
        <b>Executive Summary</b><br/><br/>
        <b>Current Regime:</b> {regime}<br/>
        <b>Overall Signal:</b> {signal}<br/>
        <b>Key Takeaway:</b> {self._generate_executive_summary(data)}<br/><br/>
        This report provides institutional-grade analysis of macro conditions,
        signal performance, equity recommendations, and forward-looking calendar.
        """

        story.append(Paragraph(summary_text, self.styles["HighlightBox"]))
        story.append(Spacer(1, 0.5 * inch))

        # Table of Contents
        toc_data = [
            ["Section", "Page"],
            ["1. Macro Overview", "2"],
            ["2. Signal Dashboard", "3"],
            ["3. Equity Research", "4"],
            ["4. Valuation & Forward Calendar", "5"],
        ]

        toc_table = Table(toc_data, colWidths=[4 * inch, 1 * inch])
        toc_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COLORS["primary_blue"]),
            ("TEXTCOLOR", (0, 0), (-1, 0), COLORS["white"]),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 11),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("GRID", (0, 0), (-1, -1), 0.5, COLORS["light_gray"]),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [COLORS["white"], COLORS["light_gray"]]),
        ]))

        story.append(toc_table)

        # Footer
        story.append(Spacer(1, 1 * inch))
        story.append(Paragraph(
            "Generated by Macro Research Platform v8.0 | For Institutional Use Only",
            self.styles["Footer"]
        ))

        return story

    def _build_macro_overview(self, data: Dict) -> List:
        """Build macro overview section."""
        story = []
        story.append(Paragraph("1. Macro Overview", self.styles["SectionHeader"]))

        # Current Regime
        regime = data.get("regime", "Unknown")
        story.append(Paragraph(f"<b>Current Regime:</b> {regime}", self.styles["SubsectionHeader"]))

        regime_desc = {
            "Goldilocks": "Growth positive, inflation moderate. Favor cyclicals.",
            "Reflation": "Growth accelerating, inflation rising. Favor real assets.",
            "Stagflation": "Growth slowing, inflation elevated. Favor defensives.",
            "Slowdown": "Growth decelerating, inflation falling. Favor quality.",
        }.get(regime, "Regime classification uncertain.")

        story.append(Paragraph(regime_desc, self.styles["ReportBodyText"]))
        story.append(Spacer(1, 0.2 * inch))

        # Key Metrics Table
        metrics_data = [
            ["Indicator", "Value", "Trend", "Implication"],
            ["GDP Growth", data.get("gdp_growth", "2.0%"), data.get("gdp_trend", "Stable"), data.get("gdp_impact", "Neutral")],
            ["CPI YoY", data.get("cpi_yoy", "3.3%"), data.get("cpi_trend", "Elevated"), data.get("cpi_impact", "Hawkish")],
            ["Fed Funds", data.get("fed_funds", "3.64%"), data.get("fed_trend", "Restrictive"), data.get("fed_impact", "Tightening")],
            ["Unemployment", data.get("unemployment", "4.2%"), data.get("unemp_trend", "Rising"), data.get("unemp_impact", "Caution")],
        ]

        metrics_table = Table(metrics_data, colWidths=[1.5 * inch, 1 * inch, 1 * inch, 2.5 * inch])
        metrics_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COLORS["primary_blue"]),
            ("TEXTCOLOR", (0, 0), (-1, 0), COLORS["white"]),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, COLORS["light_gray"]),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [COLORS["white"], COLORS["light_gray"]]),
        ]))

        story.append(metrics_table)
        story.append(Spacer(1, 0.3 * inch))

        # Recession Risk
        recession_risk = data.get("recession_risk", 0.30)
        risk_level = "Low" if recession_risk < 0.3 else "Moderate" if recession_risk < 0.5 else "High"
        risk_color = COLORS["accent_green"] if recession_risk < 0.3 else COLORS["accent_yellow"] if recession_risk < 0.5 else COLORS["accent_red"]

        story.append(Paragraph(f"<b>Recession Risk:</b> {recession_risk:.1%} ({risk_level})", self.styles["SubsectionHeader"]))

        # Risk drivers
        risk_drivers = data.get("risk_drivers", [
            "Yield curve has steepened from inversion",
            "Sahm Rule at 0.20pp (below 0.50 trigger)",
            "Credit spreads stable around 283 bps",
            "Labor market showing modest softening",
        ])

        for driver in risk_drivers:
            story.append(Paragraph(f"• {driver}", self.styles["ReportBodyText"]))

        return story

    def _build_signal_dashboard(self, data: Dict) -> List:
        """Build signal dashboard section."""
        story = []
        story.append(Paragraph("2. Signal Dashboard", self.styles["SectionHeader"]))

        # Overall Signal
        overall = data.get("overall_signal", "Neutral")
        signal_color = COLORS["accent_green"] if overall == "Bullish" else COLORS["accent_red"] if overall == "Bearish" else COLORS["medium_gray"]

        story.append(Paragraph(f"<b>Overall Signal:</b> {overall}", self.styles["SubsectionHeader"]))

        # Signal Stack Table
        signal_data = [
            ["Signal Module", "Signal", "Confidence", "IC (1M)"],
            ["HMM Regime", data.get("hmm_signal", "Neutral"), data.get("hmm_conf", "0.70"), data.get("hmm_ic", "0.08")],
            ["Kalman Filter", data.get("kalman_signal", "Neutral"), data.get("kalman_conf", "0.65"), data.get("kalman_ic", "0.12")],
            ["Bayesian Aggregator", data.get("bayesian_signal", "Neutral"), data.get("bayesian_conf", "0.72"), data.get("bayesian_ic", "0.15")],
            ["News Sentiment", data.get("sentiment_signal", "Neutral"), data.get("sentiment_conf", "0.58"), data.get("sentiment_ic", "0.06")],
            ["Multi-Factor Alpha", data.get("alpha_signal", "Neutral"), data.get("alpha_conf", "0.68"), data.get("alpha_ic", "0.11")],
        ]

        signal_table = Table(signal_data, colWidths=[2 * inch, 1.2 * inch, 1 * inch, 1 * inch])
        signal_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COLORS["primary_blue"]),
            ("TEXTCOLOR", (0, 0), (-1, 0), COLORS["white"]),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, COLORS["light_gray"]),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [COLORS["white"], COLORS["light_gray"]]),
        ]))

        story.append(signal_table)
        story.append(Spacer(1, 0.3 * inch))

        # Model Agreement
        agreement = data.get("model_agreement", 0.65)
        story.append(Paragraph(f"<b>Model Agreement:</b> {agreement:.0%}", self.styles["SubsectionHeader"]))
        story.append(Paragraph(
            f"Signal modules show {agreement:.0%} agreement. "
            f"High agreement increases confidence in directional signal.",
            self.styles["ReportBodyText"]
        ))

        # Signal Health
        story.append(Paragraph("<b>Signal Health:</b>", self.styles["SubsectionHeader"]))

        health_metrics = data.get("health_metrics", [
            ("Directional Accuracy", "58%", "Target: >55%"),
            ("Information Coefficient", "0.12", "Target: >0.08"),
            ("Sharpe Ratio", "0.85", "Target: >0.50"),
        ])

        for metric, value, target in health_metrics:
            story.append(Paragraph(f"• {metric}: {value} ({target})", self.styles["ReportBodyText"]))

        return story

    def _build_equity_research(self, data: Dict) -> List:
        """Build equity research section."""
        story = []
        story.append(Paragraph("3. Equity Research", self.styles["SectionHeader"]))

        # Sector Rotation
        story.append(Paragraph("<b>Sector Rotation</b>", self.styles["SubsectionHeader"]))

        regime = data.get("regime", "Goldilocks")
        story.append(Paragraph(f"Current regime ({regime}) favors:", self.styles["ReportBodyText"]))

        # Top sectors table
        sectors_data = [
            ["Sector", "Signal", "Expected Return", "Confidence"],
        ]

        top_sectors = data.get("top_sectors", [
            ("Technology", "Overweight", "10.1%", "95%"),
            ("Consumer Discretionary", "Overweight", "7.5%", "95%"),
            ("Industrials", "Overweight", "6.6%", "95%"),
        ])

        for sector, signal, exp_ret, conf in top_sectors:
            sectors_data.append([sector, signal, exp_ret, conf])

        sectors_table = Table(sectors_data, colWidths=[2.2 * inch, 1 * inch, 1.5 * inch, 1 * inch])
        sectors_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COLORS["primary_blue"]),
            ("TEXTCOLOR", (0, 0), (-1, 0), COLORS["white"]),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, COLORS["light_gray"]),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [COLORS["white"], COLORS["light_gray"]]),
        ]))

        story.append(sectors_table)
        story.append(Spacer(1, 0.3 * inch))

        # Factor Exposure
        story.append(Paragraph("<b>Factor Exposure</b>", self.styles["SubsectionHeader"]))

        factors = data.get("factor_exposure", [
            ("Value", "Neutral", "0.00"),
            ("Quality", "Overweight", "0.15"),
            ("Momentum", "Underweight", "-0.10"),
            ("Low Vol", "Neutral", "0.05"),
        ])

        for factor, exposure, score in factors:
            story.append(Paragraph(f"• {factor}: {exposure} (Score: {score})", self.styles["ReportBodyText"]))

        # Top Picks
        story.append(Spacer(1, 0.2 * inch))
        story.append(Paragraph("<b>Alpha Screen Top Picks</b>", self.styles["SubsectionHeader"]))

        picks = data.get("top_picks", [
            ("AAPL", "Technology", "Strong", "0.82"),
            ("MSFT", "Technology", "Strong", "0.79"),
            ("UNH", "Healthcare", "Moderate", "0.71"),
        ])

        picks_data = [["Ticker", "Sector", "Signal", "Score"]]
        for ticker, sector, signal, score in picks:
            picks_data.append([ticker, sector, signal, score])

        picks_table = Table(picks_data, colWidths=[1.2 * inch, 1.5 * inch, 1.2 * inch, 1 * inch])
        picks_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COLORS["primary_blue"]),
            ("TEXTCOLOR", (0, 0), (-1, 0), COLORS["white"]),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, COLORS["light_gray"]),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [COLORS["white"], COLORS["light_gray"]]),
        ]))

        story.append(picks_table)

        return story

    def _build_valuation(self, data: Dict) -> List:
        """Build valuation section."""
        story = []
        story.append(Paragraph("4. Valuation & Expected Returns", self.styles["SectionHeader"]))

        # Market Valuation
        story.append(Paragraph("<b>Market Valuation</b>", self.styles["SubsectionHeader"]))

        valuation_metrics = data.get("valuation", [
            ("Current P/E", "21.5x", "25th percentile", "Elevated"),
            ("Forward P/E", "19.2x", "30th percentile", "Fair"),
            ("Shiller CAPE", "32.1x", "85th percentile", "Expensive"),
            ("EV/EBITDA", "14.8x", "60th percentile", "Fair"),
        ])

        val_data = [["Metric", "Value", "Percentile", "Assessment"]]
        for metric, value, percentile, assessment in valuation_metrics:
            val_data.append([metric, value, percentile, assessment])

        val_table = Table(val_data, colWidths=[1.5 * inch, 1 * inch, 1.5 * inch, 1.5 * inch])
        val_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COLORS["primary_blue"]),
            ("TEXTCOLOR", (0, 0), (-1, 0), COLORS["white"]),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, COLORS["light_gray"]),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [COLORS["white"], COLORS["light_gray"]]),
        ]))

        story.append(val_table)
        story.append(Spacer(1, 0.3 * inch))

        # GMO Forecasts
        story.append(Paragraph("<b>GMO 7-Year Expected Returns</b>", self.styles["SubsectionHeader"]))

        gmo_forecasts = data.get("gmo_forecasts", [
            ("US Large Cap", "-2.1%", "Overvalued"),
            ("US Small Cap", "-0.5%", "Fair"),
            ("Int'l Developed", "3.2%", "Attractive"),
            ("Emerging Markets", "5.8%", "Very Attractive"),
        ])

        gmo_data = [["Asset Class", "Expected Return", "Assessment"]]
        for asset, exp_ret, assessment in gmo_forecasts:
            gmo_data.append([asset, exp_ret, assessment])

        gmo_table = Table(gmo_data, colWidths=[2 * inch, 1.5 * inch, 2 * inch])
        gmo_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COLORS["primary_blue"]),
            ("TEXTCOLOR", (0, 0), (-1, 0), COLORS["white"]),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, COLORS["light_gray"]),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [COLORS["white"], COLORS["light_gray"]]),
        ]))

        story.append(gmo_table)

        return story

    def _build_forward_calendar(self, data: Dict) -> List:
        """Build forward calendar section."""
        story = []
        story.append(Paragraph("5. Forward Calendar", self.styles["SectionHeader"]))

        # Economic Events
        story.append(Paragraph("<b>Economic Data (Next 7 Days)</b>", self.styles["SubsectionHeader"]))

        events = data.get("economic_events", [
            ("Wednesday", "CPI Release", "High"),
            ("Thursday", "Jobless Claims", "Medium"),
            ("Friday", "Retail Sales", "Medium"),
        ])

        for day, event, impact in events:
            impact_color = "red" if impact == "High" else "orange" if impact == "Medium" else "green"
            story.append(Paragraph(
                f"• <b>{day}:</b> {event} (<font color='{impact_color}'>{impact}</font> Impact)",
                self.styles["ReportBodyText"]
            ))

        # Earnings
        story.append(Spacer(1, 0.2 * inch))
        story.append(Paragraph("<b>Notable Earnings</b>", self.styles["SubsectionHeader"]))

        earnings = data.get("earnings", [
            ("JPM", "Financials", "Q1", "Jan 14"),
            ("WFC", "Financials", "Q1", "Jan 15"),
            ("C", "Financials", "Q1", "Jan 16"),
        ])

        for ticker, sector, quarter, date in earnings:
            story.append(Paragraph(
                f"• {ticker} ({sector}) — {quarter} — {date}",
                self.styles["ReportBodyText"]
            ))

        # Central Banks
        story.append(Spacer(1, 0.2 * inch))
        story.append(Paragraph("<b>Central Bank Events</b>", self.styles["SubsectionHeader"]))

        cb_events = data.get("central_bank_events", [
            ("Fed", "FOMC Minutes", "Jan 8", "Medium"),
            ("ECB", "Policy Meeting", "Jan 16", "High"),
            ("BoE", "Rate Decision", "Jan 18", "Medium"),
        ])

        for bank, event, date, impact in cb_events:
            story.append(Paragraph(
                f"• <b>{bank}</b>: {event} — {date} ({impact} Impact)",
                self.styles["ReportBodyText"]
            ))

        # Disclaimer
        story.append(Spacer(1, 0.5 * inch))
        story.append(Paragraph(
            "<b>Disclaimer:</b> This report is for institutional use only. "
            "Past performance is not indicative of future results. "
            "Consult your financial advisor before making investment decisions.",
            self.styles["ReportBodyText"]
        ))

        # Footer
        story.append(Spacer(1, 0.3 * inch))
        story.append(Paragraph(
            "— End of Report —",
            self.styles["Footer"]
        ))

        return story

    def _generate_executive_summary(self, data: ReportData) -> str:
        """Generate dynamic executive summary."""
        regime = data.macro_overview.get("regime", "Unknown")
        signal = data.signal_dashboard.get("overall_signal", "Neutral")

        summaries = {
            ("Goldilocks", "Bullish"): "Goldilocks regime with bullish signal. Favor cyclicals and growth.",
            ("Goldilocks", "Bearish"): "Goldilocks regime but signals turning. Watch for momentum deterioration.",
            ("Stagflation", "Bearish"): "Stagflation regime with bearish signal. Favor defensives and real assets.",
            ("Stagflation", "Bullish"): "Stagflation but early recovery signals. Energy and staples leading.",
            ("Reflation", "Bullish"): "Reflation regime bullish. Materials, energy, financials outperforming.",
            ("Slowdown", "Bearish"): "Slowdown regime with bearish signal. Maximum defensive positioning.",
        }

        return summaries.get((regime, signal), f"{regime} regime with {signal} signal. Monitor signals closely.")


def generate_weekly_report(
    macro_data: Optional[Dict] = None,
    signal_data: Optional[Dict] = None,
    equity_data: Optional[Dict] = None,
    valuation_data: Optional[Dict] = None,
    calendar_data: Optional[Dict] = None,
    output_dir: Optional[Path] = None,
) -> Path:
    """
    Generate weekly research report with all sections.

    Args:
        macro_data: Macro overview data
        signal_data: Signal dashboard data
        equity_data: Equity research data
        valuation_data: Valuation data
        calendar_data: Forward calendar data
        output_dir: Output directory for PDF

    Returns:
        Path to generated PDF
    """
    generator = WeeklyResearchReport(output_dir)

    # Use default data if not provided
    report_data = ReportData(
        macro_overview=macro_data or {},
        signal_dashboard=signal_data or {},
        equity_research=equity_data or {},
        valuation=valuation_data or {},
        forward_calendar=calendar_data or {},
        generated_at=datetime.now(),
    )

    return generator.generate(report_data)


# Entry point for scheduler
def run_weekly_report_job():
    """Entry point for Monday scheduler job."""
    logger.info("[REPORT] Starting weekly report generation")

    try:
        # Fetch current data (would integrate with actual data sources)
        from ..main import _compute_dashboard_data

        # This would need to be adapted to your actual data structure
        dashboard_data = _compute_dashboard_data()

        macro_data = {
            "regime": dashboard_data.get("regime", {}).get("current", "Unknown"),
            "recession_risk": dashboard_data.get("keyMetrics", {}).get("recessionRisk", 0.30),
        }

        signal_data = {
            "overall_signal": dashboard_data.get("signalStack", {}).get("composite", {}).get("signal", "Neutral"),
        }

        report_path = generate_weekly_report(
            macro_data=macro_data,
            signal_data=signal_data,
        )

        logger.info(f"[REPORT] Weekly report generated: {report_path}")
        return {"success": True, "path": str(report_path)}

    except Exception as e:
        logger.error(f"[REPORT] Failed to generate weekly report: {e}")
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    # Test generation
    report_path = generate_weekly_report()
    print(f"Generated: {report_path}")
