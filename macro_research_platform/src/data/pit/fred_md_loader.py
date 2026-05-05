"""
FRED-MD Loader

FRED-MD is a monthly macro database from McCracken and Ng (2016).
It provides a broad panel of macro indicators suitable for factor extraction.

Source: https://research.stlouisfed.org/econ/mccracken/fred-databases/

This loader downloads and processes FRED-MD for use in nowcasting models.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests

logger = logging.getLogger(__name__)


# FRED-MD series list (as of 2024)
# Categories: Output & Income, Labor Market, Consumption & Orders
#             Money & Credit, Interest Rates, Prices, Stock Market
FRED_MD_SERIES = {
    # Output & Income
    "RPI": "Real Personal Income",
    "W875RX1": "Real personal income ex transfer receipts",
    "INDPRO": "Industrial Production Index",
    "IPFPNSS": "IP: Final Products and Nonindustrial Supplies",
    "IPFINAL": "IP: Final Products (market group)",
    "IPCONGD": "IP: Consumer Goods",
    "IPDCONGD": "IP: Durable Consumer Goods",
    "IPNCONGD": "IP: Nondurable Consumer Goods",
    "IPBUSEQ": "IP: Business Equipment",
    "IPMAT": "IP: Materials",
    "IPDMAT": "IP: Durable Materials",
    "IPNMAT": "IP: Nondurable Materials",
    "IPMANSICS": "IP: Manufacturing (SIC)",
    "IPB51222S": "IP: Residential Utilities",
    "IPFUELS": "IP: Fuels",
    "NAPMPI": "ISM Manufacturing: Production Index",
    "CUMFNS": "Capacity Utilization: Manufacturing",

    # Labor Market
    "PAYEMS": "All Employees: Total nonfarm",
    "USPRIV": "All Employees: Total Private",
    "MANEMP": "All Employees: Manufacturing",
    "SRVPRD": "All Employees: Service-Providing Industries",
    "USCONS": "All Employees: Construction",
    "USGOOD": "All Employees: Goods-Producing Industries",
    "USDTLA": "All Employees: Trade, Transportation & Utilities",
    "USFIRE": "All Employees: Financial Activities",
    "USPBS": "All Employees: Professional & Business Services",
    "USINFO": "All Employees: Information Services",
    "USMINE": "All Employees: Mining and Logging",
    "USRTPR": "All Employees: Retail Trade",
    "USWTRADE": "All Employees: Wholesale Trade",
    "USTPU": "All Employees: Transportation and Warehousing",
    "USGOVT": "All Employees: Government",
    "AWHMAN": "Avg Weekly Hours: Manufacturing",
    "AWOTMAN": "Avg Weekly Hours: Overtime",
    "NAPMEI": "ISM Manufacturing: Employment Index",
    "UNRATE": "Civilian Unemployment Rate",
    "UEMPMEAN": "Avg Duration of Unemployment",
    "UEMP5TO14": "Civilians Unemployed - 5-14 Weeks",
    "UEMP15OV": "Civilians Unemployed - 15 Weeks & Over",
    "UEMP15T26": "Civilians Unemployed - 15-26 Weeks",
    "UEMP27OV": "Civilians Unemployed - 27 Weeks & Over",
    "CLAIMSx": "Initial Claims",
    "ICSA": "Initial Claims (weekly)",
    "PCEC1": "Personal Consumption Expenditures",
    "DSPI": "Disposable Personal Income",
    "M2SL": "M2 Money Stock",

    # Consumption & Orders
    "DPCERA3M086SBEA": "Real Personal Consumption Expenditures",
    "CMRMTSPLx": "Real Manu. and Trade Industries Sales",
    "RETAILx": "Retail and Food Services Sales",
    "NAPMSDI": "ISM Manufacturing: Inventories",
    "NAPM": "ISM Manufacturing: PMI",
    "ACOGNO": "New Orders for Consumer Goods",
    "AMDMNOx": "New Orders for Durable Goods",
    "ANDENOx": "New Orders for Nondefense Capital Goods",
    "AMDMUOx": "Unfilled Orders for Durable Goods",
    "BUSLOANS": "Commercial and Industrial Loans",
    "REALLN": "Real Estate Loans",
    "NONREVSL": "Total Nonrevolving Credit",
    "CONSPI": "Consumer Sentiment",

    # Interest Rates
    "FEDFUNDS": "Effective Federal Funds Rate",
    "CP3Mx": "3-Month AA Financial Commercial Paper Rate",
    "TB3MS": "3-Month Treasury Bill",
    "TB6MS": "6-Month Treasury Bill",
    "GS1": "1-Year Treasury",
    "GS5": "5-Year Treasury",
    "GS10": "10-Year Treasury",
    "AAA": "Moody's AAA Corporate Bond",
    "BAA": "Moody's BAA Corporate Bond",
    "COMPAPFFx": "CP - FF",
    "TB6SMFFM": "TB6MS - FF",
    "T1YFFM": "GS1 - FF",
    "T5YFFM": "GS5 - FF",
    "T10YFFM": "GS10 - FF",
    "AAAFFM": "AAA - FF",
    "BAAFFM": "BAA - FF",
    "TWEXAFEGSMTHx": "Trade Weighted U.S. Dollar Index",

    # Prices
    "WPSFD49504": "PPI: Finished Goods",
    "WPSFD49502": "PPI: Finished Consumer Goods",
    "WPSID61": "PPI: Intermediate Materials",
    "WPSID62": "PPI: Crude Materials",
    "CPIAUCSL": "CPI: All Items",
    "CPIAPPSL": "CPI: Apparel",
    "CPITRNSL": "CPI: Transportation",
    "CPIMEDSL": "CPI: Medical Care",
    "CUSR0000SAC": "CPI: Commodities",
    "CUSR0000SAD": "CPI: Durables",
    "CUSR0000SAS": "CPI: Services",
    "CPIULFSL": "CPI: All Items Less Food",
    "CUSR0000SA0L2": "CPI: All Items Less Shelter",
    "CUSR0000SA0L5": "CPI: All Items Less Medical Care",
    "PCEPI": "PCE Price Index",
    "DDURRG3M086SBEA": "PCE: Durable Goods",
    "DNDGRG3M086SBEA": "PCE: Nondurable Goods",
    "DSERRG3M086SBEA": "PCE: Services",

    # Stock Market
    "SP500": "S&P 500",
    "SP500DIVYIELD": "S&P 500 Dividend Yield",
    "SP500PE": "S&P 500 P/E Ratio",
    "VIXCLSx": "VIX Volatility Index",
}


class FredMDLoader:
    """
    Loader for FRED-MD macro database.

    Provides a standardized monthly macro panel for:
    - Factor extraction
    - Nowcasting
    - Business cycle analysis
    """

    FRED_MD_URL = "https://files.stlouisfed.org/research/api/fred-MD/monthly/current.csv"

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or Path("data/fred_md")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.data: Optional[pd.DataFrame] = None
        self.transformed_data: Optional[pd.DataFrame] = None

    def download(self, force_refresh: bool = False) -> pd.DataFrame:
        """Download FRED-MD data."""
        cache_file = self.cache_dir / "fred_md_current.csv"

        if cache_file.exists() and not force_refresh:
            logger.info("Loading FRED-MD from cache")
            self.data = pd.read_csv(cache_file, index_col=0, parse_dates=True)
            return self.data

        try:
            logger.info("Downloading FRED-MD from St. Louis Fed")
            self.data = pd.read_csv(self.FRED_MD_URL, index_col=0, parse_dates=True)
            self.data.to_csv(cache_file)
            return self.data
        except Exception as e:
            logger.error(f"Failed to download FRED-MD: {e}")
            if cache_file.exists():
                logger.info("Loading from cache due to download failure")
                self.data = pd.read_csv(cache_file, index_col=0, parse_dates=True)
                return self.data
            raise

    def get_available_series(self) -> List[str]:
        """Get list of available series in the current download."""
        if self.data is None:
            self.download()
        return list(self.data.columns)

    def apply_transformations(self) -> pd.DataFrame:
        """
        Apply McCracken-Ng transformations for stationarity.

        Transformation codes:
        1: No transformation (x)
        2: First difference (dx)
        3: Second difference (d2x)
        4: Log (log(x))
        5: Log first difference (dlog(x))
        6: Log second difference (d2log(x))
        7: Percent change (pct(x))
        """
        if self.data is None:
            self.download()

        # Standard transformation mapping (simplified)
        # In practice, would load from FRED-MD transformation file
        transform_map = {
            # Interest rates: first difference
            "FEDFUNDS": "diff",
            "TB3MS": "diff",
            "GS10": "diff",
            "BAA": "diff",
            "AAA": "diff",

            # Prices: log first difference (inflation rate)
            "CPIAUCSL": "log_diff",
            "PCEPI": "log_diff",
            "PPIACO": "log_diff",

            # Real activity: log first difference (growth rate)
            "INDPRO": "log_diff",
            "PAYEMS": "log_diff",
            "PCEC1": "log_diff",
            "RETAILx": "log_diff",

            # Financial: raw or percent change
            "SP500": "log_diff",
            "VIXCLSx": "raw",
        }

        transformed = self.data.copy()

        for col in transformed.columns:
            if col not in transform_map:
                continue

            t = transform_map[col]

            if t == "diff":
                transformed[col] = transformed[col].diff()
            elif t == "log_diff":
                transformed[col] = np.log(transformed[col]).diff()
            elif t == "log":
                transformed[col] = np.log(transformed[col])
            elif t == "pct":
                transformed[col] = transformed[col].pct_change()

        self.transformed_data = transformed
        return transformed

    def get_balanced_panel(
        self,
        min_observations: int = 60,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        Get balanced panel for factor extraction.

        Only includes series with sufficient data.
        """
        if self.transformed_data is None:
            self.apply_transformations()

        data = self.transformed_data.copy()

        # Date filtering
        if start_date:
            data = data[data.index >= start_date]
        if end_date:
            data = data[data.index <= end_date]

        # Drop series with too many missing values
        min_count = len(data) * 0.8  # At least 80% data
        data = data.dropna(axis=1, thresh=min_count)

        # Drop rows with any missing values (balanced panel)
        data = data.dropna()

        logger.info(f"Balanced panel: {len(data)} observations, {len(data.columns)} series")

        return data

    def extract_macro_factors(
        self,
        n_factors: int = 4,
        method: str = "pca"
    ) -> Tuple[pd.DataFrame, Dict]:
        """
        Extract common macro factors using PCA.

        Returns:
            factors: DataFrame with factor time series
            loadings: Dict mapping series to factor loadings
        """
        from sklearn.decomposition import PCA
        from sklearn.preprocessing import StandardScaler

        data = self.get_balanced_panel()

        if len(data) < 24:
            raise ValueError("Insufficient data for factor extraction")

        # Standardize
        scaler = StandardScaler()
        standardized = scaler.fit_transform(data)

        # PCA
        pca = PCA(n_components=n_factors)
        factors = pca.fit_transform(standardized)

        # Create factor DataFrame
        factor_df = pd.DataFrame(
            factors,
            index=data.index,
            columns=[f"Macro_Factor_{i+1}" for i in range(n_factors)]
        )

        # Interpret factors based on loadings
        loadings = pd.DataFrame(
            pca.components_.T,
            columns=[f"Factor_{i+1}" for i in range(n_factors)],
            index=data.columns
        )

        # Name factors based on top loadings
        factor_names = {}
        for i in range(n_factors):
            top_loadings = loadings.iloc[:, i].abs().nlargest(5)
            factor_names[f"Factor_{i+1}"] = {
                "name": self._interpret_factor(top_loadings),
                "explained_var": pca.explained_variance_ratio_[i],
                "top_series": top_loadings.to_dict(),
            }

        return factor_df, factor_names

    def _interpret_factor(self, top_loadings: pd.Series) -> str:
        """Interpret factor based on top loading series."""
        series_names = list(top_loadings.index)

        # Check for patterns
        labor_series = [s for s in series_names if any(x in s for x in ["EMP", "UNRATE", "CLAIMS"])]
        price_series = [s for s in series_names if any(x in s for x in ["CPI", "PPI", "PCE"])]
        rate_series = [s for s in series_names if any(x in s for x in ["FED", "TB", "GS"])]
        activity_series = [s for s in series_names if any(x in s for x in ["INDPRO", "PAYEMS", "RETAIL"])]

        if labor_series:
            return "Labor_Market"
        elif price_series:
            return "Inflation"
        elif rate_series:
            return "Interest_Rates"
        elif activity_series:
            return "Real_Activity"
        else:
            return "Mixed"


def get_fred_md_summary() -> pd.DataFrame:
    """Get summary of FRED-MD series and their categories."""
    return pd.DataFrame([
        {"series_id": k, "description": v}
        for k, v in FRED_MD_SERIES.items()
    ])
