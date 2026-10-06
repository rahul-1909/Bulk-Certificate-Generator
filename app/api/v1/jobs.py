"""API endpoints for managing certificate generation jobs."""

import math
from datetime import datetime, timedelta, timezone
from typing import Optional, Set
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.db import get_db
from app.core.logging import get_logger
from app.models.job import (
    CertificateRecipient,
    CertificateStatus,
    FailureType,
    Job,
    JobStatus,
)
from app.schemas.job import (
    CertificateItemResponse,
    JobCreate,
    JobCreateResponse,
    JobResponse,
    JobRetryResponse,
)
from app.services.job_processor import process_job_background
from app.services.validator import validate_recipient

logger = get_logger(__name__)
router = APIRouter(prefix="/jobs", tags=["Jobs"])

# A job whose last update is newer than this is assumed to still have a live worker.
# The worker commits after every recipient, so a healthy job keeps refreshing updated_at.
ACTIVE_JOB_WINDOW = timedelta(minutes=5)


def _clip(value: Optional[str], limit: int) -> Optional[str]:
    """Strip and truncate text so it always fits its database column (PostgreSQL is strict)."""
    if value is None:
        return None
    return str(value).strip()[:limit]


def _is_job_active(job: Job) -> bool:
    """True if the job is pending/processing and was updated recently (worker likely alive)."""
    if job.status not in (JobStatus.PENDING, JobStatus.PROCESSING):
        return False
    updated = job.updated_at
    if updated.tzinfo is None:  # SQLite returns naive datetimes
        updated = updated.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - updated < ACTIVE_JOB_WINDOW


@router.post(
    "",
    response_model=JobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create a bulk certificate generation job",
    description=(
        "Accepts certificate metadata and a list of recipients. Validates recipients "
        "individually, initiates background PDF generation for valid entries, and "
        "records any invalid entries as failed without rejecting the overall batch."
    ),
)
def create_job(
    payload: JobCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> JobCreateResponse:
    """Create a new certificate generation job and enqueue background processing."""
    settings = get_settings()

    seen_emails: Set[str] = set()
    total_recipients = len(payload.recipients)
    valid_recipients_count = 0
    invalid_recipients_count = 0

    # Initialize Job record
    job = Job(
        title=payload.title.strip(),
        issuer=payload.issuer.strip(),
        issue_date=payload.issue_date.strip(),
        status=JobStatus.PENDING,
        total_count=total_recipients,
        succeeded_count=0,
        failed_count=0,
        pending_count=0,
    )
    db.add(job)
    db.flush()  # Populates job.id

    # Evaluate each recipient individually
    for rec_in in payload.recipients:
        is_valid, error_reason = validate_recipient(rec_in, seen_emails)

        if is_valid:
            valid_recipients_count += 1
            recipient = CertificateRecipient(
                job_id=job.id,
                name=_clip(rec_in.name, 255) or "",
                email=_clip(rec_in.email, 255) or "",
                role=_clip(rec_in.role, 255) or None,
                score=_clip(rec_in.score, 100) or None,
                status=CertificateStatus.PENDING,
                error_message=None,
            )
        else:
            invalid_recipients_count += 1
            recipient = CertificateRecipient(
                job_id=job.id,
                # Truncate: invalid rows may hold over-long values that would overflow
                # the column (and crash the whole request) on PostgreSQL.
                name=_clip(rec_in.name, 255) or "",
                email=_clip(rec_in.email, 255) or "",
                role=_clip(rec_in.role, 255) or None,
                score=_clip(rec_in.score, 100) or None,
                status=CertificateStatus.FAILED,
                error_message=error_reason,
                failure_type=FailureType.VALIDATION,
            )
        db.add(recipient)

    job.pending_count = valid_recipients_count
    job.failed_count = invalid_recipients_count

    # If every recipient was invalid, mark job completed_with_errors or failed immediately
    if valid_recipients_count == 0:
        job.status = (
            JobStatus.FAILED
            if total_recipients > 0
            else JobStatus.COMPLETED
        )
        db.commit()
        db.refresh(job)
        return JobCreateResponse(
            job_id=job.id,
            status=job.status,
            total_recipients=total_recipients,
            valid_recipients=valid_recipients_count,
            invalid_recipients=invalid_recipients_count,
            created_at=job.created_at,
            message="Job created, but all recipient records failed validation.",
        )

    db.commit()
    db.refresh(job)

    # Dispatch processing: synchronously if configured (e.g. testing) or via background task
    if settings.run_background_tasks_synchronously:
        process_job_background(job.id)
        db.refresh(job)
    else:
        background_tasks.add_task(process_job_background, job.id)

    return JobCreateResponse(
        job_id=job.id,
        status=job.status,
        total_recipients=total_recipients,
        valid_recipients=valid_recipients_count,
        invalid_recipients=invalid_recipients_count,
        created_at=job.created_at,
        message="Job accepted and queued for certificate generation.",
    )


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="Get job status and paginated recipient progress",
    description="Returns aggregate job metrics and a paginated list of recipient statuses.",
)
def get_job(
    job_id: str,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    db: Session = Depends(get_db),
) -> JobResponse:
    """Retrieve detailed status for a specific job."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found.",
        )

    # Count total recipients using SQLAlchemy 2.0 select
    count_stmt = (
        select(func.count())
        .select_from(CertificateRecipient)
        .where(CertificateRecipient.job_id == job_id)
    )
    total_recipients = db.scalar(count_stmt) or 0
    total_pages = max(1, math.ceil(total_recipients / page_size))

    # Paginate recipients
    offset = (page - 1) * page_size
    recipients_stmt = (
        select(CertificateRecipient)
        .where(CertificateRecipient.job_id == job_id)
        .order_by(CertificateRecipient.created_at)
        .offset(offset)
        .limit(page_size)
    )
    recipients_query = list(db.scalars(recipients_stmt).all())

    recipient_items = []
    for r in recipients_query:
        download_url = (
            f"/api/v1/certificates/{r.id}/download"
            if r.status == CertificateStatus.SUCCESS
            else None
        )
        recipient_items.append(
            CertificateItemResponse(
                id=r.id,
                name=r.name,
                email=r.email,
                role=r.role,
                score=r.score,
                status=r.status,
                failure_type=r.failure_type,
                error_message=r.error_message,
                download_url=download_url,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
        )

    return JobResponse(
        id=job.id,
        title=job.title,
        issuer=job.issuer,
        issue_date=job.issue_date,
        status=job.status,
        total_count=job.total_count,
        succeeded_count=job.succeeded_count,
        failed_count=job.failed_count,
        pending_count=job.pending_count,
        created_at=job.created_at,
        updated_at=job.updated_at,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        recipients=recipient_items,
    )


@router.post(
    "/{job_id}/retry",
    response_model=JobRetryResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Retry failed certificates for a job",
    description=(
        "Resets failed certificates that suffered transient generation errors to pending, "
        "resumes any interrupted pending recipients (e.g. after server restart), "
        "and queues regeneration while preserving permanent validation errors."
    ),
)
def retry_failed_certificates(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> JobRetryResponse:
    """Reset transient generation failures and resume pending recipients after interruption."""
    settings = get_settings()
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found.",
        )

    # Refuse while a worker is (probably) still running: a second worker would process the
    # same recipients and double-count. A job stuck after a crash has a stale updated_at,
    # so it can still be resumed.
    if _is_job_active(job):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job is currently being processed. Retry once it finishes or becomes stale.",
        )

    # 1. Stuck pending recipients (e.g. if worker crashed mid-job)
    stuck_stmt = select(CertificateRecipient).where(
        CertificateRecipient.job_id == job_id,
        CertificateRecipient.status == CertificateStatus.PENDING,
    )
    stuck_pending_recipients = list(db.scalars(stuck_stmt).all())

    # 2. Transient generation failures only
    gen_failed_stmt = select(CertificateRecipient).where(
        CertificateRecipient.job_id == job_id,
        CertificateRecipient.status == CertificateStatus.FAILED,
        CertificateRecipient.failure_type == FailureType.GENERATION,
    )
    generation_failed_recipients = list(db.scalars(gen_failed_stmt).all())

    # 3. Any failed recipients not in generation_failed are permanently invalid
    total_failed_stmt = (
        select(func.count())
        .select_from(CertificateRecipient)
        .where(
            CertificateRecipient.job_id == job_id,
            CertificateRecipient.status == CertificateStatus.FAILED,
        )
    )
    total_failed = db.scalar(total_failed_stmt) or 0
    permanently_invalid_count = total_failed - len(generation_failed_recipients)

    total_to_process = len(stuck_pending_recipients) + len(generation_failed_recipients)

    if total_to_process == 0:
        if permanently_invalid_count > 0:
            msg = (
                f"No retryable certificates found. {permanently_invalid_count} recipient(s) "
                f"failed permanent validation (blank name, invalid email, or duplicate) and cannot be generated."
            )
        else:
            msg = "No failed certificates to retry for this job."
        return JobRetryResponse(
            job_id=job.id,
            status=job.status,
            retried_count=0,
            message=msg,
        )

    # Reset eligible generation failures to pending
    for r in generation_failed_recipients:
        r.status = CertificateStatus.PENDING
        r.failure_type = None
        r.error_message = None

    job.pending_count = total_to_process
    job.failed_count = permanently_invalid_count
    job.status = JobStatus.PENDING

    db.commit()
    db.refresh(job)

    if settings.run_background_tasks_synchronously:
        process_job_background(job.id)
        db.refresh(job)
    else:
        background_tasks.add_task(process_job_background, job.id)

    msg = f"Queued retry/resumption for {total_to_process} certificate(s)."
    if permanently_invalid_count > 0:
        msg += f" ({permanently_invalid_count} permanently invalid recipient(s) excluded)."

    return JobRetryResponse(
        job_id=job.id,
        status=job.status,
        retried_count=total_to_process,
        message=msg,
    )
