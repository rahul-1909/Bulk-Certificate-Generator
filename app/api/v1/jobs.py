"""API endpoints for managing certificate generation jobs."""

import math
from typing import Set
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.db import get_db
from app.core.logging import get_logger
from app.models.job import CertificateRecipient, CertificateStatus, Job, JobStatus
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
                name=rec_in.name.strip(),
                email=rec_in.email.strip(),
                role=rec_in.role.strip() if rec_in.role else None,
                score=rec_in.score.strip() if rec_in.score else None,
                status=CertificateStatus.PENDING,
                error_message=None,
            )
        else:
            invalid_recipients_count += 1
            recipient = CertificateRecipient(
                job_id=job.id,
                name=rec_in.name.strip() if rec_in.name else "",
                email=rec_in.email.strip() if rec_in.email else "",
                role=rec_in.role.strip() if rec_in.role else None,
                score=rec_in.score.strip() if rec_in.score else None,
                status=CertificateStatus.FAILED,
                error_message=error_reason,
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

    # Count total recipients
    total_recipients = (
        db.query(CertificateRecipient)
        .filter(CertificateRecipient.job_id == job_id)
        .count()
    )
    total_pages = max(1, math.ceil(total_recipients / page_size))

    # Paginate recipients
    offset = (page - 1) * page_size
    recipients_query = (
        db.query(CertificateRecipient)
        .filter(CertificateRecipient.job_id == job_id)
        .order_by(CertificateRecipient.created_at)
        .offset(offset)
        .limit(page_size)
        .all()
    )

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
    description="Resets all failed recipients for this job to pending and queues background regeneration.",
)
def retry_failed_certificates(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> JobRetryResponse:
    """Reset failed recipients in a job and re-queue certificate generation."""
    settings = get_settings()
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found.",
        )

    failed_recipients = (
        db.query(CertificateRecipient)
        .filter(
            CertificateRecipient.job_id == job_id,
            CertificateRecipient.status == CertificateStatus.FAILED,
        )
        .all()
    )

    if not failed_recipients:
        return JobRetryResponse(
            job_id=job.id,
            status=job.status,
            retried_count=0,
            message="No failed certificates to retry for this job.",
        )

    retried_count = len(failed_recipients)
    for r in failed_recipients:
        r.status = CertificateStatus.PENDING
        r.error_message = None

    job.pending_count += retried_count
    job.failed_count = max(0, job.failed_count - retried_count)
    job.status = JobStatus.PENDING

    db.commit()
    db.refresh(job)

    if settings.run_background_tasks_synchronously:
        process_job_background(job.id)
        db.refresh(job)
    else:
        background_tasks.add_task(process_job_background, job.id)

    return JobRetryResponse(
        job_id=job.id,
        status=job.status,
        retried_count=retried_count,
        message=f"Queued retry for {retried_count} failed certificate(s).",
    )
