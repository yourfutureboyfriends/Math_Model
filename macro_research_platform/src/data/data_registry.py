"""
Data Registry for Macro Research Platform.

Tracks all 80+ data sources with metadata, vintage, and provenance.
Provides data freshness indicators for every section.
"""

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class DataFrequency(Enum):
    REALTIME = "realtime"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"


class DataStatus(Enum):
    FRESH = "fresh"
    ACCEPTABLE = "acceptable"
    STALE = "stale"
    SEVERELY_STALE = "severely_stale"


@dataclass
class DataSeriesRegistry:
    """Complete metadata for a data series."""
    series_id: str
    source: str  # fred, yfinance, world_bank, cftc, etc.
    series_code: str  # Actual API identifier
    category: str  # equity, rates, macro, fx, commodity, positioning
    subcategory: str  # us_equity, g10_rates, em_macro, etc.
    frequency: DataFrequency
    provider: str  # BEA, BLS, Federal Reserve, Yahoo Finance, etc.
    description: str
    units: str
    typical_lag_days: int
    staleness_threshold_days: int
    last_observation_date: Optional[datetime] = None
    last_fetched_date: Optional[datetime] = None
    next_release_date: Optional[datetime] = None
    is_sample_data: bool = False
    reliability_score: float = 0.9
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with formatted dates."""
        d = asdict(self)
        # Format datetime fields
        for key in ['last_observation_date', 'last_fetched_date', 'next_release_date']:
            if d[key]:
                d[key] = d[key].isoformat() if isinstance(d[key], datetime) else str(d[key])
        d['frequency'] = self.frequency.value
        return d


class DataRegistry:
    """
    Central registry for all data series used in the platform.

    Tracks 80+ series across:
    - FRED economic data
    - yFinance market data
    - World Bank macro data
    - CFTC positioning data
    - Other public sources
    """

    def __init__(self):
        self._registry: Dict[str, DataSeriesRegistry] = {}
        self._init_fred_series()
        self._init_yfinance_series()
        self._init_world_bank_series()
        self._init_cftc_series()
        self._init_other_series()

    def _add(self, series: DataSeriesRegistry):
        """Add a series to the registry."""
        self._registry[series.series_id] = series

    def _init_fred_series(self):
        """Initialize FRED economic data series."""
        # US GDP and Growth
        self._add(DataSeriesRegistry(
            series_id="FRED_US_GDP",
            source="fred",
            series_code="GDPC1",
            category="macro",
            subcategory="us_growth",
            frequency=DataFrequency.QUARTERLY,
            provider="BEA via FRED",
            description="Real Gross Domestic Product",
            units="Billions of Chained 2017 Dollars",
            typical_lag_days=30,
            staleness_threshold_days=90,
        ))

        self._add(DataSeriesRegistry(
            series_id="FRED_US_GDP_YOY",
            source="fred",
            series_code="A191RL1Q225SBEA",
            category="macro",
            subcategory="us_growth",
            frequency=DataFrequency.QUARTERLY,
            provider="BEA via FRED",
            description="Real GDP YoY Growth Rate",
            units="Percent",
            typical_lag_days=30,
            staleness_threshold_days=90,
        ))

        # Inflation
        self._add(DataSeriesRegistry(
            series_id="FRED_US_CPI",
            source="fred",
            series_code="CPIAUCSL",
            category="macro",
            subcategory="us_inflation",
            frequency=DataFrequency.MONTHLY,
            provider="BLS via FRED",
            description="Consumer Price Index for All Urban Consumers",
            units="Index 1982-84=100",
            typical_lag_days=15,
            staleness_threshold_days=45,
        ))

        self._add(DataSeriesRegistry(
            series_id="FRED_US_CORE_CPI",
            source="fred",
            series_code="CPILFESL",
            category="macro",
            subcategory="us_inflation",
            frequency=DataFrequency.MONTHLY,
            provider="BLS via FRED",
            description="Core CPI (excluding food and energy)",
            units="Index 1982-84=100",
            typical_lag_days=15,
            staleness_threshold_days=45,
        ))

        self._add(DataSeriesRegistry(
            series_id="FRED_US_PCE",
            source="fred",
            series_code="PCEPI",
            category="macro",
            subcategory="us_inflation",
            frequency=DataFrequency.MONTHLY,
            provider="BEA via FRED",
            description="Personal Consumption Expenditures Price Index",
            units="Index 2012=100",
            typical_lag_days=30,
            staleness_threshold_days=45,
        ))

        # Employment
        self._add(DataSeriesRegistry(
            series_id="FRED_US_UNEMPLOYMENT",
            source="fred",
            series_code="UNRATE",
            category="macro",
            subcategory="us_labor",
            frequency=DataFrequency.MONTHLY,
            provider="BLS via FRED",
            description="Unemployment Rate",
            units="Percent",
            typical_lag_days=15,
            staleness_threshold_days=45,
        ))

        self._add(DataSeriesRegistry(
            series_id="FRED_US_PAYROLLS",
            source="fred",
            series_code="PAYEMS",
            category="macro",
            subcategory="us_labor",
            frequency=DataFrequency.MONTHLY,
            provider="BLS via FRED",
            description="Total Nonfarm Payrolls",
            units="Thousands of Persons",
            typical_lag_days=15,
            staleness_threshold_days=45,
        ))

        # Policy Rates
        self._add(DataSeriesRegistry(
            series_id="FRED_FEDFUNDS",
            source="fred",
            series_code="FEDFUNDS",
            category="rates",
            subcategory="us_policy",
            frequency=DataFrequency.DAILY,
            provider="Federal Reserve",
            description="Federal Funds Effective Rate",
            units="Percent",
            typical_lag_days=1,
            staleness_threshold_days=7,
        ))

        # US Yield Curve
        tenors = [
            ("1M", "DGS1MO"), ("3M", "DGS3MO"), ("6M", "DGS6MO"),
            ("1Y", "DGS1"), ("2Y", "DGS2"), ("3Y", "DGS3"),
            ("5Y", "DGS5"), ("7Y", "DGS7"), ("10Y", "DGS10"),
            ("20Y", "DGS20"), ("30Y", "DGS30"),
        ]
        for tenor, code in tenors:
            self._add(DataSeriesRegistry(
                series_id=f"FRED_US_TREASURY_{tenor}",
                source="fred",
                series_code=code,
                category="rates",
                subcategory="us_treasury",
                frequency=DataFrequency.DAILY,
                provider="Federal Reserve",
                description=f"Market Yield on U.S. Treasury Securities at {tenor} Constant Maturity",
                units="Percent",
                typical_lag_days=1,
                staleness_threshold_days=7,
            ))

        # TIPS Real Yields
        self._add(DataSeriesRegistry(
            series_id="FRED_US_TIPS_5Y",
            source="fred",
            series_code="DFII5",
            category="rates",
            subcategory="us_tips",
            frequency=DataFrequency.DAILY,
            provider="Federal Reserve",
            description="5-Year TIPS Yield",
            units="Percent",
            typical_lag_days=1,
            staleness_threshold_days=7,
        ))

        self._add(DataSeriesRegistry(
            series_id="FRED_US_TIPS_10Y",
            source="fred",
            series_code="DFII10",
            category="rates",
            subcategory="us_tips",
            frequency=DataFrequency.DAILY,
            provider="Federal Reserve",
            description="10-Year TIPS Yield",
            units="Percent",
            typical_lag_days=1,
            staleness_threshold_days=7,
        ))

        # Credit Spreads
        self._add(DataSeriesRegistry(
            series_id="FRED_HY_OAS",
            source="fred",
            series_code="BAMLH0A0HYM2",
            category="credit",
            subcategory="us_credit",
            frequency=DataFrequency.DAILY,
            provider="Bloomberg via FRED",
            description="High Yield OAS",
            units="Percent",
            typical_lag_days=1,
            staleness_threshold_days=5,
        ))

        self._add(DataSeriesRegistry(
            series_id="FRED_IG_OAS",
            source="fred",
            series_code="BAMLC0A0CM",
            category="credit",
            subcategory="us_credit",
            frequency=DataFrequency.DAILY,
            provider="Bloomberg via FRED",
            description="Investment Grade OAS",
            units="Percent",
            typical_lag_days=1,
            staleness_threshold_days=5,
        ))

        self._add(DataSeriesRegistry(
            series_id="FRED_TED_SPREAD",
            source="fred",
            series_code="TEDRATE",
            category="credit",
            subcategory="us_funding",
            frequency=DataFrequency.DAILY,
            provider="Federal Reserve",
            description="TED Spread (3M LIBOR - 3M T-bill)",
            units="Percent",
            typical_lag_days=1,
            staleness_threshold_days=7,
        ))

        # Other G10 Rates
        self._add(DataSeriesRegistry(
            series_id="FRED_UK_10Y",
            source="fred",
            series_code="IRLTLT01GBM156N",
            category="rates",
            subcategory="gilt",
            frequency=DataFrequency.MONTHLY,
            provider="Bank of England via FRED",
            description="UK 10-Year Government Bond Yield",
            units="Percent",
            typical_lag_days=30,
            staleness_threshold_days=45,
        ))

        self._add(DataSeriesRegistry(
            series_id="FRED_JAPAN_10Y",
            source="fred",
            series_code="IRLTLT01JPM156N",
            category="rates",
            subcategory="jgb",
            frequency=DataFrequency.MONTHLY,
            provider="MOF Japan via FRED",
            description="Japan 10-Year Government Bond Yield",
            units="Percent",
            typical_lag_days=30,
            staleness_threshold_days=45,
        ))

        self._add(DataSeriesRegistry(
            series_id="FRED_GERMANY_10Y",
            source="fred",
            series_code="IRLTLT01DEM156N",
            category="rates",
            subcategory="bund",
            frequency=DataFrequency.MONTHLY,
            provider="ECB via FRED",
            description="Germany 10-Year Government Bond Yield",
            units="Percent",
            typical_lag_days=30,
            staleness_threshold_days=45,
        ))

        self._add(DataSeriesRegistry(
            series_id="FRED_CANADA_10Y",
            source="fred",
            series_code="IRLTLT01CAM156N",
            category="rates",
            subcategory="canada_govt",
            frequency=DataFrequency.MONTHLY,
            provider="Bank of Canada via FRED",
            description="Canada 10-Year Government Bond Yield",
            units="Percent",
            typical_lag_days=30,
            staleness_threshold_days=45,
        ))

        self._add(DataSeriesRegistry(
            series_id="FRED_AUSTRALIA_10Y",
            source="fred",
            series_code="IRLTLT01AUM156N",
            category="rates",
            subcategory="australia_govt",
            frequency=DataFrequency.MONTHLY,
            provider="RBA via FRED",
            description="Australia 10-Year Government Bond Yield",
            units="Percent",
            typical_lag_days=30,
            staleness_threshold_days=45,
        ))

        # Euro Area
        self._add(DataSeriesRegistry(
            series_id="FRED_ECB_RATE",
            source="fred",
            series_code="ECBDFR",
            category="rates",
            subcategory="ecb_policy",
            frequency=DataFrequency.DAILY,
            provider="ECB via FRED",
            description="ECB Deposit Facility Rate",
            units="Percent",
            typical_lag_days=1,
            staleness_threshold_days=7,
        ))

        self._add(DataSeriesRegistry(
            series_id="FRED_EURO_GDP",
            source="fred",
            series_code="CLVMNACSCAB1GQEA19",
            category="macro",
            subcategory="euro_growth",
            frequency=DataFrequency.QUARTERLY,
            provider="Eurostat via FRED",
            description="Euro Area Real GDP",
            units="Euros",
            typical_lag_days=60,
            staleness_threshold_days=90,
        ))

        self._add(DataSeriesRegistry(
            series_id="FRED_EURO_CPI",
            source="fred",
            series_code="CP0000EZ19M086NEST",
            category="macro",
            subcategory="euro_inflation",
            frequency=DataFrequency.MONTHLY,
            provider="Eurostat via FRED",
            description="Euro Area HICP",
            units="Index",
            typical_lag_days=30,
            staleness_threshold_days=45,
        ))

        # UK Data
        self._add(DataSeriesRegistry(
            series_id="FRED_UK_POLICY",
            source="fred",
            series_code="BOERUKM156N",
            category="rates",
            subcategory="boe_policy",
            frequency=DataFrequency.MONTHLY,
            provider="BoE via FRED",
            description="Bank of England Official Bank Rate",
            units="Percent",
            typical_lag_days=1,
            staleness_threshold_days=7,
        ))

        # Japan Data
        self._add(DataSeriesRegistry(
            series_id="FRED_JAPAN_POLICY",
            source="fred",
            series_code="IRSTCI01JPM156N",
            category="rates",
            subcategory="boj_policy",
            frequency=DataFrequency.MONTHLY,
            provider="BoJ via FRED",
            description="Japan Policy Rate",
            units="Percent",
            typical_lag_days=1,
            staleness_threshold_days=7,
        ))

        # Financial Conditions
        self._add(DataSeriesRegistry(
            series_id="FRED_NFCI",
            source="fred",
            series_code="NFCI",
            category="macro",
            subcategory="financial_conditions",
            frequency=DataFrequency.WEEKLY,
            provider="Chicago Fed via FRED",
            description="National Financial Conditions Index",
            units="Index",
            typical_lag_days=7,
            staleness_threshold_days=14,
        ))

        # Recession Indicators
        self._add(DataSeriesRegistry(
            series_id="FRED_T10Y2Y",
            source="fred",
            series_code="T10Y2Y",
            category="macro",
            subcategory="yield_curve",
            frequency=DataFrequency.DAILY,
            provider="Federal Reserve",
            description="10-Year minus 2-Year Treasury Spread",
            units="Percent",
            typical_lag_days=1,
            staleness_threshold_days=7,
        ))

        self._add(DataSeriesRegistry(
            series_id="FRED_T10Y3M",
            source="fred",
            series_code="T10Y3M",
            category="macro",
            subcategory="yield_curve",
            frequency=DataFrequency.DAILY,
            provider="Federal Reserve",
            description="10-Year minus 3-Month Treasury Spread",
            units="Percent",
            typical_lag_days=1,
            staleness_threshold_days=7,
        ))

        # Money Market
        self._add(DataSeriesRegistry(
            series_id="FRED_MMF_ASSETS",
            source="fred",
            series_code="WRMFNS",
            category="macro",
            subcategory="money_market",
            frequency=DataFrequency.WEEKLY,
            provider="ICI via FRED",
            description="Money Market Fund Assets",
            units="Billions USD",
            typical_lag_days=7,
            staleness_threshold_days=14,
        ))

    def _init_yfinance_series(self):
        """Initialize yFinance market data series."""
        # US Equity Indices
        us_indices = [
            ("SP500", "^GSPC", "S&P 500"),
            ("NASDAQ", "^NDX", "Nasdaq 100"),
            ("DOW", "^DJI", "Dow Jones Industrial Average"),
            ("RUSSELL2000", "^RUT", "Russell 2000"),
            ("VIX", "^VIX", "CBOE Volatility Index"),
        ]
        for name, code, desc in us_indices:
            self._add(DataSeriesRegistry(
                series_id=f"YF_{name}",
                source="yfinance",
                series_code=code,
                category="equity",
                subcategory="us_index",
                frequency=DataFrequency.DAILY,
                provider="Yahoo Finance",
                description=desc,
                units="Index Points",
                typical_lag_days=1,
                staleness_threshold_days=2,
            ))

        # International Equity Indices
        intl_indices = [
            ("FTSE", "^FTSE", "UK", "FTSE 100"),
            ("DAX", "^GDAXI", "DE", "DAX"),
            ("CAC", "^FCHI", "FR", "CAC 40"),
            ("EUROSTOXX50", "^STOXX50E", "EU", "Euro Stoxx 50"),
            ("NIKKEI", "^N225", "JP", "Nikkei 225"),
            ("HANG_SENG", "^HSI", "HK", "Hang Seng Index"),
            ("ASX", "^AXJO", "AU", "ASX 200"),
            ("TSX", "^GSPTSE", "CA", "TSX Composite"),
            ("SMI", "^SMI", "CH", "Swiss Market Index"),
        ]
        for name, code, country, desc in intl_indices:
            self._add(DataSeriesRegistry(
                series_id=f"YF_{name}",
                source="yfinance",
                series_code=code,
                category="equity",
                subcategory=f"{country.lower()}_index",
                frequency=DataFrequency.DAILY,
                provider="Yahoo Finance",
                description=desc,
                units="Index Points",
                typical_lag_days=1,
                staleness_threshold_days=2,
            ))

        # EM Equity Indices
        em_indices = [
            ("EEM", "EEM", "Broad EM ETF"),
            ("SENSEX", "^BSESN", "India Sensex"),
            ("BOVESPA", "^BVSP", "Brazil Bovespa"),
            ("IPC", "^MXX", "Mexico IPC"),
            ("SHANGHAI", "000001.SS", "Shanghai Composite"),
            ("KOSPI", "^KS11", "South Korea KOSPI"),
            ("TAIEX", "^TWII", "Taiwan TAIEX"),
        ]
        for name, code, desc in em_indices:
            self._add(DataSeriesRegistry(
                series_id=f"YF_{name}",
                source="yfinance",
                series_code=code,
                category="equity",
                subcategory="em_index",
                frequency=DataFrequency.DAILY,
                provider="Yahoo Finance",
                description=desc,
                units="Index Points",
                typical_lag_days=1,
                staleness_threshold_days=2,
            ))

        # VIX Complex
        vol_indices = [
            ("VXN", "^VXN", "Nasdaq Volatility"),
            ("RVX", "^RVX", "Russell 2000 Volatility"),
            ("OVX", "^OVX", "Crude Oil Volatility"),
            ("GVZ", "^GVZ", "Gold Volatility"),
            ("EVZ", "^EVZ", "Euro Currency Volatility"),
        ]
        for name, code, desc in vol_indices:
            self._add(DataSeriesRegistry(
                series_id=f"YF_{name}",
                source="yfinance",
                series_code=code,
                category="equity",
                subcategory="volatility",
                frequency=DataFrequency.DAILY,
                provider="Yahoo Finance",
                description=desc,
                units="Index Points",
                typical_lag_days=1,
                staleness_threshold_days=2,
            ))

        # FX Pairs (G10)
        fx_pairs = [
            "EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCHF=X",
            "AUDUSD=X", "NZDUSD=X", "USDCAD=X", "USDSEK=X",
            "USDNOK=X", "EURGBP=X", "EURJPY=X", "GBPJPY=X",
        ]
        for pair in fx_pairs:
            clean = pair.replace("=X", "").replace("/", "")
            self._add(DataSeriesRegistry(
                series_id=f"YF_FX_{clean}",
                source="yfinance",
                series_code=pair,
                category="fx",
                subcategory="g10",
                frequency=DataFrequency.DAILY,
                provider="Yahoo Finance",
                description=f"{pair.replace('=X', '')} Exchange Rate",
                units="Currency Units",
                typical_lag_days=1,
                staleness_threshold_days=2,
            ))

        # EM FX
        em_fx = [
            ("CNY", "USDCNY=X", "China Yuan"),
            ("BRL", "USDBRL=X", "Brazil Real"),
            ("INR", "USDINR=X", "India Rupee"),
            ("MXN", "USDMXN=X", "Mexico Peso"),
            ("KRW", "USDKRW=X", "Korea Won"),
            ("TRY", "USDTRY=X", "Turkey Lira"),
            ("ZAR", "USDZAR=X", "South Africa Rand"),
            ("SGD", "USDSGD=X", "Singapore Dollar"),
        ]
        for code, pair, desc in em_fx:
            self._add(DataSeriesRegistry(
                series_id=f"YF_FX_{code}",
                source="yfinance",
                series_code=pair,
                category="fx",
                subcategory="em",
                frequency=DataFrequency.DAILY,
                provider="Yahoo Finance",
                description=desc,
                units="USD per Currency",
                typical_lag_days=1,
                staleness_threshold_days=2,
            ))

        # Commodities
        commodities = [
            ("WTI", "CL=F", "WTI Crude Oil"),
            ("BRENT", "BZ=F", "Brent Crude Oil"),
            ("NATGAS", "NG=F", "Natural Gas"),
            ("GOLD", "GC=F", "Gold"),
            ("SILVER", "SI=F", "Silver"),
            ("COPPER", "HG=F", "Copper"),
            ("PLATINUM", "PL=F", "Platinum"),
            ("PALLADIUM", "PA=F", "Palladium"),
            ("ALUMINUM", "ALI=F", "Aluminum"),
            ("CORN", "ZC=F", "Corn"),
            ("WHEAT", "ZW=F", "Wheat"),
            ("SOYBEANS", "ZS=F", "Soybeans"),
            ("COCOA", "CC=F", "Cocoa"),
            ("COFFEE", "KC=F", "Coffee"),
            ("COTTON", "CT=F", "Cotton"),
            ("SUGAR", "SB=F", "Sugar"),
        ]
        for name, code, desc in commodities:
            self._add(DataSeriesRegistry(
                series_id=f"YF_{name}",
                source="yfinance",
                series_code=code,
                category="commodity",
                subcategory="futures",
                frequency=DataFrequency.DAILY,
                provider="Yahoo Finance",
                description=desc,
                units="USD per Unit",
                typical_lag_days=1,
                staleness_threshold_days=2,
            ))

        # Commodity ETFs/Indices
        commodity_etfs = [
            ("DBC", "DBC", "Commodity Index ETF"),
            ("PDBC", "PDBC", "Active Commodity ETF"),
            ("CPER", "CPER", "Copper ETF"),
            ("GLD_ETF", "GLD", "Gold ETF"),
            ("DXY", "DX-Y.NYB", "US Dollar Index"),
        ]
        for name, code, desc in commodity_etfs:
            self._add(DataSeriesRegistry(
                series_id=f"YF_{name}",
                source="yfinance",
                series_code=code,
                category="commodity",
                subcategory="etf",
                frequency=DataFrequency.DAILY,
                provider="Yahoo Finance",
                description=desc,
                units="USD per Share",
                typical_lag_days=1,
                staleness_threshold_days=2,
            ))

        # Portfolio ETFs
        portfolio_etfs = [
            ("SPY", "SPY", "S&P 500 ETF"),
            ("TLT", "TLT", "20+ Year Treasury ETF"),
            ("HYG", "HYG", "High Yield Bond ETF"),
            ("EEM_ETF", "EEM", "Emerging Markets ETF"),
            ("TIP", "TIP", "TIPS ETF"),
            ("VNQ", "VNQ", "Real Estate ETF"),
            ("USO", "USO", "Oil ETF"),
            ("UUP", "UUP", "US Dollar Bull ETF"),
            ("IWM", "IWM", "Russell 2000 ETF"),
            ("QQQ", "QQQ", "Nasdaq 100 ETF"),
        ]
        for name, code, desc in portfolio_etfs:
            self._add(DataSeriesRegistry(
                series_id=f"YF_{name}",
                source="yfinance",
                series_code=code,
                category="equity",
                subcategory="etf",
                frequency=DataFrequency.DAILY,
                provider="Yahoo Finance",
                description=desc,
                units="USD per Share",
                typical_lag_days=1,
                staleness_threshold_days=2,
            ))

    def _init_world_bank_series(self):
        """Initialize World Bank macro data series."""
        # World Bank macro indicators by country
        wb_countries = [
            ("US", "USA", "United States"),
            ("UK", "GBR", "United Kingdom"),
            ("DE", "DEU", "Germany"),
            ("FR", "FRA", "France"),
            ("JP", "JPN", "Japan"),
            ("CN", "CHN", "China"),
            ("IN", "IND", "India"),
            ("BR", "BRA", "Brazil"),
            ("CA", "CAN", "Canada"),
            ("AU", "AUS", "Australia"),
            ("IT", "ITA", "Italy"),
            ("ES", "ESP", "Spain"),
            ("MX", "MEX", "Mexico"),
            ("KR", "KOR", "South Korea"),
        ]

        wb_indicators = [
            ("GDP_GROWTH", "NY.GDP.MKTP.KD.ZG", "GDP Growth Rate", "Percent"),
            ("INFLATION", "FP.CPI.TOTL.ZG", "Inflation Rate", "Percent"),
            ("UNEMPLOYMENT", "SL.UEM.TOTL.ZS", "Unemployment Rate", "Percent"),
            ("DEBT_GDP", "GC.DOD.TOTL.GD.ZS", "Government Debt to GDP", "Percent"),
            ("CA_GDP", "BN.CAB.XOKA.GD.ZS", "Current Account to GDP", "Percent"),
        ]

        for code, wb_code, country_name in wb_countries:
            for ind_name, ind_code, ind_desc, units in wb_indicators:
                self._add(DataSeriesRegistry(
                    series_id=f"WB_{code}_{ind_name}",
                    source="world_bank",
                    series_code=f"{ind_code}",
                    category="macro",
                    subcategory=f"{code.lower()}_macro",
                    frequency=DataFrequency.ANNUAL,
                    provider="World Bank",
                    description=f"{country_name} - {ind_desc}",
                    units=units,
                    typical_lag_days=90,
                    staleness_threshold_days=365,
                ))

    def _init_cftc_series(self):
        """Initialize CFTC COT data series."""
        cot_contracts = [
            ("SP500_COT", "13874A", "S&P 500 E-mini Futures", "equity"),
            ("NASDAQ_COT", "20974P", "Nasdaq 100 E-mini Futures", "equity"),
            ("USD_COT", "098662", "US Dollar Index", "fx"),
            ("EUR_COT", "095741", "Euro FX", "fx"),
            ("JPY_COT", "096742", "Japanese Yen", "fx"),
            ("GBP_COT", "097741", "British Pound", "fx"),
            ("GOLD_COT", "088691", "Gold Futures", "commodity"),
            ("WTI_COT", "067651", "WTI Crude Oil Futures", "commodity"),
            ("TENYEAR_COT", "020601", "10-Year Note Futures", "rates"),
            ("THIRTYYEAR_COT", "020604", "30-Year Bond Futures", "rates"),
        ]

        for name, code, desc, cat in cot_contracts:
            self._add(DataSeriesRegistry(
                series_id=f"CFTC_{name}",
                source="cftc",
                series_code=code,
                category=cat,
                subcategory="positioning",
                frequency=DataFrequency.WEEKLY,
                provider="CFTC",
                description=desc,
                units="Contracts",
                typical_lag_days=3,
                staleness_threshold_days=10,
                notes="Released every Friday at 15:30 ET",
            ))

    def _init_other_series(self):
        """Initialize other data sources."""
        # Breakeven Inflation
        self._add(DataSeriesRegistry(
            series_id="FRED_BREAKEVEN_5Y5Y",
            source="fred",
            series_code="T5YIFRM",
            category="macro",
            subcategory="inflation_expectations",
            frequency=DataFrequency.DAILY,
            provider="Federal Reserve",
            description="5-Year, 5-Year Forward Inflation Expectation",
            units="Percent",
            typical_lag_days=1,
            staleness_threshold_days=7,
        ))

        self._add(DataSeriesRegistry(
            series_id="FRED_BREAKEVEN_10Y",
            source="fred",
            series_code="T10YIE",
            category="macro",
            subcategory="inflation_expectations",
            frequency=DataFrequency.DAILY,
            provider="Federal Reserve",
            description="10-Year Breakeven Inflation Rate",
            units="Percent",
            typical_lag_days=1,
            staleness_threshold_days=7,
        ))

    def get_series(self, series_id: str) -> Optional[DataSeriesRegistry]:
        """Get a single series by ID."""
        return self._registry.get(series_id)

    def get_series_by_source(self, source: str) -> List[DataSeriesRegistry]:
        """Get all series from a specific source."""
        return [s for s in self._registry.values() if s.source == source]

    def get_series_by_category(self, category: str) -> List[DataSeriesRegistry]:
        """Get all series in a category."""
        return [s for s in self._registry.values() if s.category == category]

    def get_all_series(self) -> List[DataSeriesRegistry]:
        """Get all registered series."""
        return list(self._registry.values())

    def update_freshness(self, series_id: str, observation_date: Optional[datetime], fetched_date: Optional[datetime]):
        """Update the freshness timestamps for a series."""
        if series_id in self._registry:
            self._registry[series_id].last_observation_date = observation_date
            self._registry[series_id].last_fetched_date = fetched_date

    def calculate_freshness_status(self, series_id: str) -> Dict[str, Any]:
        """Calculate freshness status for a series."""
        series = self._registry.get(series_id)
        if not series:
            return {"status": "unknown", "message": "Series not found"}

        if series.is_sample_data:
            return {
                "status": "sample",
                "message": "Sample data",
                "icon": "",
                "color": "text-text-tertiary",
            }

        if not series.last_observation_date:
            return {
                "status": "missing",
                "message": "Data unavailable",
                "icon": "⚠",
                "color": "text-red",
            }

        days_since = (datetime.now() - series.last_observation_date).days

        if days_since > series.staleness_threshold_days * 2:
            return {
                "status": "severely_stale",
                "message": f"Data {days_since} days old",
                "icon": "⚠",
                "color": "text-red",
                "tooltip": f"Series typically updates every {series.typical_lag_days} days",
            }
        elif days_since > series.staleness_threshold_days:
            return {
                "status": "stale",
                "message": f"Data {days_since} days old",
                "icon": "◐",
                "color": "text-amber",
            }
        elif days_since > series.typical_lag_days:
            return {
                "status": "acceptable",
                "message": f"Updated {days_since}d ago",
                "icon": "●",
                "color": "text-text-secondary",
            }
        else:
            return {
                "status": "fresh",
                "message": "Live data",
                "icon": "●",
                "color": "text-green",
            }

    def to_dict(self) -> Dict[str, Any]:
        """Export full registry as dictionary."""
        return {
            "total_series": len(self._registry),
            "by_source": {
                source: len(self.get_series_by_source(source))
                for source in ["fred", "yfinance", "world_bank", "cftc"]
            },
            "by_category": {
                cat: len(self.get_series_by_category(cat))
                for cat in ["equity", "rates", "macro", "credit", "fx", "commodity"]
            },
            "series": [s.to_dict() for s in self._registry.values()],
        }


# Singleton instance
_registry_instance: Optional[DataRegistry] = None


def get_data_registry() -> DataRegistry:
    """Get or create data registry singleton."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = DataRegistry()
    return _registry_instance
