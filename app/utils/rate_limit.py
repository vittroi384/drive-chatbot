"""Rate limiting (ADR 0009).

slowapi 기반, 1분당 N회 제한. ★키는 IP 가 아니라 user_email★ 이 핵심.

[왜 IP 가 아니라 user_email 인가]
slowapi 기본 키는 get_remote_address(=클라이언트 IP). 그러나 운영(Cloud Run +
IAP)에서는 모든 트래픽이 프록시/IAP 를 거쳐 들어오므로 IP 가 공유되거나 프록시 IP 로
보인다 → IP 기준이면 한 사용자가 한도를 쓰면 전체 사용자가 막힌다. 사용자별 비용/어뷰징
방어가 목적이므로 인증된 user_email 을 키로 쓰고, 미인증(이메일 없음) 일 때만 IP 로 폴백한다.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.config import get_settings
from app.utils.auth_utils import get_user_email

settings = get_settings()


def get_user_key(request: Request) -> str:
    """Rate limit 키 생성. 1순위 인증 이메일, 2순위 IP(폴백).

    slowapi 가 매 요청마다 이 함수를 호출해 키를 만든다. 같은 키 = 같은 카운터.
    이메일은 대소문자를 정규화해 'User@x' 와 'user@x' 가 한 사람으로 묶이게 한다.
    """
    email = get_user_email(request)  # IAP 헤더 우선, 세션 폴백 (auth_utils)
    if email:
        return f"user:{email.lower()}"  # 사용자별 카운터
    return f"ip:{get_remote_address(request)}"  # 미인증 폴백 (로컬/엣지 케이스)


# Limiter 싱글톤. default_limits 는 '기본 한도'지만, 실제 강제는 라우터의
# @limiter.limit(...) 데코레이터가 한다(우리는 비싼 /api/chat 에만 건다).
# default_limits 를 모든 경로에 자동 적용하려면 SlowAPIMiddleware 가 필요한데,
# 의도적으로 도입하지 않는다 — 값싼 rooms CRUD 까지 제한할 이유가 없다.
limiter = Limiter(
    key_func=get_user_key,
    default_limits=[f"{settings.rate_limit_per_minute}/minute"],
)
