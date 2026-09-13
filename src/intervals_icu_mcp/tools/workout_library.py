"""Workout library tools for Intervals.icu MCP server."""

from typing import Annotated, Any

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..models import Workout
from ..response_builder import ResponseBuilder
from .event_management import ACTIVITY_TYPES_HINT, WORKOUT_SYNTAX_HINT, workout_doc_parse_info

VALID_TARGETS = ("AUTO", "POWER", "HR", "PACE")

# Library workouts use the same field names as icu_create_event (workout_type standing in
# for event_type) and are translated to the API's names at the boundary.
_WORKOUT_FIELD_MAP = {
    "workout_type": "type",
    "duration_seconds": "moving_time",
    "distance_meters": "distance",
    "training_load": "icu_training_load",
}


def _workout_payload(fields: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Drop unset fields, validate day/target, and translate to API field names.

    Shared by icu_create_workout and icu_update_workout so both accept the same
    fields and reject the same mistakes. Returns (payload, error_message).
    """
    payload = {k: v for k, v in fields.items() if v is not None}

    day = payload.get("day")
    if day is not None and day < 0:
        return {}, "day must be a non-negative integer (day offset within a plan)"
    target = payload.get("target")
    if target is not None:
        normalized_target = str(target).upper()
        if normalized_target not in VALID_TARGETS:
            return {}, f"Invalid target. Must be one of: {', '.join(VALID_TARGETS)}"
        payload["target"] = normalized_target

    for friendly, api_field in _WORKOUT_FIELD_MAP.items():
        if friendly in payload:
            payload[api_field] = payload.pop(friendly)
    return payload, None


def _workout_to_dict(workout: Workout) -> dict[str, Any]:
    """Build the tool response dict for a created or updated library workout."""
    result: dict[str, Any] = {
        "id": workout.id,
        "name": workout.name,
        "folder_id": workout.folder_id,
    }
    optional: dict[str, Any] = {
        "type": workout.type,
        "day": workout.day,
        "description": workout.description,
        "duration_seconds": workout.moving_time,
        "distance_meters": workout.distance,
        "training_load": workout.icu_training_load,
        "intensity_factor": workout.icu_intensity,
        "target": workout.target,
        "indoor": workout.indoor,
        "color": workout.color,
        "tags": workout.tags or None,
    }
    result.update({k: v for k, v in optional.items() if v is not None})

    parse_info = workout_doc_parse_info(workout.description, workout.workout_doc, workout.type)
    if parse_info:
        result.update(parse_info)
    return result


async def get_workout_library(
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """List all workout-library folders + training plans the athlete has access to (personal, shared, and followed plans).

    Each folder ID can be passed to icu_get_workouts_in_folder to see its
    contents, or to icu_apply_training_plan to schedule it onto the calendar.
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            folders = await client.get_workout_folders(athlete_id=athlete_id)

            if not folders:
                return ResponseBuilder.build_response(
                    data={"folders": [], "count": 0},
                    metadata={
                        "message": "No workout folders found. Create folders in Intervals.icu to organize your workouts."
                    },
                )

            folders_data: list[dict[str, Any]] = []
            for folder in folders:
                folder_item: dict[str, Any] = {
                    "id": folder.id,
                    "name": folder.name,
                }

                if folder.description:
                    folder_item["description"] = folder.description
                if folder.num_workouts:
                    folder_item["num_workouts"] = folder.num_workouts

                # Training plan info
                if folder.start_date_local:
                    folder_item["start_date"] = folder.start_date_local
                if folder.duration_weeks:
                    folder_item["duration_weeks"] = folder.duration_weeks
                if folder.hours_per_week_min or folder.hours_per_week_max:
                    folder_item["hours_per_week"] = {
                        "min": folder.hours_per_week_min,
                        "max": folder.hours_per_week_max,
                    }

                folders_data.append(folder_item)

            # Categorize folders
            training_plans = [f for f in folders if f.duration_weeks is not None]
            regular_folders = [f for f in folders if f.duration_weeks is None]

            summary = {
                "total_folders": len(folders),
                "training_plans": len(training_plans),
                "regular_folders": len(regular_folders),
                "total_workouts": sum(f.num_workouts or 0 for f in folders),
            }

            result_data = {
                "folders": folders_data,
                "summary": summary,
            }

            return ResponseBuilder.build_response(
                data=result_data,
                query_type="workout_library",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def get_workouts_in_folder(
    folder_id: Annotated[int, "Folder ID to get workouts from"],
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """List the workouts stored in one specific library folder or training plan — name, type, structure, training load, intensity factor."""
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            workouts = await client.get_workouts_in_folder(folder_id, athlete_id=athlete_id)

            if not workouts:
                return ResponseBuilder.build_response(
                    data={"workouts": [], "count": 0, "folder_id": folder_id},
                    metadata={"message": f"No workouts found in folder {folder_id}"},
                )

            workouts_data: list[dict[str, Any]] = []
            for workout in workouts:
                workout_item: dict[str, Any] = {
                    "id": workout.id,
                    "name": workout.name,
                }

                if workout.description:
                    workout_item["description"] = workout.description
                if workout.type:
                    workout_item["type"] = workout.type
                if workout.day is not None:
                    workout_item["day"] = workout.day

                # Workout metrics
                metrics: dict[str, Any] = {}
                if workout.moving_time:
                    metrics["duration_seconds"] = workout.moving_time
                if workout.distance:
                    metrics["distance_meters"] = workout.distance
                if workout.icu_training_load:
                    metrics["training_load"] = workout.icu_training_load
                if workout.icu_intensity:
                    metrics["intensity_factor"] = workout.icu_intensity
                if workout.joules:
                    metrics["joules"] = workout.joules
                if workout.joules_above_ftp:
                    metrics["joules_above_ftp"] = workout.joules_above_ftp

                if metrics:
                    workout_item["metrics"] = metrics

                # Other properties
                if workout.indoor is not None:
                    workout_item["indoor"] = workout.indoor
                if workout.color:
                    workout_item["color"] = workout.color

                workouts_data.append(workout_item)

            # Calculate summary
            total_duration = sum(w.moving_time or 0 for w in workouts)
            total_load = sum(w.icu_training_load or 0 for w in workouts)
            indoor_count = sum(1 for w in workouts if w.indoor)

            summary = {
                "total_workouts": len(workouts),
                "total_duration_seconds": total_duration,
                "total_training_load": total_load,
                "indoor_workouts": indoor_count,
            }

            result_data = {
                "folder_id": folder_id,
                "workouts": workouts_data,
                "summary": summary,
            }

            return ResponseBuilder.build_response(
                data=result_data,
                query_type="folder_workouts",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def create_workout(
    folder_id: Annotated[int, "Existing library folder or plan ID (from icu_get_workout_library)"],
    name: Annotated[str, "Workout name"],
    description: Annotated[
        str | None,
        "Workout steps, parsed the same way as a WORKOUT calendar event. " + WORKOUT_SYNTAX_HINT,
    ] = None,
    workout_type: Annotated[str | None, "Activity discipline: " + ACTIVITY_TYPES_HINT] = None,
    day: Annotated[
        int | None,
        "PLAN folders only: day offset from plan start (0 = day 1 of week 1, 7 = day 1 of "
        "week 2). Omit for plain folders.",
    ] = None,
    duration_seconds: Annotated[int | None, "Planned duration in seconds"] = None,
    distance_meters: Annotated[float | None, "Planned distance in meters"] = None,
    training_load: Annotated[int | None, "Planned training load"] = None,
    target: Annotated[str | None, "Device target type: AUTO, POWER, HR, or PACE"] = None,
    indoor: Annotated[bool | None, "Mark as an indoor workout"] = None,
    color: Annotated[str | None, "Custom display color (hex string)"] = None,
    tags: Annotated[list[str] | None, "Tags for organizing the library"] = None,
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Save ONE new reusable workout into a LIBRARY folder or training plan — it does not go on the calendar.

    To schedule a workout on a date use icu_create_event. To change a saved
    workout use icu_update_workout. Put a plan's workouts on the calendar with
    icu_apply_training_plan.
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    if not name.strip():
        return ResponseBuilder.build_error_response(
            "name is required", error_type="validation_error"
        )

    payload, error = _workout_payload(
        {
            "folder_id": folder_id,
            "name": name,
            "description": description,
            "workout_type": workout_type,
            "day": day,
            "duration_seconds": duration_seconds,
            "distance_meters": distance_meters,
            "training_load": training_load,
            "target": target,
            "indoor": indoor,
            "color": color,
            "tags": tags,
        }
    )
    if error:
        return ResponseBuilder.build_error_response(error, error_type="validation_error")

    try:
        async with ICUClient(config) as client:
            workout = await client.create_workout(payload, athlete_id=athlete_id)

            return ResponseBuilder.build_response(
                data=_workout_to_dict(workout),
                query_type="create_workout",
                metadata={"message": f"Saved workout to library folder {folder_id}: {name}"},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def update_workout(
    workout_id: Annotated[int, "Library workout ID (from icu_get_workouts_in_folder)"],
    name: Annotated[str | None, "Updated workout name"] = None,
    description: Annotated[str | None, "Updated workout steps. " + WORKOUT_SYNTAX_HINT] = None,
    workout_type: Annotated[
        str | None, "Updated activity discipline: " + ACTIVITY_TYPES_HINT
    ] = None,
    folder_id: Annotated[int | None, "Move the workout to this folder or plan"] = None,
    day: Annotated[int | None, "PLAN folders only: updated day offset from plan start"] = None,
    duration_seconds: Annotated[int | None, "Updated duration in seconds"] = None,
    distance_meters: Annotated[float | None, "Updated distance in meters"] = None,
    training_load: Annotated[int | None, "Updated training load"] = None,
    target: Annotated[str | None, "Updated device target type: AUTO, POWER, HR, or PACE"] = None,
    indoor: Annotated[bool | None, "Mark as an indoor workout"] = None,
    color: Annotated[str | None, "Updated color (hex string)"] = None,
    tags: Annotated[list[str] | None, "Replacement tag list"] = None,
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Change fields on an EXISTING library workout — only the fields you pass are sent.

    To save a new workout use icu_create_workout. This edits the library workout
    only; calendar events are separate records changed with icu_update_event.
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    payload, error = _workout_payload(
        {
            "name": name,
            "description": description,
            "workout_type": workout_type,
            "folder_id": folder_id,
            "day": day,
            "duration_seconds": duration_seconds,
            "distance_meters": distance_meters,
            "training_load": training_load,
            "target": target,
            "indoor": indoor,
            "color": color,
            "tags": tags,
        }
    )
    if error:
        return ResponseBuilder.build_error_response(error, error_type="validation_error")
    if not payload:
        return ResponseBuilder.build_error_response(
            "No fields provided to update. Please specify at least one field to change.",
            error_type="validation_error",
        )

    try:
        async with ICUClient(config) as client:
            workout = await client.update_workout(workout_id, payload, athlete_id=athlete_id)

            return ResponseBuilder.build_response(
                data=_workout_to_dict(workout),
                query_type="update_workout",
                metadata={"message": f"Successfully updated workout {workout_id}"},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def delete_workout(
    workout_id: Annotated[int, "Library workout ID to delete (from icu_get_workouts_in_folder)"],
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Permanently delete ONE workout from the LIBRARY. Destructive — cannot be undone.

    Removes the library workout only; calendar events are separate records
    deleted with icu_delete_event. Confirm with the user before calling if unsure.
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            deleted = await client.delete_workout(workout_id, athlete_id=athlete_id)

            return ResponseBuilder.build_response(
                data={"deleted": deleted, "deleted_count": len(deleted)},
                query_type="delete_workout",
                metadata={"message": f"Deleted workout {workout_id} from the library"},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )
