"""OAuth Drive backend (per-user Google Drive search).

Skeleton only. Real implementation lands in 7단계.
Uses the requesting user's OAuth access token to search *their* Drive with
the drive.readonly scope (see ADR 0002 / 보조 ADR on scope choice).
"""

from __future__ import annotations

from .base import DocumentSearchService, SearchResult


class OAuthDriveBackend(DocumentSearchService):
    """Searches an individual user's Google Drive via their OAuth token.

    Requires ``user_oauth_token``. Each call is scoped to exactly one user's
    files; nothing is cached server-side beyond the request lifecycle.
    """

    backend_name = "oauth"

    async def search(
        self,
        query: str,
        *,
        user_email: str,
        user_oauth_token: str | None = None,
        top_k: int = 20,
    ) -> list[SearchResult]:
        if user_oauth_token is None:
            raise ValueError("OAuthDriveBackend requires a user_oauth_token")
        # TODO(7단계): call Drive API files.list with fullText query,
        # fetch + chunk matched files, map -> SearchResult.
        raise NotImplementedError("OAuthDriveBackend.search lands in 7단계")
