"""FastAPI 애플리케이션 진입점.

로컬 실행 (프로젝트 루트에서, venv 활성화 상태):
    uvicorn app.main:app --reload --port 8000

이후 접속: http://localhost:8000  과  http://localhost:8000/health
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.database import warmup_firestore
from app.routers import auth as auth_router, chat, rooms
from app.middleware.auth_middleware import AuthRequiredMiddleware
from app.utils.logging import configure_logging
from app.utils.rate_limit import limiter

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 startup/shutdown 훅 (deprecated @app.on_event 의 최신 대체).

    startup 순서가 중요하다: configure_logging() 을 가장 먼저 호출해야 그 뒤의
    모든 로그가 같은 포맷으로 남는다. uvicorn 은 root 로거에 핸들러를 붙이지 않으므로,
    이 basicConfig 가 있어야 app.* 의 INFO 로그(미터링/타이밍)가 실제로 출력된다.
    """
    configure_logging()              # app.* INFO 로그가 묻히지 않도록 (미터링 가시성)
    logger.info("startup: 로깅 설정 완료, Firestore 워밍업 시작")
    await warmup_firestore()         # 콜드스타트 완화 (워밍업 실패해도 기동은 계속됨)
    yield
    # shutdown: 현재 정리할 리소스 없음 (Firestore AsyncClient 는 프로세스 종료 시 회수)


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

# Rate limit 등록 (Part B): limiter 를 app.state 에 두고, 한도 초과(429) 핸들러를 연결한다.
# 실제 한도 강제는 각 라우터의 @limiter.limit(...) 데코레이터가 수행한다 (현재 /api/chat).
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 순서 주의(중요): add_middleware 는 나중에 추가한 것이 바깥쪽(먼저 실행)이 됨.
# 따라서 SessionMiddleware 를 나중에 추가해야 인증 미들웨어보다 먼저 실행되어
# request.session 이 준비됨.
app.add_middleware(AuthRequiredMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    same_site="lax",
    https_only=settings.env != "local",
    max_age=60 * 60 * 8,  # 8시간
)
app.include_router(auth_router.router)
app.include_router(chat.router)      # /api/chat (Part C)
app.include_router(rooms.router)     # /api/rooms, .../messages, .../feedback (Part D)

# --- 정적 파일 + 템플릿 (9단계) ------------------------------------------------
# 경로를 __file__ 기준(프로젝트 루트 = app/ 의 부모)으로 잡아 CWD 에 의존하지 않게 함.
# → 로컬(루트에서 uvicorn 실행)과 Docker(10단계, WORKDIR 무관)에서 모두 안전.
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def root(request: Request) -> HTMLResponse:
    """챗 UI 렌더(9단계). 화이트라벨 값(회사명/로고/추천질문)을 템플릿에 주입한다.

    이 라우트는 페이지이므로, 미인증 요청은 AuthRequiredMiddleware 가 /login 으로
    302 시킨다(=여기 도달하면 인증된 상태). API 호출(/api/*)의 401 은 app.js 가 처리.
    """
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "app_name": settings.app_name,
            "company_name": settings.company_name,
            "company_logo_url": settings.company_logo_url,
            "suggested_questions": settings.suggested_questions_list,
        },
    )


@app.get("/health")
async def health() -> dict[str, str]:
    """라이브니스 프로브. Cloud Run / IAP 헬스체크(11단계)에서 사용."""
    return {"status": "ok", "env": settings.env}
