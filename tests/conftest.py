"""Pytest configuration, fixtures, and test isolation harness."""

import tempfile
from pathlib import Path
from typing import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from app.core.config import get_settings
from app.core.db import (
    Base,
    create_db_engine,
    get_db,
    set_engine_and_sessionmaker,
)
from app.main import app


@pytest.fixture(autouse=True)
def isolate_test_environment() -> Generator[None, None, None]:
    """Isolate database and certificate storage in temporary directories for each test."""
    settings = get_settings()

    # 1. Create temporary directory for certificate PDFs
    with tempfile.TemporaryDirectory() as temp_storage_dir, tempfile.TemporaryDirectory() as temp_db_dir:
        temp_db_path = Path(temp_db_dir) / "test_certificates.db"
        test_db_url = f"sqlite:///{temp_db_path}"

        # Save previous settings
        prev_storage_dir = settings.certificates_storage_dir
        prev_db_url = settings.database_url
        prev_sync_mode = settings.run_background_tasks_synchronously

        # Configure isolated settings
        settings.certificates_storage_dir = temp_storage_dir
        settings.database_url = test_db_url
        settings.run_background_tasks_synchronously = True  # Deterministic test execution

        # Create temporary database engine and tables
        temp_engine = create_engine(
            test_db_url,
            connect_args={"check_same_thread": False},
            future=True,
        )
        Base.metadata.create_all(bind=temp_engine)

        # Bind temporary engine to application db module
        set_engine_and_sessionmaker(temp_engine)

        # Override FastAPI get_db dependency
        def override_get_db() -> Generator[Session, None, None]:
            temp_session_local = sessionmaker(
                bind=temp_engine,
                autocommit=False,
                autoflush=False,
                expire_on_commit=False,
            )
            session = temp_session_local()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_get_db

        yield

        # Teardown & restore
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=temp_engine)
        temp_engine.dispose()

        # Rebind original settings and engine
        settings.certificates_storage_dir = prev_storage_dir
        settings.database_url = prev_db_url
        settings.run_background_tasks_synchronously = prev_sync_mode
        set_engine_and_sessionmaker(create_db_engine())


@pytest.fixture
def client() -> TestClient:
    """Return a FastAPI TestClient configured with isolated storage and database."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def current_storage_dir() -> Path:
    """Return the Path to the active test certificate storage directory."""
    return get_settings().storage_path
