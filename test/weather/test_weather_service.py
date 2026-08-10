from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from mcp_server.weather_service import WeatherService


def make_service(
    rows: list[dict] | None = None,
) -> tuple[WeatherService, MagicMock, MagicMock]:
    engine = MagicMock()
    connection = (
        engine.connect.return_value
        .__enter__.return_value
    )
    connection.execute.return_value.mappings.return_value.all.return_value = (
        rows or []
    )
    return WeatherService(engine), engine, connection


def test_service_uses_mcp_database_account(monkeypatch) -> None:
    engine = MagicMock()
    create_engine = MagicMock(return_value=engine)
    monkeypatch.setattr(
        "mcp_server.weather_service.create_db_engine",
        create_engine,
    )

    service = WeatherService()

    assert service.engine is engine
    create_engine.assert_called_once_with("mcp")


def test_get_latest_weather_returns_serialized_rows() -> None:
    service, _, connection = make_service(
        [
            {
                "location": "신촌",
                "observed_at": datetime(2026, 8, 10, 22, 0),
                "temperature": Decimal("26.50"),
                "risk_level": "MEDIUM",
                "risk_reasons": '["비가 관측되었습니다."]',
            }
        ]
    )

    result = service.get_latest_weather("신촌")

    assert result == [
        {
            "location": "신촌",
            "observed_at": "2026-08-10T22:00:00",
            "temperature": 26.5,
            "risk_level": "MEDIUM",
            "risk_reasons": ["비가 관측되었습니다."],
        }
    ]

    parameters = connection.execute.call_args.args[1]
    assert parameters["location"] == "신촌"
    assert set(parameters["allowed_locations"]) == {
        "신촌", "강남", "서울역", "여의도", "잠실"
    }


def test_get_latest_weather_allows_all_locations() -> None:
    service, _, connection = make_service()

    assert service.get_latest_weather() == []

    parameters = connection.execute.call_args.args[1]
    assert parameters["location"] is None
    assert set(parameters["allowed_locations"]) == {
        "신촌", "강남", "서울역", "여의도", "잠실"
    }


def test_invalid_location_is_rejected_before_query() -> None:
    service, _, connection = make_service()

    with pytest.raises(ValueError, match="허용되지 않은 지역"):
        service.get_latest_weather("신촌' OR 1=1 --")

    connection.execute.assert_not_called()


def test_search_weather_uses_bound_parameters() -> None:
    service, _, connection = make_service()

    service.search_weather(
        "2026-08-10T00:00:00",
        "2026-08-10T23:59:59",
        location="강남",
        risk_level="high",
        limit=25,
    )

    query, parameters = connection.execute.call_args.args

    assert parameters == {
        "start_at": datetime(2026, 8, 10, 0, 0),
        "end_at": datetime(2026, 8, 10, 23, 59, 59),
        "location": "강남",
        "risk_level": "HIGH",
        "limit": 25,
    }
    assert ":location" in str(query)
    assert ":risk_level" in str(query)
    assert "강남" not in str(query)


def test_date_only_end_value_includes_entire_day() -> None:
    service, _, connection = make_service()

    service.search_weather(
        "2026-08-10",
        "2026-08-10",
    )

    parameters = connection.execute.call_args.args[1]
    assert parameters["start_at"] == datetime(
        2026, 8, 10, 0, 0, 0
    )
    assert parameters["end_at"] == datetime(
        2026, 8, 10, 23, 59, 59, 999999
    )


def test_invalid_risk_level_is_rejected() -> None:
    service, _, connection = make_service()

    with pytest.raises(ValueError, match="허용되지 않은 위험등급"):
        service.search_weather(
            "2026-08-10",
            "2026-08-10",
            risk_level="DANGER",
        )

    connection.execute.assert_not_called()


def test_reversed_period_is_rejected() -> None:
    service, _, connection = make_service()

    with pytest.raises(ValueError, match="늦을 수 없습니다"):
        service.search_weather(
            "2026-08-11",
            "2026-08-10",
        )

    connection.execute.assert_not_called()


@pytest.mark.parametrize("limit", [0, 501])
def test_out_of_range_limit_is_rejected(limit: int) -> None:
    service, _, connection = make_service()

    with pytest.raises(ValueError, match="500"):
        service.search_weather(
            "2026-08-10",
            "2026-08-10",
            limit=limit,
        )

    connection.execute.assert_not_called()


def test_boolean_limit_is_rejected() -> None:
    service, _, connection = make_service()

    with pytest.raises(TypeError, match="정수"):
        service.search_weather(
            "2026-08-10",
            "2026-08-10",
            limit=True,
        )

    connection.execute.assert_not_called()


def test_risk_summary_returns_numeric_values() -> None:
    service, _, connection = make_service(
        [
            {
                "risk_level": "MEDIUM",
                "observation_count": 4,
                "average_risk_score": Decimal("42.50"),
                "maximum_risk_score": 50,
            }
        ]
    )

    result = service.get_risk_summary(
        "2026-08-10",
        "2026-08-10",
        location="신촌",
    )

    assert result == [
        {
            "risk_level": "MEDIUM",
            "observation_count": 4,
            "average_risk_score": 42.5,
            "maximum_risk_score": 50,
        }
    ]

    parameters = connection.execute.call_args.args[1]
    assert parameters["location"] == "신촌"
