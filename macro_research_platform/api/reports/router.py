"""
Reports API Router — Generate and download research reports
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from pathlib import Path

from .weekly_report import generate_weekly_report

router = APIRouter(prefix="/reports", tags=["reports"])


class GenerateReportRequest(BaseModel):
    """Request to generate a custom report."""
    regime: Optional[str] = None
    include_sections: Optional[list] = None
    custom_title: Optional[str] = None


class ReportResponse(BaseModel):
    """Report generation response."""
    success: bool
    message: str
    file_path: Optional[str] = None
    download_url: Optional[str] = None
    generated_at: Optional[str] = None


@router.post("/generate", response_model=ReportResponse)
async def generate_report(
    request: Optional[GenerateReportRequest] = None,
    background_tasks: BackgroundTasks = None
):
    """
    Generate a weekly research report.

    Returns:
        Report generation status and download URL
    """
    try:
        # Generate report with sample data (in production, fetch actual data)
        report_path = generate_weekly_report(
            macro_data={
                "regime": request.regime if request else "Goldilocks",
                "gdp_growth": "2.0%",
                "cpi_yoy": "3.3%",
                "fed_funds": "3.64%",
                "recession_risk": 0.30,
            },
            signal_data={
                "overall_signal": "Bullish",
                "hmm_signal": "Bullish",
                "hmm_conf": "0.75",
                "kalman_signal": "Neutral",
                "bayesian_signal": "Bullish",
                "model_agreement": 0.72,
            },
            equity_data={
                "regime": request.regime if request else "Goldilocks",
                "top_sectors": [
                    ("Technology", "Overweight", "10.1%", "95%"),
                    ("Consumer Discretionary", "Overweight", "7.5%", "95%"),
                    ("Industrials", "Overweight", "6.6%", "95%"),
                ],
                "top_picks": [
                    ("AAPL", "Technology", "Strong", "0.82"),
                    ("MSFT", "Technology", "Strong", "0.79"),
                    ("UNH", "Healthcare", "Moderate", "0.71"),
                ],
            },
            valuation_data={
                "valuation": [
                    ("Current P/E", "21.5x", "25th percentile", "Elevated"),
                    ("Forward P/E", "19.2x", "30th percentile", "Fair"),
                ],
                "gmo_forecasts": [
                    ("US Large Cap", "-2.1%", "Overvalued"),
                    ("Emerging Markets", "5.8%", "Very Attractive"),
                ],
            },
            calendar_data={
                "economic_events": [
                    ("Wednesday", "CPI Release", "High"),
                    ("Thursday", "Jobless Claims", "Medium"),
                ],
                "earnings": [
                    ("JPM", "Financials", "Q1", "Jan 14"),
                    ("WFC", "Financials", "Q1", "Jan 15"),
                ],
            },
        )

        # Create download URL
        filename = report_path.name
        download_url = f"/api/reports/download/{filename}"

        return ReportResponse(
            success=True,
            message=f"Report generated successfully",
            file_path=str(report_path),
            download_url=download_url,
            generated_at=datetime.now().isoformat()
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")


@router.get("/download/{filename}")
async def download_report(filename: str):
    """
    Download a generated report.

    Args:
        filename: Name of the report file

    Returns:
        PDF file download
    """
    try:
        reports_dir = Path(__file__).parent.parent.parent / "reports"
        file_path = reports_dir / filename

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Report not found")

        return FileResponse(
            path=str(file_path),
            media_type="application/pdf",
            filename=filename
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download report: {str(e)}")


@router.get("/list")
async def list_reports():
    """
    List all generated reports.

    Returns:
        List of available reports
    """
    try:
        reports_dir = Path(__file__).parent.parent.parent / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        reports = []
        for pdf_file in sorted(reports_dir.glob("*.pdf"), reverse=True):
            reports.append({
                "filename": pdf_file.name,
                "created": datetime.fromtimestamp(pdf_file.stat().st_mtime).isoformat(),
                "size": pdf_file.stat().st_size,
                "download_url": f"/api/reports/download/{pdf_file.name}",
            })

        return {"reports": reports}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list reports: {str(e)}")


@router.get("/latest")
async def get_latest_report():
    """
    Get the most recent report.

    Returns:
        Latest report information
    """
    try:
        reports_dir = Path(__file__).parent.parent.parent / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        pdf_files = sorted(reports_dir.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)

        if not pdf_files:
            return {"found": False, "message": "No reports generated yet"}

        latest = pdf_files[0]
        return {
            "found": True,
            "filename": latest.name,
            "created": datetime.fromtimestamp(latest.stat().st_mtime).isoformat(),
            "size": latest.stat().st_size,
            "download_url": f"/api/reports/download/{latest.name}",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get latest report: {str(e)}")


@router.get("/health")
async def reports_health():
    """Health check for reports module."""
    try:
        reports_dir = Path(__file__).parent.parent.parent / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        pdf_count = len(list(reports_dir.glob("*.pdf")))

        return {
            "status": "healthy",
            "reports_generated": pdf_count,
            "reports_directory": str(reports_dir),
            "generator_ready": True,
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }
