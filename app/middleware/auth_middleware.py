"""로그인 필수 미들웨어 (5단계, 8단계에서 API 분기 추가).

PUBLIC_PATHS 외의 모든 경로는 로그인 필요. 미인증 시:
  - /api/*  (JSON 클라이언트) → 401 JSON
      (HTML 로그인 페이지로의 302 가 가면 프런트엔드 fetch 가 깨진다.)
  - 그 외   (HTML 페이지)     → /login 으로 302 (브라우저 친화적)
인증 판단은 get_user_email() 에 위임(IAP/세션 통합) → 운영/로컬 동일 동작.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

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
    """미인증 요청을 차단한다. API 는 401 JSON, 그 외는 /login 으로 302."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 공개 경로는 그냥 통과
        if _is_public(path):
            return await call_next(request)

        # 미인증 처리 — 경로 종류에 따라 응답을 다르게.
        if not get_user_email(request):
            # ★ API 경로: 302(HTML 로그인)가 아니라 401 JSON.
            #   프런트엔드 fetch 는 302 를 따라가 HTML 을 받으면 깨진다.
            #   require_user_email(Depends)가 내는 401 과 동일한 {"detail": ...} 모양으로 통일.
            if path.startswith("/api"):
                return JSONResponse({"detail": "Not authenticated"}, status_code=401)
            # 그 외(HTML 페이지)는 브라우저 친화적으로 로그인 페이지로 302.
            return RedirectResponse(url="/login", status_code=302)

        return await call_next(request)
