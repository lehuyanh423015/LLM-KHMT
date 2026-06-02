"""
Pydantic schemas for request/response validation.

These schemas define the shape of data flowing through the API.
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Incoming chat request from the frontend."""

    message: str
    session_id: Optional[str] = "default-session"


class ChatResponse(BaseModel):
    """Outgoing chat response to the frontend."""

    answer: str
    session_id: str = "default-session"
    debug: Dict[str, Any] = Field(default_factory=dict)

class CustomerProfileResponse(BaseModel):
    """Profile data formatted for frontend demo usage."""

    session_id: str
    name: Optional[str]
    budget: Optional[str]
    preferred_category: Optional[str]
    preferred_color: Optional[str]
    priorities: Optional[str]
    dislikes: Optional[str]
    updated_at: str

class ModeRequest(BaseModel):
    """Request to change operation mode."""
    mode: str

class ExperimentRequest(BaseModel):
    """Request to change experiment settings."""
    enable_memory: bool
    enable_recent_context: bool
    enable_product_context: Optional[bool] = None
