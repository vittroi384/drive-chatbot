# ADR 0005 — 하이브리드 데이터소스 설계 (Hybrid Data Source Design)

- 상태(Status): Accepted
- 날짜(Date): 2026-05-25
- 작성자(Author): vittroi384
- 관련 ADR: ADR 0002 (OAuth 개인 인증), ADR 0003 (청킹), ADR 0004 (임베딩)

## 맥락 (Context)

당초 Vertex AI Search의 Google Drive 커넥터로 사내 Drive 문서를 직접 인덱싱하려
했으나, Workspace 관리자 권한 위임을 받을 수 없어(관리자 협조 불가) 커넥터 방식이
불가능하다. 사내 지식은 두 종류로 나뉜다:

- **공용 문서**: 회사 정책/매뉴얼/FAQ/회의록 등 전 임직원 공통 참조 문서.
- **개인 문서**: 사용자 개인 Drive에 있는 문서(접근 권한이 사용자별로 다름).

두 종류를 단일 인덱싱으로 처리하면 권한 격리가 깨지고, 개인 문서를 중앙 인덱스에
올리면 보안/프라이버시 문제가 생긴다.

## 결정 (Decision)

데이터소스를 **하이브리드 구조**로 분리한다.

- **공용 문서**: GCS 버킷에 적재 → Vertex AI Search(Agent Search)로 인덱싱.
  - 버킷: `my-gcp-project-docs` (개인 GCP 시점)
  - 폴더 구조: company-policies, manuals, faq, meeting-notes, _internal(인덱싱 제외)
- **개인 문서**: 사용자 OAuth 토큰으로 Drive API를 호출해 **동적 검색**(중앙 인덱싱 X).
  - 사용자 권한 범위 내 문서만 검색되므로 권한 격리 자연 보장.

두 백엔드는 `DocumentSearchService` 추상 인터페이스로 통합한다(구현: `app/search/`):
- `VertexSearchBackend` — GCS 공용 문서 검색.
- `OAuthDriveBackend` — 사용자 Drive 동적 검색.
- `HybridBackend` — 위 둘을 조합, 결과 병합/재랭킹.

미래 확장 옵션을 인터페이스 뒤에 보존한다:
- pgvector 마이그레이션(검토 미정).
- Drive 커넥터 추가(회사 GCP Internal 전환 후 가능 시).

## 근거 (Rationale)

- **제약 우회**: Workspace 관리자 위임 없이도 사내 챗봇이 동작하는 현실적 해법.
- **권한 격리**: 개인 문서를 중앙 인덱싱하지 않으므로, 사용자별 접근 권한이
  OAuth 토큰 범위로 자연스럽게 강제된다(별도 ACL 관리 불필요).
- **추상화로 미래 보존**: 검색 백엔드를 인터페이스로 감싸 pgvector/Drive 커넥터 등
  향후 옵션을 코드 변경 최소화로 도입 가능. 단독 배포형(회사=GCP 1:1) 모델과 정합.

## 결과 (Consequences)

긍정적:
- 관리자 권한 없이 공용 지식 검색 + 개인 문서 검색을 동시에 제공.
- 개인 문서 보안/권한 문제를 구조적으로 회피.
- 회사 GCP 이전 시 동일 구조를 Terraform으로 재현 가능(모듈화 계획).

부정적/리스크:
- 개인 문서는 실시간 Drive API 호출이라 공용 인덱스 대비 지연(latency)이 크고
  rate limit 영향을 받는다.
- 두 백엔드 결과를 병합/재랭킹하는 로직이 추가 복잡도를 만든다.
- 개인 문서는 사전 인덱싱이 없어 의미 검색(임베딩) 품질이 공용 대비 낮을 수 있다.

## 재검토 트리거 (Revisit Triggers)

- 회사 GCP를 Internal로 전환해 Drive 커넥터 사용이 가능해지는 경우.
- 개인 문서 동적 검색의 지연/품질이 운영상 문제로 드러나는 경우.
- pgvector 전환 결정 시 백엔드 구현 교체.

## 운영 메모 — GCS 적재 포맷 제약 (실측, 2026-05-25)

GCS → Vertex AI Search 인덱싱 경로는 **markdown(.md)을 지원하지 않는다**
(`content.mime_type "text/markdown" not allowed`, 허용: pdf, docx, txt, html, xml 등).

→ `VertexSearchBackend`(공용 문서 경로)에는 **적재 전 포맷 정규화 단계**가 필요하다.
   회사 실제 문서 적재 시 md/기타 미지원 포맷을 txt/html로 변환하는
   전처리를 적재 파이프라인에 포함한다.
   `OAuthDriveBackend`(개인 문서 동적 검색) 경로는 Drive API가 포맷을 자체 처리하므로
   이 제약의 영향을 받지 않는다 — 하이브리드 구조의 부수적 이점.

## 참고 (Notes)

- 본 파일은 초안을 docs/adr/에 옮긴 것이다.
