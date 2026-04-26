"""Event/calendar management tools for Intervals.icu MCP server."""

from datetime import datetime
from typing import Annotated, Any, cast

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..models import Event
from ..response_builder import ResponseBuilder

VALID_CATEGORIES = {
    "WORKOUT",
    "NOTE",
    "RACE_A",
    "RACE_B",
    "RACE_C",
    "TARGET",
    "PLAN",
    "HOLIDAY",
    "SICK",
    "INJURED",
    "SET_EFTP",
    "FITNESS_DAYS",
    "SEASON_START",
    "SET_FITNESS",
}
CATEGORY_ALIASES = {"RACE": "RACE_A", "GOAL": "TARGET"}
VALID_AVAILABILITY = {"NORMAL", "LIMITED", "UNAVAILABLE"}
RACE_CATEGORIES = {"RACE_A", "RACE_B", "RACE_C"}
# Canonical Intervals.icu activity disciplines accepted by the API for the
# `type` field. Must match models.ActivityType.
ACTIVITY_TYPES_HINT = "Ride, Run, Swim, Walk, Hike, VirtualRide, VirtualRun, Other"


def _normalize_category(category: str) -> tuple[str | None, str | None]:
    """Normalize a category string to its canonical API value.

    Uppercases the input, applies legacy aliases (RACE→RACE_A, GOAL→TARGET),
    and validates against the API enum. Returns (normalized, error_message).
    """
    normalized = category.upper()
    normalized = CATEGORY_ALIASES.get(normalized, normalized)
    if normalized not in VALID_CATEGORIES:
        valid = ", ".join(sorted(VALID_CATEGORIES))
        return None, f"Invalid category. Must be one of: {valid}"
    return normalized, None


def _normalize_date(date_str: str) -> str:
    """Normalize a date string to ISO-8601 (YYYY-MM-DDTHH:MM:SS).

    Accepts YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS. Raises ValueError on bad input.
    """
    return datetime.fromisoformat(date_str).strftime("%Y-%m-%dT%H:%M:%S")


def _event_to_dict(event: Event) -> dict[str, Any]:
    """Build the canonical tool response dict for an Event."""
    result: dict[str, Any] = {
        "id": event.id,
        "start_date": event.start_date_local,
        "name": event.name,
        "category": event.category,
    }

    if event.end_date_local:
        result["end_date"] = event.end_date_local
    if event.description:
        result["description"] = event.description
    if event.type:
        result["type"] = event.type
    if event.moving_time:
        result["duration_seconds"] = event.moving_time
    if event.distance:
        result["distance_meters"] = event.distance
    if event.icu_training_load:
        result["training_load"] = event.icu_training_load
    if event.training_availability:
        result["training_availability"] = event.training_availability
    if event.color:
        result["color"] = event.color
    if event.show_as_note is not None:
        result["show_as_note"] = event.show_as_note
    if event.not_on_fitness_chart is not None:
        result["not_on_fitness_chart"] = event.not_on_fitness_chart
    if event.show_on_ctl_line is not None:
        result["show_on_ctl_line"] = event.show_on_ctl_line

    return result


async def create_event(
    start_date: Annotated[str, "Start date in YYYY-MM-DD format"],
    name: Annotated[str, "Event name"],
    category: Annotated[
        str,
        "Event category. WORKOUT, NOTE, RACE_A/RACE_B/RACE_C (race tier), TARGET "
        "(performance goal), PLAN, HOLIDAY (Urlaub), SICK (Krank), INJURED "
        "(Verletzt), SET_EFTP, FITNESS_DAYS (Fitnesstage), SEASON_START (Saison), "
        "SET_FITNESS. Legacy aliases RACE→RACE_A and GOAL→TARGET are accepted.",
    ],
    description: Annotated[
        str | None,
        "Event description. For WORKOUT events, use Intervals.icu structured workout "
        "syntax to define intervals, targets, and structure. The server automatically "
        "parses this into a structured workout. Read the intervals-icu://workout-syntax "
        "resource for the complete syntax reference. Example: "
        "'Warmup\n- 10m ramp 50%-75%\n\nMain Set 3x\n- 5m 95%\n- 3m 55%\n\nCooldown\n- 10m 50%'",
    ] = None,
    event_type: Annotated[
        str | None,
        "Activity discipline (NOT the category). Must be one of: "
        "Ride, Run, Swim, Walk, Hike, VirtualRide, VirtualRun, Other. "
        "Required for RACE_A/RACE_B/RACE_C events — the API rejects races "
        "without a discipline.",
    ] = None,
    duration_seconds: Annotated[int | None, "Planned duration in seconds"] = None,
    distance_meters: Annotated[float | None, "Planned distance in meters"] = None,
    training_load: Annotated[int | None, "Planned training load"] = None,
    end_date: Annotated[
        str | None,
        "End date in YYYY-MM-DD format. Use for ranged categories like INJURED, "
        "SICK, HOLIDAY, SEASON_START to mark a multi-day block.",
    ] = None,
    training_availability: Annotated[
        str | None,
        "Training availability during the event: NORMAL (Verfügbar), LIMITED "
        "(Begrenzt), or UNAVAILABLE (Nicht verfügbar). Typical for INJURED/SICK/"
        "HOLIDAY blocks so the planner skips or scales workouts.",
    ] = None,
    color: Annotated[str | None, "Custom display color (hex string)"] = None,
    show_as_note: Annotated[bool | None, "Show event as a note marker on the fitness chart"] = None,
    not_on_fitness_chart: Annotated[
        bool | None, "Hide event entirely from the fitness chart"
    ] = None,
    show_on_ctl_line: Annotated[bool | None, "Render event on the CTL line"] = None,
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Create a new calendar event.

    Supports the full Intervals.icu calendar category set: planned workouts, notes,
    races (RACE_A/B/C tiers), performance targets, training plans, and life-event
    blocks like INJURED, SICK, HOLIDAY, SEASON_START. Block-style categories
    typically use start_date + end_date + training_availability so the planner
    treats the affected days correctly.

    For WORKOUT events, the 'description' field accepts Intervals.icu structured
    workout syntax. The server automatically parses this text into a structured
    workout with calculated training load, zone distribution, and device sync.
    Read the intervals-icu://workout-syntax resource for the complete syntax.

    Args:
        start_date: Date in ISO-8601 format (YYYY-MM-DD)
        name: Name of the event
        category: One of the categories listed in the parameter description
        description: For workouts, structured workout text (see workout-syntax resource)
        event_type: Activity type (e.g., "Ride", "Run", "Swim") for workouts
        duration_seconds: Planned duration for workouts
        distance_meters: Planned distance for workouts
        training_load: Planned training load for workouts
        end_date: End date for ranged categories (INJURED, SICK, HOLIDAY, ...)
        training_availability: NORMAL, LIMITED, or UNAVAILABLE
        color: Custom color hex string
        show_as_note: Show as a note on the fitness chart
        not_on_fitness_chart: Hide from the fitness chart
        show_on_ctl_line: Render on the CTL line

    Returns:
        JSON string with created event data
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    normalized_category, category_error = _normalize_category(category)
    if category_error or normalized_category is None:
        return ResponseBuilder.build_error_response(
            category_error or "Invalid category",
            error_type="validation_error",
        )

    if normalized_category in RACE_CATEGORIES and not event_type:
        return ResponseBuilder.build_error_response(
            f"event_type is required for {normalized_category} events. "
            f"Provide the activity discipline: {ACTIVITY_TYPES_HINT}.",
            error_type="validation_error",
        )

    if training_availability is not None:
        normalized_availability = training_availability.upper()
        if normalized_availability not in VALID_AVAILABILITY:
            return ResponseBuilder.build_error_response(
                f"Invalid training_availability. Must be one of: "
                f"{', '.join(sorted(VALID_AVAILABILITY))}",
                error_type="validation_error",
            )
    else:
        normalized_availability = None

    try:
        start_date = _normalize_date(start_date)
    except ValueError:
        return ResponseBuilder.build_error_response(
            "Invalid date format. Please use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS format.",
            error_type="validation_error",
        )

    if end_date is not None:
        try:
            end_date = _normalize_date(end_date)
        except ValueError:
            return ResponseBuilder.build_error_response(
                "Invalid end_date format. Please use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS format.",
                error_type="validation_error",
            )

    try:
        event_data: dict[str, Any] = {
            "start_date_local": start_date,
            "name": name,
            "category": normalized_category,
        }

        if description:
            event_data["description"] = description
        if event_type:
            event_data["type"] = event_type
        if duration_seconds:
            event_data["moving_time"] = duration_seconds
        if distance_meters:
            event_data["distance"] = distance_meters
        if training_load:
            event_data["icu_training_load"] = training_load
        if end_date is not None:
            event_data["end_date_local"] = end_date
        if normalized_availability is not None:
            event_data["training_availability"] = normalized_availability
        if color is not None:
            event_data["color"] = color
        if show_as_note is not None:
            event_data["show_as_note"] = show_as_note
        if not_on_fitness_chart is not None:
            event_data["not_on_fitness_chart"] = not_on_fitness_chart
        if show_on_ctl_line is not None:
            event_data["show_on_ctl_line"] = show_on_ctl_line

        async with ICUClient(config) as client:
            event = await client.create_event(event_data, athlete_id=athlete_id)

            return ResponseBuilder.build_response(
                data=_event_to_dict(event),
                query_type="create_event",
                metadata={"message": f"Successfully created {normalized_category.lower()}: {name}"},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def update_event(
    event_id: Annotated[int, "Event ID to update"],
    name: Annotated[str | None, "Updated event name"] = None,
    description: Annotated[str | None, "Updated description"] = None,
    start_date: Annotated[str | None, "Updated start date (YYYY-MM-DD)"] = None,
    event_type: Annotated[str | None, "Updated activity type"] = None,
    duration_seconds: Annotated[int | None, "Updated duration in seconds"] = None,
    distance_meters: Annotated[float | None, "Updated distance in meters"] = None,
    training_load: Annotated[int | None, "Updated training load"] = None,
    end_date: Annotated[str | None, "Updated end date (YYYY-MM-DD)"] = None,
    training_availability: Annotated[
        str | None, "Updated training availability: NORMAL, LIMITED, or UNAVAILABLE"
    ] = None,
    color: Annotated[str | None, "Updated color (hex string)"] = None,
    show_as_note: Annotated[bool | None, "Show event as a note on the fitness chart"] = None,
    not_on_fitness_chart: Annotated[bool | None, "Hide event from the fitness chart"] = None,
    show_on_ctl_line: Annotated[bool | None, "Render event on the CTL line"] = None,
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Update an existing calendar event.

    Modifies one or more fields of an existing event. Only provide the fields
    you want to change - other fields will remain unchanged. Use end_date and
    training_availability to extend or update INJURED/SICK/HOLIDAY blocks.

    Args:
        event_id: ID of the event to update
        name: New name for the event
        description: New description
        start_date: New start date in YYYY-MM-DD format
        event_type: New activity type
        duration_seconds: New planned duration
        distance_meters: New planned distance
        training_load: New planned training load
        end_date: New end date for ranged events
        training_availability: NORMAL, LIMITED, or UNAVAILABLE
        color: New color hex string
        show_as_note: Show as a note on the fitness chart
        not_on_fitness_chart: Hide from the fitness chart
        show_on_ctl_line: Render on the CTL line

    Returns:
        JSON string with updated event data
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    if start_date is not None:
        try:
            start_date = _normalize_date(start_date)
        except ValueError:
            return ResponseBuilder.build_error_response(
                "Invalid date format. Please use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS format.",
                error_type="validation_error",
            )

    if end_date is not None:
        try:
            end_date = _normalize_date(end_date)
        except ValueError:
            return ResponseBuilder.build_error_response(
                "Invalid end_date format. Please use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS format.",
                error_type="validation_error",
            )

    if training_availability is not None:
        normalized_availability = training_availability.upper()
        if normalized_availability not in VALID_AVAILABILITY:
            return ResponseBuilder.build_error_response(
                f"Invalid training_availability. Must be one of: "
                f"{', '.join(sorted(VALID_AVAILABILITY))}",
                error_type="validation_error",
            )
    else:
        normalized_availability = None

    try:
        event_data: dict[str, Any] = {}

        if name is not None:
            event_data["name"] = name
        if description is not None:
            event_data["description"] = description
        if start_date is not None:
            event_data["start_date_local"] = start_date
        if event_type is not None:
            event_data["type"] = event_type
        if duration_seconds is not None:
            event_data["moving_time"] = duration_seconds
        if distance_meters is not None:
            event_data["distance"] = distance_meters
        if training_load is not None:
            event_data["icu_training_load"] = training_load
        if end_date is not None:
            event_data["end_date_local"] = end_date
        if normalized_availability is not None:
            event_data["training_availability"] = normalized_availability
        if color is not None:
            event_data["color"] = color
        if show_as_note is not None:
            event_data["show_as_note"] = show_as_note
        if not_on_fitness_chart is not None:
            event_data["not_on_fitness_chart"] = not_on_fitness_chart
        if show_on_ctl_line is not None:
            event_data["show_on_ctl_line"] = show_on_ctl_line

        if not event_data:
            return ResponseBuilder.build_error_response(
                "No fields provided to update. Please specify at least one field to change.",
                error_type="validation_error",
            )

        async with ICUClient(config) as client:
            event = await client.update_event(event_id, event_data, athlete_id=athlete_id)

            return ResponseBuilder.build_response(
                data=_event_to_dict(event),
                query_type="update_event",
                metadata={"message": f"Successfully updated event {event_id}"},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def delete_event(
    event_id: Annotated[int, "Event ID to delete"],
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Delete a calendar event.

    Permanently removes an event from your calendar. This action cannot be undone.

    Args:
        event_id: ID of the event to delete

    Returns:
        JSON string with deletion confirmation
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            success = await client.delete_event(event_id, athlete_id=athlete_id)

            if success:
                return ResponseBuilder.build_response(
                    data={"event_id": event_id, "deleted": True},
                    query_type="delete_event",
                    metadata={"message": f"Successfully deleted event {event_id}"},
                )
            else:
                return ResponseBuilder.build_error_response(
                    f"Failed to delete event {event_id}",
                    error_type="api_error",
                )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def bulk_create_events(
    events: Annotated[
        str,
        "JSON array of events. Required per event: start_date_local, name, category. "
        "Optional: description, type, moving_time, distance, icu_training_load, "
        "end_date_local (ranged categories), training_availability "
        "(NORMAL/LIMITED/UNAVAILABLE), color, show_as_note, not_on_fitness_chart, "
        "show_on_ctl_line. Categories: WORKOUT, NOTE, RACE_A/B/C, TARGET, PLAN, "
        "HOLIDAY, SICK, INJURED, SET_EFTP, FITNESS_DAYS, SEASON_START, SET_FITNESS "
        "(legacy RACE→RACE_A and GOAL→TARGET aliases accepted). For WORKOUT events, "
        "include structured workout syntax in 'description' (see "
        "intervals-icu://workout-syntax resource).",
    ],
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Create multiple calendar events in a single operation.

    More efficient than creating events one at a time. Provide a JSON array
    of event objects with the same fields accepted by create_event.

    For WORKOUT events, include Intervals.icu structured workout syntax in the
    'description' field. Read the intervals-icu://workout-syntax resource for the
    complete syntax.

    Args:
        events: JSON array of event objects to create

    Returns:
        JSON string with created events
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        import json

        try:
            parsed_data = json.loads(events)
        except json.JSONDecodeError as e:
            return ResponseBuilder.build_error_response(
                f"Invalid JSON format: {str(e)}", error_type="validation_error"
            )

        if not isinstance(parsed_data, list):
            return ResponseBuilder.build_error_response(
                "Events must be a JSON array", error_type="validation_error"
            )

        events_data: list[dict[str, Any]] = parsed_data  # type: ignore[assignment]

        for i, event_data in enumerate(events_data):
            if "start_date_local" not in event_data:
                return ResponseBuilder.build_error_response(
                    f"Event {i}: Missing required field 'start_date_local'",
                    error_type="validation_error",
                )
            if "name" not in event_data:
                return ResponseBuilder.build_error_response(
                    f"Event {i}: Missing required field 'name'", error_type="validation_error"
                )
            if "category" not in event_data:
                return ResponseBuilder.build_error_response(
                    f"Event {i}: Missing required field 'category'",
                    error_type="validation_error",
                )

            normalized_category, category_error = _normalize_category(event_data["category"])
            if category_error or normalized_category is None:
                return ResponseBuilder.build_error_response(
                    f"Event {i}: {category_error or 'Invalid category'}",
                    error_type="validation_error",
                )
            event_data["category"] = normalized_category

            if normalized_category in RACE_CATEGORIES and not event_data.get("type"):
                return ResponseBuilder.build_error_response(
                    f"Event {i}: 'type' is required for {normalized_category} events. "
                    f"Provide the activity discipline: {ACTIVITY_TYPES_HINT}.",
                    error_type="validation_error",
                )

            try:
                event_data["start_date_local"] = _normalize_date(event_data["start_date_local"])
            except ValueError:
                return ResponseBuilder.build_error_response(
                    f"Event {i}: Invalid date format. Please use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS format.",
                    error_type="validation_error",
                )

            if "end_date_local" in event_data and event_data["end_date_local"] is not None:
                try:
                    event_data["end_date_local"] = _normalize_date(event_data["end_date_local"])
                except ValueError:
                    return ResponseBuilder.build_error_response(
                        f"Event {i}: Invalid end_date_local format. Please use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS format.",
                        error_type="validation_error",
                    )

            if (
                "training_availability" in event_data
                and event_data["training_availability"] is not None
            ):
                availability = str(event_data["training_availability"]).upper()
                if availability not in VALID_AVAILABILITY:
                    return ResponseBuilder.build_error_response(
                        f"Event {i}: Invalid training_availability. Must be one of: "
                        f"{', '.join(sorted(VALID_AVAILABILITY))}",
                        error_type="validation_error",
                    )
                event_data["training_availability"] = availability

        async with ICUClient(config) as client:
            created_events = await client.bulk_create_events(events_data, athlete_id=athlete_id)

            events_result = [_event_to_dict(event) for event in created_events]

            return ResponseBuilder.build_response(
                data={"events": events_result},
                query_type="bulk_create_events",
                metadata={
                    "message": f"Successfully created {len(created_events)} events",
                    "count": len(created_events),
                },
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def bulk_delete_events(
    event_ids: Annotated[str, "JSON array of event IDs to delete (e.g., '[123, 456, 789]')"],
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Delete multiple calendar events in a single operation.

    This is more efficient than deleting events one at a time. Provide a JSON array
    of event IDs to delete.

    Args:
        event_ids: JSON array of event IDs (integers)

    Returns:
        JSON string with deletion confirmation
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        import json

        # Parse the JSON string
        try:
            parsed_data = json.loads(event_ids)
        except json.JSONDecodeError as e:
            return ResponseBuilder.build_error_response(
                f"Invalid JSON format: {str(e)}", error_type="validation_error"
            )

        if not isinstance(parsed_data, list):
            return ResponseBuilder.build_error_response(
                "Event IDs must be a JSON array", error_type="validation_error"
            )

        if not parsed_data:
            return ResponseBuilder.build_error_response(
                "Must provide at least one event ID to delete", error_type="validation_error"
            )

        # Type cast after validation
        ids_list: list[int] = parsed_data  # type: ignore[assignment]

        async with ICUClient(config) as client:
            result = await client.bulk_delete_events(ids_list, athlete_id=athlete_id)

            return ResponseBuilder.build_response(
                data={"deleted_count": len(ids_list), "event_ids": ids_list, "result": result},
                query_type="bulk_delete_events",
                metadata={"message": f"Successfully deleted {len(ids_list)} events"},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def duplicate_events(
    event_ids: Annotated[str, "JSON array of event IDs to duplicate (e.g., '[123, 456]')"],
    num_copies: Annotated[int, "Number of copies to create"] = 1,
    weeks_between: Annotated[int, "Weeks between each copy"] = 1,
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Duplicate one or more calendar events.

    Creates copies of the specified events, placed at weekly intervals from
    the original dates. Useful for repeating workouts across multiple weeks.

    Args:
        event_ids: JSON array of event IDs to duplicate
        num_copies: Number of copies to create (default 1)
        weeks_between: Weeks between each copy (default 1)

    Returns:
        JSON string with the duplicated events
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    import json

    try:
        parsed = json.loads(event_ids)
        if not isinstance(parsed, list) or not all(
            isinstance(v, int) for v in cast(list[Any], parsed)
        ):
            return ResponseBuilder.build_error_response(
                "event_ids must be a JSON array of integers (e.g., '[123, 456]')",
                error_type="validation_error",
            )
        ids_list = cast(list[int], parsed)

        if num_copies < 1:
            return ResponseBuilder.build_error_response(
                "num_copies must be at least 1",
                error_type="validation_error",
            )

        if weeks_between < 1:
            return ResponseBuilder.build_error_response(
                "weeks_between must be at least 1",
                error_type="validation_error",
            )

        async with ICUClient(config) as client:
            duplicated = await client.duplicate_events(
                event_ids=ids_list,
                num_copies=num_copies,
                weeks_between=weeks_between,
                athlete_id=athlete_id,
            )

            events_result: list[dict[str, Any]] = []
            for event in duplicated:
                event_item: dict[str, Any] = {
                    "id": event.id,
                    "start_date": event.start_date_local,
                    "name": event.name,
                    "category": event.category,
                }
                if event.type:
                    event_item["type"] = event.type
                if event.moving_time:
                    event_item["duration_seconds"] = event.moving_time
                if event.icu_training_load:
                    event_item["training_load"] = event.icu_training_load
                events_result.append(event_item)

            return ResponseBuilder.build_response(
                data={"events": events_result, "duplicated_count": len(events_result)},
                query_type="duplicate_events",
                metadata={
                    "message": f"Duplicated {len(ids_list)} event(s), {num_copies} copies each",
                    "original_event_ids": ids_list,
                    "num_copies": num_copies,
                    "weeks_between": weeks_between,
                },
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except json.JSONDecodeError:
        return ResponseBuilder.build_error_response(
            "Invalid JSON format for event_ids. Use format: '[123, 456]'",
            error_type="validation_error",
        )
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def apply_training_plan(
    folder_id: Annotated[int, "Folder ID of the training plan to apply"],
    start_date_local: Annotated[str, "Start date in ISO-8601 format (YYYY-MM-DD)"],
    extra_workouts_json: Annotated[str | None, "Optional JSON array of additional workouts"] = None,
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Apply a training plan.

    Programmatically applies an entire training plan (workout folders/schedules)
    directly onto an athlete's calendar.

    Args:
        folder_id: Folder ID of the training plan
        start_date_local: Start date in YYYY-MM-DD format
        extra_workouts_json: Optional JSON string of extra workout objects

    Returns:
        JSON string with application confirmation
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    # Validate and normalize date format
    try:
        start_date_local = datetime.fromisoformat(start_date_local).strftime("%Y-%m-%dT00:00:00")
    except ValueError:
        return ResponseBuilder.build_error_response(
            "Invalid date format. Please use YYYY-MM-DD format.",
            error_type="validation_error",
        )

    # Parse extra workouts if provided
    extra_workouts: list[dict[str, Any]] | None = None
    if extra_workouts_json:
        import json

        try:
            extra_workouts = json.loads(extra_workouts_json)
            if not isinstance(extra_workouts, list):
                return ResponseBuilder.build_error_response(
                    "extra_workouts_json must be a JSON array",
                    error_type="validation_error",
                )
        except json.JSONDecodeError as e:
            return ResponseBuilder.build_error_response(
                f"Invalid JSON format for extra_workouts_json: {str(e)}",
                error_type="validation_error",
            )

    try:
        async with ICUClient(config) as client:
            response = await client.apply_training_plan(
                folder_id=folder_id,
                start_date_local=start_date_local,
                extra_workouts=extra_workouts,
                athlete_id=athlete_id,
            )

            return ResponseBuilder.build_response(
                data=response,
                query_type="apply_training_plan",
                metadata={"message": f"Successfully applied training plan folder {folder_id}"},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )
