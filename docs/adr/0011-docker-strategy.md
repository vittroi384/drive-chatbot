# ADR 0011 — Docker 패키징 + Secret 관리 전략

- 상태(Status): Accepted
- 날짜: 2026-06-29
- 관련 구현: `Dockerfile`, `.dockerignore`
- 관련 ADR: 0010(프론트 Vanilla JS — 빌드 단계 0 → 경량 이미지), 0001(회사=GCP 1:1 매핑), 0009(다층 방어)

## 맥락 (Context)

Cloud Run 배포(ADR 0012)를 위해 앱을 컨테이너 이미지로 패키징해야 한다. 이미지는
(1) 어디서 빌드하든 동일하게 동작하고, (2) 비밀(.env, 서비스 계정 키)을 절대 굽지 않으며,
(3) 최소 권한으로 실행돼야 한다. 동시에 로컬 개발 편의(.env 주입)와 운영 보안
(Secret Manager)을 둘 다 만족시켜야 한다.

이 프로젝트는 프론트 빌드 단계가 없고(ADR 0010, Vanilla JS + Jinja2) 파이썬 단일
서비스라, Node 빌드체인이 필요 없어 Docker 구성이 비교적 단순하다.

## 결정 (Decision)

### 결정 1 — 베이스 이미지: `python:3.11-slim`
alpine 이 아니라 slim 을 쓴다.
- 근거: 호환성 우선. slim 은 glibc 기반이라 대부분의 의존성이 cp311 manylinux wheel 로
  그대로 설치된다(빌드 도구 불필요). alpine 은 musl libc 라 일부 패키지가 소스 컴파일을
  요구해 빌드가 느려지고 깨질 위험이 있다.
- 실측: pip install 26초(컴파일 0), 최종 이미지 CONTENT SIZE 168MB(목표 500MB 이하 충족).
- apt 설치 0: 의존성이 전부 wheel 로 깔려 build-essential 불필요. 헬스체크도 curl 대신
  python 표준 urllib 로 처리해 추가 패키지를 안 깐다.

### 결정 2 — 비밀 관리: 로컬 `.env` / 운영 Secret Manager (env 분기)
- 로컬/dev: `.env` 주입(개발 편의). 운영(`env == "prod"`): GCP Secret Manager 조회.
- 분기는 `get_secret()` 헬퍼 한 곳에 가둔다(호출부는 비밀 출처를 모름). 이 헬퍼는 결정
  당시 스켈레톤이었고, 운영 주입 방식은 ADR 0013 에서 `--set-secrets` 환경변수 주입으로
  확정돼 헬퍼는 미배선으로 남았다(공개 저장소에는 포함하지 않았다).
- 서비스 계정 키(JSON)는 Secret Manager 대상이 **아니다**: Cloud Run 은 Workload Identity 로
  키 파일 자체가 불필요(ADR 0012). 로컬만 `-v` 로 read-only 마운트.
- ★ 코드의 env Literal 은 `["local","dev","prod"]`(`app/config.py`) 이므로 운영 판별은 `"prod"`다.

### 결정 3 — 비밀 차단: allowlist COPY + .dockerignore (2중 방어)
- 1차: `COPY . .`(denylist) 대신 필요한 것만 명시 복사 — `COPY app/`, `templates/`, `static/`.
  → .env/secrets/*.json 은 COPY 대상에서 원천적으로 빠진다.
- 2차: `.dockerignore` 가 `.env` / `*.json` / `progress/` / `.venv` / `.git` 등을 빌드
  컨텍스트에서 제외(컨텍스트 슬리밍 + 혹시 모를 누락 방어).

### 결정 4 — 비루트 실행
- `appuser`(uid 999, 시스템 계정) 생성, `COPY` 후 `chown -R appuser:appgroup /app`, `USER appuser`.
- 컨테이너 침해 시 권한 제한(최소 권한 원칙 — 프로젝트 일관 테마).
- 검증: `docker exec ... whoami` → appuser, `id` → uid=999.

### 결정 5 — 멀티스테이지 빌드 1차 미적용
- 단순 우선. 빌드 도구를 안 깔아서(결정 1) 런타임/빌드 분리 이득이 작다.
- CI/CD 자동화(계획) 때 이미지 최적화와 함께 재검토.

### 부수 결정 — 포트 8080 + 로컬 매핑
- 컨테이너는 8080(Cloud Run 기본 포트)에 바인딩(`--host 0.0.0.0`).
- 로컬은 `docker run -p 8000:8080` 으로 매핑 → 브라우저는 localhost:8000 접속 →
  기존 OAuth redirect_uri(`localhost:8000/auth/callback`) 그대로 유효(GCP 콘솔 무수정).

## 트레이드오프 (Consequences)

- (−) slim 은 alpine 대비 50~100MB 크다 — 단 168MB 로 충분히 작아 실익이 호환성 < 크기.
- (−) 멀티스테이지 미적용 → 이미지 최적화 여지 남음(CI/CD 자동화 때).
- (−) `.env` 마운트 방식은 운영엔 부적합 → 운영은 Secret Manager(ADR 0013).
- (−) `get_secret()` 은 스켈레톤 — `env=="prod"` 경로는 이 시점엔 미배선(로컬 폴백만 동작).
- (+) 어디서 빌드해도 동일 동작(경로 `__file__` 기준 — ADR 0010). 컨테이너에서 OAuth 로그인 +
  챗봇 + Firestore warmup 까지 로컬과 동일 동작 실증(localhost:8000).
- (+) 비밀 2중 차단 + 비루트 + 헬스체크(healthy) → 운영 준비된 이미지.

## 대안 (Alternatives considered)

- alpine 베이스: 더 작지만 musl 호환성 리스크 + 빌드 도구 필요 가능성 → 기각.
- `COPY . .` + .dockerignore 만: denylist 한 줄 누락이 곧 비밀 유출 → allowlist 로 강화.
- 서비스 계정 키를 Secret Manager 에 저장: Cloud Run 은 Workload Identity 로 키 불필요 → 제외.
- 멀티스테이지 빌드: 빌드 도구를 안 깔아 이득이 작음 → CI/CD 자동화 때 재검토.

## 후속 (Follow-ups)

- Cloud Run 배선: 운영 비밀 주입 경로 확정, Secret Manager 에 secret 생성
  (`google-client-secret`, `session-secret-key`), Workload Identity 설정 → ADR 0012·0013 으로 확정.
- CI/CD 자동화: 멀티스테이지 빌드 + 이미지 취약점 스캔(trivy 등) 본격 도입, dev 의존성 분리.
- 회사 GCP 이전: GCP_PROJECT_ID/버킷/OAuth 변경 시 .env 만 교체(이미지 재빌드 불요).
