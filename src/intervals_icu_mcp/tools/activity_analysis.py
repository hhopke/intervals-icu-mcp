"""Activity analysis tools for Intervals.icu MCP server."""

from typing import Annotated, Any

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..response_builder import ResponseBuilder
from ._strava import fetch_strava_limitation_note


async def get_activity_streams(
    activity_id: Annotated[str, "Activity ID to fetch streams for"],
    streams: Annotated[
        list[str] | None,
        "List of stream types (e.g., ['watts', 'heartrate', 'cadence']). If not specified, all streams are fetched.",
    ] = None,
    ctx: Context | None = None,
) -> str:
    """Fetch RAW per-sample time-series of one activity — second-by-second arrays for power, HR, cadence, speed, altitude, GPS, temperature, grade, etc.

    Heavy payload. Use only when you need the underlying signal for
    visualization or custom analysis. Most "how was my ride?" questions
    are better answered by get_activity_details (summary metrics) or
    get_activity_intervals (per-lap breakdown).

    Stream-type filter accepts any of: watts, heartrate, cadence,
    velocity_smooth, altitude, distance, time, latlng, temp, moving,
    grade_smooth.
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            stream_list = await client.get_activity_streams(activity_id, streams)

            if not stream_list:
                analysis: dict[str, Any] = {}
                strava_note = await fetch_strava_limitation_note(client, activity_id)
                if strava_note:
                    analysis["data_availability"] = strava_note
                return ResponseBuilder.build_response(
                    data={"streams": {}, "available_streams": []},
                    analysis=analysis if analysis else None,
                    metadata={"message": "No stream data available for this activity"},
                )

            # Build response from list of ActivityStream objects
            available_streams: list[str] = []
            streams_dict: dict[str, Any] = {}
            stream_lengths: dict[str, int] = {}

            for s in stream_list:
                name = s.type or s.name or "unknown"
                available_streams.append(name)
                if s.data is not None:
                    streams_dict[name] = s.data
                    data = s.data
                    if isinstance(data, list):
                        stream_lengths[name] = len(data)  # type: ignore[arg-type]

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
    """Fetch the per-LAP / per-interval breakdown of one activity — each segment with its target, actual power/HR/pace, and type (warm-up / work / rest / cool-down).

    Use for workout-compliance analysis, lap-by-lap review,
    "did I hit my intervals?". For headline summary metrics use
    get_activity_details; for raw second-by-second data use
    get_activity_streams.
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            intervals = await client.get_activity_intervals(activity_id)

            if not intervals:
                analysis: dict[str, Any] = {}
                strava_note = await fetch_strava_limitation_note(client, activity_id)
                if strava_note:
                    analysis["data_availability"] = strava_note
                return ResponseBuilder.build_response(
                    data={"intervals": [], "count": 0, "activity_id": activity_id},
                    analysis=analysis if analysis else None,
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
    stream: Annotated[
        str, "Stream to search for best efforts: 'watts', 'heartrate', or 'pace'"
    ] = "watts",
    duration: Annotated[
        int | None,
        "Duration of each effort in seconds (e.g., 60 for 1-min, 1200 for 20-min). "
        "At least one of 'duration' or 'distance' is required.",
    ] = None,
    distance: Annotated[
        float | None,
        "Distance of each effort in meters (e.g., 5000 for 5k). "
        "At least one of 'duration' or 'distance' is required.",
    ] = None,
    count: Annotated[int, "Number of efforts to return (default 8)"] = 8,
    ctx: Context | None = None,
) -> str:
    """Get best efforts/peak performances from an activity.

    Analyzes the activity to find the best performances for a given stream
    and duration/distance. Requires at least one of duration or distance.

    Args:
        activity_id: The unique ID of the activity
        stream: Stream to search (watts, heartrate, pace, etc.)
        duration: Duration of each effort in seconds
        distance: Distance of each effort in meters
        count: Number of efforts to return (default 8)

    Returns:
        JSON string with best efforts data
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    if duration is None and distance is None:
        return ResponseBuilder.build_error_response(
            "At least one of 'duration' or 'distance' is required",
            error_type="validation_error",
        )

    try:
        async with ICUClient(config) as client:
            best_efforts = await client.get_best_efforts(
                activity_id, stream=stream, duration=duration, distance=distance, count=count
            )

            if not best_efforts.efforts:
                analysis: dict[str, Any] = {}
                strava_note = await fetch_strava_limitation_note(client, activity_id)
                if strava_note:
                    analysis["data_availability"] = strava_note
                return ResponseBuilder.build_response(
                    data={"best_efforts": [], "count": 0, "activity_id": activity_id},
                    analysis=analysis if analysis else None,
                    metadata={"message": "No best efforts found for this activity"},
                )

            efforts_data: list[dict[str, Any]] = []
            for effort in best_efforts.efforts:
                effort_item: dict[str, Any] = {}
                if effort.average is not None:
                    effort_item["average"] = effort.average
                if effort.duration is not None:
                    effort_item["duration_seconds"] = effort.duration
                if effort.distance is not None:
                    effort_item["distance_meters"] = effort.distance
                if effort.start_index is not None:
                    effort_item["start_index"] = effort.start_index
                if effort.end_index is not None:
                    effort_item["end_index"] = effort.end_index
                efforts_data.append(effort_item)

            result_data = {
                "activity_id": activity_id,
                "stream": stream,
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
        JSON with `buckets` (each `{power_range: {min_watts, max_watts}, time_seconds}`) and `total_time_seconds`.
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            buckets = await client.get_power_histogram(activity_id)

            if not buckets:
                analysis: dict[str, Any] = {}
                strava_note = await fetch_strava_limitation_note(client, activity_id)
                if strava_note:
                    analysis["data_availability"] = strava_note
                return ResponseBuilder.build_response(
                    data={"buckets": [], "activity_id": activity_id},
                    analysis=analysis if analysis else None,
                    metadata={"message": "No power histogram data available for this activity"},
                )

            buckets_data: list[dict[str, Any]] = [
                {
                    "power_range": {
                        "min_watts": int(b.min) if b.min is not None else None,
                        "max_watts": int(b.max) if b.max is not None else None,
                    },
                    "time_seconds": b.secs or 0,
                }
                for b in buckets
            ]

            return ResponseBuilder.build_response(
                data={
                    "activity_id": activity_id,
                    "buckets": buckets_data,
                    "total_time_seconds": sum(b.secs or 0 for b in buckets),
                },
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
        JSON with `buckets` (each `{hr_range: {min_bpm, max_bpm}, time_seconds}`) and `total_time_seconds`.
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            buckets = await client.get_hr_histogram(activity_id)

            if not buckets:
                analysis: dict[str, Any] = {}
                strava_note = await fetch_strava_limitation_note(client, activity_id)
                if strava_note:
                    analysis["data_availability"] = strava_note
                return ResponseBuilder.build_response(
                    data={"buckets": [], "activity_id": activity_id},
                    analysis=analysis if analysis else None,
                    metadata={"message": "No HR histogram data available for this activity"},
                )

            buckets_data: list[dict[str, Any]] = [
                {
                    "hr_range": {
                        "min_bpm": int(b.min) if b.min is not None else None,
                        "max_bpm": int(b.max) if b.max is not None else None,
                    },
                    "time_seconds": b.secs or 0,
                }
                for b in buckets
            ]

            return ResponseBuilder.build_response(
                data={
                    "activity_id": activity_id,
                    "buckets": buckets_data,
                    "total_time_seconds": sum(b.secs or 0 for b in buckets),
                },
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
        JSON with `buckets` (each `{pace_range: {min, max}, time_seconds}`) and `total_time_seconds`.
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            buckets = await client.get_pace_histogram(activity_id)

            if not buckets:
                analysis: dict[str, Any] = {}
                strava_note = await fetch_strava_limitation_note(client, activity_id)
                if strava_note:
                    analysis["data_availability"] = strava_note
                return ResponseBuilder.build_response(
                    data={"buckets": [], "activity_id": activity_id},
                    analysis=analysis if analysis else None,
                    metadata={"message": "No pace histogram data available for this activity"},
                )

            buckets_data: list[dict[str, Any]] = [
                {
                    "pace_range": {"min": b.min, "max": b.max},
                    "time_seconds": b.secs or 0,
                }
                for b in buckets
            ]

            return ResponseBuilder.build_response(
                data={
                    "activity_id": activity_id,
                    "buckets": buckets_data,
                    "total_time_seconds": sum(b.secs or 0 for b in buckets),
                },
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
        JSON with `buckets` (each `{gap_range: {min, max}, time_seconds}`) and `total_time_seconds`.
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            buckets = await client.get_gap_histogram(activity_id)

            if not buckets:
                analysis: dict[str, Any] = {}
                strava_note = await fetch_strava_limitation_note(client, activity_id)
                if strava_note:
                    analysis["data_availability"] = strava_note
                return ResponseBuilder.build_response(
                    data={"buckets": [], "activity_id": activity_id},
                    analysis=analysis if analysis else None,
                    metadata={"message": "No GAP histogram data available for this activity"},
                )

            buckets_data: list[dict[str, Any]] = [
                {
                    "gap_range": {"min": b.min, "max": b.max},
                    "time_seconds": b.secs or 0,
                }
                for b in buckets
            ]

            return ResponseBuilder.build_response(
                data={
                    "activity_id": activity_id,
                    "buckets": buckets_data,
                    "total_time_seconds": sum(b.secs or 0 for b in buckets),
                    "note": "GAP (Grade Adjusted Pace) normalizes pace for elevation changes",
                },
                query_type="gap_histogram",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )
