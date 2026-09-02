# ADR 0009 — Rate Limit 정책 (1분 5회 / 사용자)

- 상태(Status): Accepted
- 날짜: 2026-06-15
- 관련 단계: 8단계
- 관련 ADR: 0001(회사=GCP 1:1 매핑), 1단계 비용 가드레일(예산 알림)

## 맥락 (Context)

`POST /api/chat` 한 번 호출은 LLM 을 최대 3회 부른다(rerank + generate + validate).
한 사용자가 실수(무한 루프 스크립트)나 악의로 이 엔드포인트를 폭주시키면 LLM 토큰
비용이 순식간에 급증한다. GCP 예산 알림(1단계)은 사후·지연 신호이고, Quota 는 하한이
커서 소규모 앱의 폭주를 세밀히 막지 못한다 → 애플리케이션 레벨의 즉각적 차단이
필요하다(다층 방어: 예산 알림 + Rate Limit + 실시간 미터링).

## 결정 (Decision)

slowapi 로 **1분당 5회**, **사용자(user_email) 단위**로 제한한다.

- 키: `get_user_key` = 인증 이메일(`user:{email}`), 미인증 폴백만 IP(`ip:{addr}`).
  ★IP 가 아니라 user_email★ 인 이유: 운영(11단계 Cloud Run + IAP)에서는 모든 트래픽이
  프록시/IAP 를 거쳐 들어와 클라이언트 IP 가 공유되거나 프록시 IP 로 보인다 → IP 기준이면
  한 사용자가 한도를 쓰면 전체 사용자가 막힌다.
- 적용 범위: 비싼 `POST /api/chat` 에만 `@limiter.limit` 데코레이터. 값싼 rooms CRUD 는
  제한하지 않는다(SlowAPIMiddleware 미도입 — 전역 자동적용 안 함).
- 저장소: 인메모리(slowapi 기본). 한도 초과 시 429 + `_rate_limit_exceeded_handler`.

## 트레이드오프 (Consequences)

- (−) 인메모리 → 인스턴스 재시작 시 카운터 초기화, 다중 인스턴스 시 인스턴스별로 카운트.
      현재 단일 인스턴스(Cloud Run min/max=1 예정)라 문제없음.
- (−) user_email 키라 미인증 요청엔 rate limit 이 직접 걸리지 않는다 — 단, 미인증은 그 전에
      인증 미들웨어/`Depends(require_user_email)` 가 401 로 막으므로 실질 노출은 없다.
- (+) 사용자별 격리: 한 명의 폭주가 다른 임직원을 막지 않는다(검증: A 6회째 429, B 정상 200).
- (+) 비용 폭탄/어뷰징 즉각 차단. 정상 사용은 분당 5회로 충분.

## 대안 (Alternatives considered)

- IP 기반(slowapi 기본 get_remote_address): IAP/프록시 뒤 IP 공유로 오작동 → 기각.
- Redis 분산 카운터: 다중 인스턴스엔 정답이지만 7~10명 단일 인스턴스엔 오버 → 11단계 검토.
- API Gateway / Cloud Armor quota: 인프라 레벨 가능하나 사용자 단위 세밀 제어엔 부적합.

## 후속 (Follow-ups)

- 11단계(Cloud Run 다중 인스턴스 도입 시) Redis 백엔드로 전환 검토.
- 14단계 BigQuery 사용량 분석 후 한도(5/min) 재조정.
- 거부된(429) 요청을 미터링에 포함할지 결정(현재는 정상 요청만 chat_completed 로깅).
