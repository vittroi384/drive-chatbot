"""Application configuration.

All runtime config comes from environment variables / the .env file, loaded
via pydantic-settings (v2). Nothing is hard-coded here, which is what makes the
white-label model work: COMPANY_NAME, SYSTEM_PROMPT, GEMINI_MODEL, etc. are all
per-deployment .env values (see master context: 화이트라벨 구조).

Usage:
    from app.config import get_settings
    settings = get_settings()   # cached singleton
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed view over the .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---------------------------------------------------------
    app_name: str = "Drive Chatbot"
    company_name: str = "aicoschool"
    company_logo_url: str = ""
    system_prompt: str = (
        "당신은 사내 문서 기반 어시스턴트입니다. "
        "반드시 제공된 문서 내용에만 근거해 답변하고, "
        "문서에 없는 내용은 절대 지어내지 마세요."
    )
    env: Literal["local", "dev", "prod"] = "local"

    # --- GCP -----------------------------------------------------------------
    gcp_project_id: str = "drive-chatbot-dev-personal"
    gcp_location: str = "asia-northeast3"  # REGION_GENERAL (서울)
    gcp_credentials_path: str = r"C:\dev\secrets\chatbot-app-sa.json"

    # --- OAuth ---------------------------------------------------------------
    google_client_id: str = ""
    google_client_secret: str = ""
    google_oauth_redirect_uri: str = "http://localhost:8000/auth/callback"
    google_domain: str = "aicoschool.com"  # OAuth domain allowlist
    session_secret_key: str = ""

    # --- Vertex AI Search ----------------------------------------------------
    # NOTE(3단계): data store 와 search app(engine) 이 둘 다 생성됨.
    # 결정 필요(7단계): 검색 질의를 data store serving config 로 보낼지,
    # engine(app) serving config 로 보낼지. discoveryengine SDK 경로 형식
    # 확인 후 확정. 지금은 둘 다 .env 에 보존만.
    vertex_data_store_id: str = ""   # short id, 예: drive-chatbot-docs_1779695818715
    vertex_engine_id: str = ""       # search app id, 예: drive-chatbot-search_1779696087733
    vertex_serving_config: str = "default_config"
    vertex_location: str = "global"  # REGION_VERTEX_SEARCH

    # --- Gemini --------------------------------------------------------------
    # NOTE(검증 2026-05): gemini-1.5-* / 2.0-* are retired/closed to new
    # projects. 2.5-flash retires 2026-10-16 (mid-beta). Default chosen to
    # survive the whole beta window without a forced migration. See 보조 ADR.
    gemini_model: str = "gemini-3-flash"
    gemini_location: str = "us-central1"  # REGION_VERTEX (서울 미지원 모델 회피)

    # --- Search backend ------------------------------------------------------
    search_mode: Literal["vertex", "oauth", "hybrid"] = "hybrid"

    # --- GCS -----------------------------------------------------------------
    gcs_docs_bucket: str = "drive-chatbot-dev-personal-docs"

    # --- Firestore -----------------------------------------------------------
    firestore_database: str = "(default)"

    # --- Rate limit ----------------------------------------------------------
    rate_limit_per_minute: int = 5


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings singleton.

    @lru_cache ensures the .env file is parsed exactly once per process.
    Tests can clear the cache with ``get_settings.cache_clear()``.
    """
    return Settings()
