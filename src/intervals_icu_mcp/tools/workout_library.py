"""Workout library tools for Intervals.icu MCP server."""

from typing import Annotated, Any

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..response_builder import ResponseBuilder


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
