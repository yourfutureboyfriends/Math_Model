"""
Research Library

Maps academic papers to model features, signals, and implementation files.

Every paper in this library must map to:
- A specific model area
- A business use case
- One or more signals
- An implementation file
- An affected output

This is not a reading list. It is a research-to-production pipeline.
"""

from .research_library import (
    ResearchPaper,
    ResearchCategory,
    ResearchLibrary,
    PAPER_REGISTRY,
    get_paper,
    get_papers_by_category,
    get_papers_by_signal,
    get_implementation_status,
)

from .signal_paper_mapping import (
    SignalPaperMapping,
    SIGNAL_TO_PAPERS,
    get_papers_for_signal,
    get_research_support_for_signal,
)

__all__ = [
    "ResearchPaper",
    "ResearchCategory",
    "ResearchLibrary",
    "PAPER_REGISTRY",
    "get_paper",
    "get_papers_by_category",
    "get_papers_by_signal",
    "get_implementation_status",
    "SignalPaperMapping",
    "SIGNAL_TO_PAPERS",
    "get_papers_for_signal",
    "get_research_support_for_signal",
]
