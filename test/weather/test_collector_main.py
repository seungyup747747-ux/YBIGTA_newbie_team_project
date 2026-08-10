from __future__ import annotations

from datetime import datetime
from unittest.mock import Mock

import pytest

from collector.main import main, run_collection
from collector.open_meteo_client import LOCATIONS


def make_record(location: str) -> dict:
    return {
        "location": location,
        "latitude": 37.5598,
        "longitude": 126.9423,
        "observed_at": "2026-08-10T22:00:00",
        "temperature": 28.0,
        "apparent_temperature": 31.0,
        "relative_humidity": 85,
        "precipitation": 0.0,
        "wind_speed": 2.0,
        "weather_code": 1,
    }


def test_run_collection_enriches_and_saves_all_locations() -> None:
    records = [
        make_record(location)
        for location in LOCATIONS
    ]
    client = Mock()
    client.fetch_all.return_value = records

    repository = Mock()
    repository.upsert_many.return_value = len(records)

    saved_count = run_collection(client, repository)

    assert saved_count == len(LOCATIONS)
    client.fetch_all.assert_called_once_with()
    repository.upsert_many.assert_called_once()

    saved_records = repository.upsert_many.call_args.args[0]
    assert len(saved_records) == len(LOCATIONS)

    for record in saved_records:
        assert isinstance(record["observed_at"], datetime)
        assert "risk_score" in record
        assert "risk_level" in record
        assert "risk_reasons" in record


def test_collection_failure_prevents_database_write() -> None:
    client = Mock()
    client.fetch_all.side_effect = RuntimeError("외부 API 오류")
    repository = Mock()

    with pytest.raises(RuntimeError, match="외부 API 오류"):
        run_collection(client, repository)

    repository.upsert_many.assert_not_called()


def test_partial_collection_prevents_database_write() -> None:
    client = Mock()
    client.fetch_all.return_value = [
        make_record(location)
        for location in list(LOCATIONS)[:-1]
    ]
    repository = Mock()

    with pytest.raises(RuntimeError, match="수집 건수"):
        run_collection(client, repository)

    repository.upsert_many.assert_not_called()


def test_preprocessing_failure_prevents_database_write() -> None:
    records = [
        make_record(location)
        for location in LOCATIONS
    ]
    records[-1].pop("weather_code")

    client = Mock()
    client.fetch_all.return_value = records
    repository = Mock()

    with pytest.raises(ValueError, match="전처리 필드 누락"):
        run_collection(client, repository)

    repository.upsert_many.assert_not_called()


def test_save_count_mismatch_is_rejected() -> None:
    records = [
        make_record(location)
        for location in LOCATIONS
    ]
    client = Mock()
    client.fetch_all.return_value = records

    repository = Mock()
    repository.upsert_many.return_value = len(records) - 1

    with pytest.raises(RuntimeError, match="DB 저장 건수"):
        run_collection(client, repository)


def test_main_returns_zero_on_success(monkeypatch) -> None:
    run_mock = Mock(return_value=len(LOCATIONS))
    monkeypatch.setattr("collector.main.run_collection", run_mock)

    assert main() == 0
    run_mock.assert_called_once_with()


def test_main_returns_one_on_failure(monkeypatch) -> None:
    run_mock = Mock(side_effect=RuntimeError("수집 실패"))
    monkeypatch.setattr("collector.main.run_collection", run_mock)

    assert main() == 1
    run_mock.assert_called_once_with()
