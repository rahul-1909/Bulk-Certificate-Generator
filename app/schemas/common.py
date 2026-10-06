"""Common Pydantic schemas."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check endpoint response schema."""

    status: str = Field(..., description="Overall service status")
    database: str = Field(..., description="Database connectivity status")
    storage: str = Field(..., description="Storage directory status")
    version: str = Field(default="1.0.0", description="API version")
