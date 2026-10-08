"""IAP JWT 검증 경로 테스트 (app/utils/auth_utils.get_user_email).

네트워크 없이 검증한다: google-auth 의 verify_token 을 monkeypatch 로 대체.
"""

from __future__ import annotations

from typing import Any

import pytest
from starlette.requests import Request

from app.utils import auth_utils

AUDIENCE = "/projects/000000000000/global/backendServices/0000000000000000000"


def _request(headers: dict[str, str]) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/rooms",
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "session": {},  # SessionMiddleware 가 없으므로 빈 세션을 직접 넣는다
    }
    return Request(scope)


@pytest.fixture
def iap_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_utils.settings, "iap_audience", AUDIENCE)


def test_forged_email_header_without_assertion_is_unauthenticated(
    iap_enabled: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 이메일 헤더만 위조해 넣고 JWT assertion 이 없으면 None (401 로 이어짐).
    def must_not_be_called(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("verify_token must not be called without assertion")

    monkeypatch.setattr(auth_utils.id_token, "verify_token", must_not_be_called)
    req = _request(
        {"X-Goog-Authenticated-User-Email": "accounts.google.com:evil@example.com"}
    )
    assert auth_utils.get_user_email(req) is None


def test_valid_assertion_returns_payload_email(
    iap_enabled: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}

    def fake_verify_token(token: str, request: Any, **kwargs: Any) -> dict[str, Any]:
        seen["token"] = token
        seen["audience"] = kwargs.get("audience")
        seen["certs_url"] = kwargs.get("certs_url")
        return {
            "iss": "https://cloud.google.com/iap",
            "email": "User@Example.com",
            "sub": "accounts.google.com:1234567890",
        }

    monkeypatch.setattr(auth_utils.id_token, "verify_token", fake_verify_token)
    req = _request(
        {
            "X-Goog-IAP-JWT-Assertion": "header.payload.signature",
            # 이메일 헤더는 참고용 — JWT payload 의 email 이 우선한다.
            "X-Goog-Authenticated-User-Email": "accounts.google.com:someone-else@example.com",
        }
    )
    assert auth_utils.get_user_email(req) == "user@example.com"
    assert seen == {
        "token": "header.payload.signature",
        "audience": AUDIENCE,
        "certs_url": "https://www.gstatic.com/iap/verify/public_key",
    }
