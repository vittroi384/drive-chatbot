"""Chat 엔드포인트 (API + Rate Limit + 사용량 로그).

POST /api/chat 하나로 RAG 전체 흐름을 HTTP 로 노출한다:
  방 확보 → 히스토리 로드 → user 저장 → ask() → assistant 저장 → 로깅 → 응답

[설계 원칙]
- AI 호출은 ai_service.ask() 한 곳에서만 (이 라우터는 오케스트레이션만).
- 모든 보안 검증(인증/소유자)은 명시적으로 — 주석의 ★ 표시 참고.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app import ai_service, database
from app.config import get_settings
from app.models.chat import ChatRequest, ChatResponse
from app.utils.auth_utils import get_user_oauth_access_token, require_user_email
from app.utils.rate_limit import limiter

logger = logging.getLogger(__name__)
settings = get_settings()

# prefix="/api" → 이 라우터의 /chat 은 실제 경로 /api/chat 이 된다.
router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def create_chat(
    # ★함정★ slowapi 가 매 요청 request 를 찾아 key_func(get_user_key)에 넘긴다.
    #   따라서 첫 인자는 반드시 request: Request 여야 데코레이터가 동작한다.
    request: Request,
    body: ChatRequest,
    # ★보안★ Depends(require_user_email): 미인증이면 401. 인증되면 이메일을 주입.
    #   (미들웨어가 /api 미인증을 먼저 401 로 막지만, 여기서도 한 번 더 — 방어 2겹.)
    user_email: str = Depends(require_user_email),
) -> ChatResponse:
    """질문을 받아 RAG 답변을 생성하고, user/assistant 메시지를 저장한 뒤 반환한다."""

    # ── 1) 방 확보 ──────────────────────────────────────────────────────────
    if body.room_id:
        # ★보안(IDOR 방어)★ get_room 은 소유자 불일치/없음 둘 다 None 을 준다.
        #   둘 다 404 로 처리해 "그 방이 존재하는지" 자체를 노출하지 않는다.
        room = await database.get_room(body.room_id, user_email)
        if room is None:
            raise HTTPException(status_code=404, detail="room not found")
        room_id = body.room_id

        # ── 2) 히스토리 로드 → ask() 가 먹는 [{role, content}] 형태로 어댑트 ──
        #   (get_messages 결과엔 sources/feedback 등도 있지만 대화 맥락엔 role/content 만.)
        prev = await database.get_messages(room_id)
        chat_history = [{"role": m["role"], "content": m["content"]} for m in prev]
    else:
        # 신규 방: 첫 질문을 제목으로 (create_room 이 내부에서 100자로 자른다). 히스토리는 빈다.
        room_id = await database.create_room(user_email=user_email, title=body.query)
        chat_history = []

    # ── 3) user 메시지 먼저 저장 ────────────────────────────────────────────
    #   ask() 전에 저장 → 무엇을 물었는지 항상 기록(디버깅/어뷰징 추적).
    await database.save_message(room_id, "user", body.query)

    # ── 4) OAuth access token 문자열 추출 ──────────────────────────────
    #   세션엔 토큰 dict 전체가 있으나 Drive 는 access_token '문자열'을 원한다.
    #   None(미로그인/만료)이면 ask()→Drive 는 빈 결과로 graceful degrade.
    oauth_token = get_user_oauth_access_token(request)

    # ── 5) RAG 파이프라인 실행 (dict 반환) ──────────────────────────────────
    try:
        result = await ai_service.ask(
            query=body.query,
            user_email=user_email,
            user_oauth_token=oauth_token,
            chat_history=chat_history,
        )
    except Exception as exc:
        # ★함정★ ask() 가 터지면 3)의 user 메시지가 '고아'로 남는다.
        #   assistant 자리에 에러 메시지를 저장해 턴을 완결시키고 500 을 반환한다.
        #   (정식 에러 핸들링/알림은 후속.)
        logger.error("[chat] ask() failed (room=%s, user=%s)", room_id, user_email, exc_info=True)
        await database.save_message(
            room_id,
            "assistant",
            "[일시적인 오류로 답변을 생성하지 못했습니다. 잠시 후 다시 시도해 주세요.]",
            grounded=None,
        )
        raise HTTPException(
            status_code=500, detail="answer_generation_failed"
        ) from exc

    # ── 6) assistant 메시지 저장 (출처/토큰/시간 + 검증신호 grounded/confidence) ──
    validation = result["validation"]  # ★함정★ dict 접근 (result.answer 점 접근 아님)
    message_id = await database.save_message(
        room_id,
        "assistant",
        result["answer"],
        sources=result["sources"],
        tokens_used=result["tokens_used"],
        response_time_ms=result["response_time_ms"],
        grounded=validation.get("grounded"),       # 환각률 추적
        confidence=validation.get("confidence"),
    )

    # ── 7) 구조화 로깅 (BigQuery 적재 기반, 예정) ──────────────────────────
    #   extra 의 키들은 Cloud Logging 에서 JSON 필드가 된다(로컬 콘솔엔 message 만 보임).
    logger.info(
        "chat_completed",
        extra={
            "user_email": user_email,
            "room_id": room_id,
            "message_id": message_id,
            "query_length": len(body.query),
            "tokens_used": result["tokens_used"],
            "response_time_ms": result["response_time_ms"],
            "source_count": len(result["sources"]),
            "validation_grounded": validation.get("grounded"),
            "validation_confidence": validation.get("confidence"),
        },
    )

    # ── 8) 응답 (sources 의 [{title,uri,score}] 는 SourceItem 으로 자동 변환) ──
    return ChatResponse(
        room_id=room_id,
        message_id=message_id,
        answer=result["answer"],
        sources=result["sources"],
        tokens_used=result["tokens_used"],
        response_time_ms=result["response_time_ms"],
    )
