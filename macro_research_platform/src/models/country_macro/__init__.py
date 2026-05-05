"""
Country Macro Models

Implements macro models for individual countries and regions.
"""

from .base_country_model import BaseCountryMacroModel, CountryMacroOutput
from .us_macro_model import USMacroModel
from .euro_area_macro_model import EuroAreaMacroModel
from .china_macro_model import ChinaMacroModel
from .japan_macro_model import JapanMacroModel
from .uk_macro_model import UKMacroModel
from .emerging_markets_model import EmergingMarketsModel

__all__ = [
    "BaseCountryMacroModel",
    "CountryMacroOutput",
    "USMacroModel",
    "EuroAreaMacroModel",
    "ChinaMacroModel",
    "JapanMacroModel",
    "UKMacroModel",
    "EmergingMarketsModel",
]
