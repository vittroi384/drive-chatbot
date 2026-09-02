"""Structured logging setup.

Skeleton. Wired to Cloud Logging in 12단계 (에러 핸들링 + 알림).
get_user_email() (IAP header 우선, 세션 fallback) lands in 5/11단계.
"""

from __future__ import annotations

import logging


def configure_logging(level: int = logging.INFO) -> None:
    """Configure root logging. Cloud Logging handler added in 12단계."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
