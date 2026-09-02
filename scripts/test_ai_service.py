"""ai_service.ask() 로컬 통합 테스트.

실행 (PowerShell, repo 루트에서 .venv 활성화 후):
    python scripts/test_ai_service.py

[주의]
    - SEARCH_MODE를 테스트 중엔 vertex로 두는 걸 권장 (스크립트엔 OAuth 세션이
      없어 hybrid로 돌려도 Drive 절반은 빈 결과 + 경고만 뜸).
    - 인덱스에 있는 질문은 답변+출처+grounded=true, 없는 질문은 NOT_FOUND 기대.
"""

from __future__ import annotations

import asyncio
import logging

from app.ai_service import ask

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# 3단계 GCS 인덱스에 있는 주제 / 없는 주제
SCENARIOS = [
    ("휴가는 며칠인가요?", "인덱스에 있는 질문 (답변+출처 기대)"),
    ("오늘 서울 날씨 알려줘", "인덱스에 없는 질문 (NOT_FOUND 기대)"),
]

TEST_USER = "test@example.com"


def _print_result(label: str, res: dict) -> None:
    print("\n" + "=" * 70)
    print(f"[시나리오] {label}")
    print("=" * 70)
    print(f"답변:\n{res['answer']}\n")
    print(f"출처 ({len(res['sources'])}개):")
    for i, src in enumerate(res["sources"], 1):
        print(f"  [{i}] {src['title']}  (score={src['score']}, uri={src['uri']})")
    print(f"\n토큰: {res['tokens_used']}")
    print(f"응답시간: {res['response_time_ms']} ms  세부: {res['timings_ms']}")
    print(f"검증: {res['validation']}")


async def main() -> None:
    for query, label in SCENARIOS:
        try:
            res = await ask(query=query, user_email=TEST_USER, chat_history=[])
            _print_result(label, res)
        except Exception:  # noqa: BLE001
            logging.exception("ask() raised for query=%r", query)


if __name__ == "__main__":
    asyncio.run(main())
