"""Tests for job status tracking, counter updates, and pagination."""

from fastapi.testclient import TestClient


def test_job_status_all_successful(client: TestClient):
    """Verify job transitions to 'completed' with correct counts when all recipients are valid."""
    payload = {
        "title": "Data Engineering Intensive",
        "issuer": "Tech Institute",
        "issue_date": "2026-10-07",
        "recipients": [
            {"name": "Dev One", "email": "dev1@example.com"},
            {"name": "Dev Two", "email": "dev2@example.com"},
            {"name": "Dev Three", "email": "dev3@example.com"},
        ],
    }

    create_res = client.post("/api/v1/jobs", json=payload)
    assert create_res.status_code == 202
    job_id = create_res.json()["job_id"]

    status_res = client.get(f"/api/v1/jobs/{job_id}")
    assert status_res.status_code == 200
    job = status_res.json()

    assert job["status"] == "completed"
    assert job["total_count"] == 3
    assert job["succeeded_count"] == 3
    assert job["failed_count"] == 0
    assert job["pending_count"] == 0
    assert len(job["recipients"]) == 3
    for r in job["recipients"]:
        assert r["status"] == "success"
        assert r["download_url"] is not None


def test_job_pagination(client: TestClient):
    """Verify recipient pagination controls (page, page_size, total_pages)."""
    recipients = [{"name": f"Student {i}", "email": f"student{i}@example.com"} for i in range(15)]
    payload = {
        "title": "Large Cohort Graduation",
        "issuer": "University",
        "issue_date": "2026-10-07",
        "recipients": recipients,
    }

    create_res = client.post("/api/v1/jobs", json=payload)
    job_id = create_res.json()["job_id"]

    # Request page 1 with page_size=5
    page1_res = client.get(f"/api/v1/jobs/{job_id}?page=1&page_size=5")
    assert page1_res.status_code == 200
    p1_data = page1_res.json()
    assert p1_data["page"] == 1
    assert p1_data["page_size"] == 5
    assert p1_data["total_pages"] == 3
    assert len(p1_data["recipients"]) == 5
    assert p1_data["recipients"][0]["name"] == "Student 0"

    # Request page 2 with page_size=5
    page2_res = client.get(f"/api/v1/jobs/{job_id}?page=2&page_size=5")
    assert page2_res.status_code == 200
    p2_data = page2_res.json()
    assert p2_data["page"] == 2
    assert len(p2_data["recipients"]) == 5
    assert p2_data["recipients"][0]["name"] == "Student 5"

    # Request page 3 with page_size=5
    page3_res = client.get(f"/api/v1/jobs/{job_id}?page=3&page_size=5")
    assert page3_res.status_code == 200
    p3_data = page3_res.json()
    assert len(p3_data["recipients"]) == 5
    assert p3_data["recipients"][-1]["name"] == "Student 14"
