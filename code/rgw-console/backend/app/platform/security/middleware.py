from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import re
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import unquote

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from ...config import Settings
from .passwords import verify_password
from .accounts import ConsoleRole


UUID_PATH = r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"
# Every permitted operation is named. New routes stay unavailable until they
# are reviewed as Ceph reads or local collection/scenario metadata operations.
READ_PATHS = tuple(re.compile(expression + r"\Z") for expression in (
    r"/api/(?:live|ready|health|health/dependencies|runtime-config)",
    r"/api/capacity(?:/stream|/decisions/" + UUID_PATH + r")?",
    r"/api/performance/(?:current|history|stream)",
    r"/api/v1/cluster/(?:profile|capabilities|inventory|resources|metric-catalog|metrics|collections(?:/" + UUID_PATH + r")?)",
    r"/api/v1/as-is/collections(?:/" + UUID_PATH + r"(?:/export)?)?",
    r"/api/v1/osdmap-previews/(?:capabilities|" + UUID_PATH + r")",
    r"/api/v1/sessions(?:/" + UUID_PATH + r"(?:/timeline|/report)?)?",
    r"/api/v1/osd-inventory/collections(?:/compare|/compare-config|/" + UUID_PATH + r"(?:/evidence|/osds/[0-9]+)?)?",
))
LOCAL_POST_PATHS = tuple(re.compile(expression + r"\Z") for expression in (
    r"/api/v1/(?:sessions|osd-inventory/collections)",
    r"/api/v1/(?:exports|cluster/collections)",
    r"/api/v1/as-is/(?:observe|export|collections|compare(?:/export)?)",
    r"/api/v1/as-is/collections/" + UUID_PATH + r"/restore",
    r"/api/v1/osdmap-previews(?:/" + UUID_PATH + r"/export)?",
))
LOCAL_DELETE_PATHS = (re.compile(r"/api/v1/as-is/collections/" + UUID_PATH + r"\Z"),)
VIEWER_POST_PATHS = tuple(re.compile(expression + r"\Z") for expression in (
    r"/api/v1/as-is/(?:observe|export|compare(?:/export)?)",
    r"/api/v1/exports",
    r"/api/v1/osdmap-previews/" + UUID_PATH + r"/export",
))
ADMIN_POST_PATHS = (re.compile(r"/api/v1/as-is/collections/" + UUID_PATH + r"/restore\Z"),)


@dataclass(frozen=True)
class ConsoleIdentity:
    username: str
    role: ConsoleRole


def canonical_path(scope: Scope) -> str | None:
    path = scope.get("path", "")
    raw = scope.get("raw_path", path.encode("utf-8"))
    try:
        raw_text = raw.decode("ascii")
        if re.search(r"%(?:2f|5c|25)", raw_text, flags=re.IGNORECASE):
            return None
        decoded = unquote(raw_text, errors="strict")
    except (UnicodeError, ValueError):
        return None
    if (
        decoded != path
        or not path.startswith("/")
        or "\\" in path
        or "%" in path
        or "//" in path
        or any(part in {".", ".."} for part in path.split("/"))
        or any(ord(char) < 32 for char in path)
    ):
        return None
    return path


def permitted_read_only_request(method: str, path: str) -> bool:
    if not path.startswith("/api/") and path != "/api":
        return method in {"GET", "HEAD"} and not path.startswith("/ws")
    patterns = READ_PATHS if method in {"GET", "HEAD"} else LOCAL_POST_PATHS if method == "POST" else LOCAL_DELETE_PATHS if method == "DELETE" else ()
    return any(pattern.fullmatch(path) for pattern in patterns)


def permitted_role_request(role: ConsoleRole, method: str, path: str) -> bool:
    """All role capabilities stay inside the explicit Ceph read-only policy."""

    if role not in {"viewer", "operator", "admin"} or not permitted_read_only_request(method, path):
        return False
    if role == "admin" or method in {"GET", "HEAD"}:
        return True
    if method != "POST":
        return False
    if role == "viewer":
        return any(pattern.fullmatch(path) for pattern in VIEWER_POST_PATHS)
    return not any(pattern.fullmatch(path) for pattern in ADMIN_POST_PATHS)


class ConsoleSecurityMiddleware:
    def __init__(self, app: ASGIApp, settings_provider: Callable[[], Settings]) -> None:
        self.app = app
        self.settings_provider = settings_provider
        # Cache only a digest of successful credentials, never the header or
        # plaintext password. The hash-file identity prevents stale reuse.
        self._verified: OrderedDict[bytes, float] = OrderedDict()
        self._password_checks = asyncio.Semaphore(4)

    async def _authenticated(self, headers: Headers, settings: Settings) -> ConsoleIdentity | None:
        if not settings.console_auth_username and not settings.console_auth_users:
            return ConsoleIdentity("", "admin")
        authorization = headers.get("authorization", "")
        if len(authorization) > 4096:
            return None
        scheme, separator, credential_text = authorization.partition(" ")
        if not separator or scheme.lower() != "basic":
            return None
        try:
            decoded = base64.b64decode(credential_text, validate=True).decode("utf-8")
            username, separator, password = decoded.partition(":")
        except (ValueError, UnicodeError, binascii.Error):
            return None
        if not separator:
            return None
        if settings.console_auth_users:
            account = settings.console_auth_users.get(username)
            if account is None:
                return None
            encoded_hash = account.password_hash.get_secret_value()
            identity = ConsoleIdentity(account.username, account.role)
        else:
            if not hmac.compare_digest(username.encode(), settings.console_auth_username.encode()):
                return None
            encoded_hash = settings.console_auth_password_hash.get_secret_value()
            identity = ConsoleIdentity(username, "admin")
        cache_key = hashlib.sha256((authorization + "\0" + encoded_hash + "\0" + username + "\0" + identity.role).encode()).digest()
        now = time.monotonic()
        if self._verified.get(cache_key, 0) > now:
            self._verified.move_to_end(cache_key)
            return identity
        async with self._password_checks:
            accepted = await asyncio.to_thread(verify_password, password, encoded_hash)
        if accepted:
            self._verified[cache_key] = now + 60
            self._verified.move_to_end(cache_key)
            while len(self._verified) > 128:
                self._verified.popitem(last=False)
        return identity if accepted else None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        settings = self.settings_provider()
        secured = settings.console_read_only or bool(settings.console_auth_username or settings.console_auth_users)
        if not secured:
            await self.app(scope, receive, send)
            return
        path = canonical_path(scope)
        if scope["type"] == "websocket":
            if settings.console_read_only or path is None or not await self._authenticated(Headers(scope=scope), settings):
                await send({"type": "websocket.close", "code": 1008, "reason": "Console policy denies WebSocket access"})
                return
            await self.app(scope, receive, send)
            return

        async def reject(status: int, code: str, message: str, challenge: bool = False) -> None:
            headers = {"Cache-Control": "no-store"}
            if challenge:
                headers["WWW-Authenticate"] = 'Basic realm="Storage Lab Console", charset="UTF-8"'
            await JSONResponse({"detail": {"code": code, "message": message}}, status_code=status, headers=headers)(scope, receive, send)

        if path is None:
            await reject(400, "INVALID_REQUEST_PATH", "Request path is not canonical")
            return
        method = scope.get("method", "GET")
        if path == "/api/live" and method in {"GET", "HEAD"}:
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        identity = await self._authenticated(headers, settings)
        if identity is None:
            await reject(401, "CONSOLE_AUTH_REQUIRED", "Console authentication required", challenge=True)
            return
        state = scope.setdefault("state", {})
        state["console_actor"] = identity.username
        state["console_role"] = identity.role
        if settings.console_read_only and not permitted_read_only_request(method, path):
            await reject(403, "CONSOLE_READ_ONLY", "Console chỉ cho phép đọc Ceph và quản lý dữ liệu thu thập cục bộ.")
            return
        if settings.console_auth_users and not permitted_role_request(identity.role, method, path):
            await reject(403, "CONSOLE_ROLE_FORBIDDEN", "Tài khoản không có quyền thực hiện thao tác này.")
            return
        if method not in {"GET", "HEAD", "OPTIONS"}:
            origin = headers.get("origin")
            if (origin and origin not in settings.origins) or (not origin and headers.get("x-console-request") != "1"):
                await reject(403, "CONSOLE_CSRF_REJECTED", "Use an authorized origin or X-Console-Request: 1")
                return

        async def secure_send(message):
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers", []))
                response_headers.extend([
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"same-origin"),
                    (b"cache-control", b"no-store"),
                    (b"content-security-policy", b"frame-ancestors 'none'; base-uri 'self'; object-src 'none'"),
                ])
                message = {**message, "headers": response_headers}
            await send(message)

        await self.app(scope, receive, secure_send)
