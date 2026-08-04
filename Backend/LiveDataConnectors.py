"""Small, read-only connectors for Nexa's live planning tools."""

from __future__ import annotations

import datetime as dt
import math
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

import requests

try:
    from holidays import country_holidays
except ImportError:  # pragma: no cover - deployment dependency guard
    country_holidays = None

from Backend.LLMProvider import get_config
from Backend.MapsConnector import MapsConnectorError, geoapify_configured, reverse_geocode


class LiveDataError(RuntimeError):
    """A safe, user-actionable live-data error."""


OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
NAGER_HOLIDAYS_URL = "https://nagerholidays.com/api/v4/Holidays"
FRANKFURTER_RATE_URL = "https://api.frankfurter.dev/v2/rate"
REQUEST_TIMEOUT_SECONDS = 20

_WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def _coordinates(latitude: float, longitude: float) -> tuple[float, float]:
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError) as exc:
        raise LiveDataError("Valid latitude and longitude are required.") from exc
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise LiveDataError("The supplied coordinates are outside the valid latitude/longitude range.")
    return lat, lon


def _request_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any] | list[Any]:
    try:
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise LiveDataError("The live data provider could not be reached. Check the internet connection and try again.") from exc
    if response.status_code == 429:
        raise LiveDataError("The live data provider is rate-limiting requests. Please try again shortly.")
    if response.status_code == 204:
        return []
    if not response.ok:
        detail = ""
        try:
            payload = response.json()
            if isinstance(payload, dict):
                detail = str(payload.get("reason") or payload.get("message") or "")
        except ValueError:
            pass
        suffix = f": {detail}" if detail else ""
        raise LiveDataError(f"The live data provider returned an error ({response.status_code}){suffix}")
    try:
        return response.json()
    except ValueError as exc:
        raise LiveDataError("The live data provider returned an invalid response.") from exc


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _round(value: Any, digits: int = 1) -> float | None:
    number = _number(value)
    return round(number, digits) if number is not None else None


def _aqi_label(us_aqi: float | None) -> str:
    if us_aqi is None:
        return "Unavailable"
    if us_aqi <= 50:
        return "Good"
    if us_aqi <= 100:
        return "Moderate"
    if us_aqi <= 150:
        return "Unhealthy for sensitive groups"
    if us_aqi <= 200:
        return "Unhealthy"
    if us_aqi <= 300:
        return "Very unhealthy"
    return "Hazardous"


def weather_and_air_quality(latitude: float, longitude: float, forecast_date: str = "") -> dict[str, Any]:
    """Return current conditions, AQI, and an optional day's forecast."""
    lat, lon = _coordinates(latitude, longitude)
    requested_date = forecast_date.strip()
    if requested_date:
        try:
            dt.date.fromisoformat(requested_date)
        except ValueError as exc:
            raise LiveDataError("forecast_date must be an ISO date in YYYY-MM-DD format.") from exc

    weather = _request_json(
        OPEN_METEO_FORECAST_URL,
        {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m,is_day",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,uv_index_max",
            "timezone": "auto",
            "forecast_days": 16,
        },
    )
    air = _request_json(
        OPEN_METEO_AIR_QUALITY_URL,
        {
            "latitude": lat,
            "longitude": lon,
            "current": "us_aqi,european_aqi,pm2_5,pm10,ozone,nitrogen_dioxide",
            "timezone": "auto",
        },
    )
    if not isinstance(weather, dict) or not isinstance(air, dict):
        raise LiveDataError("The weather provider returned an unexpected response.")

    current = weather.get("current") if isinstance(weather.get("current"), dict) else {}
    current_air = air.get("current") if isinstance(air.get("current"), dict) else {}
    daily = weather.get("daily") if isinstance(weather.get("daily"), dict) else {}
    dates = daily.get("time") if isinstance(daily.get("time"), list) else []
    selected_date = requested_date or (dates[0] if dates else "")
    forecast: dict[str, Any] | None = None
    if selected_date and selected_date in dates:
        index = dates.index(selected_date)
        forecast = {
            "date": selected_date,
            "summary": _WEATHER_CODES.get(daily.get("weather_code", [None])[index], "Unknown conditions"),
            "temperature_min_c": _round(daily.get("temperature_2m_min", [None])[index]),
            "temperature_max_c": _round(daily.get("temperature_2m_max", [None])[index]),
            "precipitation_probability_max_percent": _round(daily.get("precipitation_probability_max", [None])[index], 0),
            "precipitation_sum_mm": _round(daily.get("precipitation_sum", [None])[index]),
            "uv_index_max": _round(daily.get("uv_index_max", [None])[index]),
        }
    elif requested_date:
        raise LiveDataError("That date is outside the currently available 16-day forecast.")

    us_aqi = _round(current_air.get("us_aqi"), 0)
    return {
        "ok": True,
        "location": {
            "latitude": lat,
            "longitude": lon,
            "timezone": weather.get("timezone") or air.get("timezone") or "",
        },
        "observed_at": current.get("time") or current_air.get("time") or "",
        "weather": {
            "summary": _WEATHER_CODES.get(current.get("weather_code"), "Unknown conditions"),
            "temperature_c": _round(current.get("temperature_2m")),
            "feels_like_c": _round(current.get("apparent_temperature")),
            "humidity_percent": _round(current.get("relative_humidity_2m"), 0),
            "wind_kmh": _round(current.get("wind_speed_10m")),
            "precipitation_mm": _round(current.get("precipitation")),
            "is_day": bool(current.get("is_day")),
        },
        "air_quality": {
            "us_aqi": us_aqi,
            "us_aqi_label": _aqi_label(us_aqi),
            "european_aqi": _round(current_air.get("european_aqi"), 0),
            "pm2_5_ug_m3": _round(current_air.get("pm2_5")),
            "pm10_ug_m3": _round(current_air.get("pm10")),
            "ozone_ug_m3": _round(current_air.get("ozone")),
            "nitrogen_dioxide_ug_m3": _round(current_air.get("nitrogen_dioxide")),
        },
        "forecast": forecast,
        "sources": ["https://open-meteo.com/", "https://open-meteo.com/en/docs/air-quality-api"],
    }


def _country_code(country_code: str, latitude: float | None, longitude: float | None) -> str:
    supplied = country_code.strip().upper()
    if supplied:
        if len(supplied) != 2 or not supplied.isalpha():
            raise LiveDataError("country_code must be a two-letter ISO country code, such as IN, US, or GB.")
        return supplied
    if latitude is not None and longitude is not None and geoapify_configured():
        try:
            place = reverse_geocode(latitude, longitude)
            inferred = str(place.get("country_code") or "").upper()
            if len(inferred) == 2 and inferred.isalpha():
                return inferred
        except MapsConnectorError:
            pass
    configured = get_config("NEXA_DEFAULT_COUNTRY_CODE").strip().upper()
    if configured:
        return configured
    raise LiveDataError("Please provide the country for the holiday check (for example, IN or US).")


def _holidays_for_year(country_code: str, year: int, subdivision_code: str = "") -> tuple[list[dict[str, Any]], str]:
    if not 1900 <= year <= 2100:
        raise LiveDataError("The holiday year must be between 1900 and 2100.")
    payload = _request_json(f"{NAGER_HOLIDAYS_URL}/{country_code}/{year}")
    if isinstance(payload, list) and payload:
        return [item for item in payload if isinstance(item, dict)], "https://nagerholidays.com/api"
    if country_holidays is None:
        raise LiveDataError(
            f"No public-holiday data is available from the provider for {country_code}."
        )
    try:
        local_calendar = country_holidays(
            country_code,
            years=[year],
            subdiv=subdivision_code or None,
        )
    except (KeyError, NotImplementedError) as exc:
        raise LiveDataError(
            f"No public-holiday data is available for the country code {country_code}."
        ) from exc
    return [
        {
            "date": day.isoformat(),
            "name": name,
            "nationalHoliday": not bool(subdivision_code),
            "subdivisionCodes": [subdivision_code] if subdivision_code else [],
            "holidayTypes": ["Public"],
        }
        for day, name in local_calendar.items()
    ], "local open-source holiday calendar"


def holiday_schedule_check(
    date_text: str,
    country_code: str = "",
    subdivision_code: str = "",
    latitude: float | None = None,
    longitude: float | None = None,
) -> dict[str, Any]:
    """Check whether a day is usable for work and find the next workday."""
    try:
        requested_date = dt.date.fromisoformat(date_text.strip())
    except ValueError as exc:
        raise LiveDataError("date must be an ISO date in YYYY-MM-DD format.") from exc
    resolved_country = _country_code(country_code, latitude, longitude)
    subdivision = subdivision_code.strip().upper()
    cache: dict[int, list[dict[str, Any]]] = {}
    sources: set[str] = set()

    def holidays_for(day: dt.date) -> list[dict[str, Any]]:
        if day.year not in cache:
            records, source = _holidays_for_year(resolved_country, day.year, subdivision)
            cache[day.year] = records
            sources.add(source)
        matches = [item for item in cache[day.year] if str(item.get("date")) == day.isoformat()]
        if subdivision:
            matches = [
                item for item in matches
                if bool(item.get("nationalHoliday")) or subdivision in (item.get("subdivisionCodes") or [])
            ]
        return matches

    requested_holidays = holidays_for(requested_date)
    is_weekend = requested_date.weekday() >= 5
    is_holiday = bool(requested_holidays)
    next_workday = requested_date
    # For a date that is already a working day, schedule on it. Otherwise move forward.
    while next_workday.weekday() >= 5 or holidays_for(next_workday):
        next_workday += dt.timedelta(days=1)

    return {
        "ok": True,
        "country_code": resolved_country,
        "subdivision_code": subdivision or None,
        "date": requested_date.isoformat(),
        "weekday": requested_date.strftime("%A"),
        "is_weekend": is_weekend,
        "is_public_holiday": is_holiday,
        "is_working_day": not is_weekend and not is_holiday,
        "holidays": [
            {
                "name": item.get("name") or item.get("localName") or "Public holiday",
                "type": item.get("holidayTypes") or [],
                "national": bool(item.get("nationalHoliday")),
            }
            for item in requested_holidays
        ],
        "recommended_schedule_date": next_workday.isoformat(),
        "source": ", ".join(sorted(sources)),
    }


def convert_currency(amount: float, from_currency: str, to_currency: str, rate_date: str = "") -> dict[str, Any]:
    """Convert money using the latest or a requested historical reference rate."""
    source = from_currency.strip().upper()
    target = to_currency.strip().upper()
    if len(source) != 3 or not source.isalpha() or len(target) != 3 or not target.isalpha():
        raise LiveDataError("Use three-letter ISO currency codes, such as INR, USD, EUR, or GBP.")
    try:
        decimal_amount = Decimal(str(amount))
    except (InvalidOperation, ValueError) as exc:
        raise LiveDataError("amount must be a valid number.") from exc
    if not decimal_amount.is_finite() or decimal_amount < 0:
        raise LiveDataError("amount must be a non-negative finite number.")
    requested_date = rate_date.strip()
    if requested_date:
        try:
            dt.date.fromisoformat(requested_date)
        except ValueError as exc:
            raise LiveDataError("rate_date must be an ISO date in YYYY-MM-DD format.") from exc
    if source == target:
        return {
            "ok": True,
            "amount": float(decimal_amount),
            "from_currency": source,
            "to_currency": target,
            "rate": 1.0,
            "converted_amount": float(decimal_amount),
            "rate_date": requested_date or dt.date.today().isoformat(),
            "source": "No conversion was needed.",
        }
    params = {"date": requested_date} if requested_date else None
    payload = _request_json(f"{FRANKFURTER_RATE_URL}/{source}/{target}", params)
    if not isinstance(payload, dict):
        raise LiveDataError("The exchange-rate provider returned an unexpected response.")
    rate = _number(payload.get("rate"))
    if rate is None or rate <= 0:
        raise LiveDataError("The exchange-rate provider did not return a usable rate for that currency pair.")
    converted = (decimal_amount * Decimal(str(rate))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {
        "ok": True,
        "amount": float(decimal_amount),
        "from_currency": source,
        "to_currency": target,
        "rate": rate,
        "converted_amount": float(converted),
        "rate_date": payload.get("date") or requested_date or "latest available",
        "source": "https://frankfurter.dev/",
    }
