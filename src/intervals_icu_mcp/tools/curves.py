"""Additional performance curve tools for Intervals.icu MCP server."""

from collections.abc import Sequence
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


def _find_nearest_index(
    points: Sequence[float], target: float, tolerance: float = 0.02
) -> int | None:
    """Index of the point closest to target, if it is within ±tolerance (a fraction) of it.

    The default is tight (±2%) so a standard-distance label is only filled by a point at
    that distance: a 4,600 m best time is not a 5 km time.
    """
    if not points:
        return None
    best_idx = min(range(len(points)), key=lambda i: abs(points[i] - target))
    if abs(points[best_idx] - target) <= target * tolerance:
        return best_idx
    return None


def _format_pace(seconds_per_km: float) -> str:
    """Format a pace in seconds per km as m:ss /km."""
    total = round(seconds_per_km)
    return f"{total // 60}:{total % 60:02d} /km"


# Standard distances to highlight on the pace curve: (metres, label)
_KEY_DISTANCES: tuple[tuple[float, str], ...] = (
    (400.0, "400m"),
    (1000.0, "1km"),
    (1609.34, "1_mile"),
    (5000.0, "5km"),
    (10000.0, "10km"),
    (21097.5, "half_marathon"),
    (42195.0, "marathon"),
)


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

    Use for cardiovascular-fitness trends. For the athlete's HR zones and max
    HR, call icu_get_sport_settings — this tool does not return zone bands, and
    its peak_hr_bpm is the top of this curve, which Intervals.icu has already
    clipped to the configured max HR at import. For time-in-zone *distribution*
    within a single activity, use get_hr_histogram instead.
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
    """Fetch the pace-vs-distance curve — best (fastest) time and pace over distances from ~50 m up to the athlete's longest effort, aggregated over the chosen window.

    Peak efforts are reported at standard distances (400 m, 1 km, mile, 5 km,
    10 km, half marathon, marathon) when the curve reaches them. The summary's best
    pace is almost always set over the shortest distances (tens of metres), so
    compare peak_efforts rather than that headline figure. Use for run/swim
    fitness trends and race-time predictions. Pass `use_gap=True` to normalize
    for hills via Grade-Adjusted Pace. For time-in-zone *distribution* within a
    single activity, use get_pace_histogram (or get_gap_histogram) instead.
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

            curve = curve_set.curves[0] if curve_set.curves else None
            # The pace curve is distance-based: `values[i]` is the best time in seconds
            # to cover `distance[i]` metres. Keep only well-formed points, with their
            # original index so activity_id[i] still lines up.
            points = (
                [
                    (i, d, t)
                    for i, (d, t) in enumerate(zip(curve.distance, curve.values, strict=False))
                    if d > 0 and t > 0
                ]
                if curve
                else []
            )

            if curve is None or not points:
                return ResponseBuilder.build_response(
                    data={"pace_curve": [], "period": period_label, "gap_enabled": use_gap},
                    metadata={
                        "message": f"No pace curve data available for {period_label}. "
                        "Complete some runs/swims to build your pace curve."
                    },
                )

            distances = [d for _, d, _ in points]
            paces = [t / d * 1000 for _, d, t in points]

            peak_efforts: dict[str, dict[str, Any]] = {}
            for target_m, label in _KEY_DISTANCES:
                idx = _find_nearest_index(distances, target_m)
                if idx is None:
                    continue
                orig_idx, distance_m, time_s = points[idx]
                effort: dict[str, Any] = {
                    "distance_meters": round(distance_m, 2),
                    "time_seconds": time_s,
                    "pace_seconds_per_km": round(paces[idx], 1),
                    "pace_formatted": _format_pace(paces[idx]),
                }
                if orig_idx < len(curve.activity_id) and curve.activity_id[orig_idx]:
                    effort["activity_id"] = curve.activity_id[orig_idx]
                peak_efforts[label] = effort

            # Best pace = lowest seconds per km, reported with the distance it was set over
            best_idx = min(range(len(paces)), key=lambda i: paces[i])

            summary: dict[str, Any] = {
                "total_data_points": len(points),
                "best_pace_seconds_per_km": round(paces[best_idx], 1),
                "best_pace_formatted": _format_pace(paces[best_idx]),
                "best_pace_distance_meters": round(distances[best_idx], 2),
                "distance_range": {
                    "min_meters": round(min(distances), 2),
                    "max_meters": round(max(distances), 2),
                },
                "gap_enabled": use_gap,
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
                query_type="pace_curves",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )
