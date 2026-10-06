"""API v1 package router."""

from fastapi import APIRouter
from app.api.v1.certificates import router as certificates_router
from app.api.v1.health import router as health_router
from app.api.v1.jobs import router as jobs_router

api_v1_router = APIRouter()
api_v1_router.include_router(health_router)
api_v1_router.include_router(jobs_router)
api_v1_router.include_router(certificates_router)
