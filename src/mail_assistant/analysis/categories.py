from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Category(StrEnum):
    URGENT = "urgent"
    ACTION_REQUIRED = "action_required"
    FYI = "fyi"
    NEWSLETTER = "newsletter"
    SOCIAL = "social"


class Classification(BaseModel):
    """Structured output of the per-message classifier."""

    category: Category = Field(description="The single best-fit category for the message.")
    confidence: float = Field(ge=0.0, le=1.0, description="How sure the model is, 0..1.")
    reason: str = Field(
        description="One sentence (<= 25 words) justifying the choice. Cite the strongest signal."
    )
