from unittest.mock import Mock

import pytest
import requests

from collector.open_meteo_client import LOCATIONS, OpenMeteoClient


def make_payload() -> dict:
    return {
        "current": {
            "time": "2026-08-10T17:00",
            "temperature_2m": 28.1,
            "apparent_temperature": 30.2,
            "relative_humidity_2m": 71,
            "precipitation": 0.0,
            "wind_speed_10m": 2.4,
            "weather_code": 1,
        }
    }


def make_client(payload: dict | None = None) -> tuple[OpenMeteoClient, Mock]:
    response = Mock()
    response.json.return_value = payload or make_payload()
    response.raise_for_status.return_value = None

    session = Mock()
    session.get.return_value = response
    return OpenMeteoClient(session=session), session


def test_fetch_location_returns_normalized_weather() -> None:
    client, session = make_client()
    result = client.fetch_location("신촌")

    assert result["location"] == "신촌"
    assert result["temperature"] == 28.1
    assert result["relative_humidity"] == 71
    assert result["observed_at"] == "2026-08-10T17:00"

    _, kwargs = session.get.call_args
    assert kwargs["timeout"] == client.timeout
    assert kwargs["params"]["timezone"] == "Asia/Seoul"


def test_fetch_all_requests_five_locations() -> None:
    client, session = make_client()
    results = client.fetch_all()

    assert len(results) == len(LOCATIONS) == 5
    assert session.get.call_count == 5


def test_fetch_location_rejects_unknown_location() -> None:
    client = OpenMeteoClient(session=Mock())

    with pytest.raises(ValueError, match="지원하지 않는 지역"):
        client.fetch_location("부산")


def test_fetch_location_rejects_missing_fields() -> None:
    client, _ = make_client({"current": {"time": "2026-08-10T17:00"}})

    with pytest.raises(ValueError, match="응답 필드 누락"):
        client.fetch_location("신촌")


def test_fetch_location_rejects_out_of_range_humidity() -> None:
    payload = make_payload()
    payload["current"]["relative_humidity_2m"] = 150
    client, _ = make_client(payload)

    with pytest.raises(ValueError, match="허용 범위를"):
        client.fetch_location("신촌")


def test_fetch_location_rejects_invalid_json() -> None:
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.side_effect = ValueError("invalid json")

    session = Mock()
    session.get.return_value = response
    client = OpenMeteoClient(session=session)

    with pytest.raises(ValueError, match="올바른 JSON"):
        client.fetch_location("신촌")


def test_fetch_location_propagates_http_error() -> None:
    response = Mock()
    response.raise_for_status.side_effect = requests.HTTPError("503")
    session = Mock()
    session.get.return_value = response
    client = OpenMeteoClient(session=session)

    with pytest.raises(requests.HTTPError):
        client.fetch_location("신촌")


def test_retry_policy_is_configured() -> None:
    client = OpenMeteoClient()
    retry = client.session.get_adapter("https://").max_retries

    assert retry.total == client.max_retries == 3
    assert retry.connect == 3
    assert retry.read == 3
    assert retry.status == 3
    assert retry.backoff_factor == 0.5
    assert {429, 500, 502, 503, 504} <= set(retry.status_forcelist)
    assert "GET" in retry.allowed_methods


def test_rejects_invalid_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEATHER_REQUEST_TIMEOUT_SECONDS", "0")

    with pytest.raises(ValueError, match="타임아웃"):
        OpenMeteoClient()
