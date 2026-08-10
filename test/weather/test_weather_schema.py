from pathlib import Path

SCHEMA_PATH = Path("database/weather_schema.sql")


def normalized_schema() -> str:
    return " ".join(SCHEMA_PATH.read_text(encoding="utf-8").split()).lower()


def test_schema_file_exists_and_is_not_empty() -> None:
    assert SCHEMA_PATH.exists()
    assert SCHEMA_PATH.stat().st_size > 0


def test_schema_creates_database_and_table() -> None:
    schema = normalized_schema()

    assert "create database if not exists weather_db" in schema
    assert "create table if not exists weather_observations" in schema
    assert "engine=innodb" in schema


def test_schema_contains_required_weather_columns() -> None:
    schema = normalized_schema()

    required_columns = {
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
        "collected_at",
    }

    for column in required_columns:
        assert column in schema


def test_schema_prevents_duplicate_observations() -> None:
    schema = normalized_schema()

    assert "unique (location, observed_at)" in schema


def test_schema_contains_range_constraints() -> None:
    schema = normalized_schema()

    assert "relative_humidity between 0 and 100" in schema
    assert "precipitation >= 0" in schema
    assert "wind_speed >= 0" in schema
    assert "weather_code between 0 and 99" in schema
    assert "risk_score between 0 and 100" in schema


def test_schema_contains_query_indexes() -> None:
    schema = normalized_schema()

    assert "idx_weather_observed_at" in schema
    assert "idx_weather_location_time" in schema
    assert "idx_weather_risk_time" in schema
