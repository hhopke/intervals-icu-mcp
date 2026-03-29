"""Intervals.icu MCP Server - FastMCP entry point."""

from typing import Any

from dotenv import load_dotenv
from fastmcp import FastMCP

# Load environment variables
load_dotenv()

# Initialize FastMCP server
mcp = FastMCP("intervals_icu_mcp")

# Register middleware
from .middleware import ConfigMiddleware

mcp.add_middleware(ConfigMiddleware())

# Import and register tools
from .tools.activities import (
    bulk_create_manual_activities,
    delete_activity,
    download_activity_file,
    download_fit_file,
    download_gpx_file,
    get_activities_around,
    get_activity_details,
    get_recent_activities,
    search_activities,
    search_activities_full,
    update_activity,
    update_activity_streams,
)
from .tools.activity_analysis import (
    get_activity_intervals,
    get_activity_streams,
    get_best_efforts,
    get_gap_histogram,
    get_hr_histogram,
    get_pace_histogram,
    get_power_histogram,
    search_intervals,
)
from .tools.athlete import get_athlete_profile, get_fitness_summary
from .tools.curves import get_hr_curves, get_pace_curves
from .tools.event_management import (
    apply_training_plan,
    bulk_create_events,
    bulk_delete_events,
    create_event,
    delete_event,
    duplicate_events,
    update_event,
)
from .tools.events import get_calendar_events, get_event, get_upcoming_workouts
from .tools.gear import (
    create_gear,
    create_gear_reminder,
    delete_gear,
    get_gear_list,
    update_gear,
    update_gear_reminder,
)
from .tools.performance import get_power_curves
from .tools.sport_settings import (
    apply_sport_settings,
    create_sport_settings,
    delete_sport_settings,
    get_sport_settings,
    update_sport_settings,
)
from .tools.wellness import get_wellness_data, get_wellness_for_date, update_wellness
from .tools.workout_library import get_workout_library, get_workouts_in_folder

# Register activity tools
mcp.tool(
    name="icu_get_recent_activities",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(get_recent_activities)
mcp.tool(
    name="icu_get_activity_details",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(get_activity_details)
mcp.tool(
    name="icu_search_activities",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(search_activities)
mcp.tool(
    name="icu_search_activities_full",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(search_activities_full)
mcp.tool(
    name="icu_get_activities_around",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(get_activities_around)
mcp.tool(
    name="icu_update_activity",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(update_activity)
mcp.tool(
    name="icu_update_activity_streams",
    annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True},
)(update_activity_streams)
mcp.tool(
    name="icu_bulk_create_manual_activities",
    annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True},
)(bulk_create_manual_activities)
mcp.tool(
    name="icu_delete_activity",
    annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True},
)(delete_activity)
mcp.tool(
    name="icu_download_activity_file",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(download_activity_file)
mcp.tool(
    name="icu_download_fit_file",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(download_fit_file)
mcp.tool(
    name="icu_download_gpx_file",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(download_gpx_file)

# Register activity analysis tools
mcp.tool(
    name="icu_get_activity_streams",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(get_activity_streams)
mcp.tool(
    name="icu_get_activity_intervals",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(get_activity_intervals)
mcp.tool(
    name="icu_get_best_efforts",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(get_best_efforts)
mcp.tool(
    name="icu_search_intervals",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(search_intervals)
mcp.tool(
    name="icu_get_power_histogram",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(get_power_histogram)
mcp.tool(
    name="icu_get_hr_histogram",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(get_hr_histogram)
mcp.tool(
    name="icu_get_pace_histogram",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(get_pace_histogram)
mcp.tool(
    name="icu_get_gap_histogram",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(get_gap_histogram)

# Register athlete tools
mcp.tool(
    name="icu_get_athlete_profile",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(get_athlete_profile)
mcp.tool(
    name="icu_get_fitness_summary",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(get_fitness_summary)

# Register wellness tools
mcp.tool(
    name="icu_get_wellness_data",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(get_wellness_data)
mcp.tool(
    name="icu_get_wellness_for_date",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(get_wellness_for_date)
mcp.tool(
    name="icu_update_wellness",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(update_wellness)

# Register event/calendar tools
mcp.tool(
    name="icu_get_calendar_events",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(get_calendar_events)
mcp.tool(
    name="icu_get_upcoming_workouts",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(get_upcoming_workouts)
mcp.tool(
    name="icu_get_event",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(get_event)
mcp.tool(
    name="icu_create_event",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)(create_event)
mcp.tool(
    name="icu_update_event",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(update_event)
mcp.tool(
    name="icu_delete_event",
    annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True},
)(delete_event)
mcp.tool(
    name="icu_bulk_create_events",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)(bulk_create_events)
mcp.tool(
    name="icu_bulk_delete_events",
    annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True},
)(bulk_delete_events)
mcp.tool(
    name="icu_duplicate_events",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)(duplicate_events)
mcp.tool(
    name="icu_apply_training_plan",
    annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True},
)(apply_training_plan)

# Register performance/curve tools
mcp.tool(
    name="icu_get_power_curves",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(get_power_curves)
mcp.tool(
    name="icu_get_hr_curves",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(get_hr_curves)
mcp.tool(
    name="icu_get_pace_curves",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(get_pace_curves)

# Register workout library tools
mcp.tool(
    name="icu_get_workout_library",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(get_workout_library)
mcp.tool(
    name="icu_get_workouts_in_folder",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(get_workouts_in_folder)

# Register gear management tools
mcp.tool(
    name="icu_get_gear_list",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(get_gear_list)
mcp.tool(
    name="icu_create_gear",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)(create_gear)
mcp.tool(
    name="icu_update_gear",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(update_gear)
mcp.tool(
    name="icu_delete_gear",
    annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True},
)(delete_gear)
mcp.tool(
    name="icu_create_gear_reminder",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)(create_gear_reminder)
mcp.tool(
    name="icu_update_gear_reminder",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(update_gear_reminder)

# Register sport settings tools
mcp.tool(
    name="icu_get_sport_settings",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(get_sport_settings)
mcp.tool(
    name="icu_update_sport_settings",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)(update_sport_settings)
mcp.tool(
    name="icu_apply_sport_settings",
    annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True},
)(apply_sport_settings)
mcp.tool(
    name="icu_create_sport_settings",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)(create_sport_settings)
mcp.tool(
    name="icu_delete_sport_settings",
    annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True},
)(delete_sport_settings)


# MCP Resources - Provide ongoing context
@mcp.resource("intervals-icu://athlete/profile")
async def athlete_profile_resource() -> str:
    """Complete athlete profile with fitness metrics and sport settings for context."""
    from .auth import load_config
    from .client import ICUAPIError, ICUClient
    from .response_builder import ResponseBuilder

    # Load config directly since resources don't go through middleware
    config = load_config()

    try:
        async with ICUClient(config) as client:
            # Get athlete profile
            athlete = await client.get_athlete()

            # Build minimal profile data
            data: dict[str, Any] = {
                "profile": {
                    "id": athlete.id,
                    "name": athlete.name,
                    "weight": athlete.weight,
                },
                "fitness": {
                    "ctl": athlete.ctl,
                    "atl": athlete.atl,
                    "tsb": athlete.tsb,
                    "ramp_rate": athlete.ramp_rate,
                },
            }

            # Add sport settings if available
            if athlete.sport_settings:
                sport_data: list[dict[str, str | int | float | None]] = []
                for sport in athlete.sport_settings:
                    sport_info: dict[str, str | int | float | None] = {
                        "type": sport.type,
                    }
                    if sport.ftp:
                        sport_info["ftp"] = sport.ftp
                    if sport.fthr:
                        sport_info["fthr"] = sport.fthr
                    if sport.pace_threshold:
                        sport_info["threshold_pace"] = sport.pace_threshold
                    sport_data.append(sport_info)
                data["sports"] = sport_data

            return ResponseBuilder.build_response(data, metadata={"type": "athlete_profile"})
    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")


@mcp.resource("intervals-icu://workout-syntax")
async def workout_syntax_resource() -> str:
    """Intervals.icu structured workout syntax reference.

    Complete specification for writing structured workouts using Intervals.icu
    plain-text format. Use this when creating WORKOUT events via create_event
    or bulk_create_events - place the workout text in the 'description' field.

    Covers: durations, distances, power/HR/pace targets, zones, ramps, repeats,
    cadence, rest intervals, and text prompts for cycling, running, and swimming.
    """
    from .workout_syntax import WORKOUT_SYNTAX_SPEC

    return WORKOUT_SYNTAX_SPEC


# MCP Prompts - Templates for common queries
@mcp.prompt()
async def generate_workout(
    sport: str = "Ride",
    workout_type: str = "endurance",
    duration_minutes: str = "60",
) -> str:
    """Generate a structured workout for Intervals.icu.

    Args:
        sport: Sport type ("Ride", "Run", or "Swim")
        workout_type: Type of workout (e.g., "endurance", "threshold", "vo2max", "sweet spot", "tempo", "intervals")
        duration_minutes: Approximate total duration in minutes
    """
    return f"""Create a structured {workout_type} workout for {sport}, approximately {duration_minutes} minutes long.

IMPORTANT: Before creating the workout, read the intervals-icu://workout-syntax resource
to understand the exact syntax format that Intervals.icu expects.

Steps:
1. Read the workout syntax resource (intervals-icu://workout-syntax)
2. Check the athlete's current fitness using get_fitness_summary and get_sport_settings
3. Design an appropriate {workout_type} workout for {sport} based on their fitness level
4. Create the workout using create_event with:
   - category: "WORKOUT"
   - event_type: "{sport}"
   - description: The structured workout text using the syntax from the resource
   - A descriptive name

Guidelines:
- Always include Warmup, Main Set, and Cooldown sections
- Use appropriate intensity targets based on the athlete's thresholds
- Include cadence targets for cycling workouts
- Use blank lines between sections
- For {workout_type} workouts, follow standard training methodology
- Present the workout plan for approval before creating the event"""


@mcp.prompt()
async def analyze_recent_training(days: str = "30") -> str:
    """Analyze my Intervals.icu training over a time period.

    Args:
        days: Number of days to analyze (e.g., "7", "30", "90")
    """
    return f"""Analyze my Intervals.icu training over the past {days} days.

Focus on:
1. Training volume (distance, time, elevation, training load)
2. Training distribution by activity type
3. Fitness trends (CTL/ATL/TSB)
4. Recovery metrics (HRV, sleep, wellness)
5. Key insights and recommendations

Use get_recent_activities with days_back={days}, get_fitness_summary for CTL/ATL/TSB analysis,
and get_wellness_data to assess recovery. Present findings in a clear, actionable format."""


@mcp.prompt()
async def performance_analysis(metric: str = "power") -> str:
    """Analyze my performance across different durations.

    Args:
        metric: Performance metric to analyze ("power", "hr", or "pace")
    """
    if metric == "power":
        return """Analyze my power performance across all durations.

Include:
1. Power curve with best efforts (5s, 1m, 5m, 20m, 1h)
2. Estimated FTP from 20-minute power
3. Power zones and training recommendations
4. Trends and recent improvements

Use get_power_curves to get the data, then provide detailed analysis with training suggestions."""
    elif metric == "hr":
        return """Analyze my heart rate performance.

Include:
1. HR curve with best efforts across durations
2. Max HR and FTHR estimation
3. HR zones based on max HR
4. Cardiac fitness trends

Use get_hr_curves to get HR curve data, then provide detailed analysis with zone recommendations."""
    else:
        return """Analyze my pace performance.

Include:
1. Best pace efforts across distances
2. Threshold pace estimation from curve
3. Pace zones for different training intensities
4. Recent running trends

Use get_pace_curves to get pace curve data (optionally with GAP for trail running),
then provide detailed analysis with training recommendations."""


@mcp.prompt()
async def activity_deep_dive(activity_id: str) -> str:
    """Get comprehensive analysis of a specific activity.

    Args:
        activity_id: The ID of the activity to analyze
    """
    return f"""Provide a comprehensive analysis of activity {activity_id}.

Include:
1. Basic metrics (distance, time, pace/speed, elevation)
2. Power and heart rate data (if available)
3. Training load and intensity
4. Interval structure and workout compliance (if structured)
5. Best efforts found in this activity
6. Subjective metrics (feel, RPE)
7. Performance insights and comparison to recent activities

Use get_activity_details for basic info, get_activity_intervals for workout structure,
get_best_efforts for peak performances, and optionally get_activity_streams for
time-series visualization. Compare with similar recent activities to provide context."""


@mcp.prompt()
async def recovery_check() -> str:
    """Assess my current recovery and readiness to train."""
    return """Assess my current recovery status and readiness for training.

Include:
1. Recent wellness metrics (HRV, resting HR, sleep quality)
2. Training stress balance (TSB, CTL/ATL)
3. Subjective metrics (fatigue, soreness, mood)
4. Recovery trends over past week
5. Training recommendations

Use get_wellness_data for recent wellness, get_fitness_summary for TSB analysis,
then provide clear guidance on training intensity."""


@mcp.prompt()
async def training_plan_review() -> str:
    """Review my upcoming training plan."""
    return """Review my upcoming training plan and provide feedback.

Include:
1. Upcoming workouts from calendar
2. Planned training load vs current fitness
3. Recovery days and intensity distribution
4. Workout library structure (if using a training plan)
5. Recommendations for adjustments

Use get_upcoming_workouts to see the plan, get_fitness_summary for current form,
and optionally get_workout_library to see available training plans, then evaluate
if the plan is appropriate and suggest any modifications."""


@mcp.prompt()
async def plan_training_week(goal: str = "balanced") -> str:
    """Help plan my training week based on current form and goals.

    Args:
        goal: Training goal ("balanced", "build", "recover", "peak")
    """
    return f"""Help me plan my training week with a "{goal}" focus.

Steps:
1. Check current fitness status (CTL/ATL/TSB) using get_fitness_summary
2. Review recent training load and patterns with get_recent_activities
3. Check recovery markers with get_wellness_data
4. Review workout library for appropriate sessions with get_workout_library
5. Create planned workouts for the week using create_event

Provide a structured weekly plan with:
- Workout types and intensities for each day
- Recovery days placement
- Expected weekly training load
- Reasoning for the schedule based on current form

Then offer to create the events in my calendar if I approve the plan."""


@mcp.prompt()
async def verify_setup() -> str:
    """Verify the MCP server is working by exercising core tools against your account."""
    return """Verify my Intervals.icu MCP server setup by running through each tool category.
Run each step, report the result, and flag any errors.

Step 1 - Athlete Profile:
  Call get_athlete_profile. Confirm name, athlete ID, and that sport settings are returned.

Step 2 - Fitness Metrics:
  Call get_fitness_summary. Confirm CTL, ATL, TSB, and ramp rate are present.

Step 3 - Recent Activities:
  Call get_recent_activities with limit=3 and days_back=14.
  Confirm activities are returned with id, name, type, and distance.
  Check that average_watts is populated for cycling activities (verifies Pydantic alias mapping).

Step 4 - Activity Search:
  Pick the name of one activity from Step 3 and call search_activities with that name.
  Confirm it returns matching results.

Step 5 - Calendar Events:
  Call get_calendar_events with days_ahead=14 and days_back=7.
  Confirm each event includes an id field (needed for update/delete operations).
  Note whether dates are returned as full ISO-8601 datetimes.

Step 6 - Upcoming Workouts:
  Call get_upcoming_workouts with limit=5.
  Confirm each workout includes an id field.

Step 7 - Wellness Data:
  Call get_wellness_data with days=7. Confirm HRV, sleep, and subjective metrics are present.

Step 8 - Power Curves:
  Call get_power_curves with period="42days". Confirm data points are returned.

Step 9 - Event Lifecycle (create, read, update, duplicate, delete):
  a) Call create_event with start_date tomorrow, name="MCP Verification Test",
     category="NOTE". Confirm the event is created and an id is returned.
  b) Call get_event with that id. Confirm the event details match.
  c) Call update_event with that id, changing the name to "MCP Verification Test - Updated".
  d) Call duplicate_events with that id (as JSON array) to create a copy 1 week later.
     Confirm the duplicate has a new id and correct date.
  e) Call delete_event on both the original and duplicated event ids.
     Confirm both are deleted.

Step 10 - Workout Library:
  Call get_workout_library. Confirm folders are returned.

Present a summary table at the end:
| Step | Tool(s) | Status | Notes |
Report any failures with the error message so they can be investigated."""


@mcp.prompt()
async def verify_multi_athlete(athlete_id: str) -> str:
    """Verify multi-athlete support by querying a specific athlete's data.

    Args:
        athlete_id: The Intervals.icu athlete ID to test against (e.g., "i987654")
    """
    return f"""Verify multi-athlete support by querying athlete {athlete_id}.
This tests that the athlete_id parameter correctly routes API requests to a different
athlete than the default configured one. You must have coach access to this athlete.

Run each step with athlete_id="{athlete_id}" and report the result.

Step 1 - Activities:
  Call get_recent_activities with athlete_id="{athlete_id}", limit=3, days_back=14.
  Confirm activities are returned for the correct athlete.

Step 2 - Activity Search:
  Call search_activities with athlete_id="{athlete_id}" and a generic query like "ride".

Step 3 - Calendar Events:
  Call get_calendar_events with athlete_id="{athlete_id}", days_ahead=14.
  Confirm events include id fields.

Step 4 - Upcoming Workouts:
  Call get_upcoming_workouts with athlete_id="{athlete_id}", limit=5.

Step 5 - Get Event:
  If any events were returned in Step 3, call get_event with one of those ids
  and athlete_id="{athlete_id}".

Step 6 - Event Lifecycle:
  a) Call create_event with athlete_id="{athlete_id}", start_date tomorrow,
     name="Coach Test Event", category="NOTE".
  b) Call update_event with athlete_id="{athlete_id}", changing the name.
  c) Call duplicate_events with athlete_id="{athlete_id}" to create a copy 1 week later.
  d) Call delete_event on both events with athlete_id="{athlete_id}".

Present a summary table:
| Step | Tool | athlete_id Used | Status | Notes |
Flag any 401/403 errors as permission issues (coach access required)."""


def main():
    """Main entry point for the Intervals.icu MCP server."""
    # Run the server with stdio transport (default)
    mcp.run()


if __name__ == "__main__":
    main()
