# syntax=docker/dockerfile:1
# ──────────────────────────────────────────────────────────────────────────────
# Drive Chatbot — 컨테이너 이미지 (ADR 0011)
#
# 설계 요지:
#   - 단일 스테이지. 멀티스테이지는 CI/CD 하드닝 때 검토(단순 우선).
#   - 베이스: 공식 python:3.11-slim (롤링 태그 → 빌드 시점의 최신 보안 패치 빌드 수령).
#       · digest 고정(완전 재현성)은 CI/CD 하드닝 때.
#   - slim 에는 PEP668 의 EXTERNALLY-MANAGED 마커가 없어 `pip install` 이 그대로 동작.
#     (venv / --break-system-packages 불필요. alpine 이었다면 PEP668 적용돼 막힘)
#   - apt 설치 0: 의존성이 전부 cp311 manylinux wheel 제공 → build-essential 불필요.
#     헬스체크도 python 표준 라이브러리(urllib)를 써서 curl 미설치 상태로 처리.
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

# 런타임/빌드 환경변수
#   PYTHONUNBUFFERED=1              stdout/stderr 버퍼링 끔 → docker logs / Cloud Run 로그 즉시 노출.
#                                   (configure_logging 의 app.* INFO/미터링이 컨테이너에서도 바로 흐르게)
#   PYTHONDONTWRITEBYTECODE=1       .pyc 미생성 → 이미지에 불필요 산출물 X
#   PIP_NO_CACHE_DIR=1              pip 캐시를 레이어에 안 남김 → 이미지 경량
#   PIP_DISABLE_PIP_VERSION_CHECK=1 빌드 로그의 "pip 업그레이드 하세요" 잔소리 제거
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 작업 디렉토리. 아래 COPY 구조와 합쳐져 main.py 의
#   BASE_DIR = Path(__file__).resolve().parent.parent  →  /app 을 가리킴.
#   (templates/static 을 CWD 비의존 절대경로로 잡아둔 포석이 여기서 값을 함 — ADR 0010)
WORKDIR /app

# ── 의존성 레이어 (캐시 최적화) ────────────────────────────────────────────────
# requirements.txt 만 먼저 COPY → 앱 코드가 바뀌어도 의존성이 그대로면 이 레이어 캐시를 재사용.
# (앱 코드 COPY 를 이 뒤에 둬서 "코드 한 줄 고칠 때마다 pip 재설치" 를 피함)
# NOTE(CI/CD 하드닝 과제): 현재 requirements.txt 에 dev 도구(pytest/black/ruff/mypy)가 섞여 있어
#   이미지에 함께 들어감. 운영 하드닝 때 runtime/dev 분리 + 멀티스테이지로 정리 예정.
#   또한 재현 가능 빌드는 UTF-8 로 재생성한 lock 파일로 전환(현재 requirements.lock 은 UTF-16).
COPY requirements.txt ./
RUN pip install -r requirements.txt

# ── 앱 코드 + 정적 자산 (allowlist COPY) ───────────────────────────────────────
# `COPY . .` (denylist) 대신 필요한 디렉토리만 명시적으로 COPY(allowlist).
#   → .env / secrets/ / *.json 같은 비밀이 .dockerignore 에 빠지더라도 이미지에 못 들어옴(2중 방어).
# templates/ static/ 은 프로젝트 루트(app/ 의 부모)에 위치 → /app/templates, /app/static 으로.
COPY app/ ./app/
COPY templates/ ./templates/
COPY static/ ./static/

# ── 비루트 사용자 (최소 권한 원칙 — 프로젝트 일관 테마) ─────────────────────────
# COPY 산출물은 root 소유로 들어오므로 소유권을 appuser 로 이전(chown).
#   안 하면 비루트 전환 후 쓰기가 필요한 경로에서 권한 에러(흔한 함정).
# --system        : 로그인 불가 시스템 계정
# --no-create-home: 홈 디렉토리 불필요(이미지 군더더기 제거)
RUN groupadd --system appgroup \
    && useradd --system --gid appgroup --no-create-home appuser \
    && chown -R appuser:appgroup /app
USER appuser

# 포트 노출(문서화 목적). Cloud Run 기본 포트 8080 과 정렬.
#   실제 매핑은 `docker run -p 호스트:컨테이너` 에서 결정됨.
EXPOSE 8080

# 헬스체크 — 기존 GET /health 재사용(main.py 에 존재, auth_middleware 의 PUBLIC_PATHS 라 인증 면제).
#   slim 엔 curl 이 없으므로 python 표준 라이브러리(urllib)로 점검.
#   ※ Cloud Run 은 자체 헬스 프로브를 쓰므로 이 HEALTHCHECK 는 주로 로컬 docker / compose 용.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health').status==200 else 1)"]

# 실행 — 단일 uvicorn.
#   --host 0.0.0.0 : 컨테이너 외부에서 접근 가능하도록(포트 매핑 위해). 로컬 127.0.0.1 과 다름.
#   멀티워커(gunicorn -k uvicorn.workers.UvicornWorker)는 Cloud Run 운영에서 필요해지면 검토(ADR 0012).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
