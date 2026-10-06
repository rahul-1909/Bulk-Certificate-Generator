"""Regression tests for retry safety, validation persistence, and input coercion."""

from datetime import datetime, timedelta, timezone

from app.core.db import get_db_session
from app.models.job import CertificateRecipient, CertificateStatus, Job, JobStatus
from app.services import job_processor as processor_module


def _payload(recipients, title="Regression Course"):
    return {
        "title": title,
        "issuer": "Test Org",
        "issue_date": "2026-10-07",
        "recipients": recipients,
    }


def test_retry_does_not_regenerate_duplicate_email_recipient(client):
    """A duplicate-email recipient is a permanent validation failure and must stay failed."""
    res = client.post(
        "/api/v1/jobs",
        json=_payload(
            [
                {"name": "First", "email": "same@example.com"},
                {"name": "Second", "email": "same@example.com"},
            ]
        ),
    )
    job_id = res.json()["job_id"]
    status_before = client.get(f"/api/v1/jobs/{job_id}").json()
    assert status_before["succeeded_count"] == 1
    assert status_before["failed_count"] == 1

    retry = client.post(f"/api/v1/jobs/{job_id}/retry")
    assert retry.status_code == 202
    assert retry.json()["retried_count"] == 0

    status_after = client.get(f"/api/v1/jobs/{job_id}").json()
    assert status_after["succeeded_count"] == 1
    assert status_after["failed_count"] == 1
    assert status_after["status"] == "completed_with_errors"


def test_duplicate_detection_is_case_insensitive(client):
    res = client.post(
        "/api/v1/jobs",
        json=_payload(
            [
                {"name": "Lower", "email": "case@example.com"},
                {"name": "Upper", "email": "CASE@Example.com"},
            ]
        ),
    )
    assert res.json()["valid_recipients"] == 1
    assert res.json()["invalid_recipients"] == 1


def test_overlong_fields_are_stored_within_column_limits(client):
    """Invalid over-long values must be truncated so strict databases (PostgreSQL) accept them."""
    res = client.post(
        "/api/v1/jobs",
        json=_payload(
            [
                {"name": "N" * 400, "email": "long@example.com", "role": "R" * 400, "score": "S" * 300},
                {"name": "Fine", "email": "fine@example.com"},
            ]
        ),
    )
    assert res.status_code == 202
    job_id = res.json()["job_id"]
    with get_db_session() as db:
        rows = db.query(CertificateRecipient).filter(CertificateRecipient.job_id == job_id).all()
        for row in rows:
            assert len(row.name) <= 255
            assert len(row.email) <= 255
            assert row.role is None or len(row.role) <= 255
            assert row.score is None or len(row.score) <= 100


def test_overlong_recipient_is_not_retried_after_truncation(client):
    res = client.post(
        "/api/v1/jobs",
        json=_payload([{"name": "N" * 400, "email": "long@example.com"}, {"name": "Ok", "email": "ok@example.com"}]),
    )
    job_id = res.json()["job_id"]
    retry = client.post(f"/api/v1/jobs/{job_id}/retry")
    assert retry.json()["retried_count"] == 0
    after = client.get(f"/api/v1/jobs/{job_id}").json()
    assert after["succeeded_count"] == 1
    assert after["failed_count"] == 1


def test_numeric_json_values_are_coerced_not_rejected(client):
    """A numeric score (e.g. 96) must not make the whole request fail with 422."""
    res = client.post(
        "/api/v1/jobs",
        json=_payload([{"name": "Numeric", "email": "num@example.com", "score": 96}]),
    )
    assert res.status_code == 202
    job_id = res.json()["job_id"]
    status = client.get(f"/api/v1/jobs/{job_id}").json()
    assert status["succeeded_count"] == 1
    assert status["recipients"][0]["score"] == "96"


def _make_job_in_state(client, status, age_minutes):
    res = client.post("/api/v1/jobs", json=_payload([{"name": "A", "email": "a@example.com"}]))
    job_id = res.json()["job_id"]
    with get_db_session() as db:
        job = db.get(Job, job_id)
        job.status = status
        job.updated_at = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
        db.commit()
    return job_id


def test_retry_rejected_while_job_actively_processing(client):
    job_id = _make_job_in_state(client, JobStatus.PROCESSING, age_minutes=0)
    response = client.post(f"/api/v1/jobs/{job_id}/retry")
    assert response.status_code == 409


def test_retry_allowed_for_stale_processing_job(client):
    """A job stuck in 'processing' after a crash (stale updated_at) must still be resumable."""
    res = client.post("/api/v1/jobs", json=_payload([{"name": "A", "email": "a@example.com"}]))
    job_id = res.json()["job_id"]
    with get_db_session() as db:
        job = db.get(Job, job_id)
        recipient = db.query(CertificateRecipient).filter_by(job_id=job_id).one()
        recipient.status = CertificateStatus.PENDING
        recipient.certificate_file_path = None
        job.status = JobStatus.PROCESSING
        job.pending_count = 1
        job.succeeded_count = 0
        db.commit()
        # updated_at has an onupdate hook, so force an old timestamp with a raw UPDATE
        from sqlalchemy import update

        db.execute(
            update(Job).where(Job.id == job_id).values(updated_at=datetime.now(timezone.utc) - timedelta(minutes=30))
        )
        db.commit()
    response = client.post(f"/api/v1/jobs/{job_id}/retry")
    assert response.status_code == 202
    assert response.json()["retried_count"] == 1
    assert client.get(f"/api/v1/jobs/{job_id}").json()["status"] == "completed"


def test_generation_failure_stays_retryable(client, monkeypatch):
    """A system error while rendering is a generation failure: /retry must pick it up."""

    def boom(*args, **kwargs):
        raise RuntimeError("Transient disk lock exception")

    original = processor_module.generate_certificate_pdf
    monkeypatch.setattr(processor_module, "generate_certificate_pdf", boom)
    res = client.post("/api/v1/jobs", json=_payload([{"name": "Glitch", "email": "g@example.com"}]))
    job_id = res.json()["job_id"]
    status = client.get(f"/api/v1/jobs/{job_id}").json()
    assert status["failed_count"] == 1
    assert status["status"] == "failed"

    monkeypatch.setattr(processor_module, "generate_certificate_pdf", original)
    retry = client.post(f"/api/v1/jobs/{job_id}/retry")
    assert retry.status_code == 202
    assert retry.json()["retried_count"] == 1
    final = client.get(f"/api/v1/jobs/{job_id}").json()
    assert final["status"] == "completed"
    assert final["succeeded_count"] == 1
    assert final["failed_count"] == 0
    assert final["pending_count"] == 0


def test_retry_message_when_nothing_to_retry(client):
    res = client.post("/api/v1/jobs", json=_payload([{"name": "Good", "email": "good@example.com"}]))
    retry = client.post(f"/api/v1/jobs/{res.json()['job_id']}/retry")
    assert retry.json()["retried_count"] == 0
    assert "No failed certificates" in retry.json()["message"]


def test_mixed_batch_counts_and_zip_only_contains_successes(client):
    import io, zipfile

    res = client.post(
        "/api/v1/jobs",
        json=_payload(
            [
                {"name": "Valid One", "email": "v1@example.com"},
                {"name": "   ", "email": "blank@example.com"},
                {"name": "Bad Email", "email": "nope"},
                {"name": "Valid Two", "email": "v2@example.com"},
            ]
        ),
    )
    job_id = res.json()["job_id"]
    status = client.get(f"/api/v1/jobs/{job_id}").json()
    assert (status["succeeded_count"], status["failed_count"], status["pending_count"]) == (2, 2, 0)
    assert status["status"] == "completed_with_errors"
    zipped = client.get(f"/api/v1/jobs/{job_id}/download-all")
    assert zipped.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(zipped.content)).namelist()
    assert len(names) == 2


def test_rerunning_processor_does_not_change_counts(client):
    res = client.post("/api/v1/jobs", json=_payload([{"name": "Once", "email": "once@example.com"}]))
    job_id = res.json()["job_id"]
    processor_module.process_job_background(job_id)
    processor_module.process_job_background(job_id)
    status = client.get(f"/api/v1/jobs/{job_id}").json()
    assert (status["succeeded_count"], status["failed_count"], status["pending_count"]) == (1, 0, 0)
