"""Strava-source detection helpers.

Activities synced from Strava come back from the Intervals.icu API as a near-empty
stub due to Strava's November 2024 API policy: Intervals.icu cannot legally
redistribute Strava-sourced data through their API. This module detects that case
and produces a clear, actionable message so callers can surface it instead of
letting an LLM hallucinate metrics from empty fields.
"""

from ..client import ICUAPIError, ICUClient
from ..models import Activity

STRAVA_LIMITATION_NOTE = (
    "This activity was synced from Strava, which restricts redistribution of its "
    "activity data through third-party APIs (Strava policy change, November 2024). "
    "As a result, Intervals.icu cannot expose detailed metrics, streams, intervals, "
    "or histograms for Strava-sourced activities through its API — even though the "
    "activity may display correctly in the Intervals.icu web UI. "
    "To make this data available, connect your device directly to Intervals.icu "
    "(e.g. Garmin Connect, Wahoo, Zwift, COROS, Polar, or Suunto direct sync) "
    "instead of routing it through Strava."
)


def strava_limitation_note(activity: Activity) -> str | None:
    """Return a user-facing note when an activity is a Strava-restricted stub.

    Returns None for non-Strava activities and for Strava activities that still
    have metric data (so we don't false-positive on, e.g., a manually-edited
    Strava activity that happens to have populated fields).
    """
    if activity.source != "STRAVA":
        return None

    # Stub Strava activities have no metric/distance/duration data.
    has_metrics = any(
        v is not None
        for v in (
            activity.distance,
            activity.moving_time,
            activity.elapsed_time,
            activity.total_elevation_gain,
            activity.average_watts,
            activity.normalized_power,
            activity.average_heartrate,
            activity.max_heartrate,
            activity.average_cadence,
            activity.average_speed,
        )
    )
    if has_metrics:
        return None
    return STRAVA_LIMITATION_NOTE


async def fetch_strava_limitation_note(client: ICUClient, activity_id: str) -> str | None:
    """Fetch the activity and check whether it is Strava-restricted.

    Used by tools (streams, intervals, histograms, best efforts) that don't
    otherwise need the Activity object — only call this on the empty-result
    path so we don't add latency for normal activities.
    """
    try:
        activity = await client.get_activity(activity_id=activity_id)
    except ICUAPIError:
        return None
    return strava_limitation_note(activity)
