"""Hybrid backend (Vertex + OAuth Drive 결합).

두 backend를 **병렬로**(asyncio.gather) 호출하고 결과를 merge 한다.

[설계 포인트 — score 정규화]
    base.py의 contract: score는 backend 간 비교 불가, normalize는 Hybrid 책임.
    Vertex score는 0.0이 많고 Drive는 0.5 고정이라 raw 비교는 무의미하다.
    → 각 backend가 이미 자기 relevance 순으로 정렬해 주므로, rank 기반으로
      [0,1] 정규화한다 (1등=1.0, 꼴등≈0). 그 다음 합쳐서 다시 정렬.
    raw score는 metadata["raw_score"]에 보존.
"""

from __future__ import annotations

import asyncio
import logging

from .base import DocumentSearchService, SearchResult

logger = logging.getLogger(__name__)


class HybridBackend(DocumentSearchService):
    """Vertex(공용 corpus) + OAuth Drive(개인 문서)를 합치는 backend."""

    backend_name = "hybrid"

    def __init__(
        self,
        *,
        vertex: DocumentSearchService,
        oauth: DocumentSearchService,
    ) -> None:
        self.vertex = vertex
        self.oauth = oauth

    async def search(
        self,
        query: str,
        *,
        user_email: str,
        user_oauth_token: str | None = None,
        top_k: int = 20,
    ) -> list[SearchResult]:
        # top_k의 절반씩 각 backend에 할당.
        half = max(1, top_k // 2)

        # 두 backend 동시 실행. 한쪽이 터져도 나머지는 살리려고 return_exceptions=True.
        vertex_res, oauth_res = await asyncio.gather(
            self.vertex.search(query, user_email=user_email, top_k=half),
            self.oauth.search(
                query,
                user_email=user_email,
                user_oauth_token=user_oauth_token,
                top_k=half,
            ),
            return_exceptions=True,
        )

        merged: list[SearchResult] = []
        for label, res in (("vertex", vertex_res), ("oauth", oauth_res)):
            if isinstance(res, BaseException):
                logger.error("[hybrid] %s backend failed", label, exc_info=res)
                continue
            merged.extend(self._normalize_by_rank(res))

        # 정규화된 score 기준 내림차순 → top_k 만큼 cut.
        merged.sort(key=lambda r: r.score, reverse=True)
        logger.info(
            "[hybrid] query=%r → merged %d (vertex+oauth), return top %d",
            query,
            len(merged),
            min(top_k, len(merged)),
        )
        return merged[:top_k]

    @staticmethod
    def _normalize_by_rank(results: list[SearchResult]) -> list[SearchResult]:
        """rank 기반 [0,1] 정규화. results는 이미 backend별 relevance 순 정렬 가정."""
        n = len(results)
        for i, r in enumerate(results):
            r.metadata["raw_score"] = r.score
            r.score = round(1.0 - (i / n), 4) if n > 1 else 1.0
        return results
