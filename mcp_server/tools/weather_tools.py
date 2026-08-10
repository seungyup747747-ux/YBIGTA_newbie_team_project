from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from mcp_server.weather_service import WeatherService


ServiceFactory = Callable[[], WeatherService]
ToolFunction = Callable[..., dict[str, Any]]


def register_weather_tools(
    mcp: FastMCP,
    get_service: ServiceFactory,
) -> dict[str, ToolFunction]:
    @mcp.tool(
        name="get_latest_weather",
        description=(
            "서울 주요 지역의 최신 날씨와 위험도를 조회합니다. "
            "지역을 생략하면 신촌, 강남, 서울역, 여의도, 잠실을 "
            "모두 조회합니다."
        ),
    )
    def get_latest_weather(
        location: str = None,
    ) -> dict[str, Any]:
        rows = get_service().get_latest_weather(location)

        return {
            "count": len(rows),
            "location": location,
            "observations": rows,
        }

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
        limit: int = 100,
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

    return {
        "get_latest_weather": get_latest_weather,
        "search_weather": search_weather,
        "get_weather_risk_summary": get_weather_risk_summary,
    }
