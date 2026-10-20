"""Gives each browser a random id (cookie) so it gets its own database."""
from __future__ import annotations

import secrets

from .database import SESSION_ID_RE, current_session

COOKIE_NAME = "careloop_sid"
ONE_YEAR = 60 * 60 * 24 * 365


class SessionMiddleware:
    """Plain ASGI middleware, so it does not interfere with streaming responses."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        sid = None
        for name, value in scope.get("headers", []):
            if name == b"cookie":
                for part in value.decode("latin-1").split(";"):
                    key, _, val = part.strip().partition("=")
                    if key == COOKIE_NAME:
                        sid = val
        is_new = not (sid and SESSION_ID_RE.fullmatch(sid))
        if is_new:
            sid = secrets.token_hex(16)

        async def send_with_cookie(message) -> None:
            if is_new and message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                cookie = f"{COOKIE_NAME}={sid}; Path=/; Max-Age={ONE_YEAR}; HttpOnly; SameSite=Lax"
                headers.append((b"set-cookie", cookie.encode()))
                message = {**message, "headers": headers}
            await send(message)

        token = current_session.set(sid)
        try:
            await self.app(scope, receive, send_with_cookie)
        finally:
            current_session.reset(token)