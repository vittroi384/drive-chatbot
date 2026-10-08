"""Google OAuth 로그인 라우트.

흐름: /login → 구글 → /auth/callback → 도메인검증 → 세션저장 → /
로컬은 OAuth 세션 방식. 운영은 IAP 가 앞단에서 처리하므로
이 라우트들은 주로 로컬/개발 로그인 경로로 쓰임.
"""

from __future__ import annotations

import logging
from typing import Any

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from starlette.status import HTTP_403_FORBIDDEN

from app.config import get_settings
from app.utils.auth_utils import get_user_email, is_domain_allowed

logger = logging.getLogger(__name__)
settings = get_settings()

# prefix 없음(결정 2): /login, /logout, /me 는 루트에. callback 만 /auth/.
router = APIRouter(tags=["auth"])

# --- OAuth 클라이언트 등록 ------------------------------------------------
# server_metadata_url 로 구글의 OpenID 설정을 자동 로드(엔드포인트/키 등).
# openid 스코프 + 이 조합이면 authorize_access_token() 반환 dict 에
# userinfo 가 자동 포함됨 → 별도 userinfo 호출 불필요(authlib 1.7.2 확인).
oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={
        # 최소 권한: drive 는 readonly/metadata.readonly 만 (쓰기 권한 없음).
        "scope": "openid email profile "
        "https://www.googleapis.com/auth/drive.readonly "
        "https://www.googleapis.com/auth/drive.metadata.readonly",
        # refresh_token 을 받기 위해 매번 동의 화면 강제(함정: 빼먹으면 refresh_token 없음).
        "prompt": "consent",
    },
)


@router.get("/login")
async def login(request: Request) -> Response:
    """구글 로그인 페이지로 리다이렉트.

    redirect_uri 는 반드시 settings 값(=콘솔 등록값)과 정확히 일치해야 함.
    access_type=offline 도 refresh_token 수령에 필요.
    """
    redirect_uri = settings.google_oauth_redirect_uri
    return await oauth.google.authorize_redirect(
        request, redirect_uri, access_type="offline"
    )


@router.get("/auth/callback")
async def auth_callback(request: Request) -> Response:
    """구글이 돌려보낸 콜백. code→토큰 교환 + 도메인검증 + 세션저장."""
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as exc:
        logger.warning("OAuth error: %s", exc.error)
        return JSONResponse(
            {"error": "oauth_failed", "detail": exc.error},
            status_code=HTTP_403_FORBIDDEN,
        )

    # openid 스코프 → userinfo 자동 포함 (authlib 1.7.2)
    userinfo = token.get("userinfo") or {}
    email = (userinfo.get("email") or "").lower()
    name = userinfo.get("name") or ""

    # ★ 보안 게이트: 도메인/화이트리스트 검증. 실패 시 차단 + 로그.
    if not email or not is_domain_allowed(email):
        logger.warning("Unauthorized domain attempt: %s", email or "(no email)")
        return JSONResponse(
            {"error": "unauthorized_domain", "email": email},
            status_code=HTTP_403_FORBIDDEN,
        )

    # 세션 저장 (서명된 쿠키). oauth_token 은 Drive API 호출용.
    request.session["user_email"] = email
    request.session["user_name"] = name
    request.session["oauth_token"] = token
    request.session["oauth_refresh_token"] = token.get("refresh_token", "")

    logger.info("User logged in: %s", email)
    return RedirectResponse(url="/")


@router.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    """세션 클리어 후 /login 으로."""
    request.session.clear()
    return RedirectResponse(url="/login")


@router.get("/me")
async def me(request: Request) -> dict[str, Any]:
    """현재 로그인 유저 정보. 미인증이어도 200 + authenticated:false 반환.

    (미들웨어 PUBLIC_PATHS 에 /me 포함 → 리다이렉트 안 되고 JSON 그대로 나옴)
    """
    email = get_user_email(request)
    if not email:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "email": email,
        "name": request.session.get("user_name", ""),
    }
