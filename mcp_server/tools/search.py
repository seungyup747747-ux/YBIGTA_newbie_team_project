from typing import Annotated, Any, Callable

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from mcp_server.services.weather_service import WeatherService


ServiceFactory = Callable[[], WeatherService]


def register_search_tool(
    mcp: FastMCP,
    get_service: ServiceFactory,
) -> Callable[..., dict[str, Any]]:
    @mcp.tool(
        name="search_weather",
        description=(
            "지정한 기간의 날씨 관측 기록을 조회합니다. "
            "지역과 위험등급으로 추가 필터링할 수 있습니다. "
            "날짜는 ISO 8601 형식으로 입력합니다."
        ),
    )
    def search_weather(
        start_at: str,
        end_at: str,
        location: str = None,
        risk_level: str = None,
        limit: Annotated[int, Field(ge=1, le=500)] = 100,
    ) -> dict[str, Any]:
        rows = get_service().search_weather(
            start_at,
            end_at,
            location=location,
            risk_level=risk_level,
            limit=limit,
        )
        return {
            "count": len(rows),
            "filters": {
                "start_at": start_at,
                "end_at": end_at,
                "location": location,
                "risk_level": risk_level,
                "limit": limit,
            },
            "observations": rows,
        }

    return search_weather
