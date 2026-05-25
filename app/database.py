"""Firestore access layer.

Skeleton only. Schema + client wiring lands in 6단계 (Firestore 스키마).
Reminder (changes-and-updates #2): 개인 GCP 단계에서는 본인 1명 테스트 데이터만.
임직원 7명 데이터는 회사 GCP 이전(13~15단계) 후에만 적재.
"""

from __future__ import annotations


def get_firestore_client() -> object:
    """Return an async Firestore client. Implemented in 6단계."""
    raise NotImplementedError("Firestore client lands in 6단계")
