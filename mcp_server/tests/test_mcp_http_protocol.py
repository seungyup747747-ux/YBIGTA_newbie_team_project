from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

import mcp_server.server as server
from mcp_server.security import MCPRequestSecurity

TOKEN = "test-token-which-is-at-least-32-characters"


def test_authenticated_streamable_http_lists_and_calls_tools(
    monkeypatch,
) -> None:
    service = MagicMock()
    service.get_latest_weather.return_value = [
        {
            "location": "신촌",
            "temperature": 26.5,
            "risk_level": "MEDIUM",
            "collected_at": "2026-08-11T14:30:00",
        }
    ]
    monkeypatch.setattr(
        server,
        "_get_service",
        MagicMock(return_value=service),
    )

    async def scenario():
        inner = server.mcp.streamable_http_app()
        app = MCPRequestSecurity(inner, auth_token=TOKEN)

        def client_factory(headers=None, timeout=None, auth=None):
            return httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                headers=headers,
                timeout=timeout,
                auth=auth,
            )

        async with inner.router.lifespan_context(inner):
            async with streamablehttp_client(
                "http://testserver/mcp",
                headers={"Authorization": f"Bearer {TOKEN}"},
                httpx_client_factory=client_factory,
            ) as streams:
                read_stream, write_stream, _ = streams
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    assert {tool.name for tool in tools.tools} == {
                        "get_latest_weather",
                        "search_weather",
                        "get_weather_risk_summary",
                    }

                    result = await session.call_tool(
                        "get_latest_weather",
                        {"location": "신촌"},
                    )
                    return result

        raise AssertionError("MCP client session ended without a result")

    result = asyncio.run(scenario())

    service.get_latest_weather.assert_called_once_with("신촌")
    assert result.structuredContent["count"] == 1
    assert (
        result.structuredContent["observations"][0]["risk_level"]
        == "MEDIUM"
    )
