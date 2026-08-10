from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, text

from database.mysql_connection import create_db_engine

UPSERT_WEATHER = text(
    """
    INSERT INTO weather_observations (
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
        risk_reasons
    )
    VALUES (
        :location,
        :latitude,
        :longitude,
        :observed_at,
        :temperature,
        :apparent_temperature,
        :relative_humidity,
        :precipitation,
        :wind_speed,
        :weather_code,
        :risk_score,
        :risk_level,
        :risk_reasons
    )
    ON DUPLICATE KEY UPDATE
        latitude = VALUES(latitude),
        longitude = VALUES(longitude),
        temperature = VALUES(temperature),
        apparent_temperature = VALUES(apparent_temperature),
        relative_humidity = VALUES(relative_humidity),
        precipitation = VALUES(precipitation),
        wind_speed = VALUES(wind_speed),
        weather_code = VALUES(weather_code),
        risk_score = VALUES(risk_score),
        risk_level = VALUES(risk_level),
        risk_reasons = VALUES(risk_reasons),
        collected_at = CURRENT_TIMESTAMP
    """
)


class WeatherRepository:
    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or create_db_engine("collector")

    @staticmethod
    def _prepare(record: Mapping[str, Any]) -> dict[str, Any]:
        required = {
            "location",
            "latitude",
            "longitude",
            "observed_at",
            "temperature",
            "apparent_temperature",
            "relative_humidity",
            "precipitation",
            "wind_speed",
            "weather_code",
            "risk_score",
            "risk_level",
            "risk_reasons",
        }
        missing = sorted(required - record.keys())

        if missing:
            raise ValueError("DB 저장 필드 누락: " + ", ".join(missing))

        observed_at = record["observed_at"]
        if isinstance(observed_at, str):
            try:
                observed_at = datetime.fromisoformat(observed_at)
            except ValueError as exc:
                raise ValueError(
                    "observed_at이 ISO 8601 형식이 아닙니다."
                ) from exc

        if not isinstance(observed_at, datetime):
            raise TypeError("observed_at은 datetime 또는 ISO 8601 문자열이어야 합니다.")

        reasons = record["risk_reasons"]
        if not isinstance(reasons, list):
            raise TypeError("risk_reasons는 리스트여야 합니다.")

        return {
            **record,
            "observed_at": observed_at,
            "risk_reasons": json.dumps(
                reasons,
                ensure_ascii=False,
            ),
        }

    def upsert_many(
        self,
        records: Iterable[Mapping[str, Any]],
    ) -> int:
        prepared = [self._prepare(record) for record in records]

        if not prepared:
            return 0

        # engine.begin()은 성공 시 commit, 예외 시 전체 rollback한다.
        with self.engine.begin() as connection:
            connection.execute(UPSERT_WEATHER, prepared)

        return len(prepared)
