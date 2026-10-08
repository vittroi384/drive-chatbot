"""애플리케이션 설정.

모든 런타임 설정은 환경변수 / .env 파일에서 오며, pydantic-settings(v2)를
통해 로드된다. 여기에는 하드코딩된 값이 없고, 바로 그 점이 화이트라벨 모델을
가능하게 한다: COMPANY_NAME, SYSTEM_PROMPT, GEMINI_MODEL 등은 모두 배포별
.env 값이다.

사용법:
    from app.config import get_settings
    settings = get_settings()   # 캐시된 싱글톤
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """.env 파일에 대한 타입 지정 뷰(view)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- 애플리케이션 --------------------------------------------------------
    app_name: str = "Drive Chatbot"
    company_name: str = "examplecorp"
    company_logo_url: str = ""
    # 빈 화면(empty state) 추천 질문. '|' 로 구분. 비어 있으면 칩 미표시.
    # 파싱은 suggested_questions_list 프로퍼티 사용. 회사별로 .env 만 바꾸면 됨(코드 0).
    suggested_questions: str = ""
    system_prompt: str = (
        "당신은 사내 문서 기반 어시스턴트입니다. "
        "반드시 제공된 문서 내용에만 근거해 답변하고, "
        "문서에 없는 내용은 절대 지어내지 마세요."
    )
    env: Literal["local", "dev", "prod"] = "local"

    # --- GCP -----------------------------------------------------------------
    gcp_project_id: str = "my-gcp-project"
    gcp_location: str = "asia-northeast3"  # REGION_GENERAL (서울)
    # 서비스 계정 키 파일 경로. 비우면 ADC(GOOGLE_APPLICATION_CREDENTIALS 등)를 따른다.
    gcp_credentials_path: str = ""

    # --- OAuth ---------------------------------------------------------------
    google_client_id: str = ""
    google_client_secret: str = ""
    google_oauth_redirect_uri: str = "http://localhost:8000/auth/callback"
    google_domain: str = "example.com"  # OAuth 도메인 허용 목록(allowlist)
    allowed_emails: str = ""
    session_secret_key: str = ""

    # --- IAP (운영: Cloud Run + IAP) -----------------------------------------
    # X-Goog-IAP-JWT-Assertion 검증에 쓰는 audience.
    # 형식: /projects/<PROJECT_NUMBER>/global/backendServices/<BACKEND_SERVICE_ID>
    # 비어 있으면 IAP 경로 비활성 = 세션(OAuth)만 사용.
    iap_audience: str = ""

    # --- Vertex AI Search ----------------------------------------------------
    # 검색 질의는 engine(app) serving config 로 보낸다.
    #   data store 직접 경로(dataStores/{id}/servingConfigs/default_config)는 404.
    #   정답: engines/{engine_id}/servingConfigs/default_serving_config
    #   (vertex_search_target=engine, vertex_serving_config=default_serving_config)
    vertex_data_store_id: str = ""   # short id, 예: my-docs-datastore_0000000000000
    vertex_engine_id: str = ""       # search app id, 예: drive-chatbot-search_1779696087733
    vertex_serving_config: str = "default_serving_config"
    vertex_location: str = "global"  # REGION_VERTEX_SEARCH

    # --- Gemini --------------------------------------------------------------
    # NOTE(검증 2026-06): gemini-1.5-* / 2.0-* 는 신규 프로젝트에 폐기/차단됨.
    # gemini-3-flash 는 Gemini Developer API 이름일 뿐 Vertex 엔 미존재(404) →
    # Vertex 라이브인 gemini-2.5-flash 사용(2026-10-16 폐기 예정, 베타 기간 커버).
    # 모델명은 .env 한 줄로 교체 가능.
    gemini_model: str = "gemini-2.5-flash"
    gemini_location: str = "us-central1"  # REGION_VERTEX (서울 미지원 모델 회피)

    # --- 검색 백엔드 ---------------------------------------------------------
    search_mode: Literal["vertex", "oauth", "hybrid"] = "hybrid"
    enable_validation: bool = True
    vertex_search_target: Literal["data_store", "engine"] = "engine"
    # --- GCS -----------------------------------------------------------------
    gcs_docs_bucket: str = "my-gcp-project-docs"

    # --- Firestore -----------------------------------------------------------
    # database.py 가 AsyncClient(database=...) 에 넘기는 값. "(default)" = 기본 DB.
    firestore_database: str = "(default)"

    # --- 요청 제한 (Rate limit) ----------------------------------------------
    rate_limit_per_minute: int = 5

    # --- 파생 값 (computed) --------------------------------------------------
    @property
    def suggested_questions_list(self) -> list[str]:
        """추천 질문 칩 목록. '|' 구분, 공백/빈 항목 제거. 비어 있으면 빈 리스트(칩 미표시)."""
        return [q.strip() for q in self.suggested_questions.split("|") if q.strip()]


@lru_cache
def get_settings() -> Settings:
    """캐시된 Settings 싱글톤을 반환한다.

    @lru_cache 덕분에 .env 파일은 프로세스당 정확히 한 번만 파싱된다.
    테스트에서는 ``get_settings.cache_clear()`` 로 캐시를 비울 수 있다.
    """
    return Settings()