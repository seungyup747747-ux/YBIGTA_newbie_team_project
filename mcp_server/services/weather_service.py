from typing import Any

from mcp_server.repositories.weather_repository import WeatherRepository


class WeatherService:
    def __init__(
        self,
        repository: WeatherRepository | None = None,
    ) -> None:
        self.repository = repository or WeatherRepository()

    def get_latest_weather(
        self,
        location: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.repository.get_latest_weather(location)

    def search_weather(
        self,
        start_at: str,
        end_at: str,
        *,
        location: str | None = None,
        risk_level: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self.repository.search_weather(
            start_at,
            end_at,
            location=location,
            risk_level=risk_level,
            limit=limit,
        )

    def get_risk_summary(
        self,
        start_at: str,
        end_at: str,
        *,
        location: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.repository.get_risk_summary(
            start_at,
            end_at,
            location=location,
        )
