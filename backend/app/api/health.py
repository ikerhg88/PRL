from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(tags=["health"])


class DependencyStatus(BaseModel):
    name: str
    status: str
    detail: str


class HealthResponse(BaseModel):
    status: str
    app: str
    environment: str
    dependencies: list[DependencyStatus]


@router.get("/health", response_model=HealthResponse)
def healthcheck() -> HealthResponse:
    settings = get_settings()
    database_name = "sqlite" if settings.database_url.startswith("sqlite") else "postgresql"
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        environment=settings.environment,
        dependencies=[
            DependencyStatus(
                name=database_name,
                status="configured",
                detail=settings.redacted_database_url,
            ),
            DependencyStatus(
                name="redis",
                status="configured",
                detail=settings.redacted_redis_url,
            ),
        ],
    )
