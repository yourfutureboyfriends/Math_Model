"""Standard API response utilities."""
from typing import Optional, Any
from pydantic import BaseModel
from datetime import datetime


class ErrorResponse(BaseModel):
    """Standard error response format."""
    error: str
    detail: Optional[str] = None
    timestamp: datetime = datetime.now()
    endpoint: Optional[str] = None


class SuccessResponse(BaseModel):
    """Standard success response wrapper."""
    data: Any
    timestamp: datetime = datetime.now()
    cached: bool = False


def error_response(
    error: str,
    detail: Optional[str] = None,
    endpoint: Optional[str] = None
) -> dict:
    """
    Create standard error response.

    Args:
        error: Error message
        detail: Detailed error information
        endpoint: Endpoint that errored

    Returns:
        Error response dict
    """
    return ErrorResponse(
        error=error,
        detail=detail,
        endpoint=endpoint
    ).dict()


def success_response(data: Any, cached: bool = False) -> dict:
    """
    Create standard success response.

    Args:
        data: Response data
        cached: Whether data is from cache

    Returns:
        Success response dict
    """
    return SuccessResponse(
        data=data,
        cached=cached
    ).dict()
