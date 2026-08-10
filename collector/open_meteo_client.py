from __future__ import annotations

import math
import os
from numbers import Real
from typing import Any

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()

LOCATIONS: dict[str, tuple[float, float]] = {
    "신촌": (37.5598, 126.9423),
    "여의도": (37.5219, 126.9245),
    "강남": (37.4979, 127.0276),
    "잠실": (37.5133, 127.1002),
    "서울역": (37.5547, 126.9707),
}

CURRENT_FIELDS = (
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "precipitation",
    "wind_speed_10m",
    "weather_code",
)

VALUE_RANGES: dict[str, tuple[float, float]] = {
    "temperature_2m": (-100.0, 70.0),
    "apparent_temperature": (-120.0, 90.0),
    "relative_humidity_2m": (0.0, 100.0),
    "precipitation": (0.0, 500.0),
    "wind_speed_10m": (0.0, 150.0),
    "weather_code": (0.0, 99.0),
}


class OpenMeteoClient:
    def __init__(self, session: requests.Session | None = None) -> None:
        self.base_url = os.getenv(
            "OPEN_METEO_BASE_URL",
            "https://api.open-meteo.com/v1/forecast",
        )
        self.timezone = os.getenv("WEATHER_TIMEZONE", "Asia/Seoul")
        self.timeout = float(
            os.getenv("WEATHER_REQUEST_TIMEOUT_SECONDS", "10")
        )
        self.max_retries = int(os.getenv("WEATHER_MAX_RETRIES", "3"))

        if self.timeout <= 0:
            raise ValueError("요청 타임아웃은 0보다 커야 합니다.")
        if self.max_retries < 0:
            raise ValueError("최대 재시도 횟수는 0 이상이어야 합니다.")

        self.session = session if session is not None else self._create_session()

    def _create_session(self) -> requests.Session:
        retry = Retry(
            total=self.max_retries,
            connect=self.max_retries,
            read=self.max_retries,
            status=self.max_retries,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            raise_on_status=False,
        )

        adapter = HTTPAdapter(max_retries=retry)
        session = requests.Session()
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    @staticmethod
    def _validate_current(current: dict[str, Any]) -> None:
        if not isinstance(current.get("time"), str) or not current["time"]:
            raise ValueError("Open-Meteo 응답의 time 값이 올바르지 않습니다.")

        for field, (minimum, maximum) in VALUE_RANGES.items():
            value = current[field]

            if (
                isinstance(value, bool)
                or not isinstance(value, Real)
                or not math.isfinite(float(value))
            ):
                raise ValueError(
                    f"Open-Meteo 응답의 {field} 값이 숫자가 아닙니다."
                )

            if not minimum <= float(value) <= maximum:
                raise ValueError(
                    f"Open-Meteo 응답의 {field} 값이 허용 범위를 벗어났습니다: "
                    f"{value}"
                )

        weather_code = current["weather_code"]
        if float(weather_code) != int(weather_code):
            raise ValueError("weather_code는 정수여야 합니다.")

    def fetch_location(self, location: str) -> dict[str, Any]:
        if location not in LOCATIONS:
            allowed = ", ".join(LOCATIONS)
            raise ValueError(
                f"지원하지 않는 지역입니다: {location}. 허용 지역: {allowed}"
            )

        latitude, longitude = LOCATIONS[location]

        response = self.session.get(
            self.base_url,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": ",".join(CURRENT_FIELDS),
                "timezone": self.timezone,
                "wind_speed_unit": "ms",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()

        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError("Open-Meteo 응답이 올바른 JSON이 아닙니다.") from exc

        if not isinstance(payload, dict):
            raise ValueError("Open-Meteo 응답 형식이 올바르지 않습니다.")

        current = payload.get("current")
        if not isinstance(current, dict):
            raise ValueError("Open-Meteo 응답에 current 데이터가 없습니다.")

        missing = [
            field for field in ("time", *CURRENT_FIELDS)
            if field not in current
        ]
        if missing:
            raise ValueError(
                "Open-Meteo 응답 필드 누락: " + ", ".join(missing)
            )

        self._validate_current(current)

        return {
            "location": location,
            "latitude": latitude,
            "longitude": longitude,
            "observed_at": current["time"],
            "temperature": float(current["temperature_2m"]),
            "apparent_temperature": float(
                current["apparent_temperature"]
            ),
            "relative_humidity": int(current["relative_humidity_2m"]),
            "precipitation": float(current["precipitation"]),
            "wind_speed": float(current["wind_speed_10m"]),
            "weather_code": int(current["weather_code"]),
        }

    def fetch_all(self) -> list[dict[str, Any]]:
        return [
            self.fetch_location(location)
            for location in LOCATIONS
        ]
