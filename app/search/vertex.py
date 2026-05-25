"""Vertex AI Search backend (GCS-indexed corpus).

Skeleton only. Real implementation lands in 7단계 (AI 로직 + Re-ranking).
Queries the Vertex AI Search datastore created in 3단계.
"""

from __future__ import annotations

from .base import DocumentSearchService, SearchResult


class VertexSearchBackend(DocumentSearchService):
    """Searches the company-wide corpus indexed in Vertex AI Search.

    Server-side only: does not use the user's OAuth token. Access control is
    coarse (whole-corpus); per-user filtering happens at the GCS/datastore
    level if/when needed.
    """

    backend_name = "vertex"

    def __init__(
        self,
        *,
        project_id: str,
        location: str,
        data_store_id: str,
        serving_config: str,
    ) -> None:
        self.project_id = project_id
        self.location = location
        self.data_store_id = data_store_id
        self.serving_config = serving_config

    async def search(
        self,
        query: str,
        *,
        user_email: str,
        user_oauth_token: str | None = None,
        top_k: int = 20,
    ) -> list[SearchResult]:
        # TODO(7단계): call google-cloud-discoveryengine SearchServiceAsyncClient,
        # map response.results -> SearchResult.
        raise NotImplementedError("VertexSearchBackend.search lands in 7단계")
