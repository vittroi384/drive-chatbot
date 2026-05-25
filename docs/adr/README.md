# Architecture Decision Records (ADR)

이 프로젝트의 주요 설계 결정 기록. 각 ADR은 한 번 결정되면 보존하고, 번복 시 새 ADR로 supersede.

## 형식

각 ADR은 다음 구조를 따른다:
- **상태**: Proposed / Accepted / Provisional / Superseded
- **배경**: 어떤 문제/맥락에서 결정이 필요했나
- **선택지**: 고려한 옵션들
- **결정**: 무엇을 골랐나
- **근거**: 왜
- **트레이드오프**: 무엇을 포기했나

## 목록

| 번호 | 제목 | 상태 |
|---|---|---|
| [0001](0001-company-gcp-1to1-mapping.md) | 회사 = GCP 프로젝트 1:1 매핑 | Accepted |
| [0002](0002-oauth-vs-domain-delegation.md) | OAuth 개인 인증 vs 도메인 위임 | Accepted |
| [0003](0003-chunking-strategy.md) | 청킹 전략 | Provisional |
| [0004](0004-embedding-model-selection.md) | 임베딩 모델 후보 선정 | Provisional |
| [0005](0005-hybrid-data-source.md) | 하이브리드 데이터소스 설계 | Accepted |

## 작성 대기 (큐)

- 보조: GCP Quota 하한 한계 → 다층 방어 설계
- 보조: drive.readonly 스코프 선택 근거
- 보조: 회사 GCP 이전 시점 13~15단계 결정
- 보조: Gemini 모델 수명주기 기반 선택 (gemini-3-flash) — 2026-05 발견
