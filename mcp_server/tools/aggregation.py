from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from mcp_server.services.weather_service import WeatherService


ServiceFactory = Callable[[], WeatherService]


def register_aggregation_tool(
    mcp: FastMCP,
    get_service: ServiceFactory,
) -> Callable[..., dict[str, Any]]:
    @mcp.tool(
        name="get_weather_risk_summary",
        description=(
            "지정한 기간의 날씨 위험등급별 관측 건수, "
            "평균 위험점수와 최대 위험점수를 집계합니다."
        ),
    )
    def get_weather_risk_summary(
        start_at: str,
        end_at: str,
        location: str = None,
    ) -> dict[str, Any]:
        rows = get_service().get_risk_summary(
            start_at,
            end_at,
            location=location,
        )
        return {
            "filters": {
                "start_at": start_at,
                "end_at": end_at,
                "location": location,
            },
            "summary": rows,
        }

    return get_weather_risk_summary
