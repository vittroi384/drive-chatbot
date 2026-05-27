"""FastAPI application entry point.

Run locally (from the project root, venv active):
    uvicorn app.main:app --reload --port 8000

Then open http://localhost:8000  and  http://localhost:8000/health
"""

from __future__ import annotations

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from app.config import get_settings
from app.routers import auth as auth_router
from app.middleware.auth_middleware import AuthRequiredMiddleware
settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
)

# 순서 주의(중요): add_middleware 는 나중에 추가한 것이 바깥쪽(먼저 실행)이 됨.
# 따라서 SessionMiddleware 를 나중에 추가해야 인증 미들웨어보다 먼저 실행되어
# request.session 이 준비됨.
app.add_middleware(AuthRequiredMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    same_site="lax",
    https_only=settings.env != "local",
    max_age=60 * 60 * 8,  # 8시간
)
app.include_router(auth_router.router)

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
