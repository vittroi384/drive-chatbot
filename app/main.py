"""FastAPI application entry point.

Run locally (from the project root, venv active):
    uvicorn app.main:app --reload --port 8000

Then open http://localhost:8000  and  http://localhost:8000/health
"""

from __future__ import annotations

from fastapi import FastAPI

from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
)


@app.get("/")
async def root() -> dict[str, str]:
    """Landing payload. The real chat UI (templates/index.html) lands in 9단계."""
    return {
        "app": settings.app_name,
        "company": settings.company_name,
        "message": f"{settings.company_name} 사내 문서 챗봇 — 준비 중",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe. Used by Cloud Run / IAP health checks (11단계)."""
    return {"status": "ok", "env": settings.env}
