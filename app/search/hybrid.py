"""Hybrid backend: merge + re-rank Vertex + OAuth Drive results.

Skeleton only. Real implementation lands in 7단계.
Fans out to both backends concurrently, normalizes their scores, dedupes,
and returns a merged candidate list for the AI service to re-rank.
"""

from __future__ import annotations

from .base import DocumentSearchService, SearchResult
from .oauth_drive import OAuthDriveBackend
from .vertex import VertexSearchBackend


class HybridBackend(DocumentSearchService):
    """Combines company corpus (Vertex) with the user's personal Drive (OAuth)."""

    backend_name = "hybrid"

    def __init__(
        self,
        *,
        vertex: VertexSearchBackend,
        oauth_drive: OAuthDriveBackend,
    ) -> None:
        self.vertex = vertex
        self.oauth_drive = oauth_drive

    async def search(
        self,
        query: str,
        *,
        user_email: str,
        user_oauth_token: str | None = None,
        top_k: int = 20,
    ) -> list[SearchResult]:
        # TODO(7단계): asyncio.gather both backends, normalize scores,
        # dedupe by source_uri, return merged top_k.
        raise NotImplementedError("HybridBackend.search lands in 7단계")
