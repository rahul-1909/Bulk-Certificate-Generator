"""Tests for Job creation, request-level validation, and per-recipient failure isolation."""

import pytest
from fastapi.testclient import TestClient
from app.core.config import get_settings


def test_create_job_success(client: TestClient):
    """Verify standard success path returns 202 with job_id and correctly records recipients."""
    payload = {
        "title": "Cloud Architecture Masterclass",
        "issuer": "Global Tech Academy",
        "issue_date": "2026-10-07",
        "recipients": [
            {
                "name": "Alice Johnson",
                "email": "alice@example.com",
                "role": "Lead Architect",
                "score": "98%",
            },
            {
                "name": "Bob Smith",
                "email": "bob@example.com",
                "role": "Participant",
            },
        ],
    }

    response = client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 202
    data = response.json()

    assert "job_id" in data
    assert data["total_recipients"] == 2
    assert data["valid_recipients"] == 2
    assert data["invalid_recipients"] == 0
    assert data["status"] in ["pending", "processing", "completed"]

    # Verify job is queryable
    job_id = data["job_id"]
    get_res = client.get(f"/api/v1/jobs/{job_id}")
    assert get_res.status_code == 200
    job_data = get_res.json()
    assert job_data["id"] == job_id
    assert job_data["title"] == "Cloud Architecture Masterclass"
    assert job_data["total_count"] == 2
    assert job_data["succeeded_count"] == 2


def test_request_validation_missing_fields(client: TestClient):
    """Verify request-level 422 errors when required fields are missing."""
    # Missing title
    res1 = client.post(
        "/api/v1/jobs",
        json={
            "issuer": "Tech Institute",
            "issue_date": "2026-10-07",
            "recipients": [{"name": "A", "email": "a@example.com"}],
        },
    )
    assert res1.status_code == 422

    # Blank issuer (whitespace only)
    res2 = client.post(
        "/api/v1/jobs",
        json={
            "title": "Course",
            "issuer": "   ",
            "issue_date": "2026-10-07",
            "recipients": [{"name": "A", "email": "a@example.com"}],
        },
    )
    assert res2.status_code == 422


def test_request_validation_empty_recipients_list(client: TestClient):
    """Verify request-level 422 error when recipients list is empty."""
    payload = {
        "title": "Python Workshop",
        "issuer": "Academy",
        "issue_date": "2026-10-07",
        "recipients": [],
    }
    response = client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 422
    assert "detail" in response.json()


def test_request_validation_exceeding_max_recipients(client: TestClient):
    """Verify request-level 422 error when recipient count exceeds maximum configured limit."""
    settings = get_settings()
    original_max = settings.max_recipients_per_job
    try:
        settings.max_recipients_per_job = 3
        payload = {
            "title": "Overload Test",
            "issuer": "Academy",
            "issue_date": "2026-10-07",
            "recipients": [
                {"name": f"User {i}", "email": f"user{i}@example.com"}
                for i in range(4)
            ],
        }
        response = client.post("/api/v1/jobs", json=payload)
        assert response.status_code == 422
        data = response.json()
        assert "exceeds maximum allowed size" in str(data)
    finally:
        settings.max_recipients_per_job = original_max


def test_per_recipient_validation_mixed_batch(client: TestClient):
    """Verify per-recipient invalid data is marked failed while valid ones proceed to succeed.

    Batch contains:
    - 3 valid recipients
    - 1 recipient with blank name
    - 1 recipient with invalid email
    - 1 recipient with duplicate email within request
    - 1 recipient with over-long name (> 255 chars)
    """
    long_name = "X" * 300
    payload = {
        "title": "Enterprise Security Certification",
        "issuer": "CyberSec Global",
        "issue_date": "2026-10-07",
        "recipients": [
            {"name": "Valid One", "email": "valid1@example.com", "role": "Analyst"},
            {"name": "   ", "email": "blank_name@example.com"},  # Blank name
            {"name": "Valid Two", "email": "valid2@example.com", "score": "95%"},
            {"name": "Bad Email", "email": "not-a-valid-email"},  # Invalid email
            {"name": "Duplicate Copy", "email": "valid1@example.com"},  # Duplicate email
            {"name": long_name, "email": "overlong@example.com"},  # Over-long name
            {"name": "Valid Three", "email": "valid3@example.com"},
        ],
    }

    response = client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 202
    data = response.json()

    assert data["total_recipients"] == 7
    assert data["valid_recipients"] == 3
    assert data["invalid_recipients"] == 4

    job_id = data["job_id"]
    get_res = client.get(f"/api/v1/jobs/{job_id}")
    assert get_res.status_code == 200
    job_details = get_res.json()

    # Job status should be completed_with_errors
    assert job_details["status"] == "completed_with_errors"
    assert job_details["total_count"] == 7
    assert job_details["succeeded_count"] == 3
    assert job_details["failed_count"] == 4
    assert job_details["pending_count"] == 0

    # Inspect recipient list
    recipients = job_details["recipients"]
    assert len(recipients) == 7

    # Find and assert statuses and errors by recipient name
    rec_by_name = {r["name"]: r for r in recipients}

    # Valid recipients must be successful and have download URLs
    assert rec_by_name["Valid One"]["status"] == "success"
    assert rec_by_name["Valid One"]["download_url"] is not None
    assert rec_by_name["Valid Two"]["status"] == "success"
    assert rec_by_name["Valid Three"]["status"] == "success"

    # Invalid recipients must be marked failed with clear error_message
    assert rec_by_name[""]["status"] == "failed"
    assert "blank" in rec_by_name[""]["error_message"].lower()

    assert rec_by_name["Bad Email"]["status"] == "failed"
    assert "invalid email" in rec_by_name["Bad Email"]["error_message"].lower()

    assert rec_by_name["Duplicate Copy"]["status"] == "failed"
    assert "duplicate" in rec_by_name["Duplicate Copy"]["error_message"].lower()

    assert rec_by_name[long_name[:255]]["status"] == "failed"
    assert "exceeds maximum allowed length" in rec_by_name[long_name[:255]]["error_message"].lower()


def test_batch_all_recipients_invalid(client: TestClient):
    """Verify that a batch where all recipients are invalid terminates with status 'failed'."""
    payload = {
        "title": "Failed Batch Test",
        "issuer": "Test Issuer",
        "issue_date": "2026-10-07",
        "recipients": [
            {"name": "   ", "email": "valid@example.com"},  # Blank name
            {"name": "User", "email": "bad_email_format"},   # Bad email
        ],
    }

    response = client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 202
    data = response.json()

    assert data["total_recipients"] == 2
    assert data["valid_recipients"] == 0
    assert data["invalid_recipients"] == 2
    assert data["status"] == "failed"

    job_id = data["job_id"]
    get_res = client.get(f"/api/v1/jobs/{job_id}")
    assert get_res.status_code == 200
    assert get_res.json()["status"] == "failed"
    assert get_res.json()["failed_count"] == 2


def test_numeric_score_accepted(client: TestClient):
    """Verify that integer and float scores are coerced to strings without request-level 422."""
    payload = {
        "title": "Numeric Score Cohort",
        "issuer": "Academy",
        "issue_date": "2026-10-07",
        "recipients": [
            {"name": "Student A", "email": "a@example.com", "score": 96},
            {"name": "Student B", "email": "b@example.com", "score": 88.5},
        ],
    }
    response = client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    get_res = client.get(f"/api/v1/jobs/{job_id}")
    assert get_res.status_code == 200
    recipients = get_res.json()["recipients"]
    assert recipients[0]["score"] == "96"
    assert recipients[1]["score"] == "88.5"
    assert recipients[0]["status"] == "success"
    assert recipients[1]["status"] == "success"


def test_duplicate_email_case_insensitive(client: TestClient):
    """Verify duplicate detection treats mixed-case email addresses as duplicates."""
    payload = {
        "title": "Case Duplicate Test",
        "issuer": "Issuer",
        "issue_date": "2026-10-07",
        "recipients": [
            {"name": "First Entry", "email": "Scholar@Example.COM"},
            {"name": "Second Entry", "email": "scholar@example.com"},
        ],
    }
    response = client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    get_res = client.get(f"/api/v1/jobs/{job_id}")
    assert get_res.status_code == 200
    recipients = get_res.json()["recipients"]
    assert recipients[0]["status"] == "success"
    assert recipients[1]["status"] == "failed"
    assert "duplicate" in recipients[1]["error_message"].lower()


def test_missing_or_null_fields_per_recipient(client: TestClient):
    """Verify null or omitted name/email marks that recipient failed without 422 for whole batch."""
    payload = {
        "title": "Partial Batch",
        "issuer": "Issuer",
        "issue_date": "2026-10-07",
        "recipients": [
            {"name": None, "email": "valid1@example.com"},  # Null name
            {"email": "valid2@example.com"},                # Missing name
            {"name": "Valid Person", "email": "valid3@example.com"},  # Valid
        ],
    }
    response = client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    get_res = client.get(f"/api/v1/jobs/{job_id}")
    assert get_res.status_code == 200
    job_data = get_res.json()
    assert job_data["succeeded_count"] == 1
    assert job_data["failed_count"] == 2


def test_overlong_field_stored_safely_and_failed(client: TestClient):
    """Verify over-long string is safely truncated for storage and marked as validation failure."""
    overlong_name = "N" * 500
    payload = {
        "title": "Overlong Cohort",
        "issuer": "Issuer",
        "issue_date": "2026-10-07",
        "recipients": [
            {"name": overlong_name, "email": "overlong@example.com"},
        ],
    }
    response = client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    get_res = client.get(f"/api/v1/jobs/{job_id}")
    assert get_res.status_code == 200
    rec = get_res.json()["recipients"][0]
    assert rec["status"] == "failed"
    assert rec["failure_type"] == "validation"
    assert len(rec["name"]) == 255  # Truncated cleanly for DB storage
    assert "exceeds maximum allowed length" in rec["error_message"].lower()
