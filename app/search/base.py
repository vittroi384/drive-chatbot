"""Search backend abstraction layer.

This module defines the abstract contract that every document search backend
must satisfy. The point of this abstraction is to keep the rest of the
application (AI service, routers) decoupled from *how* documents are actually
retrieved, so that the retrieval backend can be swapped without touching
business logic.

Current implementations (see sibling modules):
    - VertexSearchBackend  : Vertex AI Search datastore (GCS-indexed docs)
    - OAuthDriveBackend    : per-user Google Drive search via OAuth token
    - HybridBackend        : merge + re-rank results from both

Future migration options preserved by this contract (do NOT implement now):
    - PgVectorBackend      : self-hosted pgvector, if/when we move off Vertex
                             Search for cost or control reasons (see 22단계).
    - Additional connectors: Notion / Confluence / Slack search, etc.

Because every backend returns the same ``SearchResult`` shape and implements
the same ``search`` coroutine, migration is a config change
(``SEARCH_MODE`` in .env), not a rewrite.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SearchResult:
    """A single retrieved chunk, normalized across all backends.

    Every backend MUST map its native response into this shape so downstream
    code (re-ranking, prompt assembly, answer-grounding checks) never needs to
    know which backend produced the result.

    Attributes:
        content: The retrieved text chunk.
        source_uri: Canonical locator (gs:// URI, Drive file URL, etc.).
        source_title: Human-readable document title for citations.
        chunk_index: Position of this chunk within its source document.
        score: Backend-native relevance score. NOT comparable across
            backends without normalization (HybridBackend handles that).
        metadata: Free-form extras (mime type, last_modified, page, etc.).
    """

    content: str
    source_uri: str
    source_title: str
    chunk_index: int = 0
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class DocumentSearchService(ABC):
    """Abstract base class for all document search backends.

    Subclasses implement ``search``. Keeping a single async method keeps the
    surface small and makes every backend trivially mockable in tests
    (see tests/test_search.py).
    """

    #: Short identifier used in logs / metrics (e.g. "vertex", "oauth", "hybrid").
    backend_name: str = "base"

    @abstractmethod
    async def search(
        self,
        query: str,
        *,
        user_email: str,
        user_oauth_token: str | None = None,
        top_k: int = 20,
    ) -> list[SearchResult]:
        """Retrieve the most relevant chunks for ``query``.

        Args:
            query: The user's natural-language question.
            user_email: Identity of the requester. Used for per-user access
                control and usage metering. Required even for shared corpora
                so backends can enforce domain/tenant boundaries.
            user_oauth_token: The user's Google OAuth access token. Required
                by OAuthDriveBackend to search the user's own Drive; ignored
                by purely server-side backends like VertexSearchBackend.
            top_k: How many candidates to return *before* any re-ranking.
                The AI service re-ranks top_k down to a smaller top-5
                (see 7단계).

        Returns:
            Up to ``top_k`` SearchResult items, ordered by the backend's own
            relevance score (descending). May be empty.

        Raises:
            NotImplementedError: If the concrete backend is not yet wired up.
        """
        raise NotImplementedError
