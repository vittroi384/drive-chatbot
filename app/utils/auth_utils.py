"""IAP/OAuth 통합 인증 유틸.

로컬은 OAuth 세션, 운영은 Cloud Run + IAP. 두 환경에서 동일한 코드가
돌도록 "이메일을 어디서 얻든 get_user_email() 하나로 통일"하는 추상화 레이어.
나머지 코드(라우터/미들웨어)는 환경 분기를 몰라도 됨.

IAP 경로는 ``X-Goog-IAP-JWT-Assertion`` 헤더의 서명·audience 를 검증한 뒤
payload 의 email 만 사용한다. 이메일 헤더(``X-Goog-Authenticated-User-Email``)는
참고용이며 단독으로는 신뢰하지 않는다. ``IAP_AUDIENCE`` 가 비어 있으면 IAP 경로는
비활성(세션만 사용)이다.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, Request, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# IAP 가 붙이는 헤더 이름.
_IAP_EMAIL_HEADER = "X-Goog-Authenticated-User-Email"
_IAP_JWT_HEADER = "X-Goog-IAP-JWT-Assertion"
_IAP_PREFIX = "accounts.google.com:"
# IAP 가 서명한 JWT 의 공개키와 issuer (Google 문서 기준).
_IAP_CERTS_URL = "https://www.gstatic.com/iap/verify/public_key"
_IAP_ISSUER = "https://cloud.google.com/iap"


def verify_iap_assertion(assertion: str, audience: str) -> str | None:
    """IAP JWT 를 검증하고 payload 의 email 을 반환. 실패하면 None.

    검증 항목: 서명(IAP 공개키, ES256), audience, 만료, issuer.
    google-auth 의 ``verify_token`` 이 서명·audience·만료를 확인하고, issuer 는
    여기서 추가로 비교한다.
    """
    try:
        payload = id_token.verify_token(
            assertion,
            google_requests.Request(),
            audience=audience,
            certs_url=_IAP_CERTS_URL,
        )
    except Exception as exc:  # noqa: BLE001 - 검증 실패 사유는 로그로만
        logger.warning("[iap] JWT verification failed: %s", exc)
        return None

    if payload.get("iss") != _IAP_ISSUER:
        logger.warning("[iap] unexpected issuer: %r", payload.get("iss"))
        return None

    email = payload.get("email")
    if not email:
        logger.warning("[iap] verified JWT has no email claim")
        return None
    return str(email).lower()


def get_user_email(request: Request) -> str | None:
    """현재 요청자의 이메일을 반환. 없으면 None.

    우선순위:
      1) IAP JWT (운영, ``IAP_AUDIENCE`` 설정 시) — 검증된 payload 의 email
      2) 세션의 user_email (로컬 OAuth)

    IAP 헤더(이메일/assertion)가 하나라도 있는데 assertion 이 없거나 검증에
    실패하면 세션으로 넘어가지 않고 None(미인증)을 반환한다.
    """
    if settings.iap_audience:
        email_header = request.headers.get(_IAP_EMAIL_HEADER)
        assertion = request.headers.get(_IAP_JWT_HEADER)
        if assertion or email_header:
            if not assertion:
                logger.warning(
                    "[iap] email header without JWT assertion → unauthenticated (%s)",
                    email_header,
                )
                return None
            email = verify_iap_assertion(assertion, settings.iap_audience)
            if email is None:
                return None
            if email_header and email_header.removeprefix(_IAP_PREFIX).lower() != email:
                logger.warning(
                    "[iap] email header mismatch (header=%s, jwt=%s)", email_header, email
                )
            return email

    # 2순위: 세션 (로컬 OAuth 로그인 시 저장됨)
    return request.session.get("user_email")


def get_user_oauth_token(request: Request) -> dict | None:
    """세션에 저장된 OAuth 토큰을 반환 (Drive API 호출용). 없으면 None."""
    return request.session.get("oauth_token")


def get_user_oauth_access_token(request: Request) -> str | None:
    """세션 OAuth 토큰 dict 에서 access_token '문자열'만 추출 (Drive API 용).

    세션에는 authlib 토큰 dict 전체가 저장돼 있다(auth.py 의 oauth_token).
    그러나 OAuthDriveBackend 의 Credentials(token=...) 는 access_token '문자열'을
    기대한다. dict 를 그대로 넘기면 Drive 호출이 조용히 실패(except→[])하므로,
    라우터는 이 헬퍼로 문자열을 뽑아 ask(user_oauth_token=<문자열>) 로 넘긴다.

    토큰이 없거나(미로그인) access_token 키가 없으면 None 을 반환한다.
    → ask()→OAuthDriveBackend 는 None 토큰을 빈 결과로 처리(graceful degrade,
      Vertex 결과만 사용)하므로 안전하다. access token 만료 시에도 동일하게 graceful.
    """
    token = request.session.get("oauth_token")
    if not token:
        return None
    return token.get("access_token")


def require_user_email(request: Request) -> str:
    """로그인 필수 의존성. 이메일 없으면 401.

    FastAPI 라우터에서 Depends(require_user_email) 로 사용.
    """
    email = get_user_email(request)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return email


def is_domain_allowed(email: str) -> bool:
    """이 이메일의 로그인을 허용할지 판단.

    규칙:
      - 이메일 도메인 == settings.google_domain  (정식 회사 도메인)
      - OR 이메일이 settings.allowed_emails 목록에 있음 (개인 GCP 테스트 예외)
    대소문자 무시.
    """
    email = email.lower().strip()
    domain = email.split("@")[-1]  # "user@example.com" → "example.com"

    # 도메인 매치 (정식 회사 도메인)
    if domain == settings.google_domain.lower():
        return True

    # 이메일 화이트리스트 매치 (개인 GCP 테스트 예외)
    allowed = [e.strip().lower() for e in settings.allowed_emails.split(",") if e.strip()]
    return email in allowed