"""RAG orchestration: retrieve -> re-rank -> generate -> ground-check.

Skeleton only. Implemented in 7단계 (AI 로직 + Re-ranking + 답변 검증).

Pipeline (planned):
    1. backend.search(query, top_k=20)              # search/* abstraction
    2. Gemini re-rank 20 -> top 5
    3. Gemini generate answer grounded in top 5
    4. Answer-grounding verification layer (환각 방지)
"""

from __future__ import annotations


async def answer_question(query: str, *, user_email: str) -> dict[str, object]:
    """Full RAG turn. Implemented in 7단계."""
    raise NotImplementedError("RAG pipeline lands in 7단계")
