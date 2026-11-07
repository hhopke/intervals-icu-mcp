"""Weather block for activity tools.

Intervals.icu attaches Open-Meteo weather to outdoor activities (a supporter
feature) and flags it with ``has_weather``. This is air weather along the route,
not the device's ``average_temp``, which comes from the watch or head unit and
reads high from body heat.
"""

from typing import Any


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def _range(average: float | None, low: float | None, high: float | None) -> dict[str, float]:
    values = {"average": _rounded(average), "min": _rounded(low), "max": _rounded(high)}
    return {k: v for k, v in values.items() if v is not None}


def weather_block(activity: Any) -> dict[str, Any] | None:
    """Build the ``weather`` block for an activity, or None when it has no weather.

    Zero is a real reading here (0 °C, no rain, calm wind), so fields are kept
    unless they are missing.
    """
    if not activity.has_weather:
        return None

    weather: dict[str, Any] = {}

    temperature = _range(
        activity.average_weather_temp, activity.min_weather_temp, activity.max_weather_temp
    )
    if temperature:
        weather["temperature_c"] = temperature
    feels_like = _range(
        activity.average_feels_like, activity.min_feels_like, activity.max_feels_like
    )
    if feels_like:
        weather["feels_like_c"] = feels_like

    wind_values = {
        "average_speed_meters_per_sec": _rounded(activity.average_wind_speed),
        "average_gust_meters_per_sec": _rounded(activity.average_wind_gust),
        "prevailing_direction_deg": activity.prevailing_wind_deg,
        "headwind_percent": _rounded(activity.headwind_percent),
        "tailwind_percent": _rounded(activity.tailwind_percent),
    }
    wind = {k: v for k, v in wind_values.items() if v is not None}
    if wind:
        weather["wind"] = wind

    if activity.average_clouds is not None:
        weather["cloud_cover_percent"] = activity.average_clouds
    if activity.max_rain is not None:
        weather["max_rain"] = _rounded(activity.max_rain)
    if activity.max_snow is not None:
        weather["max_snow"] = _rounded(activity.max_snow)

    return weather or None
