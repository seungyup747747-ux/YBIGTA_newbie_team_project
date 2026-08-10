from datetime import datetime

import pytest

from collector.risk import calculate_weather_risk, enrich_weather_record


def make_record(**overrides: object) -> dict:
    record = {
        "location": "신촌",
        "latitude": 37.5598,
        "longitude": 126.9423,
        "observed_at": "2026-08-10T17:00",
        "temperature": 27.0,
        "apparent_temperature": 28.0,
        "relative_humidity": 70,
        "precipitation": 0.0,
        "wind_speed": 2.0,
        "weather_code": 1,
    }
    record.update(overrides)
    return record


def test_normal_weather_is_low_risk() -> None:
    result = calculate_weather_risk(
        apparent_temperature=25.0,
        relative_humidity=60,
        precipitation=0.0,
        wind_speed=2.0,
        weather_code=1,
    )

    assert result["risk_score"] == 0
    assert result["risk_level"] == "LOW"
    assert result["risk_reasons"] == []


def test_heavy_rain_is_critical() -> None:
    result = calculate_weather_risk(
        apparent_temperature=24.0,
        relative_humidity=90,
        precipitation=35.0,
        wind_speed=4.0,
        weather_code=65,
    )

    assert result["risk_score"] == 100
    assert result["risk_level"] == "CRITICAL"
    assert any("30mm" in reason for reason in result["risk_reasons"])


def test_strong_wind_is_high_risk() -> None:
    result = calculate_weather_risk(
        apparent_temperature=20.0,
        relative_humidity=50,
        precipitation=0.0,
        wind_speed=15.0,
        weather_code=2,
    )

    assert result["risk_score"] == 80
    assert result["risk_level"] == "CRITICAL"


def test_hot_and_humid_weather_adds_penalty() -> None:
    result = calculate_weather_risk(
        apparent_temperature=33.5,
        relative_humidity=85,
        precipitation=0.0,
        wind_speed=2.0,
        weather_code=1,
    )

    assert result["risk_score"] == 75
    assert result["risk_level"] == "HIGH"
    assert any("습도" in reason for reason in result["risk_reasons"])


def test_thunderstorm_is_critical() -> None:
    result = calculate_weather_risk(
        apparent_temperature=25.0,
        relative_humidity=75,
        precipitation=2.0,
        wind_speed=5.0,
        weather_code=95,
    )

    assert result["risk_score"] == 100
    assert result["risk_level"] == "CRITICAL"
    assert any("뇌우" in reason for reason in result["risk_reasons"])


def test_enrich_weather_record_prepares_database_data() -> None:
    result = enrich_weather_record(make_record(precipitation=6.0))

    assert isinstance(result["observed_at"], datetime)
    assert result["risk_score"] == 65
    assert result["risk_level"] == "HIGH"
    assert result["location"] == "신촌"


def test_enrich_weather_record_rejects_missing_field() -> None:
    record = make_record()
    del record["wind_speed"]

    with pytest.raises(ValueError, match="전처리 필드 누락: wind_speed"):
        enrich_weather_record(record)


def test_enrich_weather_record_rejects_invalid_time() -> None:
    with pytest.raises(ValueError, match="ISO 8601"):
        enrich_weather_record(make_record(observed_at="not-a-date"))
