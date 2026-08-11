from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mcp_server.repositories.weather_repository import WeatherRepository


def test_query_period_longer_than_31_days_is_rejected() -> None:
    engine = MagicMock()
    repository = WeatherRepository(engine)

    with pytest.raises(ValueError, match="31일"):
        repository.search_weather(
            "2026-01-01",
            "2026-02-02",
        )

    engine.connect.assert_not_called()


def test_summary_period_longer_than_31_days_is_rejected() -> None:
    engine = MagicMock()
    repository = WeatherRepository(engine)

    with pytest.raises(ValueError, match="31일"):
        repository.get_risk_summary(
            "2026-01-01",
            "2026-02-02",
        )

    engine.connect.assert_not_called()
