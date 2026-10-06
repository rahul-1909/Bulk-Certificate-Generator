"""Tests for individual recipient failure isolation during background processing."""

import pytest
from fastapi.testclient import TestClient
import app.services.job_processor as processor_module


def test_individual_pdf_generation_failure_isolated(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """Force one recipient's PDF generation to throw an error and verify others succeed."""
    original_generate = processor_module.generate_certificate_pdf

    def flaky_generate(**kwargs):
        if kwargs.get("recipient_name") == "Faulty User":
            raise RuntimeError("Simulated ReportLab disk rendering failure")
        return original_generate(**kwargs)

    monkeypatch.setattr(processor_module, "generate_certificate_pdf", flaky_generate)

    payload = {
        "title": "Fault Tolerance Symposium",
        "issuer": "Resilience Guild",
        "issue_date": "2026-10-07",
        "recipients": [
            {"name": "Solid User A", "email": "user.a@example.com"},
            {"name": "Faulty User", "email": "faulty@example.com"},
            {"name": "Solid User B", "email": "user.b@example.com"},
        ],
    }

    create_res = client.post("/api/v1/jobs", json=payload)
    assert create_res.status_code == 202
    job_id = create_res.json()["job_id"]

    # Retrieve job status
    get_res = client.get(f"/api/v1/jobs/{job_id}")
    assert get_res.status_code == 200
    job = get_res.json()

    assert job["status"] == "completed_with_errors"
    assert job["total_count"] == 3
    assert job["succeeded_count"] == 2
    assert job["failed_count"] == 1
    assert job["pending_count"] == 0

    recipients_by_name = {r["name"]: r for r in job["recipients"]}

    # Solid users must succeed
    assert recipients_by_name["Solid User A"]["status"] == "success"
    assert recipients_by_name["Solid User A"]["error_message"] is None
    assert recipients_by_name["Solid User A"]["download_url"] is not None

    assert recipients_by_name["Solid User B"]["status"] == "success"
    assert recipients_by_name["Solid User B"]["error_message"] is None
    assert recipients_by_name["Solid User B"]["download_url"] is not None

    # Faulty user must fail with simulated error captured
    assert recipients_by_name["Faulty User"]["status"] == "failed"
    assert recipients_by_name["Faulty User"]["download_url"] is None
    assert "Simulated ReportLab disk rendering failure" in recipients_by_name["Faulty User"]["error_message"]
