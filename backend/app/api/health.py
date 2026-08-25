"""Health ендпойнти — liveness на приложението и readiness на базата."""

from fastapi import APIRouter, Response, status

from app.core.config import settings
from app.core.db import check_connection

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Приложението е живо. Винаги 200, без външни зависимости."""
    return {"status": "ok", "version": settings.app_version}


@router.get("/health/db")
def health_db(response: Response) -> dict[str, str]:
    """Базата е достъпна. 200 при успех, 503 при липса на връзка."""
    if check_connection():
        return {"status": "ok", "database": "reachable"}

    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "error", "database": "unreachable"}
