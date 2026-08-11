from __future__ import annotations

import os

from dotenv import load_dotenv

from mcp_server.security import MCPRequestSecurity
from mcp_server.server import mcp

load_dotenv(".env")


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"필수 환경변수가 없습니다: {name}")
    return value


def create_app() -> MCPRequestSecurity:
    max_request_bytes = int(os.getenv("MCP_MAX_REQUEST_BYTES", "65536"))
    return MCPRequestSecurity(
        mcp.streamable_http_app(),
        auth_token=_required_env("MCP_AUTH_TOKEN"),
        max_request_bytes=max_request_bytes,
    )


app = create_app()
