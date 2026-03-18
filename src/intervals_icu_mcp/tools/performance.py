"""Performance analysis tools for Intervals.icu MCP server."""

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


async def get_power_curves(
    sport_type: Annotated[str, "Sport type (e.g., Ride, Run, Swim, VirtualRide)"] = "Ride",
    days_back: Annotated[int | None, "Number of days to analyze (optional)"] = None,
    time_period: Annotated[
        str | None,
        "Time period shorthand: 'week', 'month', 'year', 'all' (optional)",
    ] = None,
    ctx: Context | None = None,
) -> str:
    """Get power curve data showing best efforts for various durations.

    Analyzes power data across activities to find peak power outputs for
    different time durations (e.g., 5 seconds, 1 minute, 5 minutes, 20 minutes).

    Useful for tracking performance improvements and identifying strengths/weaknesses
    across different power duration profiles.

    Args:
        days_back: Number of days to analyze (overrides time_period)
        time_period: Time period shorthand - 'week' (7 days), 'month' (30 days),
                     'year' (365 days), 'all' (all time). Default is 90 days.

    Returns:
        JSON string with power curve data
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        # Convert days_back/time_period to curves format
        if days_back is not None:
            curves = f"{days_back}d"
            period_label = f"{days_back}_days"
        elif time_period:
            period_map = {
                "week": ("7d", "week"),
                "month": ("30d", "month"),
                "year": ("1y", "year"),
                "all": ("all", "all_time"),
            }
            if time_period.lower() in period_map:
                curves, period_label = period_map[time_period.lower()]
            else:
                return ResponseBuilder.build_error_response(
                    "Invalid time_period. Use 'week', 'month', 'year', or 'all'",
                    error_type="validation_error",
                )
        else:
            # Default to 90 days
            curves = "90d"
            period_label = "90_days"

        async with ICUClient(config) as client:
            curve_set = await client.get_power_curves(curves=curves, type=sport_type)

            if not curve_set.curves or not curve_set.curves[0].values:
                return ResponseBuilder.build_response(
                    data={"power_curve": [], "period": period_label},
                    metadata={
                        "message": f"No power curve data available for {period_label}. "
                        "Complete some rides with power to build your power curve."
                    },
                )

            curve = curve_set.curves[0]
            secs = curve.secs
            vals = curve.values
            activity_ids = curve.activity_id

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
                    actual_secs, watts = result
                    effort: dict[str, Any] = {
                        "watts": watts,
                        "duration_seconds": actual_secs,
                    }
                    # Find activity_id for this data point
                    idx = secs.index(actual_secs)
                    if idx < len(activity_ids) and activity_ids[idx]:
                        effort["activity_id"] = activity_ids[idx]
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

            # Calculate FTP and power zones (based on 20-min power)
            ftp_analysis = None
            twenty_min = _find_value_at_duration(secs, vals, 1200)
            if twenty_min:
                _, twenty_min_watts = twenty_min
                estimated_ftp = int(twenty_min_watts * 0.95)

                if estimated_ftp > 0:
                    zones = {
                        "recovery": (0, 0.55),
                        "endurance": (0.56, 0.75),
                        "tempo": (0.76, 0.90),
                        "threshold": (0.91, 1.05),
                        "vo2max": (1.06, 1.20),
                        "anaerobic": (1.21, 1.50),
                    }

                    power_zones: dict[str, dict[str, int]] = {}
                    for zone_name, (low, high) in zones.items():
                        power_zones[zone_name] = {
                            "min_watts": int(estimated_ftp * low),
                            "max_watts": int(estimated_ftp * high),
                            "min_percent_ftp": int(low * 100),
                            "max_percent_ftp": int(high * 100),
                        }

                    ftp_analysis = {
                        "twenty_min_power": twenty_min_watts,
                        "estimated_ftp": estimated_ftp,
                        "power_zones": power_zones,
                    }

            result_data: dict[str, Any] = {
                "period": period_label,
                "peak_efforts": peak_efforts,
                "summary": summary,
            }

            if ftp_analysis:
                result_data["ftp_analysis"] = ftp_analysis

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
