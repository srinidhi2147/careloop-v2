"""Reads the care ID the website sends, so each user gets their own database."""
from __future__ import annotations

from urllib.parse import parse_qs

from .database import SESSION_ID_RE, current_session

HEADER_NAME = b"x-care-id"


def normalise_id(value: str | None) -> str | None:
    """'abcd-efgh-jkmn' -> 'ABCDEFGHJKMN'. Returns None if it is not a valid care ID."""
    cleaned = "".join(ch for ch in (value or "").upper() if ch.isalnum())
    return cleaned if SESSION_ID_RE.fullmatch(cleaned) else None


class SessionMiddleware:
    """Plain ASGI middleware, so it does not interfere with streaming responses.

    The ID comes from the X-Care-ID header, or from ?id= (the live event stream cannot set headers).
    No ID means the default database, which is what MCP clients use."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        care_id = None
        for name, value in scope.get("headers", []):
            if name == HEADER_NAME:
                care_id = normalise_id(value.decode("latin-1"))
        if care_id is None:
            query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
            care_id = normalise_id((query.get("id") or [None])[0])

        token = current_session.set(care_id)
        try:
            await self.app(scope, receive, send)
        finally:
            current_session.reset(token)