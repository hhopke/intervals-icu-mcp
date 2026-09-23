"""Format sport settings for MCP responses and Intervals.icu API write payloads."""

from collections.abc import Sequence
from typing import Any

from .models import SportSettings

# Intervals.icu caps the top power and pace zone with an open-ended sentinel instead of a
# real upper bound. Rendering it literally would claim a 999% ceiling.
_UNBOUNDED_ZONE_LIMIT = 999


def _format_zones(
    limits: Sequence[float],
    names: Sequence[str],
    *,
    min_key: str,
    max_key: str,
    integral: bool = True,
) -> list[dict[str, Any]]:
    """Convert Intervals.icu upper zone limits into explicit min/max ranges."""
    zones: list[dict[str, Any]] = []
    lower: float = 0

    for index, upper in enumerate(limits, start=1):
        zone: dict[str, Any] = {"zone": f"Z{index}"}
        # The name array can be shorter than the limits array; pair by index.
        if index <= len(names):
            zone["name"] = names[index - 1]

        zone[min_key] = lower
        if upper >= _UNBOUNDED_ZONE_LIMIT:
            zone["unbounded"] = True
        else:
            zone[max_key] = upper

        zones.append(zone)
        # Integer bands (bpm, %FTP) are inclusive, so the next zone starts one above.
        # Float pace bands share the boundary.
        lower = upper + 1 if integral else upper

    return zones


def format_sport_settings_entry(
    settings: SportSettings,
    *,
    include_id: bool = True,
    include_zones: bool = False,
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
        total = round(settings.pace_threshold * 60)
        sport_info["pace_threshold"] = f"{total // 60}:{total % 60:02d} /km"
    if settings.swim_threshold is not None:
        # round, not truncate — the m/s <-> min/100m conversion adds tiny float error
        total = round(settings.swim_threshold * 60)
        sport_info["swim_threshold"] = f"{total // 60}:{total % 60:02d} /100m"
    if include_zones:
        sport_info.update(_format_zone_config(settings))
    return sport_info


def _format_zone_config(settings: SportSettings) -> dict[str, Any]:
    """Build the athlete's configured zone sets plus the scalars that frame them."""
    config: dict[str, Any] = {}

    if settings.max_hr is not None:
        config["max_hr_bpm"] = settings.max_hr
    if settings.hr_zones:
        # HR zones are absolute bpm, not percentages, and the top bound is the real max HR.
        config["hr_zones"] = _format_zones(
            settings.hr_zones,
            settings.hr_zone_names,
            min_key="min_bpm",
            max_key="max_bpm",
        )
    if settings.hr_load_type is not None:
        config["hr_load_type"] = settings.hr_load_type
    if settings.hrrc_min_percent is not None:
        config["hrrc_min_percent"] = settings.hrrc_min_percent

    if settings.power_zones:
        config["power_zones_percent_ftp"] = _format_zones(
            settings.power_zones,
            settings.power_zone_names,
            min_key="min_percent_ftp",
            max_key="max_percent_ftp",
        )
    if settings.sweet_spot_min is not None:
        config["sweet_spot_min_percent_ftp"] = settings.sweet_spot_min
    if settings.sweet_spot_max is not None:
        config["sweet_spot_max_percent_ftp"] = settings.sweet_spot_max

    if settings.pace_zones:
        config["pace_zones_percent_threshold"] = _format_zones(
            settings.pace_zones,
            settings.pace_zone_names,
            min_key="min_percent",
            max_key="max_percent",
            integral=False,
        )

    if settings.warmup_time is not None:
        config["warmup_seconds"] = settings.warmup_time
    if settings.cooldown_time is not None:
        config["cooldown_seconds"] = settings.cooldown_time

    if not (settings.hr_zones or settings.power_zones or settings.pace_zones):
        # Intervals.icu derives zones from the threshold, so this is rare. Say so and name
        # the write that fixes it rather than synthesizing bands — invented zones would
        # disagree with the time-in-zone/HRSS/TSS this platform computes from real ones.
        config["zones_configured"] = False
        config["zones_hint"] = (
            "No zones configured for this sport. Set fthr (and ftp for power) with "
            "icu_update_sport_settings and Intervals.icu will derive them; leave "
            "recalc_hr_zones at its default of true so the HR zones are rebuilt."
        )

    return config


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
        # Intervals.icu stores swim threshold as SPEED in m/s (unlike run, which is
        # min/km). Convert min/100m -> m/s: 100 m / (minutes * 60) s. Sending the
        # pace value directly stored a bogus speed (4.0 -> 4 m/s -> 0:25/100m); the
        # old `* 60` sent seconds the API rejects with HTTP 422 (see #88).
        payload["threshold_pace"] = 100.0 / (swim_threshold * 60) if swim_threshold else 0.0
        payload["pace_units"] = "SECS_100M"
        payload["pace_load_type"] = "SWIM"
    return payload


# Power zone bounds are % of FTP. Anything above this (bar the open-ended top) is almost
# certainly a watt value copied from a lab report, which the API would store verbatim.
_MAX_PLAUSIBLE_POWER_PERCENT = 200


def _validate_bounds(name: str, bounds: Sequence[int]) -> None:
    if not bounds:
        raise ValueError(f"{name} must contain at least one zone bound")
    if any(b <= 0 for b in bounds):
        raise ValueError(f"{name} bounds must be positive")
    if any(later <= earlier for earlier, later in zip(bounds, bounds[1:], strict=False)):
        raise ValueError(f"{name} must be strictly increasing upper bounds, got {list(bounds)}")


def _validate_names(
    name: str, names: Sequence[str] | None, bounds_name: str, bounds: Sequence[int] | None
) -> None:
    if names is None:
        return
    if bounds is None:
        raise ValueError(f"{name} must be sent together with {bounds_name}")
    if len(names) != len(bounds):
        raise ValueError(
            f"{name} has {len(names)} entries but {bounds_name} has {len(bounds)}; "
            "give one name per zone"
        )


def build_zone_api_payload(
    *,
    hr_zones: Sequence[int] | None = None,
    hr_zone_names: Sequence[str] | None = None,
    max_hr: int | None = None,
    power_zones_percent_ftp: Sequence[int] | None = None,
    power_zone_names: Sequence[str] | None = None,
    sweet_spot_min: int | None = None,
    sweet_spot_max: int | None = None,
) -> dict[str, Any]:
    """Validate explicit zone boundaries and convert them to SportSettings JSON fields.

    Live-verified against the API (#137): bounds are stored exactly as sent, zones sent in
    the same call win over recalcHrZones, a names/bounds count mismatch is a bare 422
    ("Invalid HR zone names"), and max_hr is silently overwritten by the last HR bound.
    The checks here turn those into errors that say what to fix.
    """
    payload: dict[str, Any] = {}

    if hr_zones is not None:
        _validate_bounds("hr_zones", hr_zones)
        payload["hr_zones"] = list(hr_zones)
    _validate_names("hr_zone_names", hr_zone_names, "hr_zones", hr_zones)
    if hr_zone_names is not None:
        payload["hr_zone_names"] = list(hr_zone_names)

    if max_hr is not None:
        if max_hr <= 0:
            raise ValueError("max_hr must be positive")
        if hr_zones is not None and hr_zones[-1] != max_hr:
            raise ValueError(
                f"The last hr_zones bound ({hr_zones[-1]}) must equal max_hr ({max_hr}); "
                "Intervals.icu would otherwise overwrite max_hr with the last bound"
            )
        payload["max_hr"] = max_hr

    if power_zones_percent_ftp is not None:
        bounds = power_zones_percent_ftp
        _validate_bounds("power_zones_percent_ftp", bounds)
        capped = bounds[:-1] if bounds[-1] == _UNBOUNDED_ZONE_LIMIT else bounds
        if any(b > _MAX_PLAUSIBLE_POWER_PERCENT for b in capped):
            raise ValueError(
                "power_zones_percent_ftp are % of FTP, not watts; bounds above "
                f"{_MAX_PLAUSIBLE_POWER_PERCENT} are only allowed as a final "
                f"{_UNBOUNDED_ZONE_LIMIT} (open-ended top zone)"
            )
        payload["power_zones"] = list(bounds)
    _validate_names(
        "power_zone_names", power_zone_names, "power_zones_percent_ftp", power_zones_percent_ftp
    )
    if power_zone_names is not None:
        payload["power_zone_names"] = list(power_zone_names)

    if sweet_spot_min is not None and sweet_spot_max is not None:
        if sweet_spot_min >= sweet_spot_max:
            raise ValueError("sweet_spot_min must be below sweet_spot_max")
    for key, value in (("sweet_spot_min", sweet_spot_min), ("sweet_spot_max", sweet_spot_max)):
        if value is not None:
            if not 0 < value <= _MAX_PLAUSIBLE_POWER_PERCENT:
                raise ValueError(f"{key} is % of FTP and must be between 1 and 200")
            payload[key] = value

    return payload
