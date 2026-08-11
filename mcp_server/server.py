from mcp.server.fastmcp import FastMCP

from mcp_server.tools import register_weather_tools
from mcp_server.services.weather_service import WeatherService


mcp = FastMCP(
    "Seoul Weather MCP",
    host="0.0.0.0",
    port=8000,
    streamable_http_path="/mcp",
    json_response=True,
    stateless_http=True,
)

_weather_service: WeatherService = None


def _get_service() -> WeatherService:
    global _weather_service

    if _weather_service is None:
        _weather_service = WeatherService()

    return _weather_service


_registered_tools = register_weather_tools(
    mcp,
    lambda: _get_service(),
)

get_latest_weather = _registered_tools["get_latest_weather"]
search_weather = _registered_tools["search_weather"]
get_weather_risk_summary = _registered_tools[
    "get_weather_risk_summary"
]


if __name__ == "__main__":
    mcp.run(transport="stdio")
