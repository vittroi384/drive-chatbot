"""검색 백엔드 추상화 레이어 (search backend abstraction).

모든 문서 검색 backend가 따라야 하는 추상 contract를 정의한다. 이 추상화의
목적은 앱의 나머지 부분(AI service, router)을 "문서를 실제로 *어떻게* 가져오는가"
와 decouple 하는 것 — retrieval backend를 business logic 건드리지 않고 교체할
수 있게 하기 위함이다.

현재 구현체 (sibling 모듈 참고):
    - VertexSearchBackend  : Vertex AI Search datastore (GCS-indexed 문서)
    - OAuthDriveBackend    : 사용자별 Google Drive 검색 (OAuth token 사용)
    - HybridBackend        : 두 backend 결과를 merge + 정규화

이 contract로 보존되는 future migration 옵션 (지금 구현하지 말 것):
    - PgVectorBackend      : self-hosted pgvector. 비용/제어 이유로 Vertex
                             Search에서 이탈할 경우.
    - 추가 connector       : Notion / Confluence / Slack 검색 등.

모든 backend가 동일한 ``SearchResult`` 모양을 반환하고 동일한 ``search``
coroutine을 구현하기 때문에, migration은 rewrite가 아니라 config 변경
(.env의 ``SEARCH_MODE``)으로 끝난다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SearchResult:
    """단일 retrieved chunk. 모든 backend에 걸쳐 normalize된 공통 모양.

    각 backend는 자신의 native response를 반드시 이 모양으로 mapping 해야 한다.
    그래야 downstream 코드(re-ranking, prompt assembly, answer-grounding 검증)가
    "어느 backend가 만든 결과인지" 전혀 몰라도 동작한다.

    Attributes:
        content: retrieved된 text chunk (본문/스니펫/추출 답변).
        source_uri: canonical locator (gs:// URI, Drive file URL 등).
        source_title: 인용(citation)용 사람이 읽을 수 있는 문서 제목.
        chunk_index: source 문서 내에서 이 chunk의 위치.
        score: backend-native relevance score. 정규화 없이는 backend 간
            비교 불가 (HybridBackend가 normalize 담당).
        metadata: 자유 형식 부가정보 (mime type, last_modified, page 등).
    """

    content: str
    source_uri: str
    source_title: str
    chunk_index: int = 0
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class DocumentSearchService(ABC):
    """모든 문서 검색 backend의 abstract base class.

    subclass는 ``search``를 구현한다. async method 하나로 surface를 작게
    유지해서, 모든 backend를 test에서 손쉽게 mock 할 수 있게 한다
    (tests/test_search.py 참고).
    """

    #: 로그/metric에서 쓰는 짧은 식별자 (예: "vertex", "oauth", "hybrid").
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
        """``query``에 가장 relevant한 chunk들을 retrieve 한다.

        Args:
            query: 사용자의 자연어 질문.
            user_email: 요청자 identity. 사용자별 access control + 사용량
                metering에 사용. 공용 corpus에서도 backend가 domain/tenant
                boundary를 enforce 할 수 있도록 required.
            user_oauth_token: 사용자의 Google OAuth access token. 사용자
                본인 Drive를 검색하는 OAuthDriveBackend에 required. Vertex처럼
                순수 server-side backend는 무시한다.
            top_k: re-ranking *이전에* 반환할 candidate 수. AI service가 top_k를
                더 작은 top-5로 re-rank 한다 (ai_service.ask 참고).

        Returns:
            backend 자체 relevance score 기준 내림차순으로 정렬된 최대 ``top_k``개
            SearchResult. 비어 있을 수 있음.

        Raises:
            NotImplementedError: 해당 concrete backend가 아직 wiring 안 된 경우.
        """
        raise NotImplementedError
