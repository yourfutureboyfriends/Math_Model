"""Standard formatting constants and utilities."""

# Number formatting precision
FORMAT_PROBABILITY = 4      # 0.0000 to 1.0000 (probabilities)
FORMAT_PERCENTAGE = 2       # 75.25% (percentage displays)
FORMAT_INDEX = 2            # 100.00 (DXY, VIX, indices)
FORMAT_PRICE = 2            # $123.45 (prices, yields)
FORMAT_BASIS_POINTS = 0     # 250 (basis points, no decimals)

# Rate/yield formatting
FORMAT_YIELD = 2            # 4.25% (yields, rates)
FORMAT_SPREAD = 1           # 1.5% (spreads)

# FX formatting
FORMAT_FX_MAJOR = 4         # 1.0850 (EUR/USD, major pairs)
FORMAT_FX_JPY = 2           # 150.25 (USD/JPY)
FORMAT_FX_MINOR = 5         # 0.89125 (minor pairs)


def format_probability(value: float) -> str:
    """Format probability (0-1 range)."""
    return f"{value:.{FORMAT_PROBABILITY}f}"


def format_percentage(value: float, multiply: bool = False) -> str:
    """
    Format percentage.

    Args:
        value: Value to format
        multiply: If True, multiply by 100 (0.75 -> 75%)
               If False, use as-is (75 -> 75%)
    """
    if multiply:
        value = value * 100
    return f"{value:.{FORMAT_PERCENTAGE}f}%"


def format_price(value: float) -> str:
    """Format price/yield."""
    return f"{value:.{FORMAT_PRICE}f}"


def format_index(value: float) -> str:
    """Format index (DXY, VIX, etc.)."""
    return f"{value:.{FORMAT_INDEX}f}"
