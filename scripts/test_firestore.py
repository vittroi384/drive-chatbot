"""Firestore 비동기 함수 로컬 통합 테스트.

실행 (PowerShell, 프로젝트 루트에서):
    python scripts/test_firestore.py

사전 조건:
    - GOOGLE_APPLICATION_CREDENTIALS 환경변수 = 서비스계정 키 경로 (1단계에서 설정)
    - GCP_PROJECT_ID = my-gcp-project
    - Firestore 가 Native mode 로 활성화되어 있을 것

주의: 이 스크립트는 실제 Firestore 에 테스트 데이터를 생성한다.
      실행 후 GCP 콘솔 > Firestore > 데이터 탭에서 chat_rooms 컬렉션을 확인할 수 있다.
"""

import asyncio
import logging
import sys
from pathlib import Path

# scripts/ 하위에서 실행해도 app 패키지를 import 할 수 있게 루트 경로 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import (  # noqa: E402  (경로 주입 후 import 라 의도적 배치)
    create_room,
    get_messages,
    get_room,
    get_rooms,
    save_message,
    update_feedback,
    warmup_firestore,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

TEST_EMAIL = "test@example.com"
ATTACKER_EMAIL = "attacker@example.com"


async def main() -> None:
    print("\n=== Firestore 통합 테스트 시작 ===\n")

    print("1) warmup_firestore ...")
    await warmup_firestore()

    print("2) create_room ...")
    room_id = await create_room(TEST_EMAIL)
    print(f"   room_id = {room_id}")

    print("3) save_message (user) ...")
    await save_message(room_id, "user", "휴가 신청 방법?")

    print("4) save_message (assistant) ...")
    msg_id = await save_message(
        room_id,
        "assistant",
        "휴가는 X 시스템에서 신청합니다. 연차는 자동 차감됩니다.",
        sources=[
            {"title": "휴가규정.docx", "uri": "gs://bucket/휴가규정.docx", "score": 0.92}
        ],
        tokens_used=120,
        response_time_ms=850,
    )
    print(f"   assistant msg_id = {msg_id}")

    print("5) get_messages ...")
    msgs = await get_messages(room_id)
    print(f"   메시지 {len(msgs)}개 (시간순):")
    for m in msgs:
        print(f"     - [{m['role']:9}] {m['content'][:30]}")
    assert len(msgs) == 2, f"메시지가 2개여야 하는데 {len(msgs)}개"

    print("6) update_feedback (up) ...")
    await update_feedback(room_id, msg_id, "up")
    print("   assistant 메시지에 feedback=up 기록")

    print("7) get_rooms ...")
    rooms = await get_rooms(TEST_EMAIL)
    print(f"   룸 {len(rooms)}개 (updated_at 최신순)")
    assert len(rooms) >= 1, "최소 1개 룸이 있어야 함"

    print("8) [보안] get_room 소유자 검증 ...")
    mine = await get_room(room_id, TEST_EMAIL)
    other = await get_room(room_id, ATTACKER_EMAIL)
    print(f"   본인({TEST_EMAIL}) 접근    : {'dict 반환 OK' if mine else 'None'}")
    print(f"   타인({ATTACKER_EMAIL}) 접근: "
          f"{'None — 차단됨 OK' if other is None else '!!! 노출됨 — 보안 버그 !!!'}")
    assert mine is not None, "본인 룸은 반환되어야 함"
    assert other is None, "★ 소유자 검증 실패 — IDOR 취약점!"

    print("9) [검증] 잘못된 feedback 값 거부 ...")
    try:
        await update_feedback(room_id, msg_id, "invalid")
        print("   !!! ValueError 가 발생하지 않음 — 검증 누락 !!!")
        raise AssertionError("feedback 검증이 동작하지 않음")
    except ValueError as exc:
        print(f"   ValueError 정상 발생: {exc}")

    print("\n✅ 전체 시나리오 통과")
    print(f"   GCP 콘솔 > Firestore > 데이터 탭에서 chat_rooms/{room_id} 확인\n")


if __name__ == "__main__":
    asyncio.run(main())
