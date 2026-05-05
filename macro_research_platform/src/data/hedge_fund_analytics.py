"""
Hedge Fund Risk Analytics for Macro Research Platform.

Section F: Fund-Grade Risk Analytics
- Drawdown monitor with severity classification
- Risk-adjusted returns (Sharpe, Sortino, Calmar, Information Ratio)
- Correlation matrix with diversification scoring
- Position sizing engine
- Stress testing (5 scenarios)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class DrawdownMetrics:
    """Drawdown analysis metrics."""
    current_drawdown: Optional[float] = None
    current_severity: str = "MINOR"
    max_drawdown_12m: Optional[float] = None
    days_in_drawdown: int = 0
    expected_recovery_days: Optional[int] = None
    worst_component: Optional[str] = None
    recovery_time_estimate: str = ""


@dataclass
class RiskAdjustedReturns:
    """Risk-adjusted performance metrics."""
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    calmar_ratio: Optional[float] = None
    information_ratio: Optional[float] = None
    beta_spy: Optional[float] = None
    var_95: Optional[float] = None
    cvar_95: Optional[float] = None
    var_99: Optional[float] = None
    annual_return: Optional[float] = None
    annual_volatility: Optional[float] = None


@dataclass
class CorrelationPair:
    """Correlation data for an asset pair."""
    asset1: str
    asset2: str
    corr_3m: Optional[float] = None
    corr_12m: Optional[float] = None
    change: Optional[float] = None
    alert: Optional[str] = None


@dataclass
class StressScenario:
    """Stress test scenario results."""
    name: str
    description: str
    portfolio_pnl_pct: Optional[float] = None
    portfolio_pnl_usd: Optional[float] = None
    worst_component: Optional[str] = None
    best_component: Optional[str] = None
    status: str = "Historical"


@dataclass
class PositionSizing:
    """Position sizing recommendation."""
    asset: str
    signal: str
    conviction: str
    current_price: Optional[float] = None
    dollar_amount: Optional[float] = None
    percent_aum: Optional[float] = None
    shares: Optional[int] = None
    daily_var_95: Optional[float] = None
    rationale: str = ""


class HedgeFundAnalytics:
    """
    Hedge fund-grade risk analytics engine.

    Sources:
    - Historical returns from yfinance
    - Computed metrics for risk analysis
    """

    # Risk parity portfolio weights (Phase 2)
    PORTFOLIO_WEIGHTS = {
        "SPY": 0.30,   # US Equity
        "TLT": 0.25,   # Long Treasury
        "GLD": 0.15,   # Gold
        "HYG": 0.10,   # High Yield
        "EEM": 0.10,   # EM Equity
        "TIP": 0.05,   # TIPS
        "VNQ": 0.05,   # Real Estate
    }

    # Asset shock multipliers for stress tests
    STRESS_SCENARIOS = {
        "2008_GFC": {
            "name": "2008 GFC",
            "description": "Global Financial Crisis scenario",
            "SPY": -0.45,
            "TLT": 0.20,
            "GLD": 0.05,
            "HYG": -0.35,
            "EEM": -0.50,
            "TIP": 0.05,
            "VNQ": -0.55,
            "status": "Historical",
        },
        "2020_COVID": {
            "name": "2020 COVID Crash",
            "description": "March 2020 pandemic crash",
            "SPY": -0.35,
            "TLT": 0.15,
            "GLD": 0.10,
            "HYG": -0.25,
            "EEM": -0.30,
            "TIP": 0.05,
            "VNQ": -0.30,
            "status": "Historical",
        },
        "2022_STAGFLATION": {
            "name": "2022 Stagflation",
            "description": "Inflation shock, bonds and equities both down",
            "SPY": -0.20,
            "TLT": -0.20,
            "GLD": 0.00,
            "HYG": -0.15,
            "EEM": -0.15,
            "TIP": -0.05,
            "VNQ": -0.10,
            "status": "Recent (current analog)",
        },
        "EM_CRISIS": {
            "name": "EM Crisis (1997/2013)",
            "description": "Emerging market crisis with USD rally",
            "SPY": -0.10,
            "TLT": 0.05,
            "GLD": 0.00,
            "HYG": -0.20,
            "EEM": -0.35,
            "TIP": 0.00,
            "VNQ": -0.05,
            "status": "Historical",
        },
        "1970s_STAGFLATION": {
            "name": "1970s Stagflation",
            "description": "Prolonged inflation period",
            "SPY": -0.30,
            "TLT": -0.25,
            "GLD": 0.40,
            "HYG": -0.20,
            "EEM": -0.25,
            "TIP": 0.20,
            "VNQ": -0.15,
            "status": "Regime analog ⚠",
        },
    }

    CORRELATION_ASSETS = ["SPY", "TLT", "GLD", "HYG", "EEM", "TIP", "VNQ", "USO", "DBC", "UUP"]

    def __init__(self):
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_time: Optional[datetime] = None
        self.cache_duration = timedelta(hours=1)

    def _is_cache_valid(self) -> bool:
        """Check if cached data is still valid."""
        if self._cache_time is None or not self._cache:
            return False
        return (datetime.now() - self._cache_time) < self.cache_duration

    def _fetch_returns(self, ticker: str, days: int = 252) -> List[float]:
        """Fetch daily returns for an asset."""
        try:
            import yfinance as yf

            stock = yf.Ticker(ticker)
            hist = stock.history(period=f"{days}d")

            if hist.empty or len(hist) < 2:
                return []

            returns = hist["Close"].pct_change().dropna().tolist()
            return returns

        except Exception as e:
            logger.warning(f"Failed to fetch returns for {ticker}: {e}")
            return []

    def _calculate_portfolio_returns(self) -> Tuple[List[float], Dict[str, List[float]]]:
        """Calculate portfolio returns from component returns."""
        asset_returns = {}

        for ticker in self.PORTFOLIO_WEIGHTS.keys():
            returns = self._fetch_returns(ticker, days=252)
            if returns:
                asset_returns[ticker] = returns

        # Align returns to same length
        min_len = min(len(r) for r in asset_returns.values()) if asset_returns else 0
        if min_len == 0:
            return [], asset_returns

        portfolio_returns = []
        for i in range(min_len):
            daily_return = sum(
                self.PORTFOLIO_WEIGHTS[ticker] * asset_returns[ticker][i]
                for ticker in asset_returns.keys()
            )
            portfolio_returns.append(daily_return)

        # Trim asset returns to same length
        asset_returns = {k: v[:min_len] for k, v in asset_returns.items()}

        return portfolio_returns, asset_returns

    def _calculate_drawdown(self, returns: List[float]) -> DrawdownMetrics:
        """Calculate drawdown metrics."""
        if not returns:
            return DrawdownMetrics()

        # Calculate cumulative value
        cumulative = [1.0]
        for r in returns:
            cumulative.append(cumulative[-1] * (1 + r))

        # Find current drawdown
        peak = max(cumulative)
        current = cumulative[-1]
        current_dd = (current / peak - 1) * 100

        # Find max drawdown
        max_dd = 0
        peak_idx = 0
        for i, val in enumerate(cumulative):
            if val > cumulative[peak_idx]:
                peak_idx = i
            dd = (val / cumulative[peak_idx] - 1) * 100
            max_dd = min(max_dd, dd)

        # Days in drawdown
        days_in_dd = 0
        for i in range(len(cumulative) - 1, -1, -1):
            if cumulative[i] < cumulative[peak_idx]:
                days_in_dd += 1
            else:
                break

        # Severity classification
        if current_dd > -5:
            severity = "MINOR"
        elif current_dd > -10:
            severity = "MODERATE"
        elif current_dd > -15:
            severity = "SIGNIFICANT"
        else:
            severity = "SEVERE"

        # Recovery estimate
        expected_recovery = int(days_in_dd * 1.5) if days_in_dd > 0 else None

        return DrawdownMetrics(
            current_drawdown=round(current_dd, 2),
            current_severity=severity,
            max_drawdown_12m=round(max_dd, 2),
            days_in_drawdown=days_in_dd,
            expected_recovery_days=expected_recovery,
            recovery_time_estimate=f"{expected_recovery} days" if expected_recovery else "In recovery",
        )

    def _calculate_risk_adjusted_returns(self, portfolio_returns: List[float]) -> RiskAdjustedReturns:
        """Calculate risk-adjusted return metrics."""
        if not portfolio_returns or len(portfolio_returns) < 30:
            return RiskAdjustedReturns()

        # Fetch risk-free rate (3M T-bill)
        try:
            import yfinance as yf
            tbill = yf.Ticker("^IRX")
            hist = tbill.history(period="5d")
            rf_annual = hist["Close"].iloc[-1] / 100 if not hist.empty else 0.05
        except:
            rf_annual = 0.05

        rf_daily = rf_annual / 252

        # Annualized metrics
        annual_return = np.mean(portfolio_returns) * 252 * 100
        annual_vol = np.std(portfolio_returns) * np.sqrt(252) * 100

        # Sharpe Ratio
        sharpe = (annual_return - rf_annual * 100) / annual_vol if annual_vol > 0 else None

        # Sortino Ratio (downside deviation only)
        downside_returns = [r for r in portfolio_returns if r < 0]
        downside_vol = np.std(downside_returns) * np.sqrt(252) * 100 if downside_returns else annual_vol
        sortino = (annual_return - rf_annual * 100) / downside_vol if downside_vol > 0 else None

        # SPY returns for beta and IR
        spy_returns = self._fetch_returns("SPY", days=len(portfolio_returns))
        beta = None
        ir = None

        if len(spy_returns) >= len(portfolio_returns):
            spy_returns = spy_returns[:len(portfolio_returns)]
            try:
                covariance = np.cov(portfolio_returns, spy_returns)[0][1]
                spy_var = np.var(spy_returns)
                beta = covariance / spy_var if spy_var > 0 else 1.0

                # Information Ratio
                excess_returns = np.array(portfolio_returns) - np.array(spy_returns)
                excess_annual = np.mean(excess_returns) * 252 * 100
                tracking_error = np.std(excess_returns) * np.sqrt(252) * 100
                ir = excess_annual / tracking_error if tracking_error > 0 else 0
            except:
                pass

        # VaR and CVaR (assuming $100M AUM)
        aum = 100_000_000
        var_95_pct = np.percentile(portfolio_returns, 5)
        cvar_95_pct = np.mean([r for r in portfolio_returns if r <= var_95_pct]) if portfolio_returns else 0
        var_99_pct = np.percentile(portfolio_returns, 1)

        var_95 = abs(var_95_pct) * aum
        cvar_95 = abs(cvar_95_pct) * aum
        var_99 = abs(var_99_pct) * aum

        # Calmar Ratio
        max_dd = 0
        cumulative = [1.0]
        for r in portfolio_returns:
            cumulative.append(cumulative[-1] * (1 + r))
            current_peak = max(cumulative)
            dd = (cumulative[-1] / current_peak - 1) * 100
            max_dd = min(max_dd, dd)

        calmar = abs(annual_return / max_dd) if max_dd != 0 else None

        return RiskAdjustedReturns(
            sharpe_ratio=round(sharpe, 2) if sharpe else None,
            sortino_ratio=round(sortino, 2) if sortino else None,
            calmar_ratio=round(calmar, 2) if calmar else None,
            information_ratio=round(ir, 2) if ir else None,
            beta_spy=round(beta, 2) if beta else None,
            var_95=round(var_95),
            cvar_95=round(cvar_95),
            var_99=round(var_99),
            annual_return=round(annual_return, 2),
            annual_volatility=round(annual_vol, 2),
        )

    def _calculate_correlation_matrix(self) -> Dict[str, Any]:
        """Calculate correlation matrix for assets."""
        returns_matrix = {}

        for ticker in self.CORRELATION_ASSETS:
            returns = self._fetch_returns(ticker, days=252)
            if len(returns) >= 63:  # At least 3 months
                returns_matrix[ticker] = returns

        if len(returns_matrix) < 3:
            return {"matrix_3m": [], "matrix_12m": [], "diversification_score": None}

        # Calculate 3M and 12M correlations
        assets = list(returns_matrix.keys())
        matrix_3m = []
        matrix_12m = []

        for i, asset1 in enumerate(assets):
            row_3m = []
            row_12m = []
            for j, asset2 in enumerate(assets):
                if i == j:
                    row_3m.append(1.0)
                    row_12m.append(1.0)
                else:
                    # 3M correlation (63 days)
                    r1_3m = returns_matrix[asset1][-63:]
                    r2_3m = returns_matrix[asset2][-63:]
                    corr_3m = np.corrcoef(r1_3m, r2_3m)[0][1] if len(r1_3m) == len(r2_3m) else 0
                    row_3m.append(round(corr_3m, 2))

                    # 12M correlation
                    r1_12m = returns_matrix[asset1]
                    r2_12m = returns_matrix[asset2]
                    min_len = min(len(r1_12m), len(r2_12m))
                    corr_12m = np.corrcoef(r1_12m[:min_len], r2_12m[:min_len])[0][1] if min_len > 30 else 0
                    row_12m.append(round(corr_12m, 2))

            matrix_3m.append(row_3m)
            matrix_12m.append(row_12m)

        # Calculate diversification score
        # 1 - mean(abs(off-diagonal correlations))
        off_diagonal_3m = []
        for i in range(len(assets)):
            for j in range(i + 1, len(assets)):
                off_diagonal_3m.append(abs(matrix_3m[i][j]))

        diversification_score = round(1 - np.mean(off_diagonal_3m), 2) if off_diagonal_3m else 0.5

        # Calculate correlation changes
        correlation_changes = []
        for i in range(len(assets)):
            for j in range(i + 1, len(assets)):
                change = matrix_3m[i][j] - matrix_12m[i][j]
                if abs(change) > 0.30:
                    correlation_changes.append({
                        "pair": f"{assets[i]}-{assets[j]}",
                        "change": round(change, 2),
                        "direction": "rising" if change > 0 else "falling",
                    })

        return {
            "assets": assets,
            "matrix_3m": matrix_3m,
            "matrix_12m": matrix_12m,
            "diversification_score": diversification_score,
            "diversification_rating": "GOOD" if diversification_score > 0.5 else "FAIR" if diversification_score > 0.3 else "POOR",
            "correlation_changes": correlation_changes[:10],  # Top 10 changes
        }

    def _calculate_stress_tests(self, asset_returns: Dict[str, List[float]]) -> List[StressScenario]:
        """Run stress test scenarios."""
        scenarios = []
        aum = 100_000_000

        for scenario_key, config in self.STRESS_SCENARIOS.items():
            # Calculate portfolio P&L
            portfolio_pnl = 0
            component_pnls = {}

            for ticker, weight in self.PORTFOLIO_WEIGHTS.items():
                shock = config.get(ticker, 0)
                pnl = weight * shock * aum
                portfolio_pnl += pnl
                component_pnls[ticker] = pnl

            # Find worst/best components
            sorted_components = sorted(component_pnls.items(), key=lambda x: x[1])
            worst = sorted_components[0][0] if sorted_components else None
            best = sorted_components[-1][0] if sorted_components else None

            scenarios.append(StressScenario(
                name=config["name"],
                description=config["description"],
                portfolio_pnl_pct=round(portfolio_pnl / aum * 100, 1),
                portfolio_pnl_usd=round(portfolio_pnl),
                worst_component=worst,
                best_component=best,
                status=config.get("status", "Historical"),
            ))

        return scenarios

    def _calculate_position_sizing(self, asset: str, signal: str, conviction: str) -> PositionSizing:
        """Calculate position sizing for an asset."""
        try:
            import yfinance as yf

            stock = yf.Ticker(asset)
            hist = stock.history(period="21d")
            info = stock.info

            if hist.empty:
                return PositionSizing(asset=asset, signal=signal, conviction=conviction)

            current_price = hist["Close"].iloc[-1]

            # Calculate 20-day volatility (annualized)
            daily_returns = hist["Close"].pct_change().dropna()
            vol_20d = daily_returns.std() * np.sqrt(252)

            if vol_20d == 0:
                return PositionSizing(asset=asset, signal=signal, conviction=conviction)

            # Position sizing calculation
            portfolio_size = 100_000_000  # $100M
            risk_per_trade = 0.01  # 1%
            base_risk = portfolio_size * risk_per_trade  # $1M
            position_vol_target = 0.10  # 10% vol target

            position_size = (base_risk * position_vol_target) / vol_20d

            # Conviction multiplier
            conviction_mult = {"HIGH": 1.5, "MEDIUM": 1.0, "LOW": 0.5}.get(conviction.upper(), 1.0)
            final_size = position_size * conviction_mult

            percent_aum = (final_size / portfolio_size) * 100
            shares = int(final_size / current_price) if current_price > 0 else 0

            # Daily VaR
            daily_var = final_size * vol_20d / np.sqrt(252)

            # Generate rationale
            rationale = f"{signal} signal + {conviction.lower()} conviction + {signal.lower()} regime"

            return PositionSizing(
                asset=asset,
                signal=signal,
                conviction=conviction,
                current_price=round(current_price, 2),
                dollar_amount=round(final_size),
                percent_aum=round(percent_aum, 2),
                shares=shares,
                daily_var_95=round(daily_var),
                rationale=rationale,
            )

        except Exception as e:
            logger.warning(f"Failed to calculate position sizing for {asset}: {e}")
            return PositionSizing(asset=asset, signal=signal, conviction=conviction)

    def calculate_hedge_fund_analytics(self) -> Dict[str, Any]:
        """
        Calculate complete hedge fund analytics.

        Returns:
            Dictionary with drawdown, risk-adjusted returns, correlation, stress tests, and position sizing.
        """
        if self._is_cache_valid() and self._cache:
            return self._cache

        # Calculate portfolio returns
        portfolio_returns, asset_returns = self._calculate_portfolio_returns()

        # Drawdown metrics
        drawdown = self._calculate_drawdown(portfolio_returns)

        # Risk-adjusted returns
        risk_adj = self._calculate_risk_adjusted_returns(portfolio_returns)

        # Correlation matrix
        correlation = self._calculate_correlation_matrix()

        # Stress tests
        stress_tests = self._calculate_stress_tests(asset_returns)

        # Sample position sizing
        sample_sizing = self._calculate_position_sizing("GLD", "OVERWEIGHT", "HIGH")

        result = {
            "drawdown": {
                "currentDrawdown": drawdown.current_drawdown,
                "currentSeverity": drawdown.current_severity,
                "maxDrawdown12m": drawdown.max_drawdown_12m,
                "daysInDrawdown": drawdown.days_in_drawdown,
                "expectedRecoveryDays": drawdown.expected_recovery_days,
                "recoveryTimeEstimate": drawdown.recovery_time_estimate,
            },
            "riskAdjustedReturns": {
                "sharpeRatio": risk_adj.sharpe_ratio,
                "sortinoRatio": risk_adj.sortino_ratio,
                "calmarRatio": risk_adj.calmar_ratio,
                "informationRatio": risk_adj.information_ratio,
                "betaVsSpy": risk_adj.beta_spy,
                "var95": risk_adj.var_95,
                "cvar95": risk_adj.cvar_95,
                "var99": risk_adj.var_99,
                "annualReturn": risk_adj.annual_return,
                "annualVolatility": risk_adj.annual_volatility,
            },
            "correlation": correlation,
            "stressTests": [
                {
                    "name": s.name,
                    "description": s.description,
                    "portfolioPnlPct": s.portfolio_pnl_pct,
                    "portfolioPnlUsd": s.portfolio_pnl_usd,
                    "worstComponent": s.worst_component,
                    "bestComponent": s.best_component,
                    "status": s.status,
                }
                for s in stress_tests
            ],
            "positionSizing": {
                "asset": sample_sizing.asset,
                "signal": sample_sizing.signal,
                "conviction": sample_sizing.conviction,
                "currentPrice": sample_sizing.current_price,
                "dollarAmount": sample_sizing.dollar_amount,
                "percentAum": sample_sizing.percent_aum,
                "shares": sample_sizing.shares,
                "dailyVar95": sample_sizing.daily_var_95,
                "rationale": sample_sizing.rationale,
            },
            "assumptions": {
                "portfolioAum": 100_000_000,
                "riskPerTrade": "1%",
                "volTarget": "10% annualized",
            },
            "timestamp": datetime.now().isoformat(),
        }

        self._cache = result
        self._cache_time = datetime.now()

        return result


# Singleton instance
_analytics_instance: Optional[HedgeFundAnalytics] = None


def get_hedge_fund_analytics() -> HedgeFundAnalytics:
    """Get or create hedge fund analytics singleton."""
    global _analytics_instance
    if _analytics_instance is None:
        _analytics_instance = HedgeFundAnalytics()
    return _analytics_instance


def calculate_hedge_fund_analytics() -> Dict[str, Any]:
    """Public API for hedge fund analytics."""
    analytics = get_hedge_fund_analytics()
    return analytics.calculate_hedge_fund_analytics()
