from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from collector.open_meteo_client import LOCATIONS, OpenMeteoClient
from collector.risk import enrich_weather_record
from database.weather_repository import WeatherRepository

LOGGER = logging.getLogger(__name__)


def run_collection(
    client: OpenMeteoClient | None = None,
    repository: WeatherRepository | None = None,
) -> int:
    weather_client = client or OpenMeteoClient()
    weather_repository = repository or WeatherRepository()

    LOGGER.info("날씨 수집을 시작합니다. 대상 지역 수: %d", len(LOCATIONS))

    raw_records: Sequence[dict[str, Any]] = weather_client.fetch_all()

    if len(raw_records) != len(LOCATIONS):
        raise RuntimeError(
            "수집 건수가 대상 지역 수와 일치하지 않습니다: "
            f"expected={len(LOCATIONS)}, actual={len(raw_records)}"
        )

    enriched_records = [
        enrich_weather_record(record)
        for record in raw_records
    ]

    saved_count = weather_repository.upsert_many(enriched_records)

    if saved_count != len(enriched_records):
        raise RuntimeError(
            "DB 저장 건수가 수집 건수와 일치하지 않습니다: "
            f"collected={len(enriched_records)}, saved={saved_count}"
        )

    LOGGER.info(
        "날씨 수집과 저장을 완료했습니다. 저장 건수: %d",
        saved_count,
    )
    return saved_count


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    try:
        run_collection()
    except Exception:
        LOGGER.exception("날씨 수집 작업이 실패했습니다.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
