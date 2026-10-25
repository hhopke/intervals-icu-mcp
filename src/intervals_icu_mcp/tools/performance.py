"""Performance analysis tools for Intervals.icu MCP server."""

import re
from datetime import date
from typing import Annotated, Any

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..models import CurveActivity, CurveData
from ..response_builder import ResponseBuilder

_TIME_PERIODS = {
    "week": ("7d", "week"),
    "month": ("30d", "month"),
    "year": ("1y", "year"),
    "all": ("all", "all_time"),
}

# Key durations to highlight (in seconds)
_KEY_DURATIONS = {
    5: "5_sec",
    15: "15_sec",
    30: "30_sec",
    60: "1_min",
    120: "2_min",
    300: "5_min",
    600: "10_min",
    1200: "20_min",
    3600: "1_hour",
    7200: "2_hour",
    10800: "3_hour",
    14400: "4_hour",
    18000: "5_hour",
    21600: "6_hour",
}

_MAX_PERIODS = 5
_DATE_RANGE = re.compile(r"(?:r\.)?(\d{4}-\d{2}-\d{2})(?:\.\.|\.)(\d{4}-\d{2}-\d{2})")


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


def _date_range_curve(start: str, end: str) -> tuple[str, str]:
    """Build the API curve ID for an explicit date range, validating both dates."""
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    if start_date > end_date:
        raise ValueError(f"Start date {start} is after end date {end}")
    return f"r.{start}.{end}", f"{start}..{end}"


def _parse_period(spec: str) -> tuple[str, str]:
    """Map one period spec to (API curve ID, response label). Raises ValueError."""
    value = spec.strip().lower()
    if value in _TIME_PERIODS:
        return _TIME_PERIODS[value]
    if re.fullmatch(r"\d+d", value):
        return value, f"{value[:-1]}_days"
    if re.fullmatch(r"s\d+", value):
        return value, f"season_{value}"
    match = _DATE_RANGE.fullmatch(value)
    if match:
        return _date_range_curve(match.group(1), match.group(2))
    raise ValueError(
        f"Invalid period '{spec}'. Use week, month, year, all, '<N>d', a season ID "
        "like 's1', or a date range 'YYYY-MM-DD..YYYY-MM-DD'"
    )


def _analyze_curve(
    curve: CurveData, activities: dict[str, CurveActivity], full_curve: bool = False
) -> dict[str, Any]:
    """Build peak efforts, summary, FTP estimate and power models for one curve."""
    secs = curve.secs
    vals = curve.values
    activity_ids = curve.activity_id
    wkg = curve.watts_per_kg
    wkg_activity_ids = curve.wkg_activity_id

    # Find data points for key durations
    peak_efforts: dict[str, dict[str, Any]] = {}
    for target_secs, label in _KEY_DURATIONS.items():
        result = _find_value_at_duration(secs, vals, target_secs)
        if result:
            actual_secs, watts = result
            effort: dict[str, Any] = {
                "watts": watts,
                "duration_seconds": actual_secs,
            }
            # Find activity_id for this data point
            idx = secs.index(actual_secs)
            if idx < len(activity_ids) and activity_ids[idx]:
                effort["activity_id"] = activity_ids[idx]
                activity = activities.get(activity_ids[idx])
                if activity and activity.start_date_local:
                    effort["date"] = activity.start_date_local[:10]
            if idx < len(wkg):
                # Best W/kg uses each activity's own weight, so it can come from a
                # different (lighter-day) activity than the best watts.
                effort["watts_per_kg"] = round(wkg[idx], 2)
                if idx < len(wkg_activity_ids) and wkg_activity_ids[idx] != effort.get(
                    "activity_id"
                ):
                    effort["watts_per_kg_activity_id"] = wkg_activity_ids[idx]
            peak_efforts[label] = effort

    # Calculate summary statistics
    max_watts = max(vals) if vals else 0
    max_watts_idx = vals.index(max_watts) if vals else 0

    summary: dict[str, Any] = {
        "total_data_points": len(secs),
        "max_power_watts": max_watts,
        "max_power_duration_seconds": secs[max_watts_idx] if secs else 0,
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
    if curve.weight:
        summary["weight_kg"] = round(curve.weight, 1)

    analysis: dict[str, Any] = {"peak_efforts": peak_efforts, "summary": summary}

    # Estimate FTP from 20-min power
    twenty_min = _find_value_at_duration(secs, vals, 1200)
    if twenty_min:
        _, twenty_min_watts = twenty_min
        estimated_ftp = int(twenty_min_watts * 0.95)

        if estimated_ftp > 0:
            # estimated_ftp is a real signal the sport-settings tool cannot give
            # ("your recent data suggests 195W but you are set to 185W"). The
            # zone bands derived from it were removed in 5.0.0 — see #119 and
            # icu_get_sport_settings for the athlete's configured zones.
            analysis["ftp_analysis"] = {
                "twenty_min_power": twenty_min_watts,
                "estimated_ftp": estimated_ftp,
            }

    models = [
        {
            key: value
            for key, value in {
                "type": model.type,
                "critical_power": model.critical_power,
                "w_prime": model.w_prime,
                "p_max": model.p_max,
                "ftp": model.ftp,
            }.items()
            if value is not None
        }
        for model in curve.power_models
    ]
    if models:
        analysis["power_models"] = models
    if curve.vo2max_5m:
        analysis["vo2max_5m"] = round(curve.vo2max_5m, 1)
    if curve.map_plot and curve.map_plot.map_watts:
        # The API reports 0 when the curve has too few points to fit MAP.
        analysis["map"] = {
            "watts": curve.map_plot.map_watts,
            "watts_per_kg": round(curve.map_plot.map or 0, 2),
            "duration_seconds": curve.map_plot.map_secs,
        }
    if full_curve:
        analysis["curve"] = {"secs": secs, "watts": vals}

    return analysis


async def get_power_curves(
    sport_type: Annotated[str, "Sport type (e.g., Ride, Run, Swim, VirtualRide)"] = "Ride",
    days_back: Annotated[int | None, "Number of days to analyze (optional)"] = None,
    time_period: Annotated[
        str | None,
        "Time period shorthand: 'week', 'month', 'year', 'all' (optional)",
    ] = None,
    start_date: Annotated[
        str | None, "Range start (YYYY-MM-DD); use with end_date (defaults to today)"
    ] = None,
    end_date: Annotated[str | None, "Range end (YYYY-MM-DD), inclusive"] = None,
    season: Annotated[
        str | None, "Season curve ID from icu_get_seasons: 's0' = current, 's1' = previous"
    ] = None,
    periods: Annotated[
        list[str] | None,
        "Compare up to 5 periods in one call; each is week/month/year/all, '<N>d', a "
        "season ID ('s1'), or 'YYYY-MM-DD..YYYY-MM-DD'. Returns one entry per period.",
    ] = None,
    full_curve: Annotated[
        bool, "Also return every duration point (secs + watts), not just key durations"
    ] = False,
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Fetch the power-vs-duration curve — best (highest) sustained watts and W/kg across durations from 5s up to 6h, aggregated over the chosen window.

    Use for FTP estimation, peak-power tracking, durability, strengths/weaknesses
    across duration profiles. Includes fitted power models (CP, W', Pmax, FTP),
    the VO2max estimate and MAP when Intervals.icu provides them. Pick ONE window: days_back, time_period,
    start_date/end_date, season, or periods (to compare several, e.g.
    ['s0', 's1', 'all']). Default is the last 90 days. For time-in-zone
    *distribution* within a single activity, use icu_get_power_histogram instead.
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        new_selectors = sum(
            1 for value in (start_date or end_date, season, periods) if value is not None
        )
        legacy_selector = days_back is not None or time_period is not None
        if new_selectors > 1 or (new_selectors and legacy_selector):
            return ResponseBuilder.build_error_response(
                "Pass only one of: days_back/time_period, start_date/end_date, season, periods",
                error_type="validation_error",
            )

        # Convert the chosen window to the API's curves format
        try:
            if periods is not None:
                if not 1 <= len(periods) <= _MAX_PERIODS:
                    raise ValueError(f"periods must list 1 to {_MAX_PERIODS} entries")
                parsed = [_parse_period(spec) for spec in periods]
            elif start_date or end_date:
                if not start_date:
                    raise ValueError("end_date requires start_date")
                parsed = [_date_range_curve(start_date, end_date or date.today().isoformat())]
            elif season is not None:
                if not re.fullmatch(r"s\d+", season.strip().lower()):
                    raise ValueError(f"Invalid season '{season}'. Use an ID like 's0' or 's1'")
                parsed = [_parse_period(season)]
            elif days_back is not None:
                parsed = [(f"{days_back}d", f"{days_back}_days")]
            elif time_period:
                if time_period.lower() not in _TIME_PERIODS:
                    raise ValueError("Invalid time_period. Use 'week', 'month', 'year', or 'all'")
                parsed = [_TIME_PERIODS[time_period.lower()]]
            else:
                # Default to 90 days
                parsed = [("90d", "90_days")]
        except ValueError as e:
            return ResponseBuilder.build_error_response(str(e), error_type="validation_error")

        async with ICUClient(config) as client:
            curve_set = await client.get_power_curves(
                athlete_id=athlete_id,
                curves=",".join(curve_id for curve_id, _ in parsed),
                type=sport_type,
            )

        if periods is not None:
            labels = {curve_id: label for curve_id, label in parsed}
            curves_data: list[dict[str, Any]] = []
            for curve in curve_set.curves:
                entry: dict[str, Any] = {"period": labels.get(curve.id or "", curve.id)}
                if curve.label:
                    entry["label"] = curve.label
                if curve.values:
                    entry.update(_analyze_curve(curve, curve_set.activities, full_curve))
                curves_data.append(entry)
            returned = {curve.id for curve in curve_set.curves}
            missing = [label for curve_id, label in parsed if curve_id not in returned]

            metadata: dict[str, Any] = {"count": len(curves_data)}
            if missing:
                # The API silently drops curves it cannot resolve (e.g. a season that
                # does not exist).
                metadata["missing_periods"] = missing
            return ResponseBuilder.build_response(
                data={"curves": curves_data},
                metadata=metadata,
                query_type="power_curves",
            )

        period_label = parsed[0][1]
        if not curve_set.curves or not curve_set.curves[0].values:
            return ResponseBuilder.build_response(
                data={"power_curve": [], "period": period_label},
                metadata={
                    "message": f"No power curve data available for {period_label}. "
                    "Complete some rides with power to build your power curve."
                },
            )

        curve = curve_set.curves[0]
        result_data: dict[str, Any] = {"period": period_label}
        if season is not None and curve.label:
            result_data["label"] = curve.label
        result_data.update(_analyze_curve(curve, curve_set.activities, full_curve))

        return ResponseBuilder.build_response(
            data=result_data,
            query_type="power_curves",
        )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )
