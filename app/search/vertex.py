"""Vertex AI Search backend (GCS-indexed corpus).

Vertex AI Search datastore를 query 하는 server-side backend.
사용자 OAuth token을 쓰지 않는다 — access control은 coarse(corpus 전체).

[중요] retrieval-only로 동작한다.
    검색 앱이 콘솔에서 "생성형 대답 ON"(Enterprise) 이어도, 여기서는
    ``summary_spec``을 **일부러 넣지 않는다**. summary(생성형 요약)는 요청마다
    summary_spec이 있어야만 생성되므로, 빼면 문서/스니펫만 받고 생성 과금이
    붙지 않는다. 답변 생성은 ai_service.generate_answer가 단독 책임 → 이중과금 방지.
"""

from __future__ import annotations

import inspect
import logging
import re
from typing import Any

from google.api_core.client_options import ClientOptions
from google.cloud import discoveryengine_v1 as discoveryengine

from .base import DocumentSearchService, SearchResult

logger = logging.getLogger(__name__)

# Vertex 스니펫은 매칭어를 <b>...</b>로 감싸서 돌려줌 → 태그 제거 (rerank/validate 노이즈 정리)
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return _TAG_RE.sub("", text or "").strip()


class VertexSearchBackend(DocumentSearchService):
    """Vertex AI Search에 indexing된 회사 전체 corpus를 검색.

    serving_config 경로는 두 가지 target을 지원한다 (.env의 VERTEX_SEARCH_TARGET):
        - "data_store" : dataStores/{id}/servingConfigs/{cfg}  (기본, .env와 일치)
        - "engine"     : engines/{id}/servingConfigs/{cfg}     (NOT_FOUND 시 fallback)
    둘 다 동작하며, 어떤 게 맞는지는 runtime에서 한 번 확인하면 된다.
    """

    backend_name = "vertex"

    def __init__(
        self,
        *,
        project_id: str,
        location: str,
        data_store_id: str,
        serving_config: str,
        engine_id: str | None = None,
        search_target: str = "data_store",
    ) -> None:
        self.project_id = project_id
        self.location = location  # Vertex Search는 보통 "global" (.env VERTEX_LOCATION)
        self.data_store_id = data_store_id
        self.serving_config = serving_config
        self.engine_id = engine_id
        self.search_target = search_target
        self._client: discoveryengine.SearchServiceAsyncClient | None = None

    def _get_client(self) -> discoveryengine.SearchServiceAsyncClient:
        """Async client를 lazy 하게 생성 (import time에 credential 요구 X)."""
        if self._client is None:
            # location이 global이 아니면 regional endpoint를 명시해야 한다.
            client_options = (
                ClientOptions(
                    api_endpoint=f"{self.location}-discoveryengine.googleapis.com"
                )
                if self.location != "global"
                else None
            )
            self._client = discoveryengine.SearchServiceAsyncClient(
                client_options=client_options
            )
        return self._client

    def _serving_config_path(self) -> str:
        """target에 따라 serving_config full resource name을 build."""
        base = (
            f"projects/{self.project_id}"
            f"/locations/{self.location}"
            f"/collections/default_collection"
        )
        if self.search_target == "engine" and self.engine_id:
            return (
                f"{base}/engines/{self.engine_id}/servingConfigs/{self.serving_config}"
            )
        return f"{base}/dataStores/{self.data_store_id}/servingConfigs/{self.serving_config}"

    async def search(
        self,
        query: str,
        *,
        user_email: str,
        user_oauth_token: str | None = None,
        top_k: int = 20,
    ) -> list[SearchResult]:
        client = self._get_client()
        serving_config = self._serving_config_path()

        # content_search_spec: 스니펫 + extractive answer만 요청 (summary_spec 없음 → retrieval-only)
        content_spec = discoveryengine.SearchRequest.ContentSearchSpec(
            snippet_spec=discoveryengine.SearchRequest.ContentSearchSpec.SnippetSpec(
                return_snippet=True
            ),
            extractive_content_spec=(
                discoveryengine.SearchRequest.ContentSearchSpec.ExtractiveContentSpec(
                    max_extractive_answer_count=1
                )
            ),
        )
        request = discoveryengine.SearchRequest(
            serving_config=serving_config,
            query=query,
            page_size=top_k,
            content_search_spec=content_spec,
        )

        try:
            # [함정] async client의 search()는 SDK 버전에 따라 coroutine을 반환하기도,
            # pager를 바로 반환하기도 한다. isawaitable로 두 경우 모두 안전 처리.
            call = client.search(request=request)
            pager = await call if inspect.isawaitable(call) else call

            results: list[SearchResult] = []
            async for result in pager:
                mapped = self._to_search_result(result)
                if mapped is not None:
                    results.append(mapped)

            logger.info(
                "[vertex] query=%r → %d results (target=%s)",
                query,
                len(results),
                self.search_target,
            )
            return results
        except Exception:  # noqa: BLE001 - 정식 에러 핸들링은 후속
            # 검색 실패는 빈 리스트로 안전하게 fallback (pipeline 중단 방지).
            logger.error("[vertex] search failed for query=%r", query, exc_info=True)
            return []

    @staticmethod
    def _to_search_result(result: Any) -> SearchResult | None:
        """discoveryengine SearchResult → 우리 SearchResult 로 mapping.

        derived_struct_data는 proto-plus Struct(dict 유사)이고 nested 구조라
        per-result try/except로 감싼다. 하나가 malformed여도 batch 전체가 죽지 않게.
        """
        try:
            doc = result.document
            dsd = doc.derived_struct_data  # Struct (dict-like)

            def g(key: str, default: Any = None) -> Any:
                try:
                    return dsd[key]
                except (KeyError, TypeError):
                    return default

            title = g("title") or doc.id or "(제목 없음)"
            link = g("link") or ""

            # 본문 우선순위: extractive_answer > snippet
            content = ""
            extractive = g("extractive_answers")
            if extractive:
                try:
                    content = extractive[0].get("content", "") or ""
                except (AttributeError, IndexError, KeyError, TypeError):
                    content = ""
            if not content:
                snippets = g("snippets")
                if snippets:
                    try:
                        content = snippets[0].get("snippet", "") or ""
                    except (AttributeError, IndexError, KeyError, TypeError):
                        content = ""

            # relevance score: Vertex가 항상 주지는 않음 → 0.0 fallback.
            # backend 간 비교는 HybridBackend가 정규화하므로 raw 그대로 둔다.
            score = 0.0
            try:
                ms = getattr(result, "model_scores", None)
                if ms and "relevance" in ms:
                    vals = ms["relevance"].values
                    if vals:
                        score = float(vals[0])
            except Exception:  # noqa: BLE001
                score = 0.0

            return SearchResult(
                content=_strip_html(content),
                source_uri=link,
                source_title=_strip_html(str(title)) or "(제목 없음)",
                chunk_index=0,
                score=score,
                metadata={"backend": "vertex", "doc_id": getattr(doc, "id", None)},
            )
        except Exception:  # noqa: BLE001
            logger.warning("[vertex] failed to map one result", exc_info=True)
            return None
