"""
Business Layer for Macro Research Platform

This module provides business-focused outputs for the investment fund:
- Investment committee packs
- Decision logging and audit trails
- Recommendation engine with conviction levels
- Weekly macro process orchestration
- Model postmortem analysis
"""

from .business_objectives import (
    BusinessOutputType,
    BusinessObjective,
    BUSINESS_OBJECTIVES,
    ConvictionLevel,
    PositionSize,
    Recommendation,
    PlatformEffectiveness,
    BusinessObjectivesManager,
    get_business_objective,
    list_all_outputs,
)

from .recommendation_engine import (
    ConvictionEngine,
    PositionSizingEngine,
    RecommendationEngine,
)

from .decision_log import (
    DecisionLogEntry,
    DecisionLog,
    create_decision_log,
)

from .investment_committee_pack import (
    InvestmentCommitteePackGenerator,
    generate_ic_pack,
)

from .model_postmortem import (
    PostmortemAnalysis,
    ModelPostmortemEngine,
    generate_monthly_postmortem,
)

from .weekly_macro_process import (
    WeeklyMacroProcess,
    run_weekly_process,
)
from .business_integration_adapter import (
    BusinessIntegrationAdapter,
)

__all__ = [
    # Business Objectives
    "BusinessOutputType",
    "BusinessObjective",
    "BUSINESS_OBJECTIVES",
    "ConvictionLevel",
    "PositionSize",
    "Recommendation",
    "PlatformEffectiveness",
    "BusinessObjectivesManager",
    "get_business_objective",
    "list_all_outputs",
    # Recommendation Engine
    "ConvictionEngine",
    "PositionSizingEngine",
    "RecommendationEngine",
    # Decision Log
    "DecisionLogEntry",
    "DecisionLog",
    "create_decision_log",
    # Investment Committee Pack
    "InvestmentCommitteePackGenerator",
    "generate_ic_pack",
    # Postmortem
    "PostmortemAnalysis",
    "ModelPostmortemEngine",
    "generate_monthly_postmortem",
    # Weekly Process
    "WeeklyMacroProcess",
    "run_weekly_process",
    # Integration Adapter
    "BusinessIntegrationAdapter",
]
