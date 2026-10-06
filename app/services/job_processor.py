"""Background processing service for certificate generation jobs."""

import os
from datetime import datetime, timezone
from sqlalchemy import select
from app.core.db import get_db_session
from app.core.logging import get_logger
from app.models.job import (
    CertificateRecipient,
    CertificateStatus,
    FailureType,
    Job,
    JobStatus,
)
from app.services.pdf_generator import generate_certificate_pdf

logger = get_logger(__name__)


def process_job_background(job_id: str) -> None:
    """Process all pending certificates for a given job in the background.

    This function:
    1. Operates within its own isolated DB session context (never shares HTTP request session).
    2. Updates job status to 'processing'.
    3. Iterates over all pending recipients independently.
    4. Commits progress per recipient so real-time status is queryable.
    5. Isolates failures: an unhandled exception for one recipient marks that recipient
       as 'failed' with failure_type='generation', avoiding raw exception leakage.
    6. Is completely idempotent and re-runnable: skips recreation if a valid certificate
       already exists on disk, and can be safely reinvoked on retries.
    7. Updates the final job status to 'completed', 'completed_with_errors', or 'failed'.
    """
    logger.info("Starting background processing for job %s", job_id)

    with get_db_session() as db:
        job = db.get(Job, job_id)
        if not job:
            logger.warning("Job %s not found in database. Aborting processing.", job_id)
            return

        # Fetch all pending recipients using SQLAlchemy 2.0 select
        stmt = (
            select(CertificateRecipient)
            .where(
                CertificateRecipient.job_id == job_id,
                CertificateRecipient.status == CertificateStatus.PENDING,
            )
            .order_by(CertificateRecipient.created_at)
        )
        pending_recipients = list(db.scalars(stmt).all())

        if not pending_recipients:
            logger.info("No pending recipients to process for job %s", job_id)
            # Re-evaluate final status if job was still pending or processing
            _finalize_job_status(job)
            db.commit()
            return

        # Mark job as processing
        job.status = JobStatus.PROCESSING
        job.updated_at = datetime.now(timezone.utc)
        db.commit()

        # Cache job metadata needed for PDF generation
        job_title = job.title
        job_issuer = job.issuer
        job_issue_date = job.issue_date

        for recipient in pending_recipients:
            try:
                # Idempotency check: if valid certificate already exists on disk, reuse it
                if (
                    recipient.certificate_file_path
                    and os.path.exists(recipient.certificate_file_path)
                    and os.path.getsize(recipient.certificate_file_path) > 0
                ):
                    recipient.status = CertificateStatus.SUCCESS
                    recipient.failure_type = None
                    recipient.error_message = None
                    job.succeeded_count += 1
                else:
                    # Generate certificate PDF
                    pdf_path = generate_certificate_pdf(
                        recipient_id=recipient.id,
                        recipient_name=recipient.name,
                        title=job_title,
                        issuer=job_issuer,
                        issue_date=job_issue_date,
                        role=recipient.role,
                        score=recipient.score,
                    )
                    recipient.certificate_file_path = pdf_path
                    recipient.status = CertificateStatus.SUCCESS
                    recipient.failure_type = None
                    recipient.error_message = None
                    job.succeeded_count += 1

            except Exception as exc:
                logger.exception(
                    "Error generating certificate for recipient %s in job %s: %s",
                    recipient.id,
                    job_id,
                    str(exc),
                )
                recipient.status = CertificateStatus.FAILED
                recipient.failure_type = FailureType.GENERATION
                recipient.error_message = (
                    "Certificate generation failed due to an internal rendering or storage error."
                )
                job.failed_count += 1

            finally:
                job.pending_count = max(0, job.pending_count - 1)
                job.updated_at = datetime.now(timezone.utc)
                recipient.updated_at = datetime.now(timezone.utc)
                # Commit after each recipient to guarantee accurate live progress
                db.commit()

        # Finalize job status once all pending recipients are done
        _finalize_job_status(job)
        job.updated_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(
            "Completed processing job %s. Status: %s, Total: %d, Succeeded: %d, Failed: %d",
            job_id,
            job.status.value,
            job.total_count,
            job.succeeded_count,
            job.failed_count,
        )


def _finalize_job_status(job: Job) -> None:
    """Evaluate and assign the terminal status of a job based on counts."""
    if job.pending_count > 0:
        return

    if job.failed_count == 0:
        job.status = JobStatus.COMPLETED
    elif job.succeeded_count > 0:
        job.status = JobStatus.COMPLETED_WITH_ERRORS
    else:
        job.status = JobStatus.FAILED
