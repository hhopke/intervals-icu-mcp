"""Activity analysis tools for Intervals.icu MCP server."""

import asyncio
import bisect
import difflib
import math
import re
import statistics
from itertools import zip_longest
from typing import Annotated, Any, cast

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..models import ActivityStream
from ..response_builder import ResponseBuilder
from ._strava import fetch_strava_limitation_note


async def get_activity_streams(
    activity_id: Annotated[str, "Activity ID to fetch streams for"],
    streams: Annotated[
        list[str] | None,
        "List of stream types (e.g., ['watts', 'heartrate', 'cadence']). If not specified, the activity's default streams are fetched — which does NOT include raw_heartrate or fixed_heartrate; ask for those by name.",
    ] = None,
    max_points: Annotated[
        int | None,
        "Thin every returned stream to at most this many samples by keeping every Nth one (the same N for all streams, so indices stay aligned). Omit for full resolution. ~500 is plenty to trace a route or see the shape of a ride. Samples are not always 1 s apart, so include 'time' to know when each kept sample was recorded.",
    ] = None,
    start_s: Annotated[
        float | None, "Only return samples recorded at or after this elapsed second"
    ] = None,
    end_s: Annotated[
        float | None, "Only return samples recorded before this elapsed second"
    ] = None,
    names_only: Annotated[
        bool, "Return only available stream names and lengths, no data (cheap discovery)"
    ] = False,
    ctx: Context | None = None,
) -> str:
    """Fetch RAW per-sample time-series of one activity — second-by-second arrays for power, HR, cadence, speed, altitude, GPS, temperature, grade, etc.

    Heavy payload. Use only when you need the underlying signal for
    visualization or custom analysis. Most "how was my ride?" questions
    are better answered by get_activity_details (summary metrics) or
    get_activity_intervals (per-lap breakdown).

    Stream-type filter accepts any of: watts, heartrate, cadence,
    velocity_smooth, altitude, distance, time, latlng, temp, moving,
    grade_smooth, raw_heartrate, fixed_heartrate.

    `latlng` comes back as [lat, lng] pairs (null where the sample has no
    GPS fix).

    `left_right_balance` (dual-sided power meters) is the RIGHT pedal's share
    of power in percent (FIT convention), not the left's: a stream averaging
    48 means L 52% / R 48%. The response adds a `stream_notes` entry saying so whenever the
    stream is returned.

    `heartrate` is CORRECTED data: Intervals.icu replaces readings above the
    athlete's configured max HR with an interpolated line at import, so it can
    never exceed that setting. `raw_heartrate` is the uncorrected trace and is
    the only way to see a genuine new max that was clipped away — the platform
    never raises the setting on its own. Request it explicitly; it is not in
    the default set.

    For averages over time windows (HR/power drift etc.) use icu_get_stream_stats
    instead. Aliases: VE/ventilation -> tidal_volume_min, BR -> respiration.
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    if max_points is not None and max_points < 1:
        return ResponseBuilder.build_error_response(
            "max_points must be at least 1", error_type="validation_error"
        )
    if start_s is not None and end_s is not None and end_s <= start_s:
        return ResponseBuilder.build_error_response(
            "end_s must be greater than start_s", error_type="validation_error"
        )

    aliases_applied: dict[str, str] = {}
    if streams:
        streams, aliases_applied = _resolve_stream_names(streams)
    windowed = start_s is not None or end_s is not None
    if windowed and streams and "time" not in streams:
        # The time stream is needed to locate the window
        streams = [*streams, "time"]

    try:
        async with ICUClient(config) as client:
            stream_list, _ = await _fetch_streams_tolerant(client, activity_id, streams)

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

            for s in stream_list:
                name = s.type or s.name or "unknown"
                available_streams.append(name)
                data: Any = s.data
                data2: Any = s.data2
                if data is None:
                    continue
                # latlng carries latitude in `data` and longitude in `data2`.
                # Paired for any stream with a data2 array so none of it is dropped;
                # zip_longest pads a length mismatch with None instead of truncating.
                if isinstance(data, list) and isinstance(data2, list) and data2:
                    lats = cast(list[Any], data)
                    lngs = cast(list[Any], data2)
                    streams_dict[name] = [
                        None if lat is None and lng is None else [lat, lng]
                        for lat, lng in zip_longest(lats, lngs)
                    ]
                else:
                    streams_dict[name] = data

            if names_only:
                names_data: dict[str, Any] = {
                    "activity_id": activity_id,
                    "available_streams": available_streams,
                    "stream_lengths": {
                        name: len(d)  # type: ignore[arg-type]
                        for name, d in streams_dict.items()
                        if isinstance(d, list)
                    },
                }
                if aliases_applied:
                    names_data["aliases_applied"] = aliases_applied
                return ResponseBuilder.build_response(
                    data=names_data, query_type="activity_streams"
                )

            window_info: dict[str, Any] | None = None
            time_data = streams_dict.get("time")
            if windowed and isinstance(time_data, list):
                times = cast(list[float], time_data)
                lo = bisect.bisect_left(times, start_s) if start_s is not None else 0
                hi = bisect.bisect_left(times, end_s) if end_s is not None else len(times)
                for name, d in streams_dict.items():
                    if isinstance(d, list):
                        streams_dict[name] = d[lo:hi]
                window_info = {"start_index": lo, "end_index": hi}

            full_length = max(
                (len(d) for d in streams_dict.values() if isinstance(d, list)),  # type: ignore[arg-type]
                default=0,
            )
            step = 1
            if max_points is not None and full_length > max_points:
                # Same step for every stream keeps index i aligned across streams
                step = math.ceil(full_length / max_points)
                for name, d in streams_dict.items():
                    if isinstance(d, list):
                        streams_dict[name] = d[::step]

            stream_lengths = {
                name: len(d)  # type: ignore[arg-type]
                for name, d in streams_dict.items()
                if isinstance(d, list)
            }

            result_data: dict[str, Any] = {
                "activity_id": activity_id,
                "streams": streams_dict,
                "available_streams": available_streams,
                "stream_lengths": stream_lengths,
            }
            if "left_right_balance" in streams_dict:
                result_data["stream_notes"] = {
                    "left_right_balance": (
                        "Percent of power from the RIGHT pedal (FIT convention; consistent "
                        "with a reported average of 48 showing as L 52% / R 48% in the "
                        "Intervals.icu UI). Left = 100 - value. Cross-check against the "
                        "activity's average L/R if the side matters."
                    )
                }
            if aliases_applied:
                result_data["aliases_applied"] = aliases_applied
            missing = [n for n in streams or [] if n not in available_streams]
            if missing:
                result_data["missing_streams"] = missing
            if window_info is not None:
                result_data["window"] = {
                    **window_info,
                    "note": "Index i here is original sample start_index + i (before any step).",
                }
            elif windowed:
                result_data["window"] = {"note": "No time stream; start_s/end_s ignored"}
            if step > 1:
                result_data["downsampling"] = {
                    "step": step,
                    "original_length": full_length,
                    "note": f"Index i here is original sample i*{step}.",
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
    """Find the top-N peak efforts WITHIN a single activity for a given stream + target duration or distance.

    Different from get_*_curves (which span many activities). Useful for
    "what was my best 20-min power on this ride?" or "show my top 5k
    splits in this run." Requires at least one of duration or distance.
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


_INTERVAL_TARGET_TYPES = {"AUTO", "POWER", "HR", "PACE"}

# The API returns full Activity objects (~180 fields each); only these carry
# information about the interval match itself or identify the activity.
_INTERVAL_SEARCH_FIELDS = [
    "id",
    "name",
    "type",
    "start_date_local",
    "distance",
    "moving_time",
    "icu_training_load",
    "interval_summary",
]


async def search_intervals(
    interval_type: Annotated[
        str | None,
        "Interval target type: AUTO, POWER, HR, or PACE (what the interval "
        "targeted — not the sport and not a workout-step label)",
    ] = None,
    min_duration: Annotated[int | None, "Minimum interval duration in seconds"] = None,
    max_duration: Annotated[int | None, "Maximum interval duration in seconds"] = None,
    min_intensity: Annotated[
        int | None, "Minimum interval intensity in percent of threshold (e.g. 80)"
    ] = None,
    max_intensity: Annotated[
        int | None, "Maximum interval intensity in percent of threshold (e.g. 105)"
    ] = None,
    limit: Annotated[int, "Maximum number of matching activities to return"] = 30,
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Search intervals ACROSS ALL the athlete's activities (cross-activity).

    Different from icu_get_activity_intervals (single-activity). Use to track
    progress on a workout type ("all my threshold intervals over the last
    year") or find comparable historical sessions. Returns the activities
    containing matching intervals, each with an `interval_summary` like
    "2x 8m 162w" (reps x duration at target).
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    if interval_type and interval_type.upper() not in _INTERVAL_TARGET_TYPES:
        return ResponseBuilder.build_error_response(
            f"Invalid interval_type '{interval_type}'. "
            f"Must be one of: {', '.join(sorted(_INTERVAL_TARGET_TYPES))}.",
            error_type="validation_error",
        )

    try:
        async with ICUClient(config) as client:
            results = await client.search_intervals(
                athlete_id=athlete_id,
                interval_type=interval_type.upper() if interval_type else None,
                min_duration=min_duration,
                max_duration=max_duration,
                min_intensity=min_intensity,
                max_intensity=max_intensity,
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
                if min_intensity:
                    search_criteria.append(f"min_intensity={min_intensity}%")
                if max_intensity:
                    search_criteria.append(f"max_intensity={max_intensity}%")

                criteria_str = ", ".join(search_criteria) if search_criteria else "your criteria"

                return ResponseBuilder.build_response(
                    data={"activities": [], "count": 0},
                    metadata={"message": f"No intervals found matching {criteria_str}"},
                )

            activities = [
                {k: item.get(k) for k in _INTERVAL_SEARCH_FIELDS if item.get(k) is not None}
                for item in results
            ]

            result_data = {
                "activities": activities,
                "count": len(activities),
                "search_criteria": {
                    "interval_type": interval_type,
                    "min_duration_seconds": min_duration,
                    "max_duration_seconds": max_duration,
                    "min_intensity_percent": min_intensity,
                    "max_intensity_percent": max_intensity,
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
    """Time-in-zone DISTRIBUTION of power within a single activity (histogram buckets, time per bucket).

    Different from icu_get_power_curves (best efforts across many activities).
    Use for "how was my workout intensity distributed?", training-zone
    breakdown.
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
    """Time-in-zone DISTRIBUTION of heart rate within a single activity (histogram buckets, time per bucket).

    Different from icu_get_hr_curves (best efforts across many activities).
    Use for cardiovascular load breakdown and HR-zone time-in-zone.
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
    """Time-in-zone DISTRIBUTION of pace within a single running activity (histogram buckets, time per bucket).

    Different from icu_get_pace_curves (best efforts across many activities).
    Use for pace-distribution / consistency analysis. For elevation-
    normalized pace use icu_get_gap_histogram.
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
    """Time-in-zone DISTRIBUTION of grade-adjusted pace (GAP) within a single activity — elevation-normalized.

    Use for trail running where raw pace is misleading. For raw (non-
    elevation-normalized) pace use icu_get_pace_histogram.
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


# Common names for streams that Intervals.icu stores under another key. Tyme Wear
# ventilation / breath rate are mirrored into tidal_volume_min / respiration at import.
_STREAM_ALIASES: dict[str, str] = {
    "power": "watts",
    "hr": "heartrate",
    "heart_rate": "heartrate",
    "ve": "tidal_volume_min",
    "ventilation": "tidal_volume_min",
    "minute_ventilation": "tidal_volume_min",
    "br": "respiration",
    "breath_rate": "respiration",
    "breathing_rate": "respiration",
    "respiration_rate": "respiration",
    "speed": "velocity_smooth",
    "temperature": "temp",
    "grade": "grade_smooth",
}

# Built-in stream types, matched case-insensitively. Anything else is passed through
# unchanged because custom stream codes (e.g. TymeVentilation) are case-sensitive.
_STANDARD_STREAMS = frozenset(
    {
        "time",
        "watts",
        "heartrate",
        "cadence",
        "velocity_smooth",
        "altitude",
        "distance",
        "latlng",
        "temp",
        "moving",
        "grade_smooth",
        "raw_heartrate",
        "fixed_heartrate",
        "left_right_balance",
        "torque",
        "respiration",
        "tidal_volume",
        "tidal_volume_min",
    }
)


def _resolve_stream_names(names: list[str]) -> tuple[list[str], dict[str, str]]:
    """Map aliases and miscased built-in names to API stream types.

    Returns the de-duplicated resolved names and a {requested: resolved} map of
    every name that was changed.
    """
    resolved: list[str] = []
    applied: dict[str, str] = {}
    for name in names:
        key = name.strip().lower()
        target = _STREAM_ALIASES.get(key) or (key if key in _STANDARD_STREAMS else name.strip())
        if target != name:
            applied[name] = target
        if target not in resolved:
            resolved.append(target)
    return resolved, applied


_INVALID_STREAM_RE = re.compile(r"Invalid stream type \[([^\]]+)\]")


async def _fetch_streams_tolerant(
    client: ICUClient, activity_id: str, names: list[str] | None
) -> tuple[list[ActivityStream], list[str]]:
    """Fetch streams, dropping names the API rejects as invalid instead of failing.

    The API answers 422 for an unknown lower-case name (it treats those as built-in
    types) but silently omits unknown custom codes, so both end up reported as missing.
    """
    remaining = list(names) if names else None
    rejected: list[str] = []
    while True:
        try:
            return await client.get_activity_streams(activity_id, remaining), rejected
        except ICUAPIError as e:
            match = _INVALID_STREAM_RE.search(e.message)
            if e.status_code != 422 or not match or not remaining:
                raise
            bad = match.group(1)
            if bad not in remaining:
                raise
            remaining.remove(bad)
            rejected.append(bad)
            if not remaining:
                return [], rejected


def _stream_suggestions(missing: str, available: list[str]) -> list[str]:
    exact = [a for a in available if a.lower() == missing.lower()]
    if exact:
        return exact
    lowered = {a.lower(): a for a in available}
    close = difflib.get_close_matches(missing.lower(), list(lowered), n=3, cutoff=0.6)
    return [lowered[c] for c in close]


# Intervals.icu interval-stats keys surfaced per window, renamed for the response.
_ICU_WINDOW_FIELDS: dict[str, str] = {
    "moving_time": "moving_s",
    "average_watts": "avg_watts",
    "weighted_average_watts": "np_watts",
    "average_heartrate": "avg_hr",
    "max_heartrate": "max_hr",
    "decoupling": "decoupling_pct",
    "average_respiration": "avg_breath_rate",
    "average_tidal_volume_min": "avg_ventilation_l_min",
    "average_cadence": "avg_cadence",
    "average_temp": "avg_temp_c",
    "average_dfa_a1": "avg_dfa_a1",
    "training_load": "training_load",
}

# Ratios derived from the Intervals.icu window averages: response key -> numerator.
_ICU_RATIOS: dict[str, str] = {
    "hr_per_watt": "avg_hr",
    "ve_per_watt": "avg_ventilation_l_min",
    "br_per_watt": "avg_breath_rate",
}

_MAX_WINDOWS = 24
_ICU_CONCURRENCY = 4


def _round(value: float, digits: int = 1) -> float:
    return round(value, digits)


def _build_windows(
    total_s: float,
    block_minutes: float | None,
    parts: int | None,
    windows: list[list[float]] | None,
) -> list[tuple[float, float]] | str:
    """Return [(start_s, end_s)] or an error message."""
    given = sum(x is not None for x in (block_minutes, parts, windows))
    if given > 1:
        return "Give only one of block_minutes, parts or windows"
    if block_minutes is not None:
        if block_minutes <= 0:
            return "block_minutes must be positive"
        size = block_minutes * 60
        result: list[tuple[float, float]] = []
        start = 0.0
        while start < total_s:
            result.append((start, min(start + size, total_s)))
            start += size
        return result
    if parts is not None:
        if parts < 1:
            return "parts must be at least 1"
        size = total_s / parts
        return [(i * size, total_s if i == parts - 1 else (i + 1) * size) for i in range(parts)]
    if windows is not None:
        result = []
        for w in windows:
            if len(w) != 2 or w[0] < 0 or w[1] <= w[0]:
                return f"Invalid window {w}: expected [start_s, end_s] with 0 <= start_s < end_s"
            result.append((float(w[0]), float(w[1])))
        return result
    return [(0.0, total_s)]


def _trailing_mean(
    time: list[float], values: list[float | None], seconds: float
) -> list[float | None]:
    """Mean of the non-null values in the trailing `seconds` (by recording time)."""
    out: list[float | None] = []
    total = 0.0
    count = 0
    lo = 0
    for i, v in enumerate(values):
        if v is not None:
            total += v
            count += 1
        while time[i] - time[lo] >= seconds:
            old = values[lo]
            if old is not None:
                total -= old
                count -= 1
            lo += 1
        out.append(total / count if count else None)
    return out


def _filtered_window(
    i0: int,
    i1: int,
    time: list[float],
    data: dict[str, list[Any]],
    mask_power: list[float | None],
    min_power: float | None,
    max_power: float | None,
    lag_s: float,
) -> dict[str, Any]:
    """Stats computed here on the samples of [i0, i1) that pass the power filter."""
    watts = data.get("watts")
    n = len(time)
    kept: list[int] = []
    for i in range(i0, i1):
        p = mask_power[i] if watts is not None else 0.0
        if p is None:
            continue
        if min_power is not None and p < min_power:
            continue
        if max_power is not None and p > max_power:
            continue
        kept.append(i)

    streams_out: dict[str, Any] = {}
    ratios: dict[str, float] = {}
    for name, values in data.items():
        if name == "watts" or lag_s == 0:
            idx = kept
        else:
            # Pair power at t with this stream at t + lag_s
            idx = [min(bisect.bisect_left(time, time[i] + lag_s), n - 1) for i in kept]
        vals = [v for j in idx if isinstance(v := values[j], int | float)]
        if not vals:
            streams_out[name] = {"valid_s": 0}
            continue
        streams_out[name] = {
            "mean": _round(statistics.fmean(vals)),
            "median": _round(statistics.median(vals)),
            "min": _round(min(vals)),
            "max": _round(max(vals)),
            "valid_s": len(vals),
        }
        if watts is not None and name != "watts":
            pairs = [
                (values[j], watts[i])
                for i, j in zip(kept, idx, strict=True)
                if isinstance(values[j], int | float) and isinstance(watts[i], int | float)
            ]
            mean_w = statistics.fmean(w for _, w in pairs) if pairs else 0
            if mean_w > 0:
                ratios[f"{name}_per_watt"] = _round(
                    statistics.fmean(v for v, _ in pairs) / mean_w, 3
                )

    result: dict[str, Any] = {
        "kept_s": len(kept),
        "excluded_s": (i1 - i0) - len(kept),
        "streams": streams_out,
    }
    if ratios:
        result["ratios"] = ratios
    return result


def _drift(values: list[float | None]) -> list[float | None] | None:
    """Percent change of each value against the first window's value."""
    base = values[0] if values else None
    if not base:
        return None
    return [None if v is None else _round((v / base - 1) * 100) for v in values]


async def get_stream_stats(
    activity_id: Annotated[str, "Activity ID"],
    block_minutes: Annotated[
        float | None, "Split the activity into consecutive blocks of this many minutes"
    ] = None,
    parts: Annotated[int | None, "Split the activity into this many equal parts"] = None,
    windows: Annotated[
        list[list[float]] | None,
        "Explicit windows as [[start_s, end_s], ...] in elapsed seconds. "
        "Give one of block_minutes / parts / windows; none = whole activity.",
    ] = None,
    streams: Annotated[
        list[str] | None,
        "Extra streams to compute here (mean/median/min/max and per-watt ratio), e.g. "
        "['VE', 'BR', 'TymeVentilation']. Custom names are case-sensitive.",
    ] = None,
    min_power: Annotated[
        float | None, "Drop samples below this power (coasting/stops) from `filtered`"
    ] = None,
    max_power: Annotated[
        float | None, "Drop samples above this power (surges) from `filtered`"
    ] = None,
    power_smoothing_s: Annotated[
        int, "Apply min/max_power to the trailing N-second mean power instead of raw 1-s power"
    ] = 0,
    lag_s: Annotated[
        int,
        "In `filtered`, pair power at t with the other streams at t+lag_s (HR lags power ~15-30 s)",
    ] = 0,
    ctx: Context | None = None,
) -> str:
    """Compute exact SUMMARY statistics of one activity per time WINDOW (every N minutes, N equal parts, or explicit ranges) on the server, without returning raw streams.

    Use for drift questions: "how did HR/power and ventilation/power develop over the
    ride?", "compare 15-min blocks, ignoring everything below 120 W". Prefer this over
    icu_get_activity_streams for any averaging; use icu_get_activity_intervals for the
    activity's own laps.

    Each window has `icu` — computed by Intervals.icu on the whole window (avg/NP watts,
    HR, decoupling, breath rate, ventilation, DFA a1, plus hr/ve/br per watt) — and, when
    `streams` or a power filter is given, `filtered` — mean/median/min/max computed here on
    samples passing the filter, plus <stream>_per_watt. `analysis` adds Intervals.icu's
    whole-ride Pw:HR decoupling and each ratio's drift vs the first window.

    Aliases: VE/ventilation -> tidal_volume_min, BR/breath_rate -> respiration (Tyme
    sensor data is mirrored there). Missing streams are reported with suggestions.
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    if power_smoothing_s < 0 or lag_s < 0:
        return ResponseBuilder.build_error_response(
            "power_smoothing_s and lag_s must not be negative", error_type="validation_error"
        )
    if min_power is not None and max_power is not None and min_power > max_power:
        return ResponseBuilder.build_error_response(
            "min_power must not exceed max_power", error_type="validation_error"
        )

    extra, aliases_applied = _resolve_stream_names(streams or [])
    use_filtered = bool(extra) or min_power is not None or max_power is not None
    wanted = ["time"]
    if use_filtered:
        wanted += [s for s in ["watts", "heartrate", *extra] if s not in wanted]

    try:
        async with ICUClient(config) as client:
            stream_list, _ = await _fetch_streams_tolerant(client, activity_id, wanted)
            data: dict[str, list[Any]] = {}
            for s in stream_list:
                stream_data: Any = s.data
                if isinstance(stream_data, list):
                    data[s.type or s.name or ""] = cast(list[Any], stream_data)
            time_raw = data.pop("time", None)
            if not time_raw:
                analysis: dict[str, Any] = {}
                strava_note = await fetch_strava_limitation_note(client, activity_id)
                if strava_note:
                    analysis["data_availability"] = strava_note
                return ResponseBuilder.build_response(
                    data={"activity_id": activity_id, "windows": []},
                    analysis=analysis if analysis else None,
                    metadata={"message": "No stream data available for this activity"},
                )
            time = [float(t) for t in time_raw]
            n = len(time)

            missing_info: dict[str, list[str]] = {}
            missing = [s for s in extra if s not in data]
            if missing:
                everything = await client.get_activity_streams(activity_id, None)
                available = [s.type or s.name or "" for s in everything]
                missing_info = {m: _stream_suggestions(m, available) for m in missing}

            built = _build_windows(time[-1] + 1, block_minutes, parts, windows)
            if isinstance(built, str):
                return ResponseBuilder.build_error_response(built, error_type="validation_error")
            if len(built) > _MAX_WINDOWS:
                return ResponseBuilder.build_error_response(
                    f"{len(built)} windows requested; the limit is {_MAX_WINDOWS}. "
                    "Use larger blocks or fewer parts.",
                    error_type="validation_error",
                )

            index_ranges = [
                (bisect.bisect_left(time, start), bisect.bisect_left(time, end))
                for start, end in built
            ]

            semaphore = asyncio.Semaphore(_ICU_CONCURRENCY)

            async def icu_stats(i0: int, i1: int) -> dict[str, Any] | None:
                if i1 <= i0:
                    return None
                async with semaphore:
                    return await client.get_interval_stats(activity_id, i0, i1)

            async def power_hr() -> dict[str, Any] | None:
                try:
                    return await client.get_power_vs_hr(activity_id)
                except ICUAPIError:
                    return None

            icu_results, pvhr = await asyncio.gather(
                asyncio.gather(*(icu_stats(i0, i1) for i0, i1 in index_ranges)),
                power_hr(),
            )

            mask_power: list[float | None] = []
            if use_filtered and "watts" in data:
                watts = cast(list[float | None], data["watts"])
                mask_power = (
                    _trailing_mean(time, watts, power_smoothing_s)
                    if power_smoothing_s > 0
                    else watts
                )

            windows_out: list[dict[str, Any]] = []
            for (start, end), (i0, i1), raw in zip(built, index_ranges, icu_results, strict=True):
                window: dict[str, Any] = {"start_s": round(start), "end_s": round(end)}
                if raw is None:
                    window["note"] = "No samples in this window"
                    windows_out.append(window)
                    continue
                icu = {
                    out_key: _round(raw[key], 3 if key == "average_dfa_a1" else 1)
                    for key, out_key in _ICU_WINDOW_FIELDS.items()
                    if isinstance(raw.get(key), int | float)
                }
                watts_avg = icu.get("avg_watts")
                if watts_avg:
                    for ratio_key, num_key in _ICU_RATIOS.items():
                        if num_key in icu:
                            icu[ratio_key] = _round(icu[num_key] / watts_avg, 3)
                window["icu"] = icu
                if use_filtered:
                    window["filtered"] = _filtered_window(
                        i0, i1, time, data, mask_power, min_power, max_power, lag_s
                    )
                windows_out.append(window)

            analysis_out: dict[str, Any] = {}
            if len(windows_out) > 1:
                drift: dict[str, Any] = {}
                for ratio_key in _ICU_RATIOS:
                    series = [w.get("icu", {}).get(ratio_key) for w in windows_out]
                    if (d := _drift(series)) is not None:
                        drift[f"icu.{ratio_key}"] = d
                ratio_names = {
                    r for w in windows_out for r in w.get("filtered", {}).get("ratios", {})
                }
                for ratio_key in sorted(ratio_names):
                    series = [
                        w.get("filtered", {}).get("ratios", {}).get(ratio_key) for w in windows_out
                    ]
                    if (d := _drift(series)) is not None:
                        drift[f"filtered.{ratio_key}"] = d
                if drift:
                    analysis_out["ratio_drift_pct_vs_first_window"] = drift
            if pvhr and pvhr.get("powerHr") is not None:
                analysis_out["power_hr_whole_activity"] = {
                    "source": "Intervals.icu Pw:HR (watts per bpm, warm-up/cool-down excluded)",
                    "watts_per_bpm": _round(pvhr["powerHr"], 3),
                    "first_half": _round(pvhr.get("powerHrFirst") or 0, 3),
                    "second_half": _round(pvhr.get("powerHrSecond") or 0, 3),
                    "decoupling_pct": _round(pvhr.get("decoupling") or 0),
                    "hr_lag_s": pvhr.get("hrLag"),
                    "excluded_warmup_s": pvhr.get("warmup"),
                    "excluded_cooldown_s": pvhr.get("cooldown"),
                }

            result_data: dict[str, Any] = {
                "activity_id": activity_id,
                "sample_count": n,
                "windows": windows_out,
            }
            if aliases_applied:
                result_data["aliases_applied"] = aliases_applied
            if missing_info:
                result_data["missing_streams"] = {
                    name: {"did_you_mean": sugg} for name, sugg in missing_info.items()
                }

            notes = ["`icu` covers the whole window and ignores min/max_power."]
            if use_filtered:
                notes.append(
                    "`filtered` counts 1 sample as 1 s; excluded_s = samples removed by the "
                    "power filter or without power."
                )
            return ResponseBuilder.build_response(
                data=result_data,
                analysis=analysis_out if analysis_out else None,
                metadata={"notes": notes},
                query_type="stream_stats",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )
