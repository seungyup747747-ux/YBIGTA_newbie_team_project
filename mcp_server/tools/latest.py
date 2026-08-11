from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from mcp_server.services.weather_service import WeatherService


ServiceFactory = Callable[[], WeatherService]


def register_latest_tool(
    mcp: FastMCP,
    get_service: ServiceFactory,
) -> Callable[..., dict[str, Any]]:
    @mcp.tool(
        name="get_latest_weather",
        description=(
            "서울 주요 지역의 최신 날씨와 위험도를 조회합니다. "
            "지역을 생략하면 신촌, 강남, 서울역, 여의도, 잠실을 "
            "모두 조회합니다."
        ),
    )
    def get_latest_weather(location: str = None) -> dict[str, Any]:
        rows = get_service().get_latest_weather(location)
        return {
            "count": len(rows),
            "location": location,
            "observations": rows,
        }

    return get_latest_weather
