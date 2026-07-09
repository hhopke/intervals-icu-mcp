"""Sport-specific settings tools for FTP, FTHR, pace thresholds, and zones."""

from typing import Annotated, Any

from fastmcp import Context

from ..auth import load_config, validate_credentials
from ..client import ICUAPIError, ICUClient
from ..response_builder import ResponseBuilder
from ..sport_settings_format import build_sport_settings_api_payload, format_sport_settings_entry


async def get_sport_settings(
    ctx: Context | None = None,
) -> str:
    """Get all per-sport thresholds — outdoor/indoor FTP, FTHR, running pace, and swim threshold."""
    config = load_config()
    if not validate_credentials(config):
        return (
            "Error: Intervals.icu credentials not configured. Run intervals-icu-mcp-auth to set up."
        )

    try:
        async with ICUClient(config) as client:
            settings_list = await client.get_sport_settings()

            if not settings_list:
                return ResponseBuilder.build_response(
                    {"message": "No sport settings found"}, metadata={"count": 0}
                )

            settings_data = [format_sport_settings_entry(settings) for settings in settings_list]

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
    ctx: Context | None = None,
) -> str:
    """Update an existing per-sport threshold record (outdoor/indoor FTP, FTHR, pace, swim)."""
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

            if not settings_data:
                return ResponseBuilder.build_error_response(
                    "No fields provided to update", error_type="validation_error"
                )

            settings = await client.update_sport_settings(sport_id, settings_data)

            return ResponseBuilder.build_response(
                format_sport_settings_entry(settings),
                metadata={
                    "type": "sport_settings_updated",
                    "message": "Sport settings updated successfully",
                },
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(str(e), error_type="unexpected_error")


async def apply_sport_settings(
    sport_id: Annotated[int, "ID of the sport settings to apply"],
    oldest_date: Annotated[
        str | None, "Oldest date to apply settings to (YYYY-MM-DD format)"
    ] = None,
    ctx: Context | None = None,
) -> str:
    """Recompute training load, zones, and derived metrics on HISTORICAL activities using the current sport settings.

    Different from update_sport_settings (which just stores new values).
    Use after changing FTP/FTHR/pace to backfill chart math.
    """
    config = load_config()
    if not validate_credentials(config):
        return (
            "Error: Intervals.icu credentials not configured. Run intervals-icu-mcp-auth to set up."
        )

    try:
        async with ICUClient(config) as client:
            result = await client.apply_sport_settings(sport_id, oldest=oldest_date)

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

            settings = await client.create_sport_settings(settings_data)

            return ResponseBuilder.build_response(
                format_sport_settings_entry(settings),
                metadata={
                    "type": "sport_settings_created",
                    "message": "Sport settings created successfully",
                },
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(str(e), error_type="unexpected_error")


async def delete_sport_settings(
    sport_id: Annotated[int, "ID of the sport settings to delete"],
    ctx: Context | None = None,
) -> str:
    """Permanently delete a per-sport threshold record. Destructive — affects historical chart math; only registered when INTERVALS_ICU_DELETE_MODE=full."""
    config = load_config()
    if not validate_credentials(config):
        return (
            "Error: Intervals.icu credentials not configured. Run intervals-icu-mcp-auth to set up."
        )

    try:
        async with ICUClient(config) as client:
            await client.delete_sport_settings(sport_id)

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
