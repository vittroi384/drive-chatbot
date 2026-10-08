"""Structured logging setup.

Skeleton. Cloud Logging 연결은 에러 핸들링·알림 작업에서 (예정).
"""

from __future__ import annotations

import logging


def configure_logging(level: int = logging.INFO) -> None:
    """Configure root logging. Cloud Logging handler 는 예정."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
