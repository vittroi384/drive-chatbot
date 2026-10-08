"""검색 backend 패키지 + factory.

``get_search_backend()``이 .env의 SEARCH_MODE를 읽어 적절한 backend instance를
돌려준다. 앱의 나머지 코드(ai_service)는 이 factory만 알면 되고, 구체 backend는
모른다 (base.py의 contract 그대로).
"""

from __future__ import annotations

from app.config import Settings, get_settings

from .base import DocumentSearchService, SearchResult
from .hybrid import HybridBackend
from .oauth_drive import OAuthDriveBackend
from .vertex import VertexSearchBackend

__all__ = [
    "DocumentSearchService",
    "SearchResult",
    "VertexSearchBackend",
    "OAuthDriveBackend",
    "HybridBackend",
    "get_search_backend",
]


def _build_vertex(settings: Settings) -> VertexSearchBackend:
    """settings에서 Vertex backend를 조립. location은 VERTEX_LOCATION(global) 사용."""
    return VertexSearchBackend(
        project_id=settings.gcp_project_id,
        location=settings.vertex_location,
        data_store_id=settings.vertex_data_store_id,
        serving_config=settings.vertex_serving_config,
        engine_id=getattr(settings, "vertex_engine_id", None),
        search_target=getattr(settings, "vertex_search_target", "data_store"),
    )


def get_search_backend() -> DocumentSearchService:
    """SEARCH_MODE에 따라 backend를 반환.

    "vertex" → 공용 corpus만 / "oauth" → 사용자 Drive만 / "hybrid" → 둘 다.
    알 수 없는 값은 ValueError (조용히 잘못된 backend로 넘어가지 않게).
    """
    settings = get_settings()
    mode = (settings.search_mode or "").strip().lower()

    if mode == "vertex":
        return _build_vertex(settings)
    if mode == "oauth":
        return OAuthDriveBackend()
    if mode == "hybrid":
        return HybridBackend(
            vertex=_build_vertex(settings),
            oauth=OAuthDriveBackend(),
        )
    raise ValueError(
        f"Unknown SEARCH_MODE: {settings.search_mode!r} "
        "(expected one of: 'vertex', 'oauth', 'hybrid')"
    )
