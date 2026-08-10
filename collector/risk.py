from __future__ import annotations

from datetime import datetime
from typing import Any

RISK_LEVELS = (
    (80, "CRITICAL"),
    (60, "HIGH"),
    (30, "MEDIUM"),
    (0, "LOW"),
)


def _precipitation_risk(precipitation: float) -> tuple[int, str | None]:
    if precipitation >= 30:
        return 100, "시간당 강수량이 30mm 이상입니다."
    if precipitation >= 15:
        return 85, "시간당 강수량이 15mm 이상입니다."
    if precipitation >= 5:
        return 65, "시간당 강수량이 5mm 이상입니다."
    if precipitation >= 1:
        return 35, "비가 내리고 있습니다."
    return 0, None


def _wind_risk(wind_speed: float) -> tuple[int, str | None]:
    if wind_speed >= 21:
        return 100, "풍속이 21m/s 이상입니다."
    if wind_speed >= 14:
        return 80, "풍속이 14m/s 이상입니다."
    if wind_speed >= 9:
        return 55, "풍속이 9m/s 이상입니다."
    if wind_speed >= 5:
        return 25, "바람이 다소 강합니다."
    return 0, None


def _temperature_risk(
    apparent_temperature: float,
) -> tuple[int, str | None]:
    if apparent_temperature >= 40:
        return 100, "체감온도가 40°C 이상입니다."
    if apparent_temperature >= 35:
        return 80, "체감온도가 35°C 이상입니다."
    if apparent_temperature >= 33:
        return 65, "체감온도가 33°C 이상입니다."
    if apparent_temperature >= 30:
        return 40, "체감온도가 30°C 이상입니다."

    if apparent_temperature <= -15:
        return 100, "체감온도가 -15°C 이하입니다."
    if apparent_temperature <= -10:
        return 80, "체감온도가 -10°C 이하입니다."
    if apparent_temperature <= -5:
        return 55, "체감온도가 -5°C 이하입니다."
    if apparent_temperature <= 0:
        return 30, "체감온도가 0°C 이하입니다."

    return 0, None


def _weather_code_risk(weather_code: int) -> tuple[int, str | None]:
    if weather_code in {95, 96, 99}:
        return 100, "뇌우가 관측되었습니다."
    if weather_code == 82:
        return 90, "매우 강한 소나기가 관측되었습니다."
    if weather_code in {65, 67, 86}:
        return 80, "강한 비 또는 눈이 관측되었습니다."
    if weather_code in {81, 85}:
        return 65, "강한 소나기 또는 눈이 관측되었습니다."
    if weather_code in {63, 66}:
        return 60, "비 또는 어는 비가 관측되었습니다."
    if weather_code in {80, 61}:
        return 40, "약한 비 또는 소나기가 관측되었습니다."
    if weather_code in {51, 53, 55, 56, 57, 71, 73, 75, 77}:
        return 30, "이슬비 또는 눈이 관측되었습니다."
    if weather_code in {45, 48}:
        return 25, "안개로 시야가 제한될 수 있습니다."
    return 0, None


def _risk_level(score: int) -> str:
    for minimum, level in RISK_LEVELS:
        if score >= minimum:
            return level
    raise RuntimeError("위험 등급을 결정할 수 없습니다.")


def calculate_weather_risk(
    *,
    apparent_temperature: float,
    relative_humidity: int,
    precipitation: float,
    wind_speed: float,
    weather_code: int,
) -> dict[str, Any]:
    components = [
        _precipitation_risk(precipitation),
        _wind_risk(wind_speed),
        _temperature_risk(apparent_temperature),
        _weather_code_risk(weather_code),
    ]

    score = max(component_score for component_score, _ in components)
    reasons = [
        reason
        for component_score, reason in components
        if reason is not None and component_score > 0
    ]

    if apparent_temperature >= 30 and relative_humidity >= 80:
        score = min(100, score + 10)
        reasons.append("높은 기온과 습도로 온열 위험이 증가합니다.")

    return {
        "risk_score": score,
        "risk_level": _risk_level(score),
        "risk_reasons": reasons,
    }


def enrich_weather_record(record: dict[str, Any]) -> dict[str, Any]:
    required = {
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
    }
    missing = sorted(required - record.keys())

    if missing:
        raise ValueError("전처리 필드 누락: " + ", ".join(missing))

    try:
        observed_at = datetime.fromisoformat(str(record["observed_at"]))
    except ValueError as exc:
        raise ValueError("observed_at이 ISO 8601 형식이 아닙니다.") from exc

    risk = calculate_weather_risk(
        apparent_temperature=float(record["apparent_temperature"]),
        relative_humidity=int(record["relative_humidity"]),
        precipitation=float(record["precipitation"]),
        wind_speed=float(record["wind_speed"]),
        weather_code=int(record["weather_code"]),
    )

    return {
        **record,
        "observed_at": observed_at,
        "risk_score": risk["risk_score"],
        "risk_level": risk["risk_level"],
        "risk_reasons": risk["risk_reasons"],
    }
