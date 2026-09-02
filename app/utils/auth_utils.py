"""IAP/OAuth 통합 인증 유틸.

로컬은 OAuth 세션, 운영은 Cloud Run + IAP(11단계). 두 환경에서 동일한 코드가
돌도록 "이메일을 어디서 얻든 get_user_email() 하나로 통일"하는 추상화 레이어.
나머지 코드(라우터/미들웨어)는 환경 분기를 몰라도 됨.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.config import get_settings

settings = get_settings()

# IAP 가 붙이는 헤더 이름. 운영(Cloud Run + IAP)에서만 신뢰 가능.
# ⚠️ 로컬에서는 누구나 수동 주입 가능 → 위조 위험. 로컬 테스트 시 주입 금지.
_IAP_EMAIL_HEADER = "X-Goog-Authenticated-User-Email"
_IAP_PREFIX = "accounts.google.com:"


def get_user_email(request: Request) -> str | None:
    """현재 요청자의 이메일을 반환. 없으면 None.

    우선순위:
      1) IAP 헤더 (운영) — accounts.google.com: 접두사 제거
      2) 세션의 user_email (로컬 OAuth)
    """
    # 1순위: IAP 헤더 (운영 환경에서 IAP 통과 시에만 존재)
    iap_value = request.headers.get(_IAP_EMAIL_HEADER)
    if iap_value:
        # "accounts.google.com:user@x.com" → "user@x.com"
        return iap_value.removeprefix(_IAP_PREFIX)

    # 2순위: 세션 (로컬 OAuth 로그인 시 저장됨)
    return request.session.get("user_email")


def get_user_oauth_token(request: Request) -> dict | None:
    """세션에 저장된 OAuth 토큰을 반환 (Drive API 호출용). 없으면 None."""
    return request.session.get("oauth_token")


def get_user_oauth_access_token(request: Request) -> str | None:
    """세션 OAuth 토큰 dict 에서 access_token '문자열'만 추출 (Drive API 용).

    [S1] 세션에는 authlib 토큰 dict 전체가 저장돼 있다(auth.py 의 oauth_token).
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

    규칙(5단계 결정, 오버레이 섹션 21):
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