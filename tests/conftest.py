"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from app.search.base import DocumentSearchService, SearchResult


class FakeBackend(DocumentSearchService):
    """In-memory backend for tests. Returns canned results, never network."""

    backend_name = "fake"

    def __init__(self, results: list[SearchResult] | None = None) -> None:
        self._results = results or []

    async def search(
        self,
        query: str,
        *,
        user_email: str,
        user_oauth_token: str | None = None,
        top_k: int = 20,
    ) -> list[SearchResult]:
        return self._results[:top_k]


@pytest.fixture
def fake_backend() -> FakeBackend:
    return FakeBackend(
        results=[
            SearchResult(
                content="휴가 신청은 인사팀에 제출합니다.",
                source_uri="gs://my-gcp-project-docs/hr.pdf",
                source_title="인사 규정",
                chunk_index=0,
                score=0.9,
            )
        ]
    )
