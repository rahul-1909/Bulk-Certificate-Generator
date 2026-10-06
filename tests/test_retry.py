"""Tests for retrying failed certificates on a job."""

import pytest
from fastapi.testclient import TestClient
import app.services.job_processor as processor_module


def test_retry_failed_certificates_success(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """Test that failed certificates can be retried and successfully processed on subsequent attempts."""
    should_fail = True
    original_generate = processor_module.generate_certificate_pdf

    def conditionally_flaky_generate(**kwargs):
        if should_fail and kwargs.get("recipient_name") == "Temporary Glitch User":
            raise RuntimeError("Transient disk lock exception")
        return original_generate(**kwargs)

    monkeypatch.setattr(processor_module, "generate_certificate_pdf", conditionally_flaky_generate)

    payload = {
        "title": "Cloud Resilience Certification",
        "issuer": "Resilience Board",
        "issue_date": "2026-10-07",
        "recipients": [
            {"name": "Stable User", "email": "stable@example.com"},
            {"name": "Temporary Glitch User", "email": "glitch@example.com"},
        ],
    }

    create_res = client.post("/api/v1/jobs", json=payload)
    job_id = create_res.json()["job_id"]

    # Initial check: 1 succeeded, 1 failed
    job_res = client.get(f"/api/v1/jobs/{job_id}")
    assert job_res.status_code == 200
    job_data = job_res.json()
    assert job_data["status"] == "completed_with_errors"
    assert job_data["failed_count"] == 1
    assert job_data["succeeded_count"] == 1

    # Now transient failure is resolved
    should_fail = False

    # Trigger retry endpoint
    retry_res = client.post(f"/api/v1/jobs/{job_id}/retry")
    assert retry_res.status_code == 202
    retry_data = retry_res.json()
    assert retry_data["retried_count"] == 1

    # Verify updated job status
    updated_job_res = client.get(f"/api/v1/jobs/{job_id}")
    assert updated_job_res.status_code == 200
    updated_job = updated_job_res.json()
    assert updated_job["status"] == "completed"
    assert updated_job["failed_count"] == 0
    assert updated_job["succeeded_count"] == 2
    assert updated_job["pending_count"] == 0


def test_retry_when_no_failed_certificates(client: TestClient):
    """Verify calling retry on a job with zero failed certificates returns 0 retried count."""
    payload = {
        "title": "Clean Job",
        "issuer": "Issuer",
        "issue_date": "2026-10-07",
        "recipients": [{"name": "Good User", "email": "good@example.com"}],
    }
    create_res = client.post("/api/v1/jobs", json=payload)
    job_id = create_res.json()["job_id"]

    retry_res = client.post(f"/api/v1/jobs/{job_id}/retry")
    assert retry_res.status_code == 202
    assert retry_res.json()["retried_count"] == 0
    assert "no pending or failed certificates to retry" in retry_res.json()["message"].lower()


def test_retry_non_existent_job(client: TestClient):
    """Verify 404 response when trying to retry a non-existent job."""
    response = client.post("/api/v1/jobs/missing-job-uuid/retry")
    assert response.status_code == 404


def test_retry_preserves_permanently_invalid_validation_failures(client: TestClient):
    """Verify retry ignores recipients with permanently invalid data (blank name, invalid email)."""
    payload = {
        "title": "Validation Failure Job",
        "issuer": "Issuer",
        "issue_date": "2026-10-07",
        "recipients": [
            {"name": "   ", "email": "blank@example.com"},
            {"name": "Bad Email", "email": "not-valid-syntax"},
        ],
    }
    create_res = client.post("/api/v1/jobs", json=payload)
    job_id = create_res.json()["job_id"]

    retry_res = client.post(f"/api/v1/jobs/{job_id}/retry")
    assert retry_res.status_code == 202
    data = retry_res.json()
    assert data["retried_count"] == 0
    assert "permanent validation" in data["message"].lower()

    # Verify recipients are still failed with their validation errors
    job_res = client.get(f"/api/v1/jobs/{job_id}")
    assert job_res.status_code == 200
    assert job_res.json()["failed_count"] == 2
    for r in job_res.json()["recipients"]:
        assert r["status"] == "failed"


def test_retry_resumes_interrupted_pending_recipients(client: TestClient):
    """Verify retry picks up recipients left in pending status after an interruption or crash."""
    from app.core.db import get_db_session
    from app.models.job import CertificateRecipient, CertificateStatus

    payload = {
        "title": "Interrupted Job",
        "issuer": "Issuer",
        "issue_date": "2026-10-07",
        "recipients": [
            {"name": "Done User", "email": "done@example.com"},
            {"name": "Interrupted User", "email": "interrupted@example.com"},
        ],
    }
    create_res = client.post("/api/v1/jobs", json=payload)
    job_id = create_res.json()["job_id"]

    # Simulate an interruption by manually reverting one recipient back to PENDING and decrementing succeeded count
    with get_db_session() as db:
        from app.models.job import Job, JobStatus
        job_obj = db.get(Job, job_id)
        rec = (
            db.query(CertificateRecipient)
            .filter(CertificateRecipient.email == "interrupted@example.com")
            .first()
        )
        rec.status = CertificateStatus.PENDING
        rec.certificate_file_path = None
        job_obj.succeeded_count = 1
        job_obj.pending_count = 1
        job_obj.status = JobStatus.PROCESSING
        db.commit()

    # Call retry
    retry_res = client.post(f"/api/v1/jobs/{job_id}/retry")
    assert retry_res.status_code == 202
    assert retry_res.json()["retried_count"] >= 1

    # Verify both recipients are now completed
    job_res = client.get(f"/api/v1/jobs/{job_id}")
    assert job_res.status_code == 200
    assert job_res.json()["status"] == "completed"
    assert job_res.json()["succeeded_count"] == 2
    assert job_res.json()["pending_count"] == 0
