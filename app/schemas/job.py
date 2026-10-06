"""Pydantic v2 schemas for certificate generation jobs and recipients."""

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.core.config import get_settings
from app.models.job import CertificateStatus, JobStatus


class RecipientInput(BaseModel):
    """Schema for individual recipient input in a job creation request."""

    name: str = Field(..., description="Full name of the certificate recipient")
    email: str = Field(..., description="Email address of the certificate recipient")
    role: Optional[str] = Field(default=None, description="Optional role or distinction")
    score: Optional[str] = Field(default=None, description="Optional score, grade, or metric")

    model_config = ConfigDict(extra="ignore")


class JobCreate(BaseModel):
    """Request schema for initiating a bulk certificate generation job."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Course, event, or certificate title",
    )
    issuer: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Issuing organization or authority",
    )
    issue_date: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Issue date (e.g. '2026-10-07' or 'October 7, 2026')",
    )
    recipients: list[RecipientInput] = Field(
        ...,
        description="List of recipient entries for bulk generation",
    )

    model_config = ConfigDict(extra="ignore")

    @field_validator("title", "issuer", "issue_date", mode="before")
    @classmethod
    def validate_non_empty_strings(cls, value: Any) -> Any:
        """Ensure required string fields are non-empty after stripping whitespace."""
        if isinstance(value, str) and not value.strip():
            raise ValueError("Field cannot be empty or solely whitespace.")
        return value

    @model_validator(mode="after")
    def validate_recipients_bounds(self) -> "JobCreate":
        """Validate request-level recipient list constraints."""
        settings = get_settings()
        if not self.recipients:
            raise ValueError("Recipient list cannot be empty. At least one recipient is required.")
        if len(self.recipients) > settings.max_recipients_per_job:
            raise ValueError(
                f"Recipient list exceeds maximum allowed size of {settings.max_recipients_per_job} items."
            )
        return self


class JobCreateResponse(BaseModel):
    """Response returned immediately upon accepting a job generation request."""

    job_id: str
    status: JobStatus
    total_recipients: int
    valid_recipients: int
    invalid_recipients: int
    created_at: datetime
    message: str

    model_config = ConfigDict(from_attributes=True)


class CertificateItemResponse(BaseModel):
    """Detailed view of an individual certificate recipient and status."""

    id: str
    name: str
    email: str
    role: Optional[str] = None
    score: Optional[str] = None
    status: CertificateStatus
    error_message: Optional[str] = None
    download_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class JobResponse(BaseModel):
    """Full status response for a certificate generation job, including paginated recipients."""

    id: str
    title: str
    issuer: str
    issue_date: str
    status: JobStatus
    total_count: int
    succeeded_count: int
    failed_count: int
    pending_count: int
    created_at: datetime
    updated_at: datetime
    page: int
    page_size: int
    total_pages: int
    recipients: list[CertificateItemResponse]

    model_config = ConfigDict(from_attributes=True)


class JobRetryResponse(BaseModel):
    """Response returned when triggering a retry for failed certificates."""

    job_id: str
    status: JobStatus
    retried_count: int
    message: str

    model_config = ConfigDict(from_attributes=True)
