# Drive Chatbot

사내 Google Drive / GCS 문서 기반 RAG 챗봇. **단독 배포형**(회사 = GCP 프로젝트 1:1 매핑) 아키텍처로, 멀티테넌트 SaaS가 아닙니다.

> 상태: Phase 1 진행 중 (4단계 — 프로젝트 뼈대 + 검색 백엔드 추상화 + GitHub 셋업 완료)

## 아키텍처 다이어그램

```
(9단계에서 Mermaid 다이어그램으로 교체 예정)
User → FastAPI → SearchBackend(추상) → {Vertex AI Search | OAuth Drive} → Gemini(RAG) → 답변 검증
```

## 기술 스택

| 영역 | 선택 | 선택 이유 |
|---|---|---|
| Backend | FastAPI + Uvicorn (Python 3.11, async) | 비동기 I/O, 자동 OpenAPI 문서 |
| 검색 | Vertex AI Search + OAuth Drive (추상화) | 백엔드 교체를 config 한 줄로 (pgvector 마이그레이션 옵션 보존) |
| 생성 | Gemini Flash (RAG) | 비용/지연 균형. 모델명은 `.env`로 관리(수명주기 대응) |
| 인증 | Google OAuth 2.0 (로컬) → IAP (운영) | Workspace 관리자 권한 없이 개인 OAuth로 진행 |
| DB | Firestore(실시간) + BigQuery(분석) | 실시간 대화 저장 / 일배치 분석 분리 |
| 변환 | dbt (raw→staging→mart) | 사내 KPI 데이터 마트 |
| 미터링 | Pub/Sub + Cloud Functions | Dataflow 대비 트래픽 규모에 맞는 저비용 |
| 배포 | Docker + Cloud Run | 서버리스, 사용량 기반 과금 |
| IaC | Terraform (17단계+) | 신규 회사 = apply 한 번 |

## 화이트라벨

`COMPANY_NAME`, `COMPANY_LOGO_URL`, `SYSTEM_PROMPT`, `GEMINI_MODEL` 등 모든 회사별 값은 `.env`로 관리. 코드 수정 없이 배포 단위로 커스터마이징.

## 로컬 실행

```powershell
# 프로젝트 루트(C:\dev\drive-chatbot)에서, venv 활성화 후
Copy-Item .env.example .env   # 그리고 빈 값 채우기
uvicorn app.main:app --reload --port 8000
```

- http://localhost:8000 — 회사명 표시
- http://localhost:8000/health — `{"status":"ok","env":"local"}`

## 운영 지표

(운영 시작 후 채움 — 환각률, 검색 실패율, 일 사용량 등)

## 설계 결정 (ADR)

주요 아키텍처 결정은 [docs/adr/](docs/adr/README.md) 참고.

## License

Private (배포/판매 시점에 라이선스 정책 재결정).
