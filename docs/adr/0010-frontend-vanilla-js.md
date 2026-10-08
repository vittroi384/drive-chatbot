# ADR 0010 — 프론트엔드: Vanilla JS + Jinja2 (React/Vue 미사용)

- 상태(Status): Accepted
- 일자: 2026-06
- 관련 구현: `templates/index.html`, `static/app.js`

## 맥락 (Context)

챗 UI가 필요했다. 요구사항은 사이드바(대화 목록), 메시지
말풍선, 출처 표시, 피드백(👍/👎), 화이트라벨(회사명/로고/추천 질문), 모바일
기본 대응이다.

제약:
- 개발자 1명(솔로), 초기 사용자 7~10명 규모
- REST API(`/api/chat`, `/api/rooms`, `.../messages`, `.../feedback`)가
  이미 완성 — 프론트는 이 API를 호출하는 얇은 클라이언트면 충분
- Docker 이미지로 패키징 (빌드 단계가 적을수록 이미지가 가벼움)
- 화이트라벨이 핵심 — 회사별 커스터마이징을 코드 수정 없이 해야 함

## 결정 (Decision)

프론트엔드를 **Jinja2 템플릿 + Vanilla JS**로 구현한다. React/Vue 등 SPA
프레임워크는 도입하지 않는다.

- 서버 렌더: `GET /`에서 Jinja2로 `index.html`을 렌더링하며 화이트라벨 값
  (`app_name`, `company_name`, `company_logo_url`, `suggested_questions`)을 주입
- 클라이언트: `static/app.js` 단일 파일 (API 헬퍼 / 렌더링 / 이벤트로 모듈 분리)
- 화이트라벨/추천 질문은 전부 `.env` → 코드 수정 0 (`SUGGESTED_QUESTIONS`는
  `|` 구분, 비우면 칩 미표시)
- 모바일은 CSS 미디어쿼리(≤768px) 기반 off-canvas 사이드바 + 햄버거 토글로 대응
  (PC 레이아웃은 그대로 유지)

## 근거 (Rationale)

- 솔로 개발자 + 소규모 사용자 → React 도입은 학습/빌드/유지보수 비용 대비 과함
- 빌드 단계 없음 → 배포 단순, Docker 이미지 경량 (Node 빌드 체인 불필요)
- API가 이미 완성돼 있어 프론트는 fetch 호출 + DOM 렌더면 충분
- 추후 화면이 복잡해지면 React/Vue로 마이그레이션하는 옵션은 그대로 열려 있음

## 결과 / 트레이드오프 (Consequences)

장점:
- 의존성/빌드 0, 배포 단순, 이미지 경량
- 코드 흐름이 직관적이라 디버깅/온보딩 쉬움

단점(수용):
- 답변 스트리밍 같은 고급 UX 구현이 번거로움 (1차는 전체 대기 후 표시)
- 컴포넌트 재사용성 낮음 — 지금은 화면이 단순해 문제 없음
- 화면이 복잡해지면 마이그레이션 필요 가능성

## 구현 메모 (보안/함정)

- **XSS**: 모든 사용자/AI 텍스트는 `escapeHtml()` 후 삽입. 줄바꿈은 `<br>` 주입
  대신 CSS `white-space: pre-wrap`으로 표현 (주입 표면 최소화)
- **세션**: 모든 fetch에 `credentials:"include"` (쿠키 전달) + `redirect:"manual"`
  (세션 만료 시 302→로그인 페이지를 fetch가 따라가 깨지는 문제 차단, `opaqueredirect` 감지)
- **출처 링크**: `target="_blank" rel="noopener noreferrer"` (탭 하이재킹 방어)
- **응답 매핑**: `POST /api/chat`은 `answer`, `GET messages`는 `content` 키 →
  전송 후 `answer`를 `content`로 매핑해 렌더(렌더 함수 일원화)
- **피드백 active**: 스펙의 "매번 reload" 대신 낙관적 토글 채택(스크롤 튐 방지).
  `MessageItem.feedback`이 응답에 포함되므로 새로고침/룸 재진입 시에도 active 유지.
  `FeedbackRequest`는 `up|down`만 허용 → 해제 불가, up↔down 전환만.
- **입력 길이**: textarea `maxlength=2000` = `ChatRequest.query` 검증값과 일치(422 예방)

## 대안 (Alternatives)

- React/Vue SPA: 위 비용 사유로 보류 (마이그레이션 옵션 보존)
- 단발성 검색 UI(대화 스레드 없음): 멀티턴 백엔드(history truncation, rooms)를
  버리게 되고 후속 질문이 불가 → 대화형 유지
