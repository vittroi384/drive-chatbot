# Drive Chatbot

사내 Google Drive / GCS 문서를 검색해 답변하는 RAG 챗봇입니다.
회사 문서를 근거로만 답하도록 설계해 환각(없는 내용 지어내기)을 줄이는 데 초점을 맞췄습니다.

> 상태: 개발 진행 중 (프로젝트 뼈대 + 검색 백엔드 추상화 완료)

## 주요 특징

- **하이브리드 검색**: 공용 문서(GCS + Vertex AI Search) + 개인 문서(OAuth Drive)를 함께 검색
- **검색 백엔드 추상화**: 검색 구현을 인터페이스 뒤로 분리해 교체/확장이 쉬움
- **환각 방지**: 답변을 문서 근거에 한정 + 답변 검증 레이어 (개발 예정)
- **설정 분리**: 회사명/프롬프트/모델 등을 `.env`로 관리해 코드 수정 없이 조정

## 기술 스택

| 영역 | 선택 | 이유 |
|---|---|---|
| Backend | FastAPI + Uvicorn (Python 3.11, async) | 비동기 I/O, 자동 API 문서 |
| 검색 | Vertex AI Search + OAuth Drive (추상화) | 백엔드 교체를 설정 한 줄로 |
| 생성 | Gemini Flash (RAG) | 비용/지연 균형, 모델명은 `.env`로 관리 |
| 인증 | Google OAuth 2.0 | 관리자 권한 없이 개인 인증 방식 |
| DB | Firestore(실시간) + BigQuery(분석) | 대화 저장 / 분석 분리 |
| 배포 | Docker + Cloud Run | 서버리스, 사용량 기반 |

## 로컬 실행

```powershell
Copy-Item .env.example .env   # 그리고 값 채우기
uvicorn app.main:app --reload --port 8000
```

- http://localhost:8000 — 상태 확인
- http://localhost:8000/health — 헬스 체크

## 설계 결정 (ADR)

주요 아키텍처 결정은 [docs/adr/](docs/adr/README.md) 참고.