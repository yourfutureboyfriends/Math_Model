"""
data.connectors — Data ingestion layer for macro regime model.

This module provides connectors to various data sources:
  - fred_connector: Federal Reserve Economic Data (FRED) API
  - manual_override: Load custom CSV files for non-FRED indicators
  - data_pipeline: Orchestrates loading from multiple sources with fallback logic
"""

from .fred_connector import FredConnector
from .manual_override import ManualOverrideLoader
from .data_pipeline import DataPipeline, load_data, get_data_freshness

__all__ = [
    "FredConnector",
    "ManualOverrideLoader",
    "DataPipeline",
    "load_data",
    "get_data_freshness",
]
