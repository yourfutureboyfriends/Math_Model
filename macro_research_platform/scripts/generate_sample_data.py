"""
Generate synthetic macro data following the 2018-2024 macro cycle.

Financial context:
  This script creates realistic (but fictional) indicator data that traces the
  key macro regimes of the past 7 years so the model has something coherent to
  classify and explain.  The broad arc is:

  2018  Late Goldilocks  — strong growth, mild inflation, Fed hiking rates
  2019  Slowdown         — trade-war headwinds, Fed pauses then cuts
  2020  Crisis → Recovery— COVID shock, emergency cuts, fiscal stimulus
  2021  Reflation        — booming recovery, supply-chain inflation emerges
  2022  Stagflation      — CPI peaks ~9%, Fed hikes 425bp in a year
  2023  Disinflation     — inflation falling, growth resilient ("soft landing")
  2024  Goldilocks       — inflation near target, growth steady, Fed cutting

Run this script once to create data/raw/sample_macro_data.csv, then run the
dashboard.  You can also call generate() directly from other scripts.
"""

import numpy as np
import pandas as pd
from pathlib import Path

np.random.seed(42)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def interp(start: float, end: float, n: int, noise: float = 0.0) -> np.ndarray:
    """Linearly interpolate from start to end over n months with optional noise."""
    arr = np.linspace(start, end, n)
    if noise > 0:
        arr += np.random.normal(0, noise, n)
    return arr


def seg(*arrays) -> np.ndarray:
    """Concatenate arrays (segments) into one series."""
    return np.concatenate([np.asarray(a) for a in arrays])


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate() -> pd.DataFrame:
    """Return a DataFrame with 84 months of synthetic macro data (2018-01 to 2024-12)."""

    dates = pd.date_range("2018-01-01", "2024-12-01", freq="MS")  # 84 months
    assert len(dates) == 84, "Date range must produce exactly 84 months"

    # ------------------------------------------------------------------
    # GROWTH INDICATORS
    # ------------------------------------------------------------------

    # PMI (Purchasing Managers Index)
    # Financial logic: PMI above 50 signals expansion; below 50 signals contraction.
    # It is one of the most timely leading indicators of economic activity.
    pmi = seg(
        interp(55.0, 57.0, 12, 0.5),   # 2018: strong expansion
        interp(56.5, 50.5, 12, 0.5),   # 2019: trade-war softening
        [48.5, 36.1, 41.5, 49.0, 52.0, 55.0, 57.0, 58.0, 57.0, 58.5, 59.0, 60.0],  # 2020
        interp(60.0, 63.0, 12, 0.8),   # 2021: red-hot recovery
        interp(57.0, 44.0, 12, 1.0),   # 2022: rate hikes bite
        interp(46.0, 51.0, 12, 0.7),   # 2023: slow recovery
        interp(50.5, 52.5, 12, 0.5),   # 2024: stable expansion
    )

    # GDP growth (year-on-year %)
    # Financial logic: GDP is the broadest measure of economic output.
    # Markets often price expected GDP rather than current; surprises drive moves.
    gdp_growth = seg(
        interp(2.8, 3.0, 12, 0.1),
        interp(2.9, 2.1, 12, 0.1),
        [2.1, 0.3, -4.9, -9.1, -2.9, -2.8, 4.0, 4.0, 4.3, 4.3, 4.3, 4.3],
        interp(0.5, 5.7, 12, 0.2),
        interp(5.5, 0.9, 12, 0.3),
        interp(2.0, 2.5, 12, 0.2),
        interp(2.5, 2.8, 12, 0.15),
    )

    # Industrial production (month-on-month %)
    industrial_production = seg(
        interp(0.3, 0.2, 12, 0.15),
        interp(0.2, -0.1, 12, 0.15),
        [0.1, -0.4, -5.2, -4.0, 1.5, 3.0, 0.8, 0.5, 0.4, 0.6, 0.3, 0.5],
        interp(0.8, 0.4, 12, 0.2),
        interp(0.3, -0.2, 12, 0.2),
        interp(0.0, 0.2, 12, 0.15),
        interp(0.2, 0.3, 12, 0.1),
    )

    # Retail sales (month-on-month %)
    # Financial logic: Consumer spending is ~70% of US GDP; retail sales is a
    # high-frequency proxy.  Watches real (inflation-adjusted) trends carefully.
    retail_sales = seg(
        interp(0.4, 0.3, 12, 0.3),
        interp(0.3, 0.1, 12, 0.3),
        [0.2, -0.8, -8.7, 17.7, 18.2, 0.9, 1.2, 0.4, 1.0, 0.2, 0.2, 0.3],
        interp(0.5, 0.3, 12, 0.4),
        interp(0.2, -0.2, 12, 0.4),
        interp(0.0, 0.3, 12, 0.3),
        interp(0.3, 0.4, 12, 0.2),
    )

    # Unemployment rate (%)
    # Financial logic: Lower unemployment = tighter labour markets = wage pressure.
    # Note: unemployment is a LAGGING indicator — it peaks AFTER recessions end.
    unemployment_rate = seg(
        interp(4.1, 3.7, 12, 0.05),
        interp(3.7, 3.5, 12, 0.05),
        [3.5, 3.5, 4.4, 14.7, 13.3, 11.1, 10.2, 8.4, 7.9, 6.9, 6.7, 6.7],
        interp(6.4, 4.2, 12, 0.10),
        interp(4.0, 3.5, 12, 0.05),
        interp(3.4, 3.7, 12, 0.05),
        interp(3.7, 4.1, 12, 0.05),
    )

    # ------------------------------------------------------------------
    # INFLATION INDICATORS
    # ------------------------------------------------------------------

    # CPI year-on-year (%)
    # Financial logic: CPI is the primary inflation gauge central banks target.
    # Fed target is 2%.  Above target → rate hikes → higher discount rates → lower equity valuations.
    cpi_yoy = seg(
        interp(2.1, 2.4, 12, 0.1),
        interp(2.3, 2.3, 12, 0.1),
        [2.5, 2.3, 1.5, 0.3, 0.1, 0.6, 1.0, 1.3, 1.4, 1.2, 1.2, 1.4],
        interp(1.4, 6.8, 12, 0.3),
        interp(7.0, 9.1, 6, 0.3),   # 2022 H1: CPI peaks
        interp(9.1, 7.1, 6, 0.3),   # 2022 H2: starts falling
        interp(6.5, 3.2, 12, 0.2),
        interp(3.1, 2.7, 12, 0.1),
    )

    # Core CPI (ex food & energy) — smoother, tracks services inflation
    core_cpi_yoy = np.clip(cpi_yoy * 0.85 + np.random.normal(0, 0.1, 84), 0.5, 9.5)

    # PPI year-on-year (%) — upstream pricing pressure; leads CPI by ~3-6 months
    ppi_yoy = cpi_yoy * 1.35 + np.random.normal(0, 0.4, 84)

    # Wage growth year-on-year (%)
    # Financial logic: Wages are the key driver of services inflation.  A tight
    # labour market → high wages → persistent core inflation ("wage-price spiral").
    wage_growth_yoy = seg(
        interp(2.5, 3.1, 12, 0.1),
        interp(3.1, 3.3, 12, 0.1),
        [3.3, 3.1, 3.1, 7.9, 6.6, 4.9, 4.7, 4.7, 4.5, 4.4, 4.4, 5.1],
        interp(5.0, 4.7, 12, 0.2),
        interp(5.1, 4.6, 12, 0.2),
        interp(4.4, 4.0, 12, 0.15),
        interp(4.0, 3.8, 12, 0.1),
    )

    # Oil price (USD per barrel)
    # Financial logic: Oil is the primary input cost for transport and manufacturing.
    # Rising oil → higher PPI/CPI → stagflation risk.  Oil also reflects global demand.
    oil_price = seg(
        interp(65, 76, 6, 2.0),    # 2018 H1
        interp(75, 50, 6, 2.0),    # 2018 H2
        interp(55, 61, 12, 2.0),   # 2019
        [63, 55, 25, 21, 34, 40, 42, 43, 40, 40, 44, 48],   # 2020
        interp(50, 85, 12, 3.0),   # 2021
        interp(80, 130, 3, 5.0),   # 2022 Q1: Russia/Ukraine spike
        interp(110, 80, 9, 3.0),   # 2022 Q2-Q4: price falls back
        interp(78, 72, 12, 2.0),   # 2023
        interp(72, 75, 12, 2.0),   # 2024
    )

    # ------------------------------------------------------------------
    # LIQUIDITY INDICATORS
    # ------------------------------------------------------------------

    # Policy rate (Fed Funds, %)
    # Financial logic: The policy rate is the price of money.  Higher rates raise
    # discount rates (lower equity valuations), tighten credit, and slow the economy.
    policy_rate = seg(
        interp(1.25, 2.50, 12, 0.05),   # 2018: hiking cycle
        interp(2.50, 1.75, 12, 0.05),   # 2019: three cuts (insurance)
        [1.75, 1.75, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25],  # 2020: emergency cut to 0
        interp(0.25, 0.25, 12, 0.01),   # 2021: zero lower bound
        interp(0.25, 4.50, 12, 0.10),   # 2022: fastest hiking cycle since 1980s
        interp(4.75, 5.50, 6, 0.05),    # 2023 H1: final hikes
        interp(5.50, 5.50, 6, 0.01),    # 2023 H2: plateau
        interp(5.50, 4.75, 12, 0.05),   # 2024: cutting cycle begins
    )

    # 10-year government yield (%)
    # Financial logic: The 10Y is the benchmark risk-free rate.  It prices the
    # long-run growth + inflation expectation.  Rising 10Y hurts long-duration
    # assets (tech, growth stocks, bonds) and helps financials.
    yield_10y = seg(
        interp(2.5, 3.2, 6, 0.08),    # 2018 H1
        interp(3.2, 2.7, 6, 0.08),    # 2018 H2
        interp(2.7, 1.7, 12, 0.07),   # 2019
        [1.8, 1.5, 0.9, 0.6, 0.7, 0.7, 0.7, 0.7, 0.8, 0.9, 0.9, 0.9],  # 2020
        interp(1.1, 1.7, 12, 0.08),   # 2021
        interp(1.7, 4.0, 12, 0.10),   # 2022
        interp(3.9, 5.0, 12, 0.10),   # 2023
        interp(4.9, 4.2, 12, 0.10),   # 2024
    )

    # 2-year government yield (%)
    # Financial logic: The 2Y closely tracks expected policy rates over the next
    # 2 years.  When 2Y > 10Y (inverted curve) it has historically preceded recessions.
    yield_2y = seg(
        interp(2.0, 2.8, 6, 0.08),
        interp(2.8, 2.5, 6, 0.08),
        interp(2.5, 1.6, 12, 0.08),
        [1.4, 0.9, 0.4, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2],
        interp(0.1, 0.7, 12, 0.05),
        interp(0.8, 4.6, 12, 0.10),
        interp(4.7, 5.0, 12, 0.08),
        interp(5.0, 4.3, 12, 0.08),
    )

    # Yield curve (10Y minus 2Y in %)
    # Financial logic: A positive slope (normal) means lenders earn more for
    # longer maturities — encourages banks to lend.  An inverted curve (negative)
    # signals recession risk and squeezes bank margins.
    yield_curve = yield_10y - yield_2y

    # IG credit spreads (basis points over government bonds)
    # Financial logic: Credit spreads measure how much extra yield investors demand
    # for corporate bonds vs. risk-free government bonds.  Wider spreads = tighter
    # financial conditions = harder for companies to refinance debt.
    credit_spreads = seg(
        interp(100, 120, 12, 5),
        interp(130, 100, 12, 5),
        [110, 150, 320, 250, 200, 160, 140, 130, 120, 115, 110, 110],
        interp(105, 90, 12, 5),
        interp(85, 160, 12, 8),
        interp(155, 125, 12, 6),
        interp(120, 110, 12, 5),
    )

    # M2 money supply growth (year-on-year %)
    # Financial logic: Rapid M2 growth = more money chasing same goods → inflation.
    # Falling M2 = tightening liquidity → risk-off.  2020 saw historic M2 surge
    # from QE + fiscal stimulus, which later contributed to the 2021-22 inflation.
    money_supply_yoy = seg(
        interp(4.0, 4.5, 12, 0.2),
        interp(4.5, 6.0, 12, 0.2),
        [6.5, 8.0, 10.0, 18.5, 22.5, 23.0, 24.0, 24.5, 25.0, 25.5, 26.0, 26.9],
        interp(26.5, 12.5, 12, 0.5),
        interp(10.0, -1.5, 12, 0.4),
        interp(-2.0, -3.5, 12, 0.3),
        interp(-2.0,  1.5, 12, 0.3),
    )

    # ------------------------------------------------------------------
    # MARKET RISK INDICATORS
    # ------------------------------------------------------------------

    # VIX (CBOE Volatility Index)
    # Financial logic: VIX measures the implied volatility of S&P 500 options.
    # It is often called the "fear gauge."  Spikes above 30 indicate stress; below
    # 15 indicates complacency.  Useful as a contrarian signal at extremes.
    vix = seg(
        interp(11, 16, 6, 1.0),     # 2018 H1: calm
        interp(16, 25, 6, 2.0),     # 2018 H2: Q4 sell-off
        interp(24, 12, 12, 1.5),    # 2019: rally
        [14, 18, 66, 40, 27, 25, 22, 22, 26, 27, 25, 22],  # 2020: COVID spike
        interp(22, 17, 12, 1.5),    # 2021
        interp(17, 33, 12, 2.0),    # 2022: bear market
        interp(32, 13, 12, 1.5),    # 2023: normalising
        interp(13, 16, 12, 1.5),    # 2024
    )

    # Equity index (S&P 500 approximation)
    # This is used only to compute trailing momentum, not scored directly.
    equity_index = seg(
        interp(2700, 2850, 6, 30),
        interp(2850, 2500, 6, 40),
        interp(2550, 3240, 12, 40),
        [3280, 2950, 2400, 2750, 2850, 3100, 3200, 3300, 3360, 3450, 3620, 3750],
        interp(3700, 4800, 12, 60),
        interp(4800, 3800, 12, 80),
        interp(3800, 4750, 12, 60),
        interp(4750, 5200, 12, 60),
    )

    # Dollar Index (DXY)
    # Financial logic: A stronger dollar tightens global financial conditions
    # because dollar-denominated debt becomes more expensive.  Emerging markets
    # and commodity exporters suffer most from a strong dollar.
    dollar_index = seg(
        interp(90, 97, 12, 0.5),
        interp(97, 96, 12, 0.5),
        [96, 99, 103, 100, 97, 97, 92, 93, 93, 93, 92, 90],
        interp(90, 96, 12, 0.5),
        interp(96, 114, 12, 0.8),
        interp(114, 101, 12, 0.8),
        interp(101, 104, 12, 0.5),
    )

    # High-yield (HY) credit spreads (basis points)
    # Financial logic: HY spreads are one of the most sensitive risk indicators.
    # They widen sharply in recessions as default risk rises.  Tight HY spreads
    # indicate investor confidence; wide spreads signal credit stress.
    hy_spreads = seg(
        interp(320, 380, 12, 15),
        interp(380, 330, 12, 15),
        [330, 400, 820, 650, 560, 480, 430, 400, 380, 360, 340, 340],
        interp(340, 280, 12, 15),
        interp(280, 480, 12, 20),
        interp(470, 380, 12, 15),
        interp(380, 340, 12, 12),
    )

    # Trailing 12-month equity return (%) — momentum signal
    # Financial logic: Time-series momentum in equities is well-documented (see
    # Moskowitz, Ooi & Pedersen 2012).  A market trending up for 12 months
    # signals risk-on sentiment; negative momentum = risk-off.
    eq_series = pd.Series(equity_index)
    equity_momentum_12m = (eq_series.pct_change(12) * 100).fillna(0).values

    # ------------------------------------------------------------------
    # Assemble DataFrame
    # ------------------------------------------------------------------

    df = pd.DataFrame({
        "date":                 dates,
        # Growth
        "pmi":                  pmi.round(1),
        "gdp_growth":           gdp_growth.round(2),
        "industrial_production": industrial_production.round(2),
        "retail_sales":         retail_sales.round(2),
        "unemployment_rate":    unemployment_rate.round(1),
        # Inflation
        "cpi_yoy":              cpi_yoy.round(1),
        "core_cpi_yoy":         core_cpi_yoy.round(1),
        "ppi_yoy":              ppi_yoy.round(1),
        "wage_growth_yoy":      wage_growth_yoy.round(1),
        "oil_price":            oil_price.round(1),
        # Liquidity
        "policy_rate":          policy_rate.round(2),
        "yield_10y":            yield_10y.round(2),
        "yield_2y":             yield_2y.round(2),
        "yield_curve":          yield_curve.round(2),
        "credit_spreads":       credit_spreads.round(0),
        "money_supply_yoy":     money_supply_yoy.round(1),
        # Market risk
        "vix":                  vix.round(1),
        "equity_index":         equity_index.round(0),
        "dollar_index":         dollar_index.round(1),
        "hy_spreads":           hy_spreads.round(0),
        "equity_momentum_12m":  equity_momentum_12m.round(1),
    })

    # Validate lengths
    for col in df.columns:
        if col != "date":
            assert len(df[col]) == 84, f"{col} has wrong length"

    return df


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    out = Path(__file__).parent.parent / "data" / "raw" / "sample_macro_data.csv"
    out.parent.mkdir(parents=True, exist_ok=True)

    df = generate()
    df.to_csv(out, index=False)

    print(f"✓ Generated {len(df)} rows  →  {out}")
    print(f"\nDate range: {df['date'].iloc[0].strftime('%Y-%m')} to {df['date'].iloc[-1].strftime('%Y-%m')}")
    print(f"\nLast 3 rows:\n{df[['date','pmi','cpi_yoy','policy_rate','vix']].tail(3).to_string(index=False)}")
