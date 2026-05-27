"""로그인 필수 미들웨어 (5단계).

PUBLIC_PATHS 외의 모든 경로는 로그인 필요. 미인증 시 /login 으로 302.
인증 판단은 get_user_email() 에 위임(IAP/세션 통합) → 운영/로컬 동일 동작.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.utils.auth_utils import get_user_email

# 로그인 없이 접근 가능한 경로. /me 는 자체적으로 인증여부 JSON 반환하므로 포함.
PUBLIC_PATHS = {
    "/login",
    "/auth/callback",
    "/logout",
    "/health",
    "/me",
    "/docs",
    "/openapi.json",
    "/redoc",
}


def _is_public(path: str) -> bool:
    """공개 경로 여부. /static 같은 prefix 도 허용."""
    if path in PUBLIC_PATHS:
        return True
    # 정적 파일 등 하위 경로 전체 허용
    return path.startswith("/static")


class AuthRequiredMiddleware(BaseHTTPMiddleware):
    """미인증 요청을 /login 으로 리다이렉트."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 공개 경로는 그냥 통과
        if _is_public(path):
            return await call_next(request)

        # 로그인 확인 (IAP 헤더 or 세션). 없으면 /login 으로.
        if not get_user_email(request):
            return RedirectResponse(url="/login", status_code=302)

        return await call_next(request)