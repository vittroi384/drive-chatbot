"""Tests for the search backend abstraction.

These tests assert the *contract*, not any real backend. They guarantee that:
  - the ABC cannot be instantiated directly,
  - SearchResult has the agreed shape,
  - a conforming backend satisfies the async interface.
"""

from __future__ import annotations

import pytest

from app.search.base import DocumentSearchService, SearchResult


def test_abc_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        DocumentSearchService()  # type: ignore[abstract]


def test_search_result_shape() -> None:
    r = SearchResult(
        content="hello",
        source_uri="gs://bucket/doc.pdf",
        source_title="Doc",
    )
    assert r.chunk_index == 0
    assert r.score == 0.0
    assert r.metadata == {}


@pytest.mark.asyncio
async def test_conforming_backend_returns_results(fake_backend) -> None:
    results = await fake_backend.search("휴가", user_email="me@example.com")
    assert len(results) == 1
    assert results[0].source_title == "인사 규정"
    assert isinstance(results[0], SearchResult)
