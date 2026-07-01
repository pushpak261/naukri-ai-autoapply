"""Pydantic schemas for agent SSE events."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentEvent(BaseModel):
    id: str
    run_id: int
    type: str
    timestamp: str
    data: dict[str, Any] = Field(default_factory=dict)
