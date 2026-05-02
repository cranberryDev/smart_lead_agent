from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Contact(BaseModel):
    """Lead contact; supports CSV-style names or event-scan `full_name`."""

    model_config = ConfigDict(str_strip_whitespace=True)

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    email: str = ""
    phone: Optional[str] = None
    title: Optional[str] = None


class Company(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = ""
    website: str = ""
    industry: str = ""
    employee_count: Optional[int] = None
    hq_country: str = ""


class Intent(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    use_case: str = ""
    timeline: str = ""
    budget_range_usd: str = ""
    notes: str = ""


class LeadPayload(BaseModel):
    """Inbound lead record for follow-up generation (matches JSON 1–3 shapes)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    lead_id: str = Field(..., examples=["L-1001"])
    created_at: datetime = Field(..., examples=["2026-03-06T10:15:00Z"])
    source: str = Field(..., examples=["website_form"])
    contact: Contact
    company: Company
    intent: Intent
    raw_notes: Optional[str] = None


class FollowUpEmail(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    subject: str = ""
    body: str = ""


class FollowUpEnrichment(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    persona: str = ""
    pain_points: list[str] = Field(default_factory=list)
    urgency: str = ""
    industry_context: str = ""

    @field_validator("pain_points", mode="before")
    @classmethod
    def coerce_pain_points(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        if isinstance(v, list):
            return [str(x) for x in v]
        return []


class FollowUpAgentResponse(BaseModel):
    """Matches the JSON shape returned by the Foundry-hosted agent."""

    status: str = Field(default="success", examples=["success"])
    lead_id: str
    email: FollowUpEmail
    enrichment: FollowUpEnrichment = Field(default_factory=FollowUpEnrichment)
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="before")
    @classmethod
    def unwrap_outer_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        for key in ("output", "result", "response", "data"):
            inner = data.get(key)
            if isinstance(inner, dict) and (
                "email" in inner or "lead_id" in inner or "enrichment" in inner
            ):
                return inner
        return data
