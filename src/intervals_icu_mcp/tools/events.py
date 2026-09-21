"""Calendar and event tools for Intervals.icu MCP server."""

from datetime import datetime, timedelta
from typing import Annotated, Any

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..response_builder import ResponseBuilder


async def get_calendar_events(
    days_ahead: Annotated[int, "Number of days to look ahead"] = 7,
    days_back: Annotated[int, "Number of days to look back"] = 0,
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Fetch ALL calendar entries in a date window — workouts, notes, races, goals, life-event blocks.

    Use for "what's on my calendar?", "show this week", broad calendar
    queries. For just the planned WORKOUT entries (filtered) use
    icu_get_upcoming_workouts. For one specific event by ID use get_event.
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        # Calculate date range
        oldest_date = datetime.now() - timedelta(days=days_back)
        newest_date = datetime.now() + timedelta(days=days_ahead)

        oldest = oldest_date.strftime("%Y-%m-%d")
        newest = newest_date.strftime("%Y-%m-%d")

        async with ICUClient(config) as client:
            events = await client.get_events(
                athlete_id=athlete_id,
                oldest=oldest,
                newest=newest,
            )

            if not events:
                return ResponseBuilder.build_response(
                    data={
                        "events": [],
                        "count": 0,
                        "date_range": {"oldest": oldest, "newest": newest},
                    },
                    metadata={
                        "message": "No events found on your calendar for the specified period"
                    },
                )

            # Sort by date
            events.sort(key=lambda x: x.start_date_local)

            # Group events by date
            events_by_date: dict[str, list[dict[str, Any]]] = {}
            for event in events:
                date = event.start_date_local
                if date not in events_by_date:
                    events_by_date[date] = []

                # Determine relative timing
                date_obj = datetime.fromisoformat(date).date()
                today = datetime.now().date()

                if date_obj == today:
                    relative_timing = "today"
                elif date_obj < today:
                    days_ago = (today - date_obj).days
                    relative_timing = f"{days_ago}_days_ago"
                else:
                    days_until = (date_obj - today).days
                    relative_timing = f"in_{days_until}_days"

                event_item: dict[str, Any] = {
                    "id": event.id,
                    "date": date,
                    "relative_timing": relative_timing,
                    "name": event.name or event.category or "Event",
                    "category": event.category,
                }

                if event.type:
                    event_item["type"] = event.type
                if event.tags:
                    event_item["tags"] = event.tags

                # Workout details
                if event.category == "WORKOUT":
                    if event.distance or event.distance_target:
                        distance = event.distance or event.distance_target
                        if distance:
                            event_item["distance_meters"] = distance

                    if event.moving_time:
                        event_item["duration_seconds"] = event.moving_time

                    if event.icu_training_load:
                        event_item["training_load"] = event.icu_training_load

                    if event.icu_intensity:
                        event_item["intensity_factor"] = event.icu_intensity

                # Ranged events (INJURED, SICK, HOLIDAY, SEASON_START, ...)
                if event.end_date_local:
                    event_item["end_date"] = event.end_date_local
                if event.training_availability:
                    event_item["training_availability"] = event.training_availability

                # Description
                if event.description:
                    event_item["description"] = event.description.strip()

                events_by_date[date].append(event_item)

            # Calculate summary
            workout_count = sum(1 for e in events if e.category == "WORKOUT")
            race_count = sum(1 for e in events if e.category in ("RACE_A", "RACE_B", "RACE_C"))
            note_count = sum(1 for e in events if e.category == "NOTE")
            target_count = sum(1 for e in events if e.category == "TARGET")
            block_count = sum(
                1 for e in events if e.category in ("INJURED", "SICK", "HOLIDAY", "SEASON_START")
            )

            summary = {
                "total_events": len(events),
                "by_category": {
                    "workouts": workout_count,
                    "races": race_count,
                    "notes": note_count,
                    "targets": target_count,
                    "blocks": block_count,
                },
            }

            return ResponseBuilder.build_response(
                data={
                    "events_by_date": events_by_date,
                    "date_range": {"oldest": oldest, "newest": newest},
                    "summary": summary,
                },
                query_type="calendar_events",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def get_upcoming_workouts(
    limit: Annotated[int, "Maximum number of planned workout events to return"] = 7,
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Fetch the planned WORKOUT entries dated on the upcoming CALENDAR (filters out notes, races, goals) — these are calendar EVENTS, not workout-library templates.

    Use for "what's my next workout?", "what training is planned". Each `id` is
    a calendar event ID: pass it to icu_get_event / icu_update_event /
    icu_delete_event, never to the icu_*_workout library tools. For every
    calendar entry type use icu_get_calendar_events; for reusable templates
    stored in the library use icu_get_workouts_in_folder.
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        # Look ahead 30 days to find workouts
        oldest = datetime.now().strftime("%Y-%m-%d")
        newest_date = datetime.now() + timedelta(days=30)
        newest = newest_date.strftime("%Y-%m-%d")

        async with ICUClient(config) as client:
            events = await client.get_events(
                athlete_id=athlete_id,
                oldest=oldest,
                newest=newest,
            )

            # Filter for workouts only
            workouts = [e for e in events if e.category == "WORKOUT"]

            if not workouts:
                return ResponseBuilder.build_response(
                    data={"workouts": [], "count": 0},
                    metadata={"message": "No workouts planned on your calendar"},
                )

            # Sort by date and limit
            workouts.sort(key=lambda x: x.start_date_local)
            workouts = workouts[:limit]

            workouts_data: list[dict[str, Any]] = []
            for workout in workouts:
                date_obj = datetime.fromisoformat(workout.start_date_local).date()
                today = datetime.now().date()

                if date_obj == today:
                    relative_timing = "today"
                elif date_obj == today + timedelta(days=1):
                    relative_timing = "tomorrow"
                else:
                    days_until = (date_obj - today).days
                    relative_timing = f"in_{days_until}_days"

                workout_item: dict[str, Any] = {
                    "id": workout.id,
                    "date": workout.start_date_local,
                    "relative_timing": relative_timing,
                    "name": workout.name or "Workout",
                }

                if workout.type:
                    workout_item["type"] = workout.type
                if workout.tags:
                    workout_item["tags"] = workout.tags

                # Workout metrics
                if workout.distance or workout.distance_target:
                    distance = workout.distance or workout.distance_target
                    if distance:
                        workout_item["distance_meters"] = distance

                if workout.moving_time:
                    workout_item["duration_seconds"] = workout.moving_time

                if workout.icu_training_load:
                    workout_item["training_load"] = workout.icu_training_load

                if workout.icu_intensity:
                    workout_item["intensity_factor"] = workout.icu_intensity

                # Workout description
                if workout.description:
                    workout_item["description"] = workout.description.strip()

                workouts_data.append(workout_item)

            # Calculate total load
            total_load = sum(w.icu_training_load or 0 for w in workouts)

            return ResponseBuilder.build_response(
                data={
                    "workouts": workouts_data,
                    "count": len(workouts_data),
                    "total_planned_load": total_load if total_load > 0 else None,
                },
                query_type="upcoming_workouts",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def get_event(
    event_id: Annotated[int, "Event ID to retrieve"],
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Fetch ONE specific calendar event by ID — full details including description, workout structure, and metrics."""
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            event = await client.get_event(event_id, athlete_id=athlete_id)

            event_data: dict[str, Any] = {
                "id": event.id,
                "date": event.start_date_local,
                "name": event.name or event.category or "Event",
                "category": event.category,
            }

            if event.description:
                event_data["description"] = event.description
            if event.type:
                event_data["type"] = event.type
            if event.tags:
                event_data["tags"] = event.tags

            # Workout/Event metrics
            metrics: dict[str, Any] = {}
            if event.distance or event.distance_target:
                distance = event.distance or event.distance_target
                if distance:
                    metrics["distance_meters"] = distance
            if event.moving_time:
                metrics["duration_seconds"] = event.moving_time
            if event.icu_training_load:
                metrics["training_load"] = event.icu_training_load
            if event.icu_intensity:
                metrics["intensity_factor"] = event.icu_intensity
            if event.joules:
                metrics["joules"] = event.joules
            if event.joules_above_ftp:
                metrics["joules_above_ftp"] = event.joules_above_ftp

            if metrics:
                event_data["metrics"] = metrics

            # Fitness context
            fitness: dict[str, Any] = {}
            if event.icu_ctl is not None:
                fitness["ctl"] = round(event.icu_ctl, 1)
            if event.icu_atl is not None:
                fitness["atl"] = round(event.icu_atl, 1)
            if fitness:
                event_data["fitness_context"] = fitness

            # Date range and availability (INJURED/SICK/HOLIDAY/SEASON_START)
            if event.end_date_local:
                event_data["end_date"] = event.end_date_local
            if event.training_availability:
                event_data["training_availability"] = event.training_availability

            # Display flags
            if event.show_as_note is not None:
                event_data["show_as_note"] = event.show_as_note
            if event.not_on_fitness_chart is not None:
                event_data["not_on_fitness_chart"] = event.not_on_fitness_chart
            if event.show_on_ctl_line is not None:
                event_data["show_on_ctl_line"] = event.show_on_ctl_line

            # Metadata
            if event.color:
                event_data["color"] = event.color
            if event.external_id:
                event_data["external_id"] = event.external_id

            return ResponseBuilder.build_response(
                data=event_data,
                query_type="get_event",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )
