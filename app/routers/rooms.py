"""대화방 관리 엔드포인트.

방 목록/생성, 메시지 조회, 피드백 저장. AI 호출은 없고 Firestore CRUD 만 한다.
모든 엔드포인트는 require_user_email 로 인증을 강제하고, 특정 방을 다루는
엔드포인트는 get_room 으로 ★소유자 검증★ 후에만 진행한다(IDOR 방어).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from app import database
from app.models.chat import FeedbackRequest, MessageItem, RoomItem
from app.utils.auth_utils import require_user_email

logger = logging.getLogger(__name__)

# prefix 끝에 "" 를 쓰는 라우트는 정확히 /api/rooms 가 된다("/" 면 /api/rooms/ 로 307 유발).
router = APIRouter(prefix="/api/rooms", tags=["rooms"])


@router.get("", response_model=list[RoomItem])
async def list_rooms(user_email: str = Depends(require_user_email)) -> list[RoomItem]:
    """내 대화방 목록을 updated_at 최신순으로 반환한다."""
    rooms = await database.get_rooms(user_email)
    # 각 dict 의 'id' 키가 RoomItem.room_id 로 매핑됨(validation_alias). 잡키는 무시.
    return [RoomItem(**r) for r in rooms]


@router.post("")
async def create_room(user_email: str = Depends(require_user_email)) -> dict:
    """빈 대화방을 생성하고 room_id 를 반환한다 (제목 기본값 '새 대화')."""
    room_id = await database.create_room(user_email=user_email)
    return {"room_id": room_id}


@router.get("/{room_id}/messages", response_model=list[MessageItem])
async def list_messages(
    room_id: str,
    user_email: str = Depends(require_user_email),
) -> list[MessageItem]:
    """방의 메시지를 시간순으로 반환한다. ★소유자 검증★ 후에만."""
    # 없음/남의 방 둘 다 None → 404 (존재 여부 비노출)
    room = await database.get_room(room_id, user_email)
    if room is None:
        raise HTTPException(status_code=404, detail="room not found")
    msgs = await database.get_messages(room_id)
    # user 메시지는 sources/feedback 키가 없어 Optional 로 흡수됨(MessageItem).
    return [MessageItem(**m) for m in msgs]


@router.post("/{room_id}/messages/{message_id}/feedback")
async def submit_feedback(
    room_id: str,
    message_id: str,
    body: FeedbackRequest,
    user_email: str = Depends(require_user_email),
) -> dict:
    """메시지에 👍/👎 피드백을 저장한다. ★소유자 검증★ 후에만.

    FeedbackRequest 가 up|down 패턴을 강제(그 외 422). 소유자 검증으로 남의 방
    메시지에 피드백 다는 것을 차단한다.
    """
    room = await database.get_room(room_id, user_email)
    if room is None:
        raise HTTPException(status_code=404, detail="room not found")
    await database.update_feedback(room_id, message_id, body.feedback)
    return {"status": "ok", "feedback": body.feedback}
