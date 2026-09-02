"""Search-related API models. Fleshed out in 7~8단계.

Note: the internal retrieval result type is ``app.search.base.SearchResult``
(a dataclass). These pydantic models are for the HTTP boundary only.
"""

from __future__ import annotations

from pydantic import BaseModel


class SearchHit(BaseModel):
    """One search hit as exposed over the API."""

    content: str
    source_title: str
    source_uri: str
    score: float = 0.0
