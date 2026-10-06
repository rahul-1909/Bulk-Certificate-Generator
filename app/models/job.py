"""SQLAlchemy ORM models for jobs and certificate recipients."""

import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from app.core.db import Base


def generate_uuid() -> str:
    """Generate a random UUID4 hex string."""
    return str(uuid.uuid4())


def utc_now() -> datetime:
    """Return current UTC datetime with timezone information."""
    return datetime.now(timezone.utc)


class JobStatus(str, enum.Enum):
    """Lifecycle statuses for a certificate generation job."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


class CertificateStatus(str, enum.Enum):
    """Status for an individual recipient's certificate generation."""

    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class FailureType:
    """Why a recipient failed, so retry can tell fixable errors from bad input."""

    VALIDATION = "validation"  # bad input (blank name, duplicate email, ...): never retried
    GENERATION = "generation"  # system error while rendering the PDF: safe to retry


class Job(Base):
    """Database model representing a bulk certificate generation job."""

    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    title = Column(String(255), nullable=False)
    issuer = Column(String(255), nullable=False)
    issue_date = Column(String(50), nullable=False)

    status = Column(
        Enum(JobStatus),
        nullable=False,
        default=JobStatus.PENDING,
        index=True,
    )

    total_count = Column(Integer, nullable=False, default=0)
    succeeded_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    pending_count = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    # Relationships
    recipients = relationship(
        "CertificateRecipient",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="CertificateRecipient.created_at",
    )


class CertificateRecipient(Base):
    """Database model representing an individual recipient and their generated certificate."""

    __tablename__ = "certificate_recipients"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    job_id = Column(
        String(36),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False, index=True)
    role = Column(String(255), nullable=True)
    score = Column(String(100), nullable=True)

    status = Column(
        Enum(CertificateStatus),
        nullable=False,
        default=CertificateStatus.PENDING,
        index=True,
    )
    failure_type = Column(String(50), nullable=True, index=True)
    error_message = Column(Text, nullable=True)
    certificate_file_path = Column(String(512), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    # Relationships
    job = relationship("Job", back_populates="recipients")
