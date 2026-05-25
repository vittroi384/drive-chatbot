# ADR 0002 — OAuth 개인 인증 vs 도메인 위임

- 상태: Accepted
- 날짜: 2026-05

## 배경
사내 Drive 문서를 검색하려면 사용자 인증과 Drive 접근 권한이 필요하다. Google Workspace에는 관리자가 서비스 계정에 도메인 전체 위임(domain-wide delegation)을 부여해 모든 사용자의 Drive에 접근하는 방식이 있다. 그러나 본 프로젝트는 Workspace 관리자 권한 협조를 받을 수 없는 상황에서 시작했다.

## 선택지
1. **도메인 전체 위임(서비스 계정)**: 관리자가 SA에 위임 → 전사 Drive 일괄 접근.
2. **사용자별 OAuth 2.0 개인 인증**: 각 사용자가 본인 토큰으로 본인 Drive만 접근.

## 결정
**사용자별 OAuth 2.0 개인 인증** 을 채택한다.

## 근거
- **관리자 권한 대기 불필요**: 솔로 개발자가 자율적으로 진행 가능. 협조 병목 제거.
- **최소 권한**: 사용자는 본인이 볼 수 있는 문서만 검색 → 권한 상승 위험 없음.
- **개인정보 관점 안전**: SA가 전사 문서를 항상 들고 있는 구조가 아님.
- 공용 문서는 별도로 GCS + Vertex AI Search에 인덱싱(ADR 0005)해 보완.

## 트레이드오프
- 사용자마다 OAuth 동의/토큰 갱신 흐름 필요 → 구현 복잡도 증가(5단계).
- restricted scope(`drive.readonly`)는 Production 게시 시 Google verification 필요 → 회사 GCP 이전 시 Internal로 우회(보조 ADR).
- 전사 문서 일괄 인덱싱 불가 → 공용 코퍼스는 GCS 경로로만. 개인 Drive와 공용을 Hybrid로 합침.
