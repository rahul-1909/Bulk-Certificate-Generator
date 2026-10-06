# Bulk Certificate Generator (Backend API)

Enterprise-grade, asynchronous backend API designed to handle bulk certificate generation requests for large recipient cohorts. Built with **FastAPI**, **SQLAlchemy 2.x**, **Pydantic v2**, and **ReportLab**.

---

## 1. Overview

The Bulk Certificate Generator accepts a single batch API request containing certificate-level metadata (course/event title, issuer, issue date) along with an array of recipients (name, email, and optional attributes like role or score).

Key capabilities:
- **Asynchronous Non-Blocking Processing**: Accepts large batches immediately, returns HTTP `202 Accepted` with a Job ID, and renders PDF certificates in the background.
- **Resilient Failure Isolation**: Per-recipient validation or PDF generation errors (such as blank names, invalid emails, duplicates, or corrupt data) never abort the overall batch. Invalid entries are recorded as failed with explicit diagnostic reasons, while valid recipients proceed to completion.
- **Granular Real-Time Status Tracking**: Job and per-recipient progression statuses (`pending`, `processing`, `completed`, `completed_with_errors`, `failed`) are committed per recipient so clients can monitor progress live.
- **Multi-Format Retrieval**: Supports single PDF certificate downloads and full-batch ZIP archive downloads with path traversal security.
- **Built-in Resilience**: Includes an endpoint to retry failed certificates without regenerating already completed certificates.

---

## 2. Setup (venv, install)

### Prerequisites
- Python 3.11+
- Git

### Linux / macOS
```bash
# Clone the repository
git clone https://github.com/rahul-1909/Bulk-Certificate-Generator.git
cd Bulk-Certificate-Generator

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install pinned dependencies
pip install -r requirements.txt
```

### Windows (PowerShell)
```powershell
# Clone the repository
git clone https://github.com/rahul-1909/Bulk-Certificate-Generator.git
cd "Bulk-Certificate-Generator"

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install pinned dependencies
pip install -r requirements.txt
```

*(Optional)* Copy the environment template if customization is needed:
```bash
cp .env.example .env
```

---

## 3. Running the App

Start the Uvicorn server using the standard command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Once running, access the interactive API documentation at:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

## 4. Running Tests

Run the complete test suite with `pytest`:

```bash
pytest -v
```

To run with verbose output and coverage reporting:
```bash
pytest -v --tb=short
```

---

## 5. How to Submit a Generation Request

Submit a POST request to `/api/v1/jobs` with the certificate metadata and recipient list.

### `curl` Command (Linux / macOS / Git Bash)
```bash
curl -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Advanced Python Engineering",
    "issuer": "Tech Institute",
    "issue_date": "2026-10-07",
    "recipients": [
      {
        "name": "Alice Chen",
        "email": "alice@example.com",
        "role": "Distinction",
        "score": "96%"
      },
      {
        "name": "Bob Miller",
        "email": "bob@example.com",
        "role": "Graduate",
        "score": "88%"
      },
      {
        "name": "Charlie Davis",
        "email": "charlie@example.com",
        "role": "Participant",
        "score": "91%"
      },
      {
        "name": "   ",
        "email": "blank@example.com"
      },
      {
        "name": "Eve Stone",
        "email": "invalid-email-format"
      }
    ]
  }'
```

### `curl.exe` Command (Windows PowerShell using payload file)
```powershell
curl.exe -X POST http://localhost:8000/api/v1/jobs -H "Content-Type: application/json" -d "@sample_request.json"
```

### Sample Response (`202 Accepted`)
```json
{
  "job_id": "254290cd-9089-4452-a5a2-b2caa47e7106",
  "status": "pending",
  "total_recipients": 5,
  "valid_recipients": 3,
  "invalid_recipients": 2,
  "created_at": "2026-10-06T18:56:19.716900",
  "message": "Job accepted and queued for certificate generation."
}
```

---

## 6. How to Check Status

Query the job status by passing the `job_id` returned from the creation step. The response includes aggregate metrics and paginated recipient progress.

### `curl` Command
```bash
curl -X GET http://localhost:8000/api/v1/jobs/254290cd-9089-4452-a5a2-b2caa47e7106
```

### Sample Response (`200 OK`)
```json
{
  "id": "254290cd-9089-4452-a5a2-b2caa47e7106",
  "title": "Advanced Python Engineering",
  "issuer": "Tech Institute",
  "issue_date": "2026-10-07",
  "status": "completed_with_errors",
  "total_count": 5,
  "succeeded_count": 3,
  "failed_count": 2,
  "pending_count": 0,
  "created_at": "2026-10-06T18:56:19.716900",
  "updated_at": "2026-10-06T18:56:19.791070",
  "page": 1,
  "page_size": 50,
  "total_pages": 1,
  "recipients": [
    {
      "id": "05fd614f-cf2f-438f-8a56-5de290c1bee0",
      "name": "Alice Chen",
      "email": "alice@example.com",
      "role": "Distinction",
      "score": "96%",
      "status": "success",
      "error_message": null,
      "download_url": "/api/v1/certificates/05fd614f-cf2f-438f-8a56-5de290c1bee0/download",
      "created_at": "2026-10-06T18:56:19.724303",
      "updated_at": "2026-10-06T18:56:19.757350"
    },
    {
      "id": "33d841c8-791a-4fb1-a477-553194c6c309",
      "name": "Bob Miller",
      "email": "bob@example.com",
      "role": "Graduate",
      "score": "88%",
      "status": "success",
      "error_message": null,
      "download_url": "/api/v1/certificates/33d841c8-791a-4fb1-a477-553194c6c309/download",
      "created_at": "2026-10-06T18:56:19.724303",
      "updated_at": "2026-10-06T18:56:19.770611"
    },
    {
      "id": "02672839-ef2b-4ffe-996a-3601391d532d",
      "name": "Charlie Davis",
      "email": "charlie@example.com",
      "role": "Participant",
      "score": "91%",
      "status": "success",
      "error_message": null,
      "download_url": "/api/v1/certificates/02672839-ef2b-4ffe-996a-3601391d532d/download",
      "created_at": "2026-10-06T18:56:19.724303",
      "updated_at": "2026-10-06T18:56:19.785619"
    },
    {
      "id": "24459dcb-2af8-4cff-bf33-44f31d62a039",
      "name": "",
      "email": "blank@example.com",
      "role": null,
      "score": null,
      "status": "failed",
      "error_message": "Recipient name cannot be blank.",
      "download_url": null,
      "created_at": "2026-10-06T18:56:19.724303",
      "updated_at": "2026-10-06T18:56:19.724303"
    },
    {
      "id": "be20bcb4-bf04-48bf-ac5c-dc9d7e098bfa",
      "name": "Eve Stone",
      "email": "invalid-email-format",
      "role": null,
      "score": null,
      "status": "failed",
      "error_message": "Invalid email address: An email address must have an @-sign.",
      "download_url": null,
      "created_at": "2026-10-06T18:56:19.724303",
      "updated_at": "2026-10-06T18:56:19.724303"
    }
  ]
}
```

---

## 7. How to Retrieve Certificates

### A. Download an Individual Certificate PDF
Download a single recipient's certificate using the certificate ID:

```bash
curl -X GET http://localhost:8000/api/v1/certificates/05fd614f-cf2f-438f-8a56-5de290c1bee0/download \
  -o "Alice_Chen_Certificate.pdf"
```

- Returns: `200 OK` with `Content-Type: application/pdf`
- If still in progress: `409 Conflict`
- If generation failed: `400 Bad Request` with diagnostic reason
- If not found: `404 Not Found`

### B. Download All Completed Certificates as a ZIP
Download an archive of all successfully generated certificates for a job:

```bash
curl -X GET http://localhost:8000/api/v1/jobs/254290cd-9089-4452-a5a2-b2caa47e7106/download-all \
  -o "certificates.zip"
```

- Returns: `200 OK` with `Content-Type: application/zip`
- If no certificates have completed yet: `400 Bad Request`
- If job does not exist: `404 Not Found`

---

## 8. API Reference Table

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Service index and API metadata |
| `GET` | `/health` | Health check verifying database and storage connectivity |
| `GET` | `/api/v1/health` | API v1 health check endpoint |
| `POST` | `/api/v1/jobs` | Enqueue a new bulk certificate generation job |
| `GET` | `/api/v1/jobs/{job_id}` | Retrieve job status, counters, and paginated recipient items |
| `POST` | `/api/v1/jobs/{job_id}/retry` | Retry generation for all failed certificates of a job |
| `GET` | `/api/v1/certificates/{certificate_id}/download` | Download an individual certificate PDF |
| `GET` | `/api/v1/jobs/{job_id}/download-all` | Download all completed certificates for a job as a ZIP archive |

---

## 9. Design Decisions

### 1. Framework Choice: FastAPI
- **Rationale**: FastAPI is selected for its native asynchronous capabilities, automatic OpenAPI/Swagger documentation, high throughput with ASGI/Uvicorn, and seamless integration with Pydantic v2 for data validation.

### 2. Database Choice & Schema
- **Relational ORM**: SQLAlchemy 2.0 with standard 2.0 declarative syntax (`DeclarativeBase`, typed session queries).
- **Default Database**: SQLite by default (`sqlite:///./certificates.db`) with `check_same_thread=False` to allow concurrent background worker access. The connection string is completely driven by the `DATABASE_URL` environment variable, enabling direct drops into PostgreSQL without code modification.
- **Table Creation vs. Alembic Migrations**:
  - Clean table initialization on startup (`Base.metadata.create_all`) is selected.
  - *Justification*: For a self-contained, domain-focused service with an established schema, running `create_all` during FastAPI's application lifespan provides zero-friction deployment with zero external CLI orchestration needed for initial boots.
  - *Production Path*: For multi-instance, rolling-update production deployments, Alembic migrations should be used alongside CI/CD release phases to manage backward-compatible column migrations and index creations.
- **Schema Design**:
  - `jobs`: Stores batch-level attributes (`title`, `issuer`, `issue_date`), state enum (`pending`, `processing`, `completed`, `completed_with_errors`, `failed`), live counters (`total_count`, `succeeded_count`, `failed_count`, `pending_count`), and timestamps.
  - `certificate_recipients`: Foreign key relation back to `jobs.id` with `ondelete="CASCADE"`. Stores recipient details (`name`, `email`, `role`, `score`), per-item status (`pending`, `success`, `failed`), `error_message`, generated file path, and timestamps.

### 3. Synchronous vs. Background Processing & Why
- **Chosen Mechanism**: FastAPI `BackgroundTasks` triggered upon request acceptance.
- **Why**:
  - Bulk requests may contain thousands of recipients. Synchronous PDF rendering in the request cycle would exhaust HTTP timeouts, block connection pools, and degrade API responsiveness.
  - Using built-in background task processing avoids requiring heavy external brokers (RabbitMQ/Redis) for standalone or containerized developer environments.
- **DB Session Handling**:
  - Background workers NEVER reuse the caller's request DB session.
  - A dedicated context manager `with get_db_session() as db:` creates an independent database session for the background thread, avoiding session concurrency violations and connection pool leaks.
- **Limitations**:
  - In-process background tasks run in the memory of the web server worker. If the container or server process restarts during execution, jobs in the `processing` state will not resume automatically unless picked up by a recovery reaper.
- **Production Architecture**:
  - In a high-volume production environment, we recommend an external distributed task queue such as **Celery** or **RQ** backed by **Redis** or **RabbitMQ**. Tasks can be partitioned into recipient chunks, scaled horizontally across dedicated worker nodes, and tracked with dead-letter queues.

### 4. Failure Isolation
- **Per-Recipient Fault Boundaries**:
  - Every recipient is evaluated and processed inside an isolated `try...except Exception` block.
  - If PDF compilation fails (e.g., unexpected character encoding, disk I/O glitch, or mocked rendering failure), only that specific recipient is flagged with `status="failed"` and the exact error recorded in `error_message`.
  - The loop continues immediately to the next recipient.
- **Terminal Job States**:
  - `completed`: All recipients generated successfully (`failed_count == 0`).
  - `completed_with_errors`: Some succeeded and some failed (`succeeded_count > 0` and `failed_count > 0`).
  - `failed`: All recipients failed validation or generation (`succeeded_count == 0` and `failed_count > 0`).

### 5. Validation Strategy
- **Two-Tier Validation**:
  1. *Request-level*: Validates structural integrity (missing title, issuer, issue date, empty recipient list, payload size exceeding `MAX_RECIPIENTS_PER_JOB`). Failures return `422 Unprocessable Content`.
  2. *Per-recipient level*: Evaluates individual business constraints (blank names, invalid email syntax via `email_validator`, string lengths exceeding 255 characters, and duplicate emails within the same request batch).
  - *Non-Rejection Policy*: Per-recipient validation issues do NOT abort the batch; invalid records are inserted into the database as `failed` with diagnostic messages, and valid records are queued for generation.

### 6. File Storage & Path Traversal Security
- **Directory**: Configurable via `CERTIFICATES_STORAGE_DIR` (defaults to `./storage/certificates`).
- **Sanitization**: Names are sanitized to alphanumeric, dash, and underscore characters (`re.sub(r"[^\w\-]", "_", ...)`).
- **Security Guardrail**: The resolved target path is checked to guarantee that it is strictly located within the configured storage directory, preventing directory traversal (`../../`).
- **Cleanup & Streaming**: ZIP retrieval aggregates files directly from storage into an in-memory streaming archive without temporary file clutter.

### 7. Idempotency & Re-runnability
- Before generating a certificate, the processor verifies if the recipient already has a valid non-empty PDF file on disk. If so, it marks the recipient as successful without regenerating.
- The `POST /api/v1/jobs/{job_id}/retry` endpoint resets failed certificates back to `pending` and re-triggers background processing, seamlessly handling transient faults.

### 8. What I Would Improve in Production
1. **Distributed Task Queue**: Replace in-process `BackgroundTasks` with Celery or Temporal backed by Redis/RabbitMQ.
2. **Object Storage**: Store certificates in AWS S3 or Google Cloud Storage with pre-signed download URLs rather than local block storage.
3. **Template Engine**: Add SVG or HTML-to-PDF rendering (e.g. WeasyPrint) with configurable dynamic certificate templates.
4. **Rate Limiting & Authentication**: Enforce API Key / JWT authentication and rate limits per tenant.
5. **Observability**: Export OpenTelemetry metrics (job latency, queue depth, PDF generation rate) and integrate Prometheus/Grafana dashboards.
