"""Chat endpoints. Implemented in 8단계 (API + Rate Limit + 미터링)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/chat", tags=["chat"])

# TODO(8단계): POST /chat (rate-limited via slowapi)
