from __future__ import annotations

import hmac
import json
from collections.abc import Awaitable, Callable
from typing import Any

ASGIApp = Callable[
    [dict[str, Any], Callable[[], Awaitable[dict[str, Any]]], Callable[[dict[str, Any]], Awaitable[None]]],
    Awaitable[None],
]


class MCPRequestSecurity:
    """Authenticate MCP HTTP requests and cap their request body size."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        auth_token: str,
        max_request_bytes: int = 65_536,
    ) -> None:
        if not auth_token:
            raise RuntimeError("MCP_AUTH_TOKEN이 설정되지 않았습니다.")
        if auth_token == "change-me" or len(auth_token) < 32:
            raise RuntimeError(
                "MCP_AUTH_TOKEN은 32자 이상의 임의 문자열이어야 합니다."
            )
        if not 1_024 <= max_request_bytes <= 1_048_576:
            raise RuntimeError(
                "MCP_MAX_REQUEST_BYTES는 1024~1048576 범위여야 합니다."
            )

        self.app = app
        self.auth_token = auth_token
        self.max_request_bytes = max_request_bytes

    @staticmethod
    def _headers(scope: dict[str, Any]) -> dict[bytes, bytes]:
        return {key.lower(): value for key, value in scope.get("headers", [])}

    async def _json_response(
        self,
        send: Callable[[dict[str, Any]], Awaitable[None]],
        status: int,
        message: str,
        *,
        authenticate: bool = False,
    ) -> None:
        body = json.dumps(
            {"error": message},
            ensure_ascii=False,
        ).encode("utf-8")
        headers = [
            (b"content-type", b"application/json; charset=utf-8"),
            (b"content-length", str(len(body)).encode("ascii")),
            (b"cache-control", b"no-store"),
            (b"x-content-type-options", b"nosniff"),
        ]
        if authenticate:
            headers.append((b"www-authenticate", b"Bearer"))

        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": headers,
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": body,
            }
        )

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path == "/healthz":
            body = b'{"status":"ok"}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                        (b"cache-control", b"no-store"),
                        (b"x-content-type-options", b"nosniff"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        headers = self._headers(scope)
        authorization = headers.get(b"authorization", b"").decode(
            "utf-8", errors="ignore"
        )
        scheme, separator, supplied_token = authorization.partition(" ")
        authorized = (
            separator == " "
            and scheme.lower() == "bearer"
            and hmac.compare_digest(supplied_token, self.auth_token)
        )
        if not authorized:
            await self._json_response(
                send,
                401,
                "Bearer token이 없거나 유효하지 않습니다.",
                authenticate=True,
            )
            return

        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                declared_length = int(content_length)
            except ValueError:
                await self._json_response(send, 400, "Content-Length가 잘못되었습니다.")
                return
            if declared_length > self.max_request_bytes:
                await self._json_response(send, 413, "MCP 요청 크기 제한을 초과했습니다.")
                return

        messages: list[dict[str, Any]] = []
        total = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.disconnect":
                break
            total += len(message.get("body", b""))
            if total > self.max_request_bytes:
                await self._json_response(send, 413, "MCP 요청 크기 제한을 초과했습니다.")
                return
            if not message.get("more_body", False):
                break

        async def replay_receive() -> dict[str, Any]:
            if messages:
                return messages.pop(0)
            return {"type": "http.request", "body": b"", "more_body": False}

        async def secure_send(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers", []))
                response_headers.extend(
                    [
                        (b"cache-control", b"no-store"),
                        (b"x-content-type-options", b"nosniff"),
                    ]
                )
                message = {**message, "headers": response_headers}
            await send(message)

        await self.app(scope, replay_receive, secure_send)
