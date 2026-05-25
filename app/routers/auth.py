"""Google OAuth login routes. Implemented in 5단계 (feat/oauth-login)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])

# TODO(5단계): /auth/login, /auth/callback, /auth/logout
