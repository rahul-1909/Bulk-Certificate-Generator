"""Tests for downloading single certificates and bulk ZIP archives."""

import io
import os
import zipfile
from fastapi.testclient import TestClient
from app.core.db import get_db_session
from app.models.job import CertificateRecipient, CertificateStatus


def test_download_single_certificate_success(client: TestClient):
    """Verify downloading an individual certificate returns PDF with correct media type."""
    payload = {
        "title": "Systems Engineering",
        "issuer": "Engineering Council",
        "issue_date": "2026-10-07",
        "recipients": [{"name": "Dennis Ritchie", "email": "dennis@example.com"}],
    }

    create_res = client.post("/api/v1/jobs", json=payload)
    job_id = create_res.json()["job_id"]

    job_res = client.get(f"/api/v1/jobs/{job_id}")
    cert_id = job_res.json()["recipients"][0]["id"]

    download_res = client.get(f"/api/v1/certificates/{cert_id}/download")
    assert download_res.status_code == 200
    assert download_res.headers["content-type"] == "application/pdf"
    assert download_res.content.startswith(b"%PDF")


def test_download_single_certificate_not_found(client: TestClient):
    """Verify 404 response for non-existent certificate ID."""
    response = client.get("/api/v1/certificates/non-existent-uuid/download")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_download_single_certificate_pending_status(client: TestClient):
    """Verify 409 response when attempting to download a certificate currently pending."""
    # Create job with recipient manually kept pending in DB
    payload = {
        "title": "Pending Test",
        "issuer": "Issuer",
        "issue_date": "2026-10-07",
        "recipients": [{"name": "Pending User", "email": "pending@example.com"}],
    }
    create_res = client.post("/api/v1/jobs", json=payload)
    job_id = create_res.json()["job_id"]
    cert_id = client.get(f"/api/v1/jobs/{job_id}").json()["recipients"][0]["id"]

    # Temporarily set recipient status to pending in DB
    with get_db_session() as db:
        rec = db.get(CertificateRecipient, cert_id)
        rec.status = CertificateStatus.PENDING
        db.commit()

    response = client.get(f"/api/v1/certificates/{cert_id}/download")
    assert response.status_code == 409
    assert "in progress" in response.json()["detail"].lower()


def test_download_single_certificate_failed_status(client: TestClient):
    """Verify 400 response when attempting to download a failed certificate."""
    payload = {
        "title": "Failed Cert Test",
        "issuer": "Issuer",
        "issue_date": "2026-10-07",
        "recipients": [{"name": "   ", "email": "blank@example.com"}],
    }
    create_res = client.post("/api/v1/jobs", json=payload)
    job_id = create_res.json()["job_id"]
    cert_id = client.get(f"/api/v1/jobs/{job_id}").json()["recipients"][0]["id"]

    response = client.get(f"/api/v1/certificates/{cert_id}/download")
    assert response.status_code == 400
    assert "failed" in response.json()["detail"].lower()


def test_download_single_certificate_file_missing_from_disk(client: TestClient):
    """Verify 404 response if database records success but the PDF file was deleted from disk."""
    payload = {
        "title": "Missing File Test",
        "issuer": "Issuer",
        "issue_date": "2026-10-07",
        "recipients": [{"name": "User", "email": "user@example.com"}],
    }
    create_res = client.post("/api/v1/jobs", json=payload)
    job_id = create_res.json()["job_id"]
    cert_id = client.get(f"/api/v1/jobs/{job_id}").json()["recipients"][0]["id"]

    # Remove physical file
    with get_db_session() as db:
        rec = db.get(CertificateRecipient, cert_id)
        if rec.certificate_file_path and os.path.exists(rec.certificate_file_path):
            os.remove(rec.certificate_file_path)

    response = client.get(f"/api/v1/certificates/{cert_id}/download")
    assert response.status_code == 404
    assert "missing" in response.json()["detail"].lower()


def test_download_all_certificates_zip_success(client: TestClient):
    """Verify downloading all completed certificates for a job as a valid ZIP archive."""
    payload = {
        "title": "Batch ZIP Test",
        "issuer": "Issuer Org",
        "issue_date": "2026-10-07",
        "recipients": [
            {"name": "Winner One", "email": "winner1@example.com"},
            {"name": "Winner Two", "email": "winner2@example.com"},
        ],
    }

    create_res = client.post("/api/v1/jobs", json=payload)
    job_id = create_res.json()["job_id"]

    zip_res = client.get(f"/api/v1/jobs/{job_id}/download-all")
    assert zip_res.status_code == 200
    assert zip_res.headers["content-type"] == "application/zip"
    assert "attachment" in zip_res.headers["content-disposition"]

    # Inspect ZIP contents
    with zipfile.ZipFile(io.BytesIO(zip_res.content)) as zip_archive:
        namelist = zip_archive.namelist()
        assert len(namelist) == 2
        for filename in namelist:
            assert filename.endswith(".pdf")
            file_data = zip_archive.read(filename)
            assert file_data.startswith(b"%PDF")


def test_download_all_certificates_not_found(client: TestClient):
    """Verify 404 response when requesting ZIP for a non-existent job."""
    response = client.get("/api/v1/jobs/non-existent-uuid/download-all")
    assert response.status_code == 404


def test_download_all_certificates_none_available(client: TestClient):
    """Verify 400 response when job has no successful certificates to archive."""
    payload = {
        "title": "No Success Job",
        "issuer": "Issuer",
        "issue_date": "2026-10-07",
        "recipients": [{"name": "   ", "email": "bad@example.com"}],
    }
    create_res = client.post("/api/v1/jobs", json=payload)
    job_id = create_res.json()["job_id"]

    response = client.get(f"/api/v1/jobs/{job_id}/download-all")
    assert response.status_code == 400
    assert "no successfully generated certificates" in response.json()["detail"].lower()
