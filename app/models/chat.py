"""Chat / Room API 모델 (API 경계 전용).

내부 검색 결과 타입은 app.search.base.SearchResult(dataclass)이고,
저장은 Firestore dict다. 이 pydantic 모델들은 HTTP 입출력 경계에서만 쓴다.

채팅 경로의 '출처'는 {title, uri, score} 한 가지 모양으로 통일.
  - ai_service.ask() 출력이 이미 이 모양 (ai_service.py:413-416)
  - database.save_message(sources=...) 가 그대로 저장 (database.py:232)
  - get_messages() 가 그대로 반환
  → SourceItem 이 전 구간 1:1 매핑, 변환 코드 0.
  (models/search.py 의 SearchHit 는 raw-search 용 별도 모양 → 여기서 안 다룸)
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SourceItem(BaseModel):
    """답변 출처 1건. ask() 출력 / Firestore 저장과 동일한 키 모양."""

    title: str
    uri: str
    score: float = 0.0


# ===========================================================================
# 요청 (request body)
# ===========================================================================
class ChatRequest(BaseModel):
    """POST /api/chat 입력.

    query 길이 제한은 입력 검증이자 비용 방어선이다(과도한 토큰 차단).
    """

    query: str = Field(..., min_length=1, max_length=2000)
    room_id: str | None = None


class FeedbackRequest(BaseModel):
    """POST /api/rooms/{room_id}/messages/{message_id}/feedback 입력.

    pattern 으로 up|down 만 허용 — BigQuery 만족도 집계(예정)의 값 무결성.
    """

    feedback: str = Field(pattern="^(up|down)$")


# ===========================================================================
# 응답 (response body)
# ===========================================================================
class ChatResponse(BaseModel):
    """POST /api/chat 출력."""

    room_id: str
    message_id: str
    answer: str
    sources: list[SourceItem] = []
    tokens_used: int = 0
    response_time_ms: int = 0


class RoomItem(BaseModel):
    """GET /api/rooms 목록 항목.

    Firestore 문서는 방 ID 를 'id' 키로 담는다(database.py: data["id"]=doc.id).
    validation_alias 로 입력은 'id' 에서 읽고, 출력(JSON)은 room_id 로 내보낸다.
    (alias= 가 아니라 validation_alias= — alias 는 출력까지 id 로 바꿔버린다.)
    """

    room_id: str = Field(validation_alias="id")
    title: str
    created_at: datetime
    updated_at: datetime


class MessageItem(BaseModel):
    """GET /api/rooms/{room_id}/messages 항목.

    user 메시지는 sources/feedback 키가 아예 없다 → Optional + 기본값으로 흡수.
    문서 ID 는 'id' 키 → message_id 로 노출 (RoomItem 과 동일한 alias 패턴).
    """

    message_id: str = Field(validation_alias="id")
    role: str
    content: str
    sources: list[SourceItem] | None = None
    feedback: str | None = None
    created_at: datetime
