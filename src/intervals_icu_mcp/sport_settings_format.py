"""Format sport settings for MCP responses and Intervals.icu API write payloads."""

from typing import Any

from .models import SportSettings


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
    if settings.ftp is not None:
        sport_info["ftp_watts"] = settings.ftp
    if settings.indoor_ftp is not None:
        sport_info["indoor_ftp_watts"] = settings.indoor_ftp
    if settings.fthr is not None:
        sport_info["fthr_bpm"] = settings.fthr
    if settings.pace_threshold is not None:
        pace_secs = settings.pace_threshold * 60
        minutes = int(pace_secs // 60)
        seconds = int(pace_secs % 60)
        sport_info["pace_threshold"] = f"{minutes}:{seconds:02d} /km"
    if settings.swim_threshold is not None:
        swim_secs = settings.swim_threshold * 60
        minutes = int(swim_secs // 60)
        seconds = int(swim_secs % 60)
        sport_info["swim_threshold"] = f"{minutes}:{seconds:02d} /100m"
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
        payload["threshold_pace"] = swim_threshold * 60
        payload["pace_units"] = "SECS_100M"
        payload["pace_load_type"] = "SWIM"
    return payload
