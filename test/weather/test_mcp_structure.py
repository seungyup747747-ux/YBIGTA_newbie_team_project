import asyncio
from unittest.mock import MagicMock

from mcp.server.fastmcp import FastMCP

from mcp_server.tools.weather_tools import register_weather_tools


def make_mcp():
    mcp = FastMCP("Weather Tool Structure Test")
    service = MagicMock()

    register_weather_tools(
        mcp,
        lambda: service,
    )

    return mcp, service


def test_weather_tools_can_be_registered_on_new_server() -> None:
    mcp, _ = make_mcp()

    tools = asyncio.run(mcp.list_tools())
    names = {tool.name for tool in tools}

    assert names == {
        "get_latest_weather",
        "search_weather",
        "get_weather_risk_summary",
    }


def test_registration_does_not_create_database_service() -> None:
    factory = MagicMock()
    mcp = FastMCP("Lazy Service Test")

    register_weather_tools(mcp, factory)
    asyncio.run(mcp.list_tools())

    factory.assert_not_called()


def test_registered_tool_uses_injected_service() -> None:
    mcp, service = make_mcp()
    service.get_latest_weather.return_value = [
        {
            "location": "신촌",
            "risk_level": "MEDIUM",
        }
    ]

    result = asyncio.run(
        mcp.call_tool(
            "get_latest_weather",
            {"location": "신촌"},
        )
    )

    service.get_latest_weather.assert_called_once_with("신촌")
    assert result[1]["count"] == 1
