"""Bulk Certificate Generator FastAPI Application."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.api.router import main_router
from app.api.v1.health import router as health_router
from app.core.config import get_settings
from app.core.db import init_db
from app.core.logging import get_logger, setup_logging

logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and shutdown routines."""
    # Startup actions
    setup_logging()
    logger.info("Initializing application resources and database tables...")
    settings = get_settings()
    # Initialize storage folder
    _ = settings.storage_path
    # Initialize DB schemas
    init_db()
    logger.info("Bulk Certificate Generator API successfully started.")

    yield

    # Shutdown actions
    logger.info("Shutting down Bulk Certificate Generator API...")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    application = FastAPI(
        title="Bulk Certificate Generator API",
        description=(
            "Asynchronous backend API for bulk certificate generation. "
            "Supports high-volume recipient processing, independent failure isolation, "
            "live progress tracking, and batch ZIP retrieval."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Global validation error handler for friendly, structured error responses
    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        errors = []
        for err in exc.errors():
            loc = " -> ".join(str(item) for item in err.get("loc", []))
            msg = err.get("msg", "Validation error")
            errors.append({"location": loc, "message": msg})
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": "Request validation failed.",
                "errors": errors,
            },
        )

    # Mount routers
    application.include_router(main_router)
    # Direct access to health check at root /health in addition to /api/v1/health
    application.include_router(health_router)

    @application.get(
        "/",
        summary="Service Index",
        description="Root index endpoint providing service metadata.",
        tags=["Index"],
    )
    def index():
        return {
            "service": "Bulk Certificate Generator API",
            "version": "1.0.0",
            "status": "online",
            "documentation": "/docs",
        }

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
