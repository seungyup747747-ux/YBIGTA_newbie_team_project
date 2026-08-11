from __future__ import annotations

import json
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import Engine, bindparam, text

from collector.open_meteo_client import LOCATIONS
from database.mysql_connection import create_db_engine

ALLOWED_LOCATIONS = frozenset(LOCATIONS)
ALLOWED_RISK_LEVELS = frozenset(
    {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
)

LATEST_WEATHER_QUERY = text(
    """
    SELECT
        weather.location,
        weather.latitude,
        weather.longitude,
        weather.observed_at,
        weather.temperature,
        weather.apparent_temperature,
        weather.relative_humidity,
        weather.precipitation,
        weather.wind_speed,
        weather.weather_code,
        weather.risk_score,
        weather.risk_level,
        weather.risk_reasons,
        weather.collected_at
    FROM weather_observations AS weather
    INNER JOIN (
        SELECT
            location,
            MAX(observed_at) AS latest_observed_at
        FROM weather_observations
        GROUP BY location
    ) AS latest
        ON latest.location = weather.location
        AND latest.latest_observed_at = weather.observed_at
    WHERE weather.location IN :allowed_locations
        AND (
            :location IS NULL
            OR weather.location = :location
        )
    ORDER BY weather.location
    """
).bindparams(
    bindparam("allowed_locations", expanding=True)
)


class WeatherRepository:
    def __init__(self, engine: Engine | None = None) -> None:
        # MCP Service는 읽기 전용 mcp_user 계정만 사용한다.
        self.engine = engine or create_db_engine("mcp")

    @staticmethod
    def _validate_location(location: str | None) -> str | None:
        if location is None:
            return None

        normalized = location.strip()
        if normalized not in ALLOWED_LOCATIONS:
            allowed = ", ".join(sorted(ALLOWED_LOCATIONS))
            raise ValueError(
                f"허용되지 않은 지역입니다: {location}. "
                f"허용 지역: {allowed}"
            )

        return normalized

    @staticmethod
    def _validate_risk_level(
        risk_level: str | None,
    ) -> str | None:
        if risk_level is None:
            return None

        normalized = risk_level.strip().upper()
        if normalized not in ALLOWED_RISK_LEVELS:
            allowed = ", ".join(sorted(ALLOWED_RISK_LEVELS))
            raise ValueError(
                f"허용되지 않은 위험등급입니다: {risk_level}. "
                f"허용 등급: {allowed}"
            )

        return normalized

    @staticmethod
    def _parse_datetime(
        value: datetime | date | str,
        field_name: str,
        *,
        end_of_day: bool = False,
    ) -> datetime:
        if isinstance(value, datetime):
            return value

        if isinstance(value, date):
            return datetime.combine(
                value,
                time.max if end_of_day else time.min,
            )

        if not isinstance(value, str):
            raise TypeError(
                f"{field_name}은 datetime, date 또는 "
                "ISO 8601 문자열이어야 합니다."
            )

        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{field_name}이 비어 있습니다.")

        # 날짜만 입력된 경우 종료일은 그날의 마지막 시각으로 처리한다.
        try:
            parsed_date = date.fromisoformat(normalized)
        except ValueError:
            parsed_date = None

        if (
            parsed_date is not None
            and parsed_date.isoformat() == normalized
        ):
            return datetime.combine(
                parsed_date,
                time.max if end_of_day else time.min,
            )

        try:
            return datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError(
                f"{field_name}이 ISO 8601 형식이 아닙니다."
            ) from exc

    @staticmethod
    def _validate_period(
        start_at: datetime | date | str,
        end_at: datetime | date | str,
    ) -> tuple[datetime, datetime]:
        start = WeatherRepository._parse_datetime(
            start_at,
            "start_at",
        )
        end = WeatherRepository._parse_datetime(
            end_at,
            "end_at",
            end_of_day=True,
        )

        if start > end:
            raise ValueError(
                "start_at은 end_at보다 늦을 수 없습니다."
            )

        return start, end

    @staticmethod
    def _validate_limit(limit: int) -> int:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("limit은 정수여야 합니다.")

        if not 1 <= limit <= 500:
            raise ValueError("limit은 1 이상 500 이하여야 합니다.")

        return limit

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()

        if isinstance(value, Decimal):
            return float(value)

        return value

    @classmethod
    def _serialize_row(cls, row: dict[str, Any]) -> dict[str, Any]:
        serialized = {
            key: cls._serialize_value(value)
            for key, value in row.items()
        }

        reasons = serialized.get("risk_reasons")
        if isinstance(reasons, str):
            try:
                serialized["risk_reasons"] = json.loads(reasons)
            except json.JSONDecodeError:
                serialized["risk_reasons"] = [reasons]

        return serialized

    def get_latest_weather(
        self,
        location: str | None = None,
    ) -> list[dict[str, Any]]:
        normalized_location = self._validate_location(location)

        with self.engine.connect() as connection:
            rows = connection.execute(
                LATEST_WEATHER_QUERY,
                {
                    "location": normalized_location,
                    "allowed_locations": sorted(ALLOWED_LOCATIONS),
                },
            ).mappings().all()

        return [
            self._serialize_row(dict(row))
            for row in rows
        ]

    def search_weather(
        self,
        start_at: datetime | date | str,
        end_at: datetime | date | str,
        *,
        location: str | None = None,
        risk_level: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        start, end = self._validate_period(start_at, end_at)
        normalized_location = self._validate_location(location)
        normalized_level = self._validate_risk_level(risk_level)
        validated_limit = self._validate_limit(limit)

        clauses = [
            "observed_at >= :start_at",
            "observed_at <= :end_at",
        ]
        parameters: dict[str, Any] = {
            "start_at": start,
            "end_at": end,
            "limit": validated_limit,
        }

        if normalized_location is not None:
            clauses.append("location = :location")
            parameters["location"] = normalized_location

        if normalized_level is not None:
            clauses.append("risk_level = :risk_level")
            parameters["risk_level"] = normalized_level

        query = text(
            f"""
            SELECT
                location,
                latitude,
                longitude,
                observed_at,
                temperature,
                apparent_temperature,
                relative_humidity,
                precipitation,
                wind_speed,
                weather_code,
                risk_score,
                risk_level,
                risk_reasons,
                collected_at
            FROM weather_observations
            WHERE {" AND ".join(clauses)}
            ORDER BY observed_at DESC, location
            LIMIT :limit
            """
        )

        with self.engine.connect() as connection:
            rows = connection.execute(
                query,
                parameters,
            ).mappings().all()

        return [
            self._serialize_row(dict(row))
            for row in rows
        ]

    def get_risk_summary(
        self,
        start_at: datetime | date | str,
        end_at: datetime | date | str,
        *,
        location: str | None = None,
    ) -> list[dict[str, Any]]:
        start, end = self._validate_period(start_at, end_at)
        normalized_location = self._validate_location(location)

        clauses = [
            "observed_at >= :start_at",
            "observed_at <= :end_at",
        ]
        parameters: dict[str, Any] = {
            "start_at": start,
            "end_at": end,
        }

        if normalized_location is not None:
            clauses.append("location = :location")
            parameters["location"] = normalized_location

        query = text(
            f"""
            SELECT
                risk_level,
                COUNT(*) AS observation_count,
                ROUND(AVG(risk_score), 2) AS average_risk_score,
                MAX(risk_score) AS maximum_risk_score
            FROM weather_observations
            WHERE {" AND ".join(clauses)}
            GROUP BY risk_level
            ORDER BY FIELD(
                risk_level,
                'CRITICAL',
                'HIGH',
                'MEDIUM',
                'LOW'
            )
            """
        )

        with self.engine.connect() as connection:
            rows = connection.execute(
                query,
                parameters,
            ).mappings().all()

        return [
            self._serialize_row(dict(row))
            for row in rows
        ]
