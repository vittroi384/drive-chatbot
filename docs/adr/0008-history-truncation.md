# ADR 0008 — 대화 컨텍스트 truncation 정책 (최근 5 문답)

- 상태(Status): Accepted
- 날짜: 2026-06-XX
- 관련 단계: 7단계
- 관련 ADR: 0007(RAG 파이프라인)

## 맥락 (Context)

답변 생성 시 이전 대화(chat_history)를 함께 넣으면 맥락 있는 답변이 되지만,
대화가 길어질수록 prompt 토큰이 선형으로 늘어 비용과 지연이 커진다. Gemini의
context window는 넉넉하지만(1M), 7~10명 사내 단순 질의응답 챗봇에 장기 컨텍스트는
대부분 불필요하고 비용만 증가시킨다.

## 결정 (Decision)

`generate_answer`에 들어가는 chat_history는 **뒤에서 max_pairs=5 문답(=10 메시지)**
만 유지한다 (`_truncate_history`). 그 이전 대화는 prompt에서 제외한다.

## 트레이드오프 (Consequences)

- (−) 매우 긴 대화 흐름은 앞부분이 끊긴다 (예: 20번째 질문이 1번째 답을 참조 못함).
- (−) 장기 대화 요약(summary memory)은 1차에서 미구현.
- (+) prompt 토큰이 대화 길이와 무관하게 상한선 안에 묶임 → 비용/지연 예측 가능.
- (+) 단순 구현 (슬라이싱 한 줄), 운영 후 필요 시 요약 메모리 도입 가능.

## 대안 (Alternatives considered)

- 전체 history 전달: 맥락 보존은 최고지만 비용/지연이 대화 길이에 비례 → 기각.
- 토큰 기준 truncation: 더 정밀하지만 토큰 카운팅 오버헤드 → 1차는 문답 수 기준.
- 장기 요약 메모리: 가치 있지만 구현 복잡도↑ → 운영 데이터로 필요성 확인 후 도입.

## 후속 (Follow-ups)

- 운영 로그에서 "5문답 초과 대화" 빈도 측정. 잦으면 요약 메모리(rolling summary) 검토.
- max_pairs는 상수 → 추후 .env 노출 가능 (현재는 코드 상수로 단순화).
