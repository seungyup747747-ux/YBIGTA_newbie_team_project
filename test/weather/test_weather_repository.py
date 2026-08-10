from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from database.mysql_connection import create_db_engine
from database.weather_repository import WeatherRepository


def make_record(**overrides: object) -> dict:
    record = {
        "location": f"테스트-{uuid4().hex[:12]}",
        "latitude": 37.5598,
        "longitude": 126.9423,
        "observed_at": datetime(2099, 1, 1, 12, 0),
        "temperature": 25.0,
        "apparent_temperature": 26.0,
        "relative_humidity": 60,
        "precipitation": 0.0,
        "wind_speed": 2.0,
        "weather_code": 1,
        "risk_score": 0,
        "risk_level": "LOW",
        "risk_reasons": [],
    }
    record.update(overrides)
    return record


def count_location(engine, location: str) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM weather_observations
                    WHERE location = :location
                    """
                ),
                {"location": location},
            ).scalar_one()
        )


def test_collector_can_insert_and_update_duplicate() -> None:
    engine = create_db_engine("collector")
    repository = WeatherRepository(engine)
    record = make_record()

    assert repository.upsert_many([record]) == 1
    assert count_location(engine, record["location"]) == 1

    updated = {
        **record,
        "temperature": 31.5,
        "apparent_temperature": 34.0,
        "risk_score": 65,
        "risk_level": "HIGH",
        "risk_reasons": ["체감온도가 높습니다."],
    }
    assert repository.upsert_many([updated]) == 1
    assert count_location(engine, record["location"]) == 1

    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT temperature, risk_score, risk_level
                FROM weather_observations
                WHERE location = :location
                """
            ),
            {"location": record["location"]},
        ).mappings().one()

    assert float(row["temperature"]) == 31.5
    assert row["risk_score"] == 65
    assert row["risk_level"] == "HIGH"

    engine.dispose()


def test_batch_failure_rolls_back_all_records() -> None:
    engine = create_db_engine("collector")
    repository = WeatherRepository(engine)

    valid = make_record()
    invalid = make_record(risk_score=101)

    with pytest.raises(DBAPIError):
        repository.upsert_many([valid, invalid])

    assert count_location(engine, valid["location"]) == 0
    assert count_location(engine, invalid["location"]) == 0

    engine.dispose()


def test_mcp_user_can_read_but_cannot_write() -> None:
    engine = create_db_engine("mcp")

    with engine.connect() as connection:
        connection.execute(
            text("SELECT COUNT(*) FROM weather_observations")
        ).scalar_one()

    repository = WeatherRepository(engine)

    with pytest.raises(DBAPIError):
        repository.upsert_many([make_record()])

    engine.dispose()
