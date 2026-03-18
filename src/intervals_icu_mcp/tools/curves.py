"""Additional performance curve tools for Intervals.icu MCP server."""

from typing import Annotated, Any

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..response_builder import ResponseBuilder


def _find_value_at_duration(
    secs: list[int], values: list[int], target: int
) -> tuple[int, int] | None:
    """Find the value closest to target duration. Returns (secs, value) or None."""
    if not secs:
        return None
    best_idx = min(range(len(secs)), key=lambda i: abs(secs[i] - target))
    if abs(secs[best_idx] - target) <= target * 0.1:
        return secs[best_idx], values[best_idx]
    return None


def _resolve_period(
    days_back: int | None, time_period: str | None
) -> tuple[str, str] | str:
    """Resolve days_back/time_period to (curves, period_label) or error string."""
    if days_back is not None:
        return f"{days_back}d", f"{days_back}_days"
    if time_period:
        period_map = {
            "week": ("7d", "week"),
            "month": ("30d", "month"),
            "year": ("1y", "year"),
            "all": ("all", "all_time"),
        }
        if time_period.lower() in period_map:
            return period_map[time_period.lower()]
        return ResponseBuilder.build_error_response(
            "Invalid time_period. Use 'week', 'month', 'year', or 'all'",
            error_type="validation_error",
        )
    return "90d", "90_days"


async def get_hr_curves(
    sport_type: Annotated[str, "Sport type (e.g., Ride, Run, Swim, VirtualRide)"] = "Ride",
    days_back: Annotated[int | None, "Number of days to analyze (optional)"] = None,
    time_period: Annotated[
        str | None,
        "Time period shorthand: 'week', 'month', 'year', 'all' (optional)",
    ] = None,
    ctx: Context | None = None,
) -> str:
    """Get heart rate curve data showing best efforts for various durations.

    Analyzes heart rate data across activities to find peak heart rate outputs for
    different time durations (e.g., 5 seconds, 1 minute, 5 minutes, 20 minutes).

    Useful for tracking cardiovascular fitness improvements and identifying HR zones
    across different effort durations.

    Args:
        days_back: Number of days to analyze (overrides time_period)
        time_period: Time period shorthand - 'week' (7 days), 'month' (30 days),
                     'year' (365 days), 'all' (all time). Default is 90 days.

    Returns:
        JSON string with HR curve data
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        period = _resolve_period(days_back, time_period)
        if isinstance(period, str):
            return period
        curves, period_label = period

        async with ICUClient(config) as client:
            curve_set = await client.get_hr_curves(curves=curves, type=sport_type)

            if not curve_set.curves or not curve_set.curves[0].values:
                return ResponseBuilder.build_response(
                    data={"hr_curve": [], "period": period_label},
                    metadata={
                        "message": f"No HR curve data available for {period_label}. "
                        "Complete some activities with heart rate to build your HR curve."
                    },
                )

            curve = curve_set.curves[0]
            secs = curve.secs
            vals = curve.values

            # Key durations to highlight (in seconds)
            key_durations = {
                5: "5_sec",
                15: "15_sec",
                30: "30_sec",
                60: "1_min",
                120: "2_min",
                300: "5_min",
                600: "10_min",
                1200: "20_min",
                3600: "1_hour",
            }

            # Find data points for key durations
            peak_efforts: dict[str, dict[str, Any]] = {}
            for target_secs, label in key_durations.items():
                result = _find_value_at_duration(secs, vals, target_secs)
                if result:
                    actual_secs, bpm = result
                    effort: dict[str, Any] = {
                        "bpm": bpm,
                        "duration_seconds": actual_secs,
                    }
                    idx = secs.index(actual_secs)
                    if idx < len(curve.activity_id) and curve.activity_id[idx]:
                        effort["activity_id"] = curve.activity_id[idx]
                    peak_efforts[label] = effort

            # Calculate summary statistics
            max_hr = max(vals) if vals else 0
            max_hr_idx = vals.index(max_hr) if vals else 0

            summary: dict[str, Any] = {
                "total_data_points": len(secs),
                "max_hr_bpm": max_hr,
                "max_hr_duration_seconds": secs[max_hr_idx] if secs else 0,
                "duration_range": {
                    "min_seconds": min(secs) if secs else 0,
                    "max_seconds": max(secs) if secs else 0,
                },
            }

            if curve.start_date_local and curve.end_date_local:
                summary["effort_date_range"] = {
                    "oldest": curve.start_date_local,
                    "newest": curve.end_date_local,
                }

            # Calculate HR zones (based on max HR if available)
            hr_zones: dict[str, dict[str, int]] | None = None
            if max_hr > 0:
                zones = {
                    "zone_1_recovery": (0.50, 0.60),
                    "zone_2_endurance": (0.60, 0.70),
                    "zone_3_tempo": (0.70, 0.80),
                    "zone_4_threshold": (0.80, 0.90),
                    "zone_5_vo2max": (0.90, 1.00),
                }

                hr_zones = {}
                for zone_name, (low, high) in zones.items():
                    hr_zones[zone_name] = {
                        "min_bpm": int(max_hr * low),
                        "max_bpm": int(max_hr * high),
                        "min_percent_max": int(low * 100),
                        "max_percent_max": int(high * 100),
                    }

            result_data: dict[str, Any] = {
                "period": period_label,
                "peak_efforts": peak_efforts,
                "summary": summary,
            }

            if hr_zones:
                result_data["hr_zones"] = hr_zones

            return ResponseBuilder.build_response(
                data=result_data,
                query_type="hr_curves",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def get_pace_curves(
    sport_type: Annotated[str, "Sport type (e.g., Run, Swim)"] = "Run",
    days_back: Annotated[int | None, "Number of days to analyze (optional)"] = None,
    time_period: Annotated[
        str | None,
        "Time period shorthand: 'week', 'month', 'year', 'all' (optional)",
    ] = None,
    use_gap: Annotated[bool, "Use Grade Adjusted Pace (GAP) for running"] = False,
    ctx: Context | None = None,
) -> str:
    """Get pace curve data showing best efforts for various durations.

    Analyzes pace data across running/swimming activities to find best pace outputs for
    different time durations (e.g., 400m, 1km, 5km, 10km).

    Useful for tracking running fitness and race predictions. Can use Grade Adjusted Pace
    (GAP) to normalize for hills.

    Args:
        days_back: Number of days to analyze (overrides time_period)
        time_period: Time period shorthand - 'week' (7 days), 'month' (30 days),
                     'year' (365 days), 'all' (all time). Default is 90 days.
        use_gap: Use Grade Adjusted Pace (GAP) for running to account for hills

    Returns:
        JSON string with pace curve data
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        period = _resolve_period(days_back, time_period)
        if isinstance(period, str):
            return period
        curves, period_label = period

        async with ICUClient(config) as client:
            curve_set = await client.get_pace_curves(
                curves=curves, type=sport_type, use_gap=use_gap
            )

            if not curve_set.curves or not curve_set.curves[0].values:
                return ResponseBuilder.build_response(
                    data={"pace_curve": [], "period": period_label, "gap_enabled": use_gap},
                    metadata={
                        "message": f"No pace curve data available for {period_label}. "
                        "Complete some runs/swims to build your pace curve."
                    },
                )

            curve = curve_set.curves[0]
            secs = curve.secs
            vals = curve.values

            # Key durations to highlight (in seconds)
            key_durations = {
                60: "400m_equivalent",
                180: "1km_equivalent",
                300: "5_min",
                600: "10_min",
                900: "15_min",
                1200: "20_min",
                1800: "30_min",
                3600: "1_hour",
            }

            # Find data points for key durations
            # Pace values are in seconds per km (lower = faster)
            peak_efforts: dict[str, dict[str, Any]] = {}
            for target_secs, label in key_durations.items():
                result = _find_value_at_duration(secs, vals, target_secs)
                if result:
                    actual_secs, pace_val = result
                    # Convert pace from seconds/km to min:sec/km
                    pace_min = pace_val // 60
                    pace_sec = pace_val % 60
                    effort: dict[str, Any] = {
                        "pace_seconds_per_km": pace_val,
                        "pace_formatted": f"{pace_min}:{pace_sec:02d} /km",
                        "duration_seconds": actual_secs,
                    }
                    idx = secs.index(actual_secs)
                    if idx < len(curve.activity_id) and curve.activity_id[idx]:
                        effort["activity_id"] = curve.activity_id[idx]
                    peak_efforts[label] = effort

            # Calculate summary statistics (best pace = lowest value)
            best_pace = min(vals) if vals else 0
            best_pace_idx = vals.index(best_pace) if vals else 0

            summary: dict[str, Any] = {
                "total_data_points": len(secs),
                "best_pace_seconds_per_km": best_pace,
                "best_pace_duration_seconds": secs[best_pace_idx] if secs else 0,
                "duration_range": {
                    "min_seconds": min(secs) if secs else 0,
                    "max_seconds": max(secs) if secs else 0,
                },
                "gap_enabled": use_gap,
            }

            if best_pace > 0:
                pace_min = best_pace // 60
                pace_sec = best_pace % 60
                summary["best_pace_formatted"] = f"{pace_min}:{pace_sec:02d} /km"

            if curve.start_date_local and curve.end_date_local:
                summary["effort_date_range"] = {
                    "oldest": curve.start_date_local,
                    "newest": curve.end_date_local,
                }

            result_data: dict[str, Any] = {
                "period": period_label,
                "peak_efforts": peak_efforts,
                "summary": summary,
            }

            return ResponseBuilder.build_response(
                data=result_data,
                query_type="pace_curves",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )
