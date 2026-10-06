"""API endpoints for downloading individual and bulk certificates."""

import io
import os
import zipfile
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.models.job import CertificateRecipient, CertificateStatus, Job

router = APIRouter(tags=["Certificates"])


@router.get(
    "/certificates/{certificate_id}/download",
    summary="Download a single certificate PDF",
    description="Returns the generated PDF certificate for a recipient.",
    response_class=FileResponse,
)
def download_certificate(
    certificate_id: str,
    db: Session = Depends(get_db),
):
    """Download a single generated certificate PDF."""
    recipient = db.get(CertificateRecipient, certificate_id)
    if not recipient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate with ID '{certificate_id}' not found.",
        )

    if recipient.status == CertificateStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Certificate generation is currently in progress. Please check back shortly.",
        )

    if recipient.status == CertificateStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Certificate generation failed: {recipient.error_message or 'Unknown error'}",
        )

    if (
        not recipient.certificate_file_path
        or not os.path.exists(recipient.certificate_file_path)
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificate PDF file is missing from storage.",
        )

    filename = os.path.basename(recipient.certificate_file_path)
    return FileResponse(
        path=recipient.certificate_file_path,
        media_type="application/pdf",
        filename=filename,
    )


@router.get(
    "/jobs/{job_id}/download-all",
    summary="Download all certificates for a job as a ZIP file",
    description="Creates and streams a ZIP archive containing all successfully generated certificates for the job.",
)
def download_all_certificates(
    job_id: str,
    db: Session = Depends(get_db),
):
    """Download all completed certificates for a job as a single ZIP archive."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found.",
        )

    stmt = select(CertificateRecipient).where(
        CertificateRecipient.job_id == job_id,
        CertificateRecipient.status == CertificateStatus.SUCCESS,
    )
    successful_recipients = list(db.scalars(stmt).all())

    valid_files = [
        r.certificate_file_path
        for r in successful_recipients
        if r.certificate_file_path and os.path.exists(r.certificate_file_path)
    ]

    if not valid_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No successfully generated certificates are currently available for download.",
        )

    # Build ZIP archive in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for file_path in valid_files:
            arcname = os.path.basename(file_path)
            zip_file.write(file_path, arcname=arcname)

    zip_buffer.seek(0)
    zip_data = zip_buffer.getvalue()

    headers = {
        "Content-Disposition": f'attachment; filename="job_{job_id}_certificates.zip"',
        "Content-Length": str(len(zip_data)),
    }

    return Response(
        content=zip_data,
        media_type="application/zip",
        headers=headers,
    )
