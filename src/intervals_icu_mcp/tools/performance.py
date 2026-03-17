"""Performance analysis tools for Intervals.icu MCP server."""

from datetime import datetime, timedelta
from typing import Annotated, Any

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..response_builder import ResponseBuilder


async def get_power_curves(
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
        # Determine date range
        oldest = None

        if days_back is not None:
            oldest_date = datetime.now() - timedelta(days=days_back)
            oldest = oldest_date.strftime("%Y-%m-%d")
            period_label = f"{days_back}_days"
        elif time_period:
            period_map = {
                "week": 7,
                "month": 30,
                "year": 365,
            }
            if time_period.lower() in period_map:
                days = period_map[time_period.lower()]
                oldest_date = datetime.now() - timedelta(days=days)
                oldest = oldest_date.strftime("%Y-%m-%d")
                period_label = time_period.lower()
            elif time_period.lower() == "all":
                oldest = None
                period_label = "all_time"
            else:
                return ResponseBuilder.build_error_response(
                    "Invalid time_period. Use 'week', 'month', 'year', or 'all'",
                    error_type="validation_error",
                )
        else:
            # Default to 90 days
            oldest_date = datetime.now() - timedelta(days=90)
            oldest = oldest_date.strftime("%Y-%m-%d")
            period_label = "90_days"

        async with ICUClient(config) as client:
            power_curve = await client.get_power_curves(oldest=oldest)

            if not power_curve.data or len(power_curve.data) == 0:
                return ResponseBuilder.build_response(
                    data={"power_curve": [], "period": period_label},
                    metadata={
                        "message": f"No power curve data available for {period_label}. "
                        "Complete some rides with power to build your power curve."
                    },
                )

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
            for seconds, label in key_durations.items():
                # Find closest data point
                closest_point = min(
                    power_curve.data,
                    key=lambda p: abs(p.secs - seconds),
                    default=None,
                )

                if closest_point and abs(closest_point.secs - seconds) <= seconds * 0.1:
                    # Only include if within 10% of target duration
                    effort: dict[str, Any] = {
                        "watts": closest_point.watts,
                        "duration_seconds": closest_point.secs,
                    }
                    if closest_point.date:
                        effort["date"] = closest_point.date
                    if closest_point.src_activity_id:
                        effort["activity_id"] = closest_point.src_activity_id

                    peak_efforts[label] = effort

            # Calculate summary statistics
            max_power_point = max(power_curve.data, key=lambda p: p.watts or 0)
            min_duration = min(power_curve.data, key=lambda p: p.secs)
            max_duration = max(power_curve.data, key=lambda p: p.secs)

            summary: dict[str, Any] = {
                "total_data_points": len(power_curve.data),
                "max_power_watts": max_power_point.watts,
                "max_power_duration_seconds": max_power_point.secs,
                "duration_range": {
                    "min_seconds": min_duration.secs,
                    "max_seconds": max_duration.secs,
                },
            }

            # If we have dates, show range
            dates = [p.date for p in power_curve.data if p.date]
            if dates:
                summary["effort_date_range"] = {"oldest": min(dates), "newest": max(dates)}

            # Calculate FTP and power zones (based on 20-min power)
            twenty_min_point = min(
                power_curve.data,
                key=lambda p: abs(p.secs - 1200),
                default=None,
            )

            ftp_analysis = None
            if twenty_min_point and abs(twenty_min_point.secs - 1200) <= 120:
                # Estimate FTP as 95% of 20-min power
                estimated_ftp = int((twenty_min_point.watts or 0) * 0.95)

                if estimated_ftp > 0:
                    # Power zones
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
                        "twenty_min_power": twenty_min_point.watts,
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
