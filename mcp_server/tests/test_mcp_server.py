from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

import mcp_server.server as server


@pytest.fixture
def service(monkeypatch) -> MagicMock:
    mocked_service = MagicMock()
    monkeypatch.setattr(
        server,
        "_get_service",
        MagicMock(return_value=mocked_service),
    )
    return mocked_service


def test_three_weather_tools_are_registered() -> None:
    tools = asyncio.run(server.mcp.list_tools())
    names = {tool.name for tool in tools}

    assert names == {
        "get_latest_weather",
        "search_weather",
        "get_weather_risk_summary",
    }


def test_latest_weather_tool_returns_count(
    service: MagicMock,
) -> None:
    service.get_latest_weather.return_value = [
        {
            "location": "신촌",
            "temperature": 26.5,
            "risk_level": "MEDIUM",
        }
    ]

    result = server.get_latest_weather("신촌")

    service.get_latest_weather.assert_called_once_with("신촌")
    assert result["count"] == 1
    assert result["location"] == "신촌"
    assert result["observations"][0]["risk_level"] == "MEDIUM"


def test_latest_weather_tool_accepts_no_location(
    service: MagicMock,
) -> None:
    service.get_latest_weather.return_value = []

    result = server.get_latest_weather()

    service.get_latest_weather.assert_called_once_with(None)
    assert result["count"] == 0


def test_search_weather_tool_passes_filters(
    service: MagicMock,
) -> None:
    service.search_weather.return_value = [
        {
            "location": "강남",
            "risk_level": "MEDIUM",
        }
    ]

    result = server.search_weather(
        "2026-08-10",
        "2026-08-10",
        location="강남",
        risk_level="MEDIUM",
        limit=25,
    )

    service.search_weather.assert_called_once_with(
        "2026-08-10",
        "2026-08-10",
        location="강남",
        risk_level="MEDIUM",
        limit=25,
    )
    assert result["count"] == 1
    assert result["filters"]["limit"] == 25


def test_risk_summary_tool_returns_summary(
    service: MagicMock,
) -> None:
    service.get_risk_summary.return_value = [
        {
            "risk_level": "MEDIUM",
            "observation_count": 4,
            "average_risk_score": 42.5,
            "maximum_risk_score": 50,
        }
    ]

    result = server.get_weather_risk_summary(
        "2026-08-10",
        "2026-08-10",
        location="신촌",
    )

    service.get_risk_summary.assert_called_once_with(
        "2026-08-10",
        "2026-08-10",
        location="신촌",
    )
    assert result["summary"][0]["observation_count"] == 4


def test_service_validation_error_is_propagated(
    service: MagicMock,
) -> None:
    service.get_latest_weather.side_effect = ValueError(
        "허용되지 않은 지역입니다."
    )

    with pytest.raises(ValueError, match="허용되지 않은 지역"):
        server.get_latest_weather("신촌' OR 1=1 --")
