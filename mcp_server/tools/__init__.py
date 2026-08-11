from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from mcp_server.services.weather_service import WeatherService
from mcp_server.tools.aggregation import register_aggregation_tool
from mcp_server.tools.latest import register_latest_tool
from mcp_server.tools.search import register_search_tool


ServiceFactory = Callable[[], WeatherService]
ToolFunction = Callable[..., dict[str, Any]]


def register_weather_tools(
    mcp: FastMCP,
    get_service: ServiceFactory,
) -> dict[str, ToolFunction]:
    """Register the three read-only weather tools on an MCP server."""
    return {
        "get_latest_weather": register_latest_tool(mcp, get_service),
        "search_weather": register_search_tool(mcp, get_service),
        "get_weather_risk_summary": register_aggregation_tool(mcp, get_service),
    }


__all__ = ["register_weather_tools"]
