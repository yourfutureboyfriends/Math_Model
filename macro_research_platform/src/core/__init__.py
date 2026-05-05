"""
Core orchestration module.

Provides the main entry point for the macro research platform.
"""

from .platform import MacroResearchPlatform, create_platform
from .config import PlatformConfig

__all__ = [
    "MacroResearchPlatform",
    "PlatformConfig",
    "create_platform",
]
