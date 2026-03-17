"""Activity analysis tools for Intervals.icu MCP server."""

from typing import Annotated, Any, cast

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..response_builder import ResponseBuilder


async def get_activity_streams(
    activity_id: Annotated[str, "Activity ID to fetch streams for"],
    streams: Annotated[
        list[str] | None,
        "List of stream types (e.g., ['watts', 'heartrate', 'cadence']). If not specified, all streams are fetched.",
    ] = None,
    ctx: Context | None = None,
) -> str:
    """Get time-series data streams for an activity.

    Returns second-by-second data for various metrics like power, heart rate,
    cadence, speed, altitude, etc. This data is essential for detailed workout
    analysis and visualization.

    Available stream types:
    - watts: Power data
    - heartrate: Heart rate data
    - cadence: Cadence (rpm or spm)
    - velocity_smooth: Smoothed speed
    - altitude: Elevation
    - distance: Cumulative distance
    - time: Time stamps
    - latlng: GPS coordinates
    - temp: Temperature
    - moving: Moving status
    - grade_smooth: Gradient

    Args:
        activity_id: The unique ID of the activity
        streams: Optional list of specific stream types to fetch

    Returns:
        JSON string with time-series data streams
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            streams_data = await client.get_activity_streams(activity_id, streams)

            # Count available streams
            available_streams: list[str] = []
            stream_lengths: dict[str, int] = {}

            for stream_name in [
                "watts",
                "heartrate",
                "cadence",
                "velocity_smooth",
                "altitude",
                "distance",
                "time",
                "latlng",
                "temp",
                "moving",
                "grade_smooth",
            ]:
                stream_value: Any = getattr(streams_data, stream_name, None)
                if stream_value is not None:
                    available_streams.append(stream_name)
                    if isinstance(stream_value, list):
                        stream_lengths[stream_name] = len(cast(list[Any], stream_value))

            if not available_streams:
                return ResponseBuilder.build_response(
                    data={"streams": {}, "available_streams": []},
                    metadata={"message": "No stream data available for this activity"},
                )

            # Build response
            streams_dict: dict[str, Any] = {}
            for stream_name in available_streams:
                stream_value = getattr(streams_data, stream_name)
                if stream_value is not None:
                    streams_dict[stream_name] = stream_value

            result_data = {
                "activity_id": activity_id,
                "streams": streams_dict,
                "available_streams": available_streams,
                "stream_lengths": stream_lengths,
            }

            return ResponseBuilder.build_response(
                data=result_data,
                query_type="activity_streams",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def get_activity_intervals(
    activity_id: Annotated[str, "Activity ID to fetch intervals for"],
    ctx: Context | None = None,
) -> str:
    """Get structured interval data for an activity.

    Returns the intervals/segments of a workout, including targets, actual performance,
    and interval types (warm-up, work, rest, cool-down). Essential for analyzing
    structured workouts and training compliance.

    Args:
        activity_id: The unique ID of the activity

    Returns:
        JSON string with interval data
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            intervals = await client.get_activity_intervals(activity_id)

            if not intervals:
                return ResponseBuilder.build_response(
                    data={"intervals": [], "count": 0, "activity_id": activity_id},
                    metadata={"message": "No intervals found for this activity"},
                )

            intervals_data: list[dict[str, Any]] = []
            for interval in intervals:
                interval_item: dict[str, Any] = {
                    "id": interval.id,
                    "type": interval.type,
                }

                if interval.start is not None:
                    interval_item["start_seconds"] = interval.start
                if interval.end is not None:
                    interval_item["end_seconds"] = interval.end
                if interval.duration is not None:
                    interval_item["duration_seconds"] = interval.duration

                # Performance metrics
                performance: dict[str, Any] = {}
                if interval.average_watts:
                    performance["average_watts"] = interval.average_watts
                if interval.normalized_power:
                    performance["normalized_power"] = interval.normalized_power
                if interval.average_heartrate:
                    performance["average_heartrate"] = interval.average_heartrate
                if interval.max_heartrate:
                    performance["max_heartrate"] = interval.max_heartrate
                if interval.average_cadence:
                    performance["average_cadence"] = interval.average_cadence
                if interval.average_speed:
                    performance["average_speed_meters_per_sec"] = interval.average_speed
                if interval.distance:
                    performance["distance_meters"] = interval.distance

                if performance:
                    interval_item["performance"] = performance

                # Target data
                if interval.target:
                    interval_item["target_description"] = interval.target
                if interval.target_min is not None or interval.target_max is not None:
                    interval_item["target_range"] = {
                        "min": interval.target_min,
                        "max": interval.target_max,
                    }

                intervals_data.append(interval_item)

            # Calculate summary
            work_intervals = [i for i in intervals if i.type and "WORK" in i.type.upper()]
            rest_intervals = [i for i in intervals if i.type and "REST" in i.type.upper()]

            summary = {
                "total_intervals": len(intervals),
                "work_intervals": len(work_intervals),
                "rest_intervals": len(rest_intervals),
            }

            # Calculate total work time
            if work_intervals:
                total_work_time = sum(i.duration for i in work_intervals if i.duration)
                if total_work_time:
                    summary["total_work_time_seconds"] = total_work_time

            result_data = {
                "activity_id": activity_id,
                "intervals": intervals_data,
                "summary": summary,
            }

            return ResponseBuilder.build_response(
                data=result_data,
                query_type="activity_intervals",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def get_best_efforts(
    activity_id: Annotated[str, "Activity ID to analyze"],
    ctx: Context | None = None,
) -> str:
    """Get best efforts/peak performances from an activity.

    Analyzes the activity to find the best performances across various durations
    (e.g., best 5-second power, best 1-minute power, best 20-minute power).
    Similar to Strava segments but for all durations.

    Args:
        activity_id: The unique ID of the activity

    Returns:
        JSON string with best efforts data
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            best_efforts = await client.get_best_efforts(activity_id)

            if not best_efforts:
                return ResponseBuilder.build_response(
                    data={"best_efforts": [], "count": 0, "activity_id": activity_id},
                    metadata={"message": "No best efforts found for this activity"},
                )

            efforts_data: list[dict[str, Any]] = []
            for effort in best_efforts:
                effort_item: dict[str, Any] = {
                    "name": effort.name,
                    "elapsed_time_seconds": effort.elapsed_time,
                }

                if effort.moving_time:
                    effort_item["moving_time_seconds"] = effort.moving_time
                if effort.distance:
                    effort_item["distance_meters"] = effort.distance

                # Performance metrics
                performance: dict[str, Any] = {}
                if effort.average_watts:
                    performance["average_watts"] = effort.average_watts
                if effort.normalized_power:
                    performance["normalized_power"] = effort.normalized_power
                if effort.average_heartrate:
                    performance["average_heartrate"] = effort.average_heartrate
                if effort.average_cadence:
                    performance["average_cadence"] = effort.average_cadence
                if effort.average_speed:
                    performance["average_speed_meters_per_sec"] = effort.average_speed

                if performance:
                    effort_item["performance"] = performance

                # Location in activity
                if effort.start_index is not None:
                    effort_item["start_index"] = effort.start_index
                if effort.end_index is not None:
                    effort_item["end_index"] = effort.end_index

                efforts_data.append(effort_item)

            result_data = {
                "activity_id": activity_id,
                "best_efforts": efforts_data,
                "count": len(efforts_data),
            }

            return ResponseBuilder.build_response(
                data=result_data,
                query_type="best_efforts",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def search_intervals(
    interval_type: Annotated[str | None, "Type of interval to search for"] = None,
    min_duration: Annotated[int | None, "Minimum duration in seconds"] = None,
    max_duration: Annotated[int | None, "Maximum duration in seconds"] = None,
    limit: Annotated[int, "Maximum number of results to return"] = 30,
    ctx: Context | None = None,
) -> str:
    """Search for similar intervals across all activities.

    Finds intervals matching specific criteria across your activity history.
    Useful for tracking progress on specific workout types or finding comparable
    training sessions.

    Args:
        interval_type: Type of interval (e.g., "WORK", "THRESHOLD", "VO2MAX")
        min_duration: Minimum interval duration in seconds
        max_duration: Maximum interval duration in seconds
        limit: Maximum number of results to return (default 30)

    Returns:
        JSON string with matching intervals
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            results = await client.search_intervals(
                interval_type=interval_type,
                min_duration=min_duration,
                max_duration=max_duration,
                limit=limit,
            )

            if not results:
                search_criteria: list[str] = []
                if interval_type:
                    search_criteria.append(f"type={interval_type}")
                if min_duration:
                    search_criteria.append(f"min_duration={min_duration}s")
                if max_duration:
                    search_criteria.append(f"max_duration={max_duration}s")

                criteria_str = ", ".join(search_criteria) if search_criteria else "your criteria"

                return ResponseBuilder.build_response(
                    data={"intervals": [], "count": 0},
                    metadata={"message": f"No intervals found matching {criteria_str}"},
                )

            result_data = {
                "intervals": results,
                "count": len(results),
                "search_criteria": {
                    "interval_type": interval_type,
                    "min_duration_seconds": min_duration,
                    "max_duration_seconds": max_duration,
                },
            }

            return ResponseBuilder.build_response(
                data=result_data,
                query_type="interval_search",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def get_power_histogram(
    activity_id: Annotated[str, "Activity ID to analyze"],
    ctx: Context | None = None,
) -> str:
    """Get power distribution histogram for an activity.

    Analyzes how power was distributed across the activity, showing time spent
    at different power levels. Useful for understanding workout intensity distribution
    and identifying training zones.

    Args:
        activity_id: The unique ID of the activity

    Returns:
        JSON string with power distribution bins
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            histogram = await client.get_power_histogram(activity_id)

            if not histogram.bins:
                return ResponseBuilder.build_response(
                    data={"histogram": [], "activity_id": activity_id},
                    metadata={"message": "No power histogram data available for this activity"},
                )

            bins_data: list[dict[str, Any]] = []
            for bin_item in histogram.bins:
                bin_data: dict[str, Any] = {
                    "power_range": {"min_watts": int(bin_item.min), "max_watts": int(bin_item.max)},
                    "count": bin_item.count,
                }
                if bin_item.secs is not None:
                    bin_data["time_seconds"] = bin_item.secs
                bins_data.append(bin_data)

            result_data = {
                "activity_id": activity_id,
                "bins": bins_data,
                "total_samples": histogram.total_count,
            }
            if histogram.total_secs is not None:
                result_data["total_time_seconds"] = histogram.total_secs

            return ResponseBuilder.build_response(
                data=result_data,
                query_type="power_histogram",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def get_hr_histogram(
    activity_id: Annotated[str, "Activity ID to analyze"],
    ctx: Context | None = None,
) -> str:
    """Get heart rate distribution histogram for an activity.

    Analyzes how heart rate was distributed across the activity, showing time spent
    at different HR levels. Useful for understanding cardiovascular load and
    training zone distribution.

    Args:
        activity_id: The unique ID of the activity

    Returns:
        JSON string with HR distribution bins
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            histogram = await client.get_hr_histogram(activity_id)

            if not histogram.bins:
                return ResponseBuilder.build_response(
                    data={"histogram": [], "activity_id": activity_id},
                    metadata={"message": "No HR histogram data available for this activity"},
                )

            bins_data: list[dict[str, Any]] = []
            for bin_item in histogram.bins:
                bin_data: dict[str, Any] = {
                    "hr_range": {"min_bpm": int(bin_item.min), "max_bpm": int(bin_item.max)},
                    "count": bin_item.count,
                }
                if bin_item.secs is not None:
                    bin_data["time_seconds"] = bin_item.secs
                bins_data.append(bin_data)

            result_data = {
                "activity_id": activity_id,
                "bins": bins_data,
                "total_samples": histogram.total_count,
            }
            if histogram.total_secs is not None:
                result_data["total_time_seconds"] = histogram.total_secs

            return ResponseBuilder.build_response(
                data=result_data,
                query_type="hr_histogram",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def get_pace_histogram(
    activity_id: Annotated[str, "Activity ID to analyze"],
    ctx: Context | None = None,
) -> str:
    """Get pace distribution histogram for an activity.

    Analyzes how pace was distributed across the activity, showing time spent
    at different pace levels. Useful for running activities to understand
    pace distribution and consistency.

    Args:
        activity_id: The unique ID of the activity

    Returns:
        JSON string with pace distribution bins
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            histogram = await client.get_pace_histogram(activity_id)

            if not histogram.bins:
                return ResponseBuilder.build_response(
                    data={"histogram": [], "activity_id": activity_id},
                    metadata={"message": "No pace histogram data available for this activity"},
                )

            bins_data: list[dict[str, Any]] = []
            for bin_item in histogram.bins:
                # Convert pace from min/km to formatted string
                min_minutes = int(bin_item.min)
                min_seconds = int((bin_item.min - min_minutes) * 60)
                max_minutes = int(bin_item.max)
                max_seconds = int((bin_item.max - max_minutes) * 60)

                bin_data: dict[str, Any] = {
                    "pace_range": {
                        "min_pace_min_per_km": bin_item.min,
                        "max_pace_min_per_km": bin_item.max,
                        "min_pace_formatted": f"{min_minutes}:{min_seconds:02d} /km",
                        "max_pace_formatted": f"{max_minutes}:{max_seconds:02d} /km",
                    },
                    "count": bin_item.count,
                }
                if bin_item.secs is not None:
                    bin_data["time_seconds"] = bin_item.secs
                bins_data.append(bin_data)

            result_data = {
                "activity_id": activity_id,
                "bins": bins_data,
                "total_samples": histogram.total_count,
            }
            if histogram.total_secs is not None:
                result_data["total_time_seconds"] = histogram.total_secs

            return ResponseBuilder.build_response(
                data=result_data,
                query_type="pace_histogram",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def get_gap_histogram(
    activity_id: Annotated[str, "Activity ID to analyze"],
    ctx: Context | None = None,
) -> str:
    """Get grade-adjusted pace (GAP) histogram for an activity.

    Analyzes grade-adjusted pace distribution, which normalizes pace for elevation
    changes. Useful for trail running to understand true effort distribution
    independent of terrain.

    Args:
        activity_id: The unique ID of the activity

    Returns:
        JSON string with GAP distribution bins
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            histogram = await client.get_gap_histogram(activity_id)

            if not histogram.bins:
                return ResponseBuilder.build_response(
                    data={"histogram": [], "activity_id": activity_id},
                    metadata={"message": "No GAP histogram data available for this activity"},
                )

            bins_data: list[dict[str, Any]] = []
            for bin_item in histogram.bins:
                # Convert GAP from min/km to formatted string
                min_minutes = int(bin_item.min)
                min_seconds = int((bin_item.min - min_minutes) * 60)
                max_minutes = int(bin_item.max)
                max_seconds = int((bin_item.max - max_minutes) * 60)

                bin_data: dict[str, Any] = {
                    "gap_range": {
                        "min_gap_min_per_km": bin_item.min,
                        "max_gap_min_per_km": bin_item.max,
                        "min_gap_formatted": f"{min_minutes}:{min_seconds:02d} /km",
                        "max_gap_formatted": f"{max_minutes}:{max_seconds:02d} /km",
                    },
                    "count": bin_item.count,
                }
                if bin_item.secs is not None:
                    bin_data["time_seconds"] = bin_item.secs
                bins_data.append(bin_data)

            result_data = {
                "activity_id": activity_id,
                "bins": bins_data,
                "total_samples": histogram.total_count,
                "note": "GAP (Grade Adjusted Pace) normalizes pace for elevation changes",
            }
            if histogram.total_secs is not None:
                result_data["total_time_seconds"] = histogram.total_secs

            return ResponseBuilder.build_response(
                data=result_data,
                query_type="gap_histogram",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )
