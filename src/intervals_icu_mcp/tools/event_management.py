"""Event/calendar management tools for Intervals.icu MCP server."""

from datetime import datetime
from typing import Annotated, Any, cast

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..response_builder import ResponseBuilder


async def create_event(
    start_date: Annotated[str, "Start date in YYYY-MM-DD format"],
    name: Annotated[str, "Event name"],
    category: Annotated[str, "Event category: WORKOUT, NOTE, RACE, or GOAL"],
    description: Annotated[
        str | None,
        "Event description. For WORKOUT events, use Intervals.icu structured workout "
        "syntax to define intervals, targets, and structure. The server automatically "
        "parses this into a structured workout. Read the intervals-icu://workout-syntax "
        "resource for the complete syntax reference. Example: "
        "'Warmup\n- 10m ramp 50%-75%\n\nMain Set 3x\n- 5m 95%\n- 3m 55%\n\nCooldown\n- 10m 50%'",
    ] = None,
    event_type: Annotated[str | None, "Activity type (e.g., Ride, Run, Swim)"] = None,
    duration_seconds: Annotated[int | None, "Planned duration in seconds"] = None,
    distance_meters: Annotated[float | None, "Planned distance in meters"] = None,
    training_load: Annotated[int | None, "Planned training load"] = None,
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Create a new calendar event (planned workout, note, race, or goal).

    Adds an event to your Intervals.icu calendar. Events can be workouts with
    planned metrics, notes for tracking information, races, or training goals.

    For WORKOUT events, the 'description' field accepts Intervals.icu structured
    workout syntax. The server automatically parses this text into a structured
    workout with calculated training load, zone distribution, and device sync.
    Read the intervals-icu://workout-syntax resource for the complete syntax.

    Args:
        start_date: Date in ISO-8601 format (YYYY-MM-DD)
        name: Name of the event
        category: Type of event - WORKOUT, NOTE, RACE, or GOAL
        description: For workouts, structured workout text (see workout-syntax resource)
        event_type: Activity type (e.g., "Ride", "Run", "Swim") for workouts
        duration_seconds: Planned duration for workouts
        distance_meters: Planned distance for workouts
        training_load: Planned training load for workouts

    Returns:
        JSON string with created event data
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    # Validate category
    valid_categories = ["WORKOUT", "NOTE", "RACE", "GOAL"]
    if category.upper() not in valid_categories:
        return ResponseBuilder.build_error_response(
            f"Invalid category. Must be one of: {', '.join(valid_categories)}",
            error_type="validation_error",
        )

    # Validate and normalize date format (accept YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
    try:
        start_date = datetime.fromisoformat(start_date).strftime("%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return ResponseBuilder.build_error_response(
            "Invalid date format. Please use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS format.",
            error_type="validation_error",
        )

    try:
        # Build event data
        event_data: dict[str, Any] = {
            "start_date_local": start_date,
            "name": name,
            "category": category.upper(),
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

        async with ICUClient(config) as client:
            event = await client.create_event(event_data, athlete_id=athlete_id)

            event_result: dict[str, Any] = {
                "id": event.id,
                "start_date": event.start_date_local,
                "name": event.name,
                "category": event.category,
            }

            if event.description:
                event_result["description"] = event.description
            if event.type:
                event_result["type"] = event.type
            if event.moving_time:
                event_result["duration_seconds"] = event.moving_time
            if event.distance:
                event_result["distance_meters"] = event.distance
            if event.icu_training_load:
                event_result["training_load"] = event.icu_training_load

            return ResponseBuilder.build_response(
                data=event_result,
                query_type="create_event",
                metadata={"message": f"Successfully created {category.lower()}: {name}"},
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
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Update an existing calendar event.

    Modifies one or more fields of an existing event. Only provide the fields
    you want to change - other fields will remain unchanged.

    Args:
        event_id: ID of the event to update
        name: New name for the event
        description: New description
        start_date: New start date in YYYY-MM-DD format
        event_type: New activity type
        duration_seconds: New planned duration
        distance_meters: New planned distance
        training_load: New planned training load

    Returns:
        JSON string with updated event data
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    # Validate and normalize date format if provided (accept YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
    if start_date:
        try:
            start_date = datetime.fromisoformat(start_date).strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return ResponseBuilder.build_error_response(
                "Invalid date format. Please use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS format.",
                error_type="validation_error",
            )

    try:
        # Build update data (only include provided fields)
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

        if not event_data:
            return ResponseBuilder.build_error_response(
                "No fields provided to update. Please specify at least one field to change.",
                error_type="validation_error",
            )

        async with ICUClient(config) as client:
            event = await client.update_event(event_id, event_data, athlete_id=athlete_id)

            event_result: dict[str, Any] = {
                "id": event.id,
                "start_date": event.start_date_local,
                "name": event.name,
                "category": event.category,
            }

            if event.description:
                event_result["description"] = event.description
            if event.type:
                event_result["type"] = event.type
            if event.moving_time:
                event_result["duration_seconds"] = event.moving_time
            if event.distance:
                event_result["distance_meters"] = event.distance
            if event.icu_training_load:
                event_result["training_load"] = event.icu_training_load

            return ResponseBuilder.build_response(
                data=event_result,
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
        "JSON string containing array of events. Each event should have: "
        "start_date_local, name, category, and optional fields like description, "
        "type, moving_time, distance, icu_training_load. For WORKOUT events, "
        "include structured workout syntax in the 'description' field "
        "(see intervals-icu://workout-syntax resource for syntax reference).",
    ],
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Create multiple calendar events in a single operation.

    This is more efficient than creating events one at a time. Provide a JSON array
    of event objects, each with the same structure as create_event.

    For WORKOUT events, include Intervals.icu structured workout syntax in the
    'description' field. The server automatically parses workout text into structured
    workouts. Read the intervals-icu://workout-syntax resource for the complete syntax.

    Args:
        events: JSON array of event objects to create

    Returns:
        JSON string with created events
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        import json

        # Parse the JSON string
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

        # Type cast after validation
        events_data: list[dict[str, Any]] = parsed_data  # type: ignore[assignment]

        # Validate each event
        valid_categories = ["WORKOUT", "NOTE", "RACE", "GOAL"]
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
            if event_data["category"].upper() not in valid_categories:
                return ResponseBuilder.build_error_response(
                    f"Event {i}: Invalid category. Must be one of: {', '.join(valid_categories)}",
                    error_type="validation_error",
                )

            # Normalize category to uppercase
            event_data["category"] = event_data["category"].upper()

            # Validate and normalize date format (accept YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
            try:
                event_data["start_date_local"] = datetime.fromisoformat(
                    event_data["start_date_local"]
                ).strftime("%Y-%m-%dT%H:%M:%S")
            except ValueError:
                return ResponseBuilder.build_error_response(
                    f"Event {i}: Invalid date format. Please use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS format.",
                    error_type="validation_error",
                )

        async with ICUClient(config) as client:
            created_events = await client.bulk_create_events(events_data, athlete_id=athlete_id)

            events_result: list[dict[str, Any]] = []
            for event in created_events:
                event_info: dict[str, Any] = {
                    "id": event.id,
                    "start_date": event.start_date_local,
                    "name": event.name,
                    "category": event.category,
                }

                if event.description:
                    event_info["description"] = event.description
                if event.type:
                    event_info["type"] = event.type
                if event.moving_time:
                    event_info["duration_seconds"] = event.moving_time
                if event.distance:
                    event_info["distance_meters"] = event.distance
                if event.icu_training_load:
                    event_info["training_load"] = event.icu_training_load

                events_result.append(event_info)

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
