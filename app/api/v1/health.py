"""Health check endpoint for service monitoring."""

import os
import tempfile
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.db import get_db
from app.schemas.common import HealthResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health check",
    description="Validates database connectivity and disk storage writeability.",
)
def health_check(db: Session = Depends(get_db)):
    """Perform health checks on database and file storage."""
    settings = get_settings()

    # 1. Database check
    db_status = "healthy"
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"unhealthy: {str(exc)}"

    # 2. File storage check
    storage_status = "healthy"
    try:
        storage_path = settings.storage_path
        test_file = storage_path / f".health_check_{os.getpid()}"
        test_file.write_text("health-check-ok", encoding="utf-8")
        if test_file.exists():
            test_file.unlink()
    except Exception as exc:
        storage_status = f"unhealthy: {str(exc)}"

    is_overall_healthy = db_status == "healthy" and storage_status == "healthy"
    overall_status = "healthy" if is_overall_healthy else "unhealthy"

    response_payload = HealthResponse(
        status=overall_status,
        database=db_status,
        storage=storage_status,
        version="1.0.0",
    )

    if not is_overall_healthy:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response_payload.model_dump(),
        )

    return response_payload
