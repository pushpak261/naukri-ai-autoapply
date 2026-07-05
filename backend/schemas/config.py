"""Pydantic schemas for config update endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class SearchExperienceUpdate(BaseModel):
    experience_min: int = Field(ge=0, le=50)
    experience_max: int = Field(ge=0, le=50)

    @model_validator(mode="after")
    def validate_range(self) -> SearchExperienceUpdate:
        if self.experience_min > self.experience_max:
            raise ValueError("experience_min cannot be greater than experience_max")
        return self
