"""Format sport settings for MCP responses and Intervals.icu API write payloads."""

from typing import Any

from .models import SportSettings


def _format_zones(
    limits: list[int],
    names: list[str] | None = None,
    *,
    min_value: int = 0,
    min_key: str,
    max_key: str,
) -> list[dict[str, Any]]:
    """Convert Intervals.icu upper zone limits into explicit zone ranges."""
    zones: list[dict[str, Any]] = []
    current_min = min_value

    for index, max_value in enumerate(limits, start=1):
        zone: dict[str, Any] = {
            "zone": f"Z{index}",
            min_key: current_min,
            max_key: max_value,
        }

        if names and index <= len(names):
            zone["name"] = names[index - 1]

        zones.append(zone)
        current_min = max_value + 1

    return zones


def format_sport_settings_entry(
    settings: SportSettings,
    *,
    include_id: bool = True,
) -> dict[str, Any]:
    """Build an LLM-facing sport settings dict with consistent unit suffixes."""
    sport_info: dict[str, Any] = {}

    if include_id:
        sport_info["id"] = settings.id

    if settings.type is not None:
        sport_info["type"] = settings.type

    # Default workout timings
    if settings.warmup_time is not None:
        sport_info["warmup_seconds"] = settings.warmup_time

    if settings.cooldown_time is not None:
        sport_info["cooldown_seconds"] = settings.cooldown_time

    # Power
    if settings.ftp is not None:
        sport_info["ftp_watts"] = settings.ftp

    if settings.indoor_ftp is not None:
        sport_info["indoor_ftp_watts"] = settings.indoor_ftp

    if settings.power_zones is not None:
        sport_info["power_zones_percent_ftp"] = _format_zones(
            settings.power_zones,
            settings.power_zone_names,
            min_value=0,
            min_key="min_percent_ftp",
            max_key="max_percent_ftp",
        )

    if settings.sweet_spot_min is not None:
        sport_info["sweet_spot_min_percent_ftp"] = settings.sweet_spot_min

    if settings.sweet_spot_max is not None:
        sport_info["sweet_spot_max_percent_ftp"] = settings.sweet_spot_max

    # Heart rate
    if settings.fthr is not None:
        sport_info["fthr_bpm"] = settings.fthr

    if settings.max_hr is not None:
        sport_info["max_hr_bpm"] = settings.max_hr

    if settings.hr_zones is not None:
        sport_info["hr_zones"] = _format_zones(
            settings.hr_zones,
            settings.hr_zone_names,
            min_value=0,
            min_key="min_bpm",
            max_key="max_bpm",
        )

    if settings.hr_load_type is not None:
        sport_info["hr_load_type"] = settings.hr_load_type

    if settings.hrrc_min_percent is not None:
        sport_info["hrrc_min_percent"] = settings.hrrc_min_percent

    # Running pace
    if settings.pace_threshold is not None:
        total = round(settings.pace_threshold * 60)
        sport_info["pace_threshold"] = (
            f"{total // 60}:{total % 60:02d} /km"
        )

    # Swimming pace
    if settings.swim_threshold is not None:
        # round, not truncate — the m/s <-> min/100m conversion
        # adds tiny floating-point error
        total = round(settings.swim_threshold * 60)
        sport_info["swim_threshold"] = (
            f"{total // 60}:{total % 60:02d} /100m"
        )

    return sport_info


def build_sport_settings_api_payload(
    *,
    sport_type: str | None = None,
    ftp: int | None = None,
    indoor_ftp: int | None = None,
    fthr: int | None = None,
    pace_threshold: float | None = None,
    swim_threshold: float | None = None,
) -> dict[str, Any]:
    """Convert MCP tool parameters to Intervals.icu SportSettings JSON field names."""
    if pace_threshold is not None and swim_threshold is not None:
        raise ValueError(
            "Cannot set pace_threshold and swim_threshold in the same call; "
            "the API stores one pace threshold per sport settings record. "
            "Use separate calls for Run and Swim settings."
        )

    payload: dict[str, Any] = {}

    if sport_type is not None:
        payload["types"] = [sport_type]

    if ftp is not None:
        payload["ftp"] = ftp

    if indoor_ftp is not None:
        payload["indoor_ftp"] = indoor_ftp

    if fthr is not None:
        payload["lthr"] = fthr

    if pace_threshold is not None:
        payload["threshold_pace"] = pace_threshold
        payload["pace_units"] = "MINS_KM"
        payload["pace_load_type"] = "RUN"

    if swim_threshold is not None:
        # Intervals.icu stores swim threshold as SPEED in m/s.
        # Convert min/100m -> m/s:
        # 100 m / (minutes * 60 seconds)
        payload["threshold_pace"] = (
            100.0 / (swim_threshold * 60)
            if swim_threshold
            else 0.0
        )
        payload["pace_units"] = "SECS_100M"
        payload["pace_load_type"] = "SWIM"

    return payload