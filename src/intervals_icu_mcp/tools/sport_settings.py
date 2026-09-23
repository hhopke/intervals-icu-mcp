"""Sport-specific settings tools for FTP, FTHR, pace thresholds, and zones."""

from typing import Annotated, Any

from fastmcp import Context

from ..auth import load_config, validate_credentials
from ..client import ICUAPIError, ICUClient
from ..response_builder import ResponseBuilder
from ..sport_settings_format import (
    build_sport_settings_api_payload,
    build_zone_api_payload,
    format_sport_settings_entry,
)


async def get_sport_settings(
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Get per-sport thresholds and the athlete's configured power/HR/pace zones.

    Returns outdoor/indoor FTP, FTHR, max HR, running pace and swim threshold, plus the
    zone sets configured in Intervals.icu (HR zones in bpm, power zones as %FTP, pace
    zones as % of threshold pace) with their names.

    This is the ONLY source of the athlete's real zones. Intervals.icu derives them from
    the threshold (unless set explicitly) and stamps them into every activity at import,
    so time-in-zone, HRSS and TSS are all computed from these — reasoning about zones from any other number puts the
    answer at odds with the athlete's own charts. Zones are not derived from curve data.
    """
    config = load_config()
    if not validate_credentials(config):
        return (
            "Error: Intervals.icu credentials not configured. Run intervals-icu-mcp-auth to set up."
        )

    try:
        async with ICUClient(config) as client:
            settings_list = await client.get_sport_settings(athlete_id=athlete_id)

            if not settings_list:
                return ResponseBuilder.build_response(
                    {"message": "No sport settings found"}, metadata={"count": 0}
                )

            settings_data = [
                format_sport_settings_entry(settings, include_zones=True)
                for settings in settings_list
            ]

            return ResponseBuilder.build_response(
                {"sport_settings": settings_data},
                metadata={"count": len(settings_list), "type": "sport_settings_list"},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(str(e), error_type="unexpected_error")


async def update_sport_settings(
    sport_id: Annotated[int, "ID of the sport settings to update"],
    ftp: Annotated[int | None, "Functional Threshold Power in watts (for cycling)"] = None,
    indoor_ftp: Annotated[
        int | None, "Indoor Functional Threshold Power in watts (for cycling)"
    ] = None,
    fthr: Annotated[int | None, "Functional Threshold Heart Rate in bpm"] = None,
    pace_threshold: Annotated[
        float | None, "Threshold pace in min/km (e.g., 4.5 for 4:30/km)"
    ] = None,
    swim_threshold: Annotated[
        float | None, "Swim threshold in min/100m (e.g., 1.5 for 1:30/100m)"
    ] = None,
    recalc_hr_zones: Annotated[
        bool,
        "Rescale HR zones when fthr changes. Explicit lab zones are rescaled too; pass "
        "false to keep them. Zones sent in the same call are kept either way",
    ] = True,
    hr_zones: Annotated[
        list[int] | None,
        "Explicit HR zone upper bounds in bpm, strictly increasing (e.g. lab VT1/VT2). "
        "The last bound becomes max_hr",
    ] = None,
    hr_zone_names: Annotated[list[str] | None, "One name per hr_zones bound"] = None,
    max_hr: Annotated[int | None, "Max HR in bpm; must equal the last hr_zones bound"] = None,
    power_zones_percent_ftp: Annotated[
        list[int] | None,
        "Explicit power zone upper bounds as % of FTP (not watts), strictly increasing; "
        "999 as the last value makes the top zone open-ended",
    ] = None,
    power_zone_names: Annotated[
        list[str] | None, "One name per power_zones_percent_ftp bound"
    ] = None,
    sweet_spot_min: Annotated[int | None, "Sweet spot lower bound, % of FTP"] = None,
    sweet_spot_max: Annotated[int | None, "Sweet spot upper bound, % of FTP"] = None,
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Update a per-sport record: FTP, FTHR, pace/swim thresholds, or explicit zone bounds.

    Explicit zones replace the threshold-derived ones (e.g. to match a lab test).
    Changes apply from now on; past activities keep the zones they were analysed with.
    """
    config = load_config()
    if not validate_credentials(config):
        return (
            "Error: Intervals.icu credentials not configured. Run intervals-icu-mcp-auth to set up."
        )

    try:
        async with ICUClient(config) as client:
            settings_data = build_sport_settings_api_payload(
                ftp=ftp,
                indoor_ftp=indoor_ftp,
                fthr=fthr,
                pace_threshold=pace_threshold,
                swim_threshold=swim_threshold,
            )
            settings_data.update(
                build_zone_api_payload(
                    hr_zones=hr_zones,
                    hr_zone_names=hr_zone_names,
                    max_hr=max_hr,
                    power_zones_percent_ftp=power_zones_percent_ftp,
                    power_zone_names=power_zone_names,
                    sweet_spot_min=sweet_spot_min,
                    sweet_spot_max=sweet_spot_max,
                )
            )

            if not settings_data:
                return ResponseBuilder.build_error_response(
                    "No fields provided to update", error_type="validation_error"
                )

            settings = await client.update_sport_settings(
                sport_id,
                settings_data,
                athlete_id=athlete_id,
                recalc_hr_zones=recalc_hr_zones,
            )

            metadata: dict[str, Any] = {
                "type": "sport_settings_updated",
                "message": "Sport settings updated successfully",
            }
            if max_hr is not None and settings.max_hr != max_hr:
                # The API overwrites max_hr with the last stored HR bound (live-verified).
                metadata["warning"] = (
                    f"max_hr {max_hr} was not kept; Intervals.icu stored {settings.max_hr}, "
                    "the top of the current HR zones. Send hr_zones ending at the new max_hr."
                )

            return ResponseBuilder.build_response(
                format_sport_settings_entry(settings, include_zones=True),
                metadata=metadata,
            )

    except ValueError as e:
        return ResponseBuilder.build_error_response(str(e), error_type="validation_error")
    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(str(e), error_type="unexpected_error")


async def apply_sport_settings(
    sport_id: Annotated[int, "ID of the sport settings to apply"],
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Overwrite the zones on EVERY past activity of this sport with the current settings' zones.

    No date range: all matching activities are rewritten. FTP and other thresholds stored
    on past activities are kept; for sports with HR zones, LTHR and max HR are updated.
    Not needed after update_sport_settings — new values already apply to activities from
    now on, and past ones keep the settings they were analysed with. Use only to correct
    wrong settings across the whole history. For selected activities or a date range, tell
    the user to use Update zones in the Intervals.icu activity list view (not in the API).
    """
    config = load_config()
    if not validate_credentials(config):
        return (
            "Error: Intervals.icu credentials not configured. Run intervals-icu-mcp-auth to set up."
        )

    try:
        async with ICUClient(config) as client:
            result = await client.apply_sport_settings(sport_id, athlete_id=athlete_id)

            return ResponseBuilder.build_response(
                result,
                metadata={
                    "type": "sport_settings_applied",
                    "message": "Sport settings applied to activities successfully",
                },
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(str(e), error_type="unexpected_error")


async def create_sport_settings(
    sport_type: Annotated[str, "Type of sport (e.g., 'Ride', 'Run', 'Swim')"],
    ftp: Annotated[int | None, "Functional Threshold Power in watts (for cycling)"] = None,
    indoor_ftp: Annotated[
        int | None, "Indoor Functional Threshold Power in watts (for cycling)"
    ] = None,
    fthr: Annotated[int | None, "Functional Threshold Heart Rate in bpm"] = None,
    pace_threshold: Annotated[
        float | None, "Threshold pace in min/km (e.g., 4.5 for 4:30/km)"
    ] = None,
    swim_threshold: Annotated[
        float | None, "Swim threshold in min/100m (e.g., 1.5 for 1:30/100m)"
    ] = None,
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Create a per-sport threshold record with outdoor/indoor FTP, FTHR, pace, or swim settings."""
    config = load_config()
    if not validate_credentials(config):
        return (
            "Error: Intervals.icu credentials not configured. Run intervals-icu-mcp-auth to set up."
        )

    try:
        async with ICUClient(config) as client:
            settings_data = build_sport_settings_api_payload(
                sport_type=sport_type,
                ftp=ftp,
                indoor_ftp=indoor_ftp,
                fthr=fthr,
                pace_threshold=pace_threshold,
                swim_threshold=swim_threshold,
            )

            settings = await client.create_sport_settings(settings_data, athlete_id=athlete_id)

            return ResponseBuilder.build_response(
                format_sport_settings_entry(settings, include_zones=True),
                metadata={
                    "type": "sport_settings_created",
                    "message": "Sport settings created successfully",
                },
            )

    except ValueError as e:
        return ResponseBuilder.build_error_response(str(e), error_type="validation_error")
    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(str(e), error_type="unexpected_error")


async def delete_sport_settings(
    sport_id: Annotated[int, "ID of the sport settings to delete"],
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Permanently delete a per-sport threshold record. Destructive — re-creating it starts from defaults, not the deleted values; only registered when INTERVALS_ICU_DELETE_MODE=full."""
    config = load_config()
    if not validate_credentials(config):
        return (
            "Error: Intervals.icu credentials not configured. Run intervals-icu-mcp-auth to set up."
        )

    try:
        async with ICUClient(config) as client:
            await client.delete_sport_settings(sport_id, athlete_id=athlete_id)

            return ResponseBuilder.build_response(
                {"sport_id": sport_id, "deleted": True},
                metadata={
                    "type": "sport_settings_deleted",
                    "message": "Sport settings deleted successfully",
                },
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(str(e), error_type="unexpected_error")
