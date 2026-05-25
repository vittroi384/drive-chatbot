"""Conversation room endpoints. Implemented in 8단계."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/rooms", tags=["rooms"])

# TODO(8단계): CRUD for chat rooms (Firestore-backed)
