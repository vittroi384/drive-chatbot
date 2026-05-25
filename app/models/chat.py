"""Chat request/response models. Fleshed out in 8단계 (API)."""

from __future__ import annotations

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Incoming chat message. Fields finalized in 8단계."""

    message: str
    room_id: str | None = None


class ChatResponse(BaseModel):
    """Outgoing answer with citations. Fields finalized in 8단계."""

    answer: str
    sources: list[str] = []
