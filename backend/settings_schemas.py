"""Pydantic schemas for user settings endpoints."""

from pydantic import BaseModel, Field, field_validator


# Allowed values for validation
VALID_THEMES = {
    "none", "default-dark", "northern-lights", "still-water", "cosmic-drift",
    "rainy-window", "forest-stream", "campfire", "golden-sunset",
    "misty-forest", "soft-bokeh", "custom",
}

VALID_VOICES = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}

VALID_AMBIENCES = {"rain", "ocean", "forest", "bowls", "silence"}


class LifeSettingsResponse(BaseModel):
    display_name: str | None
    timezone: str
    theme: str
    theme_opacity: float
    med_length: str = "medium"
    med_voice: str = "nova"
    med_ambience: str = "rain"

    model_config = {"from_attributes": True}

    @field_validator("med_length", mode="before")
    @classmethod
    def _default_med_length(cls, v):
        return v if v is not None else "medium"


class LifeSettingsUpdate(BaseModel):
    """Partial update — all fields optional."""
    display_name: str | None = Field(None, max_length=100)
    timezone: str | None = Field(None, max_length=50)
    theme: str | None = Field(None, max_length=30)
    theme_opacity: float | None = Field(None, ge=0.0, le=1.0)
    med_length: str | None = Field(None, max_length=10)
    med_voice: str | None = Field(None, max_length=20)
    med_ambience: str | None = Field(None, max_length=20)
