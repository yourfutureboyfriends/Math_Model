"""
Business Conditions Nowcast Model.

Implements diffusion index approach inspired by:
- Stock and Watson (2002) - Macroeconomic forecasting using diffusion indexes
- Aruoba-Diebold-Scotti (2009) - Real-time measurement of business conditions
- Giannone-Reichlin-Small (2008) - Nowcasting GDP and inflation

Estimates real-time growth momentum before GDP confirms it.
"""

from .business_conditions_model import (
    BusinessConditionsModel,
    BusinessConditionsResult,
    get_business_conditions_summary,
)

__all__ = [
    "BusinessConditionsModel",
    "BusinessConditionsResult",
    "get_business_conditions_summary",
]
