# ADR 0007 — RAG 4단계 파이프라인 (Search → Rerank → Generate → Validate)

- 상태(Status): Accepted
- 날짜: 2026-06-XX
- 관련 단계: 7단계
- 관련 ADR: 0003(청킹), 0004(임베딩), 0005(하이브리드 데이터소스)

## 맥락 (Context)

3단계에서 Vertex AI Search datastore + 검색 앱을 구성했고, 검색 자체는 동작한다.
하지만 사내 QA 챗봇으로 쓰려면 두 가지가 부족했다.

1. 한국어 검색 정확도 — Vertex 자동 청킹/임베딩(text-embedding-004)의 top 결과가
   질문 의도와 어긋나는 경우가 있어, 그대로 답변 생성에 넣으면 품질이 흔들린다.
2. 환각(hallucination) — 시스템 프롬프트만으로는 모델이 문서에 없는 내용을
   "그럴듯하게" 지어내는 것을 완전히 막지 못한다.

또한 generative SDK 환경이 바뀌었다. 기존 프롬프트가 가정한
`vertexai.generative_models`(=google-cloud-aiplatform의 GenAI 모듈)는
**2026-06-24 제거 예정**이라 신규 코드에 쓸 수 없다.

## 결정 (Decision)

응답 1건을 **4단계 파이프라인**으로 처리한다.

1. **Search** — `DocumentSearchService.search(top_k=20)`. Vertex는 retrieval-only
   (summary_spec 미사용 → 생성형 요약 과금 없음, 이중과금 방지).
2. **Rerank** — Gemini로 후보 20개를 다시 점수화해 top_n=5만 남김. JSON 구조화
   출력(`response_mime_type=application/json`)으로 파싱 안정화.
3. **Generate** — top_5 문서 + 최근 대화로 답변 생성. 환각 방지 5규칙을
   `system_instruction`으로 강제 (user turn이 아닌 system turn에 둠).
4. **Validate** — 생성된 답변이 문서에 grounded 되는지 별도 Gemini 호출로 검증.
   `{grounded, confidence, reason}` JSON 반환. `ENABLE_VALIDATION`로 on/off.

SDK는 **google-genai**로 확정한다. `genai.Client(vertexai=True, project, location)`
+ 비동기 `client.aio.models.generate_content(...)`. 모델명은 하드코딩하지 않고
`settings.gemini_model`(.env)로 관리 — 모델 교체가 한 줄.

모든 generative 호출은 `ai_service.py` 한 곳에서만 한다 (다른 모듈은 import만).

## 트레이드오프 (Consequences)

- (−) 응답 1건당 LLM 호출 최대 3회(rerank+generate+validate) → 지연 증가
  (1차 운영 3~5초대 예상, 순차 실행). 토큰 비용도 검색 1 + LLM 3.
- (−) rerank/validate가 그 자체로 또 다른 실패 지점 → 각각 fallback 필수
  (rerank 실패 → 원본 top_n, validate 실패 → grounded=True + 로그).
- (+) 환각 방지가 "프롬프트 + 사후 검증" 이중 레이어가 됨 → grounded 비율을
  운영 데이터로 측정 가능 (블로그 3편 메인 소재).
- (+) 검색 backend가 추상화돼 있어 rerank/generate는 backend에 무관하게 동작.
- (+) 죽어가는 SDK를 미리 버려서 2026-06-24 강제 마이그레이션을 회피.

## 대안 (Alternatives considered)

- Rerank 없이 Vertex top-5 직행: 단순하지만 한국어 정확도 보정 기회 상실.
- Validate 없이 system 프롬프트만: 비용↓ 지만 환각 측정/억제 수단이 사라짐.
- Vertex 검색 앱의 "생성형 대답"을 그대로 사용: 파이프라인 제어권을 잃고,
  자체 generate와 함께 쓰면 이중과금. → retrieval-only로 결정.

## 후속 (Follow-ups)

- 13단계 골든셋으로 rerank 전/후 정확도, grounded 비율 정량 측정.
- 지연이 문제면 rerank/generate 일부 병렬화 또는 validate 샘플링 검토.
- SDK 전환은 본 ADR에 녹였지만, "deprecated SDK 사전 이탈"은 독립 ADR(0009)로
  분리해도 좋음 (면접 카드 가치).
