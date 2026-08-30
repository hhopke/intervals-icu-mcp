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


def _resolve_period(days_back: int | None, time_period: str | None) -> tuple[str, str] | str:
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
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Fetch the HR-vs-duration curve — best (highest) sustained HR across durations from 5s up to 1h, aggregated over the chosen window.

    Use for cardiovascular-fitness trends and HR-zone calibration. For
    time-in-zone *distribution* within a single activity, use
    get_hr_histogram instead.
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        period = _resolve_period(days_back, time_period)
        if isinstance(period, str):
            return period
        curves, period_label = period

        async with ICUClient(config) as client:
            curve_set = await client.get_hr_curves(
                athlete_id=athlete_id, curves=curves, type=sport_type
            )

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

            # Calculate summary statistics. This is the highest value on THIS curve, which
            # is not the athlete's max HR: Intervals.icu clips HR above the configured max
            # at import, so the curve can only ever echo a past value of that setting.
            # icu_get_sport_settings is the source of the real max HR (#119).
            peak_hr = max(vals) if vals else 0
            peak_hr_idx = vals.index(peak_hr) if vals else 0

            summary: dict[str, Any] = {
                "total_data_points": len(secs),
                "peak_hr_bpm": peak_hr,
                "peak_hr_duration_seconds": secs[peak_hr_idx] if secs else 0,
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

            result_data: dict[str, Any] = {
                "period": period_label,
                "peak_efforts": peak_efforts,
                "summary": summary,
            }

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
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Fetch the pace-vs-duration curve — best (fastest) sustained pace across durations from 5s up to 1h, aggregated over the chosen window.

    Use for run/swim fitness trends and race-time predictions. Pass
    `use_gap=True` to normalize for hills via Grade-Adjusted Pace. For
    time-in-zone *distribution* within a single activity, use
    get_pace_histogram (or get_gap_histogram) instead.
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
                athlete_id=athlete_id, curves=curves, type=sport_type, use_gap=use_gap
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
