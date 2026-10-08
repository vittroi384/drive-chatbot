"""OAuth Drive backend (사용자별 Google Drive 검색).

로그인한 사용자 본인의 OAuth access token으로 그 사용자의 Drive를 검색한다.
사용자 token을 쓰므로 Google의 ACL이 자동 적용 → 다른 사용자 문서는 보이지 않는다.

[1차 범위] 본문 추출은 아직 구현하지 않는다 (제목만 content로 사용).
    골든셋 평가 후 본문 추출(파일 export/다운로드 + 파싱) 추가 결정.

[함정] googleapiclient는 동기(sync) 라이브러리다. async pipeline 안에서 그냥
    호출하면 event loop를 block 한다 → asyncio.to_thread로 thread off-load.
"""

from __future__ import annotations

import asyncio
import logging

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from .base import DocumentSearchService, SearchResult

logger = logging.getLogger(__name__)

# Drive API는 점수를 주지 않으므로 고정 baseline (정규화는 Hybrid가 처리).
_DRIVE_FALLBACK_SCORE = 0.5


class OAuthDriveBackend(DocumentSearchService):
    """사용자 본인 Drive를 fullText 검색하는 per-user backend."""

    backend_name = "oauth"

    async def search(
        self,
        query: str,
        *,
        user_email: str,
        user_oauth_token: str | None = None,
        top_k: int = 20,
    ) -> list[SearchResult]:
        # token이 없으면 검색 불가 → 빈 리스트 + 경고.
        # (예: scripts/test_ai_service.py 는 세션이 없어 token=None → 정상적으로 빈 결과)
        if not user_oauth_token:
            logger.warning(
                "[oauth] no OAuth token for %s → skip Drive search", user_email
            )
            return []

        try:
            files = await asyncio.to_thread(
                self._search_drive_sync, user_oauth_token, query, top_k
            )
        except Exception:  # noqa: BLE001 - 정식 에러 핸들링은 후속
            logger.error(
                "[oauth] Drive search failed for %s, query=%r",
                user_email,
                query,
                exc_info=True,
            )
            return []

        results = [
            SearchResult(
                # 1차: 제목만 content로 (본문 추출은 미구현).
                content=f.get("name", ""),
                source_uri=f.get("webViewLink", ""),
                source_title=f.get("name", "(이름 없음)"),
                chunk_index=0,
                score=_DRIVE_FALLBACK_SCORE,
                metadata={
                    "backend": "oauth",
                    "file_id": f.get("id"),
                    "mime_type": f.get("mimeType"),
                    "modified_time": f.get("modifiedTime"),
                },
            )
            for f in files[:top_k]
        ]
        logger.info("[oauth] query=%r → %d files for %s", query, len(results), user_email)
        return results

    @staticmethod
    def _search_drive_sync(token: str, query: str, top_k: int) -> list[dict]:
        """동기 Drive API 호출 (asyncio.to_thread 안에서 실행됨).

        [함정] Drive q 파라미터에서 작은따옴표는 escape 해야 한다 → \\' 로 치환.
        [참고] fullText contains는 본문/제목 매칭. 메타데이터만 있는 파일은 안 잡힘.
        """
        creds = Credentials(token=token)
        service = build("drive", "v3", credentials=creds, cache_discovery=False)
        escaped = query.replace("\\", "\\\\").replace("'", "\\'")
        response = (
            service.files()
            .list(
                q=f"fullText contains '{escaped}' and trashed = false",
                fields="files(id, name, webViewLink, mimeType, modifiedTime)",
                pageSize=min(max(top_k, 1), 100),
                spaces="drive",
                corpora="user",
            )
            .execute()
        )
        return response.get("files", [])
