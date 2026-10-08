# Drive Chatbot — 사내 문서 RAG 챗봇

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)
![Cloud Run](https://img.shields.io/badge/Cloud%20Run-deployed-4285F4?logo=googlecloud&logoColor=white)
![Vertex AI](https://img.shields.io/badge/Vertex%20AI-Search%20%2B%20Gemini-4285F4?logo=googlecloud&logoColor=white)
![pytest](https://img.shields.io/badge/tests-pytest-0A9EDC?logo=pytest&logoColor=white)
![ruff](https://img.shields.io/badge/lint-ruff-D7FF64?logo=ruff&logoColor=black)
![mypy](https://img.shields.io/badge/types-mypy-2A6DB2)

사내 Google Drive / GCS 문서를 검색해, **문서 근거에 한정해 답변하는** RAG 챗봇입니다.
"그럴듯한 답"이 아니라 "근거 있는 답"을 목표로, 검색→재정렬→생성→검증 4단계 파이프라인으로 설계했습니다.

> **상태**: 회사 GCP Cloud Run으로 이전 완료, 운영 중
> (에러 핸들링·알림 체계 구축 중 → 이후 골든셋 기반 품질 평가, BigQuery 분석 파이프라인 예정. [로드맵](#로드맵) 참고)
>
> 공개판은 회사 식별자를 제거한 뒤 단일 커밋으로 재게시한 사본이다. Dockerfile·Cloud Run·Secret Manager 구성은 저장소에 포함(ADR 0011~0013), 실제 프로젝트 ID 등은 자리표시자.

---

## 스크린샷

> 아래 그림은 **가상 데이터**로 렌더링한 화면입니다 (실제 사내 문서·계정 없음).

![대화 화면](assets/ui-chat.png)

*답변마다 근거 문서(출처 칩)를 함께 표시하고, 문서에서 근거를 찾지 못하면 지어내지 않고 그렇게 답합니다. 👍/👎 피드백은 Firestore 에 기록됩니다.*

![첫 화면](assets/ui-home.png)

## 아키텍처

```
사용자 질문
   │
   ▼
[1. 검색]  Vertex AI Search (공용 문서, GCS 인덱스)
   │        + Drive 파일명 검색 (로컬 OAuth 세션 한정, 운영은 Vertex 단독)
   │        hybrid 모드는 백엔드당 최대 10건 (top_k 20의 절반씩)
   ▼
[2. 재정렬]  Gemini re-rank — 후보를 질문 관련도로 다시 점수화해 top-5
   ▼
[3. 생성]  Gemini — 재정렬된 문서 근거로만 답변 생성
   ▼
[4. 검증]  근거 검증 — 답변의 근거 포함 여부를 grounded 플래그로 기록 (차단 아님)
   │
   ▼
답변 + 근거 문서 출처

대화 로그 ──▶ Firestore(실시간 저장) ──▶ BigQuery(분석, 예정)
```

## 주요 특징

- **4단계 RAG 파이프라인** — 검색·재정렬·생성·검증을 분리해, 각 단계를 독립적으로 교체·개선 가능
- **검색 구성** — Vertex AI Search(공용 문서) + Drive 파일명 검색(로컬 OAuth 세션 한정). 운영은 Vertex 단독
- **검색 백엔드 추상화** — 검색 구현을 인터페이스 뒤로 분리, 설정 변경만으로 백엔드 교체
- **근거 검증** — 답변의 근거 포함 여부를 grounded 플래그로 기록(차단 아님, 환각률 측정용)
- **API 보호** — 사용자별 Rate Limit(분당 5회). 사용량은 요청당 로그 1줄(집계는 미구축)
- **화이트라벨 UI** — 회사명·프롬프트·모델을 `.env`로 관리, 코드 수정 없이 재배포 가능
- **설계 결정 문서화** — 주요 아키텍처 결정을 ADR로 기록 ([docs/adr/](docs/adr/README.md))

## 보안·운영

| 항목 | 적용 내용 |
|---|---|
| 접근 제어 | Cloud Run 앞단에 **IAP**(Identity-Aware Proxy) — 허용된 계정만 접근. 앱은 `X-Goog-IAP-JWT-Assertion` 의 서명·audience 를 검증한 뒤 이메일을 사용 (`app/utils/auth_utils.py`) |
| 비밀 관리 | API 키·자격증명은 **Secret Manager**로 분리, 코드·이미지에 미포함 (`--set-secrets` 환경변수 주입, ADR 0013) |
| 인증 | Google OAuth 2.0 — 관리자 권한 없이 개인 인증 방식 |
| 비용 통제 | GCP 프로젝트 분리 + 예산 알림 가드레일, API Rate Limit (사용량 미터링은 로그 1줄) |
| 안정성 | 에러 핸들링·장애 알림 체계 구축 중 (진행 중) |

## 기술 스택

| 영역 | 선택 | 이유 |
|---|---|---|
| Backend | FastAPI + Uvicorn (Python 3.11, async) | 비동기 I/O, 자동 API 문서 |
| 검색 | Vertex AI Search + Drive 파일명 검색 (추상화) | 백엔드 교체를 설정 한 줄로 (`SEARCH_MODE`) |
| 생성 | Gemini (`gemini-2.5-flash`, `app/config.py` 기본값) | 비용/지연 균형. 모델은 설정값 한 곳(`GEMINI_MODEL`)에서 교체 |
| 인증 | Google OAuth 2.0 + IAP | 개인 인증 + 배포 환경 접근 제어 |
| DB | Firestore(실시간) + BigQuery(분석) | 대화 저장 / 분석 워크로드 분리 |
| 배포 | Docker + Cloud Run + Secret Manager | 서버리스, 사용량 기반, 비밀 분리 |

## 설계 결정 (ADR)

주요 아키텍처 결정은 [docs/adr/](docs/adr/README.md)에 문서화했습니다. 대표 예:

- 하이브리드 데이터소스 구성 (0005) — 공용 검색과 개인 문서 검색을 분리한 이유
- 청킹·임베딩 전략 (0003·0004) — 문서 분할 단위와 검색 품질의 트레이드오프
- RAG 파이프라인 (0007) — 재정렬·근거 검증을 별도 호출로 둔 이유와 비용
- 배포 구성 (0011·0012·0013) — slim 이미지·allowlist COPY, Cloud Run direct IAP + Workload Identity, `--set-secrets` 주입

## 테스트 · 코드 품질

```powershell
pytest            # 검색 백엔드 계약 3건 + IAP JWT 검증 2건 (재정렬·생성·검증은 미작성)
ruff check .      # 린트 — pyflakes/pycodestyle + isort + pyupgrade + bugbear + async 검사
mypy app          # 정적 타입 검사 — disallow_untyped_defs, pydantic 플러그인
black .           # 포매팅
```

- 테스트 범위: 검색 백엔드 계약 3건(`tests/test_search.py` — ABC 인스턴스화 불가, `SearchResult` 형태,
  가짜 백엔드 호출)과 IAP JWT 검증 2건(`tests/test_auth_utils.py`). 재정렬·생성·검증 단계의 테스트는 미작성
- `mypy` 는 앱 전역에 **함수 시그니처 타입 강제**(`disallow_untyped_defs`) — Google 클라이언트
  라이브러리처럼 스텁이 불완전한 모듈만 명시적으로 예외 처리. `ruff check .`·`mypy app` 0건 (2026-10-08 로컬 실행, CI 미구축)

## 로컬 실행

```powershell
Copy-Item .env.example .env   # 값 채우기
uvicorn app.main:app --reload --port 8000
```

- http://localhost:8000 — 상태 확인
- http://localhost:8000/health — 헬스 체크

## 로드맵

- [x] 검색 백엔드 추상화 (Vertex · Drive 파일명 · hybrid)
- [x] OAuth 로그인, Firestore 스키마 + 비동기 DB 연결
- [x] 4단계 RAG 파이프라인 (검색→재정렬→생성→검증)
- [x] API 엔드포인트 + Rate Limit · [ ] 사용량 미터링 (현재 로그 1줄)
- [x] 화이트라벨 UI + 사용자 피드백 수집
- [x] Docker 패키징 + Secret Manager (ADR 0011·0013)
- [x] Cloud Run 배포 + IAP (ADR 0012)
- [x] IAP JWT 검증 적용 (이번 커밋)
- [ ] 에러 핸들링 + 장애 알림 **(진행 중)**
- [ ] 골든셋 기반 RAG 품질 평가 — 20문항 초안 작성([docs/eval](docs/eval)), 측정 스크립트·수치는 미착수
- [ ] BigQuery 분석 파이프라인 + 자동 리포트
- [ ] dbt 데이터 마트
- [ ] Terraform 모듈화 (IaC)

## 알려진 한계

- 세션 서명 키 기본값이 빈 문자열 — `SESSION_SECRET_KEY` 를 비워도 그대로 기동한다 (`app/config.py` `session_secret_key`, `app/main.py` `SessionMiddleware`)
- OAuth 토큰이 세션 쿠키에 서명만 된 채 평문으로 들어가고, refresh 토큰은 저장만 하고 갱신에 쓰지 않는다 (`app/routers/auth.py` `auth_callback`, `app/utils/auth_utils.py` `get_user_oauth_access_token`)
- Gemini 호출에 타임아웃·재시도가 없다 — thinking 설정 거부 시 1회 재시도만 (`app/ai_service.py` `_generate`)
- 검색 로그에 질문 원문이 남는다 (`app/search/hybrid.py`·`vertex.py`·`oauth_drive.py` 의 `query=%r` 로그)
- 프롬프트에 문서·질문을 구분자 없이 삽입한다 — 문서 본문에 섞인 지시문을 분리하지 않는다 (`app/ai_service.py` `RERANK_PROMPT`·`ANSWER_PROMPT_TEMPLATE`·`VALIDATION_PROMPT`)
- Vertex 코퍼스는 인증된 사용자 전원이 열람한다 — `user_email` 로 결과를 거르지 않는다 (`app/search/vertex.py` `search`)
- Rate Limit 카운터가 프로세스 메모리에 있어 단일 인스턴스를 전제한다 — Cloud Run max 인스턴스 2 라 최악 1분 10회 (`app/utils/rate_limit.py`, ADR 0009·0012)
