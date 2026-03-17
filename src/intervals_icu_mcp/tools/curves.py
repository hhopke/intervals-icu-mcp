"""Additional performance curve tools for Intervals.icu MCP server."""

from datetime import datetime, timedelta
from typing import Annotated, Any

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..response_builder import ResponseBuilder


async def get_hr_curves(
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
            hr_curve = await client.get_hr_curves(oldest=oldest)

            if not hr_curve.data or len(hr_curve.data) == 0:
                return ResponseBuilder.build_response(
                    data={"hr_curve": [], "period": period_label},
                    metadata={
                        "message": f"No HR curve data available for {period_label}. "
                        "Complete some activities with heart rate to build your HR curve."
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
                    hr_curve.data,
                    key=lambda p: abs(p.secs - seconds),
                    default=None,
                )

                if closest_point and abs(closest_point.secs - seconds) <= seconds * 0.1:
                    # Only include if within 10% of target duration
                    effort: dict[str, Any] = {
                        "bpm": closest_point.bpm,
                        "duration_seconds": closest_point.secs,
                    }
                    if closest_point.date:
                        effort["date"] = closest_point.date
                    if closest_point.src_activity_id:
                        effort["activity_id"] = closest_point.src_activity_id

                    peak_efforts[label] = effort

            # Calculate summary statistics
            max_hr_point = max(hr_curve.data, key=lambda p: p.bpm or 0)
            min_duration = min(hr_curve.data, key=lambda p: p.secs)
            max_duration = max(hr_curve.data, key=lambda p: p.secs)

            summary: dict[str, Any] = {
                "total_data_points": len(hr_curve.data),
                "max_hr_bpm": max_hr_point.bpm,
                "max_hr_duration_seconds": max_hr_point.secs,
                "duration_range": {
                    "min_seconds": min_duration.secs,
                    "max_seconds": max_duration.secs,
                },
            }

            # If we have dates, show range
            dates = [p.date for p in hr_curve.data if p.date]
            if dates:
                summary["effort_date_range"] = {"oldest": min(dates), "newest": max(dates)}

            # Calculate HR zones (based on max HR if available)
            hr_zones: dict[str, dict[str, int]] | None = None
            if max_hr_point.bpm:
                max_hr = max_hr_point.bpm
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
            pace_curve = await client.get_pace_curves(oldest=oldest, use_gap=use_gap)

            if not pace_curve.data or len(pace_curve.data) == 0:
                return ResponseBuilder.build_response(
                    data={"pace_curve": [], "period": period_label, "gap_enabled": use_gap},
                    metadata={
                        "message": f"No pace curve data available for {period_label}. "
                        "Complete some runs/swims to build your pace curve."
                    },
                )

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
            peak_efforts: dict[str, dict[str, Any]] = {}
            for seconds, label in key_durations.items():
                # Find closest data point
                closest_point = min(
                    pace_curve.data,
                    key=lambda p: abs(p.secs - seconds),
                    default=None,
                )

                if closest_point and abs(closest_point.secs - seconds) <= seconds * 0.1:
                    # Only include if within 10% of target duration
                    effort: dict[str, Any] = {
                        "pace_min_per_km": closest_point.pace,
                        "duration_seconds": closest_point.secs,
                    }
                    # Convert pace to min:sec per km format
                    if closest_point.pace:
                        minutes = int(closest_point.pace)
                        seconds_part = int((closest_point.pace - minutes) * 60)
                        effort["pace_formatted"] = f"{minutes}:{seconds_part:02d} /km"

                    if closest_point.date:
                        effort["date"] = closest_point.date
                    if closest_point.src_activity_id:
                        effort["activity_id"] = closest_point.src_activity_id

                    peak_efforts[label] = effort

            # Calculate summary statistics
            best_pace_point = min(pace_curve.data, key=lambda p: p.pace or float("inf"))
            min_duration = min(pace_curve.data, key=lambda p: p.secs)
            max_duration = max(pace_curve.data, key=lambda p: p.secs)

            summary: dict[str, Any] = {
                "total_data_points": len(pace_curve.data),
                "best_pace_min_per_km": best_pace_point.pace,
                "best_pace_duration_seconds": best_pace_point.secs,
                "duration_range": {
                    "min_seconds": min_duration.secs,
                    "max_seconds": max_duration.secs,
                },
                "gap_enabled": use_gap,
            }

            if best_pace_point.pace:
                minutes = int(best_pace_point.pace)
                seconds_part = int((best_pace_point.pace - minutes) * 60)
                summary["best_pace_formatted"] = f"{minutes}:{seconds_part:02d} /km"

            # If we have dates, show range
            dates = [p.date for p in pace_curve.data if p.date]
            if dates:
                summary["effort_date_range"] = {"oldest": min(dates), "newest": max(dates)}

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
