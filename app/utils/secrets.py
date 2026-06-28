"""Secret Manager 접근 헬퍼 (Phase 2 / 10단계 — 스켈레톤).

목적
----
로컬/개발에서는 비밀을 .env 로 주입하고(개발 편의), 운영(Cloud Run, 11단계)에서는
GCP Secret Manager 에서 조회한다(운영 보안). 그 분기를 이 한 곳에 가둬,
호출부(ai_service / auth 등)는 "비밀이 어디서 오는지" 몰라도 되게 한다.

설계 메모 (왜 이렇게)
--------------------
- 분기 키는 settings.env. 이 프로젝트의 env Literal 은 ["local","dev","prod"] 이므로
  운영 판별은 env == "prod" 다. (10단계 프롬프트의 'ENV=production' 표기는 코드 실제값
  "prod" 로 정정 — 오버레이 §12 충돌 시 명시 규칙.)
- google-cloud-secret-manager 는 함수 안에서 lazy import 한다. 로컬 컨테이너는 이 경로를
  타지 않으므로, 모듈 로딩 비용/실패 위험을 운영 경로로만 한정한다.
- @lru_cache 로 (secret_id, version) 단위 캐싱. Secret Manager 는 access 호출당 과금이라
  한 번 읽으면 메모리에 보관해 재호출 시 네트워크 0.

★ 스켈레톤 범위 (10단계): 함수는 완성돼 import 하면 바로 쓸 수 있으나, 아직 어떤
  런타임 코드에도 배선하지 않는다. 실제 호출 연결(main.py / settings 대체)은 11단계.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.config import get_settings

logger = logging.getLogger(__name__)


# Secret Manager 의 secret 리소스 ID ←→ 로컬(.env) Settings 필드 매핑.
# 운영에서는 이 ID 로 조회하고, 로컬에서는 대응하는 settings 속성을 그대로 돌려준다.
# 11단계에서 실제 secret 들을 이 ID 로 생성한다(예: gcloud secrets create ...).
_LOCAL_FALLBACK: dict[str, str] = {
    "google-client-secret": "google_client_secret",
    "session-secret-key": "session_secret_key",
    # 참고: 서비스 계정 키(JSON)는 Secret Manager 대상이 아니다.
    # Cloud Run 은 Workload Identity 로 키 파일 자체가 불필요(11단계). 로컬만 -v 마운트.
}


@lru_cache
def get_secret(secret_id: str, version: str = "latest") -> str:
    """비밀 하나를 반환한다.

    - 로컬/개발(settings.env != "prod"): 대응하는 .env 값을 그대로 반환.
    - 운영(settings.env == "prod"): GCP Secret Manager 에서 조회.

    Args:
        secret_id: Secret Manager 의 secret 이름(= _LOCAL_FALLBACK 키).
        version: secret 버전. 기본 "latest".

    Returns:
        비밀 평문 문자열.
    """
    settings = get_settings()

    # --- 로컬/개발: .env 폴백 -------------------------------------------------
    if settings.env != "prod":
        field = _LOCAL_FALLBACK.get(secret_id)
        if field is None:
            raise KeyError(
                f"로컬 폴백에 매핑되지 않은 secret_id: {secret_id!r}. "
                f"_LOCAL_FALLBACK 에 (secret_id -> settings 필드)를 추가하세요."
            )
        return str(getattr(settings, field))

    # --- 운영(11단계 활성화): Secret Manager 조회 ----------------------------
    # lazy import: 운영 경로에서만 의존성을 로딩한다(로컬 컨테이너는 미진입).
    from google.cloud import secretmanager  # noqa: PLC0415

    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{settings.gcp_project_id}/secrets/{secret_id}/versions/{version}"
    response = client.access_secret_version(request={"name": name})
    payload = response.payload.data.decode("UTF-8")
    logger.info("Secret Manager 조회 완료: %s (version=%s)", secret_id, version)
    return payload
