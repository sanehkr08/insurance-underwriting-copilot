"""Data shapes passed between the steps of the copilot.

SubmissionFacts  - what the AI pulls out of an application (step 1)
Assessment       - the AI's check of each guideline rule (step 2)
UnderwritingDecision - the final result our code puts together (step 3)
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class Claim(BaseModel):
    date: Optional[str] = Field(None, description="Date of loss as written, e.g. '03/2024'")
    description: str
    amount: Optional[float] = Field(None, description="Total incurred in USD (paid plus reserved)")
    status: Optional[str] = Field(None, description="open or closed")


class WorkShare(BaseModel):
    work_type: str
    percent: float = Field(description="Share of revenue, 0 to 100")


class SubmissionFacts(BaseModel):
    submission_date: Optional[str] = Field(None, description="Date of the submission as YYYY-MM-DD")
    business_name: Optional[str] = None
    business_description: Optional[str] = Field(None, description="What the business does")
    business_class: Optional[str] = Field(None, description="Short class, e.g. 'cafe', 'retail hardware', 'handyman contractor'")
    is_contractor: bool = False
    years_in_business: Optional[float] = None
    annual_revenue: Optional[float] = Field(None, description="USD")
    address: Optional[str] = None
    country: Optional[str] = None
    flood_zone: Optional[str] = Field(None, description="FEMA flood zone, e.g. 'X' or 'AE'")

    # Restaurants, cafes and bars
    alcohol_share_percent: Optional[float] = Field(None, description="Current alcohol share of revenue, 0 to 100")
    planned_alcohol_note: Optional[str] = Field(None, description="Any planned future alcohol sales")
    cooking_equipment: list[str] = Field(default_factory=list)
    hood_suppression_last_serviced: Optional[str] = None

    # Building (only when the applicant insures the building)
    insures_building: Optional[bool] = None
    year_built: Optional[int] = None
    construction: Optional[str] = Field(None, description="masonry, joisted masonry, noncombustible or frame")
    square_feet: Optional[float] = None
    sprinklered: Optional[bool] = None
    occupancy_percent: Optional[float] = None
    roof_year: Optional[int] = Field(None, description="Year the roof was installed or replaced")
    roof_inspection_date: Optional[str] = None
    electrical_updated_year: Optional[int] = None
    plumbing_updated_year: Optional[int] = None
    heating_updated_year: Optional[int] = None

    # Values in USD
    building_value: Optional[float] = None
    contents_value: Optional[float] = None
    business_income_value: Optional[float] = None

    # History
    claims_past_3_years: list[Claim] = Field(default_factory=list)
    loss_history_provided: bool = Field(False, description="True if claims are listed or the application says there were none")
    prior_cancellation_or_nonrenewal: Optional[bool] = None
    prior_cancellation_reason: Optional[str] = None

    # Contractors
    work_breakdown: list[WorkShare] = Field(default_factory=list)
    max_working_stories: Optional[int] = None
    subcontracted_percent: Optional[float] = None
    certificates_from_all_subcontractors: Optional[bool] = None


Outcome = Literal["ACCEPTABLE", "REFER", "DECLINE", "NOT_APPLICABLE"]


class RuleFinding(BaseModel):
    rule_id: str = Field(description="Guideline rule ID, e.g. 'PROP-4'")
    outcome: Outcome
    evidence: str = Field(description="Facts from the application that this outcome is based on")
    explanation: str = Field(description="One sentence on how the rule applies")

    @field_validator("rule_id", "outcome", mode="before")
    @classmethod
    def _upper(cls, value):
        return value.strip().upper().replace(" ", "_") if isinstance(value, str) else value


class Assessment(BaseModel):
    findings: list[RuleFinding] = Field(description="Exactly one finding per guideline rule")
    missing_information: list[str] = Field(default_factory=list, description="Required items (AUTH-5) that are missing or unclear")
    summary: str = Field(description="Two or three sentences for the underwriter")


Decision = Literal["ACCEPT", "REFER", "DECLINE"]


class UnderwritingDecision(BaseModel):
    submission: str
    decision: Decision
    reasons: list[RuleFinding] = Field(description="Findings that caused REFER or DECLINE")
    missing_information: list[str]
    summary: str
    warnings: list[str] = Field(default_factory=list, description="Problems with the AI's answer that a person should check")
    derived: dict
    facts: SubmissionFacts
    findings: list[RuleFinding]
    models_used: list[str]
