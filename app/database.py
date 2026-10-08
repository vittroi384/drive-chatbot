"""Firestore 비동기 클라이언트 + 채팅 스키마 접근 계층.

스키마 구조 (ADR 0006 은 폐기, 이 docstring 이 기준):
    chat_rooms (컬렉션)
      └─ {room_id} (문서)
           └─ messages (서브컬렉션)
                └─ {message_id} (문서)

모든 함수는 google-cloud-firestore 의 AsyncClient 를 사용하는 비동기 함수다.
회사 = GCP 프로젝트 1:1 (단독 배포) 모델이므로 company_id 는 기본값을 두되,
미래 분석/멀티 옵션을 위해 스키마에는 처음부터 포함한다.

검증 기준: google-cloud-firestore 2.27.0
"""

import logging
from datetime import UTC, datetime

from google.cloud import firestore_v1
from google.cloud.firestore_v1.base_query import FieldFilter

from app.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 클라이언트 싱글톤
# ---------------------------------------------------------------------------
# 모듈 레벨 변수로 클라이언트를 1회만 만들어 재사용한다.
# Cloud Run 은 인스턴스 하나가 여러 요청을 처리하므로, 요청마다 AsyncClient 를
# 새로 만들면 인증/커넥션 비용이 매 요청 발생한다. 싱글톤으로 그 비용을 1회로 줄인다.
_db_client: firestore_v1.AsyncClient | None = None


def get_db() -> firestore_v1.AsyncClient:
    """비동기 Firestore 클라이언트를 lazy 초기화하여 반환한다 (싱글톤).

    최초 호출 시에만 AsyncClient 를 생성하고, 이후에는 동일 인스턴스를 재사용한다.
    """
    global _db_client
    if _db_client is None:
        settings = get_settings()
        _db_client = firestore_v1.AsyncClient(
            project=settings.gcp_project_id,
            database=settings.firestore_database,  # "(default)"
        )
        logger.info(
            "Firestore AsyncClient initialized (project=%s, database=%s)",
            settings.gcp_project_id,
            settings.firestore_database,
        )
    return _db_client


def _now() -> datetime:
    """UTC timezone-aware 현재 시각.

    ★ datetime.now() (naive) 를 쓰면 타임존 정보가 없어 Firestore 저장 시
      해석이 모호해진다. 반드시 UTC 를 붙여 aware datetime 으로 저장한다.
      (Firestore 는 내부적으로 UTC 기준 timestamp 로 보관)
    """
    return datetime.now(UTC)


async def warmup_firestore() -> None:
    """startup 시 가벼운 더미 읽기로 연결을 미리 데운다 (콜드스타트 대응).

    Cloud Run 콜드스타트 직후 첫 사용자 요청이 느려지는 것을 막기 위해,
    서버 기동 직후 limit(1) 읽기 1회로 인증/커넥션을 미리 establish 한다.
    워밍업 실패가 서버 기동 자체를 막으면 안 되므로 예외는 로깅만 한다.
    """
    try:
        db = get_db()
        async for _ in db.collection("chat_rooms").limit(1).stream():
            break  # 1건이라도 읽으면 충분, 즉시 종료
        logger.info("Firestore warmup completed")
    except Exception as exc:  # noqa: BLE001 - 기동 차단 방지 목적의 광범위 catch
        logger.warning("Firestore warmup failed (계속 진행): %s", exc)


# ===========================================================================
# 대화방 (chat_rooms)
# ===========================================================================


async def create_room(
    user_email: str,
    company_id: str = "examplecorp",
    title: str = "새 대화",
) -> str:
    """새 대화방을 생성하고 room_id 를 반환한다.

    Args:
        user_email: 대화방 소유자 이메일.
        company_id: 회사 식별자. 단독 배포라 기본 고정이지만 스키마에는 항상 포함.
        title: 대화방 제목. 첫 질문에서 자동 생성하며 최대 100자.

    Returns:
        생성된 대화방 문서 ID.
    """
    db = get_db()
    # .document() 을 인자 없이 호출하면 20자 ID 를 로컬에서 즉시 생성한다 (네트워크 X).
    doc_ref = db.collection("chat_rooms").document()
    now = _now()
    await doc_ref.set(
        {
            "company_id": company_id,
            "user_email": user_email,
            "title": title[:100],  # 최대 100자 방어
            "created_at": now,
            "updated_at": now,
        }
    )
    logger.info("Room created: %s (user=%s)", doc_ref.id, user_email)
    return doc_ref.id


async def get_rooms(user_email: str, limit: int = 50) -> list[dict]:
    """특정 유저의 대화방 목록을 updated_at 최신순으로 반환한다.

    ★ 복합 인덱스 필요: chat_rooms (user_email ASC, updated_at DESC)
      where + 다른 필드 order_by 조합이라 단일 필드 자동 인덱스로는 부족하다.
      인덱스 없으면 첫 실행 시 FAILED_PRECONDITION 에러 + 생성 URL 이 안내된다.
    """
    db = get_db()
    query = (
        db.collection("chat_rooms")
        .where(filter=FieldFilter("user_email", "==", user_email))
        .order_by("updated_at", direction=firestore_v1.Query.DESCENDING)
        .limit(limit)
    )
    rooms: list[dict] = []
    # stream() 은 AsyncStreamGenerator 를 반환 → async for 로 소비 (앞에 await 안 붙임)
    async for doc in query.stream():
        data = doc.to_dict() or {}
        data["id"] = doc.id
        rooms.append(data)
    logger.info("get_rooms: %d rooms for %s", len(rooms), user_email)
    return rooms


async def get_room(room_id: str, user_email: str) -> dict | None:
    """단일 대화방을 조회하되 ★소유자 검증★ 후 반환한다.

    ★★★ 보안 핵심 (IDOR 방지) ★★★
    room_id 만 알면 누구나 접근 가능한 구조이므로, 요청자(user_email)가 실제
    소유자와 일치하는지 반드시 확인한다. 이 비교를 빠뜨리면 다른 유저의 대화를
    그대로 읽을 수 있는 취약점이 된다. 불일치 시 None 을 반환하고 경고 로깅한다.

    Returns:
        소유자가 일치하는 경우 대화방 dict, 그 외(없음/불일치)에는 None.
    """
    db = get_db()
    doc = await db.collection("chat_rooms").document(room_id).get()
    if not doc.exists:
        logger.warning("get_room: room not found (room_id=%s)", room_id)
        return None

    data = doc.to_dict() or {}
    # ★ 소유자 검증: 이메일 대소문자 차이로 오탐/우회되지 않도록 lower() 로 일관 비교
    owner = (data.get("user_email") or "").lower()
    if owner != user_email.lower():
        logger.warning(
            "get_room: ACCESS DENIED (room_id=%s, owner=%s, requester=%s)",
            room_id,
            data.get("user_email"),
            user_email,
        )
        return None

    data["id"] = doc.id
    return data


async def update_room_title(room_id: str, title: str) -> None:
    """대화방 제목을 갱신한다 (첫 질문 기반 자동 제목 등)."""
    db = get_db()
    await db.collection("chat_rooms").document(room_id).update(
        {
            "title": title[:100],
            "updated_at": _now(),
        }
    )
    logger.info("Room title updated: %s -> %s", room_id, title[:30])


# ===========================================================================
# 메시지 (messages 서브컬렉션)
# ===========================================================================

_VALID_ROLES = {"user", "assistant"}
_VALID_FEEDBACK = {"up", "down"}


async def save_message(
    room_id: str,
    role: str,
    content: str,
    sources: list | None = None,
    tokens_used: int = 0,
    response_time_ms: int = 0,
    grounded: bool | None = None,
    confidence: float | None = None,
) -> str:
    """메시지를 저장하고 message_id 를 반환한다. 부모 룸의 updated_at 도 갱신한다.

    - role 검증: "user" | "assistant" 만 허용 (그 외 ValueError).
    - sources/feedback/grounded/confidence 필드는 assistant role 일 때만 추가한다.
    - grounded/confidence 는 답변 검증 레이어(ai_service) 결과로, 환각률 추적의
      핵심 신호다(BigQuery 분석 예정). validation 비활성 시 None 으로 들어올 수 있다.
    - 저장 후 부모 룸 updated_at 을 갱신해 목록 최신순 정렬을 유지한다.

    Args:
        room_id: 대상 대화방 ID.
        role: "user" 또는 "assistant".
        content: 메시지 본문.
        sources: assistant 답변의 출처 목록 [{title, uri, score}, ...].
        tokens_used: 사용 토큰 수 (비용/미터링 분석용).
        response_time_ms: 응답 생성 소요 시간(ms).
        grounded: 답변이 출처에 근거하는지 (True/False/None). 환각률 추적용.
        confidence: 검증 신뢰도 0.0~1.0 (또는 None).

    Returns:
        생성된 메시지 문서 ID.
    """
    if role not in _VALID_ROLES:
        raise ValueError(f"invalid role: {role!r} (허용: user, assistant)")

    db = get_db()
    msg: dict = {
        "role": role,
        "content": content,
        "tokens_used": tokens_used,
        "response_time_ms": response_time_ms,
        "created_at": _now(),
    }
    # assistant 답변만 출처/피드백/검증신호를 보유한다
    if role == "assistant":
        msg["sources"] = sources or []
        msg["feedback"] = None
        msg["grounded"] = grounded  # 환각률 추적 (BigQuery 분석 예정)
        msg["confidence"] = confidence

    room_ref = db.collection("chat_rooms").document(room_id)
    msg_ref = room_ref.collection("messages").document()
    await msg_ref.set(msg)

    # 부모 룸 updated_at 갱신 (get_rooms 최신순 정렬을 위해 필수)
    await room_ref.update({"updated_at": _now()})

    logger.info(
        "Message saved: room=%s msg=%s role=%s (tokens=%d)",
        room_id,
        msg_ref.id,
        role,
        tokens_used,
    )
    return msg_ref.id


async def get_messages(room_id: str, limit: int = 100) -> list[dict]:
    """대화방의 메시지를 created_at 오름차순(시간순)으로 반환한다.

    특정 룸의 messages 서브컬렉션만 조회한다 (collection group 아님).
    단일 필드 order_by 라 자동 단일 필드 인덱스로 동작 → 별도 복합 인덱스 불필요.
    """
    db = get_db()
    query = (
        db.collection("chat_rooms")
        .document(room_id)
        .collection("messages")
        .order_by("created_at", direction=firestore_v1.Query.ASCENDING)
        .limit(limit)
    )
    messages: list[dict] = []
    async for doc in query.stream():
        data = doc.to_dict() or {}
        data["id"] = doc.id
        messages.append(data)
    logger.info("get_messages: %d messages for room %s", len(messages), room_id)
    return messages


async def update_feedback(room_id: str, message_id: str, feedback: str) -> None:
    """메시지 피드백을 갱신한다.

    - feedback 검증: "up" | "down" 만 허용 (그 외 ValueError).
      운영 데이터(BigQuery 분석 예정)에서 만족도 집계의 기반이 되므로 값 무결성이 중요.
    """
    if feedback not in _VALID_FEEDBACK:
        raise ValueError(f"invalid feedback: {feedback!r} (허용: up, down)")
    db = get_db()
    await (
        db.collection("chat_rooms")
        .document(room_id)
        .collection("messages")
        .document(message_id)
        .update({"feedback": feedback})
    )
    logger.info("Feedback updated: room=%s msg=%s -> %s", room_id, message_id, feedback)
