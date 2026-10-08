# 아키텍처 개요

> 살아있는 문서. 구현 진행에 따라 갱신.

## 핵심 원칙

1. **단독 배포형 (회사 = GCP 프로젝트 1:1)** — 멀티테넌트/SaaS 아님. 데이터 격리 + 비용 추적 + 권한 격리.
2. **검색 백엔드 추상화** — `DocumentSearchService` ABC 뒤로 Vertex/OAuth/Hybrid 은닉. 교체는 `SEARCH_MODE` 한 줄.
3. **근거 검증** — 시스템 프롬프트 강제 + 근거 검증(grounded 플래그 기록, 차단 아님) + 운영 환각률 추적.
4. **화이트라벨** — 회사별 값 전부 `.env`.

## 시점 분리

- 개발: **개인 GCP**(`my-gcp-project`). 가짜/공개 샘플 문서만.
- 운영: **회사 GCP로 이전 완료**(운영 데이터 0 시점에 이전). 실제 임직원 문서 적재.
- 이후: Terraform 모듈화 (계획).

## 데이터 흐름 (목표)

User → FastAPI(OAuth 세션/IAP JWT 검증) → SearchBackend → 후보 최대 20(hybrid 는 백엔드당 10) → Gemini re-rank top-5 → Gemini 생성 → 답변 검증 → 응답
→ (비동기) Firestore 저장 → 자정 BigQuery 적재 → dbt 마트 → 리포트

## 리전 (ADR 거리)

- 일반(GCS/Firestore/Cloud Run): `asia-northeast3` (서울, latency)
- Vertex Gemini: `us-central1` (서울 미지원 모델 회피)
- Vertex AI Search: `global`
