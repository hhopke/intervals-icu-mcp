"""Gear management tools for tracking equipment and maintenance."""

from typing import Annotated, Any

from fastmcp import Context

from ..auth import load_config, validate_credentials
from ..client import ICUAPIError, ICUClient
from ..response_builder import ResponseBuilder


async def get_gear_list(
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """List all gear items with usage stats (distance, time, activity count) and maintenance reminders."""
    config = load_config()
    if not validate_credentials(config):
        return (
            "Error: Intervals.icu credentials not configured. Run intervals-icu-mcp-auth to set up."
        )

    try:
        async with ICUClient(config) as client:
            gear_list = await client.get_gear(athlete_id=athlete_id)

            if not gear_list:
                return ResponseBuilder.build_response(
                    {"message": "No gear items found"}, metadata={"count": 0}
                )

            gear_data: list[dict[str, Any]] = []

            for gear in gear_list:
                gear_info: dict[str, Any] = {
                    "id": gear.id,
                    "name": gear.name,
                    "type": gear.gear_type,
                    "active": gear.active,
                }

                # Brand and model
                if gear.brand:
                    gear_info["brand"] = gear.brand
                if gear.model:
                    gear_info["model"] = gear.model

                # Usage statistics
                usage: dict[str, Any] = {}
                if gear.distance is not None:
                    usage["total_distance_km"] = round(gear.distance / 1000, 2)
                if gear.moving_time is not None:
                    hours = gear.moving_time // 3600
                    minutes = (gear.moving_time % 3600) // 60
                    usage["total_time"] = f"{hours}h {minutes}m"
                if gear.activity_count is not None:
                    usage["activity_count"] = gear.activity_count

                if usage:
                    gear_info["usage"] = usage

                # Maintenance reminders
                if gear.reminders:
                    reminders_data: list[dict[str, Any]] = []
                    for reminder in gear.reminders:
                        reminder_info: dict[str, Any] = {
                            "id": reminder.id,
                            "text": reminder.text,
                        }

                        # Alert thresholds
                        if reminder.distance_alert is not None:
                            reminder_info["alert_every_km"] = round(
                                reminder.distance_alert / 1000, 2
                            )
                        if reminder.time_alert is not None:
                            hours = reminder.time_alert // 3600
                            reminder_info["alert_every_hours"] = hours

                        # Due status
                        if reminder.is_due is not None:
                            reminder_info["is_due"] = reminder.is_due

                        if reminder.due_distance is not None:
                            reminder_info["due_in_km"] = round(reminder.due_distance / 1000, 2)
                        if reminder.due_time is not None:
                            hours = reminder.due_time // 3600
                            reminder_info["due_in_hours"] = hours

                        if reminder.snoozed_until:
                            reminder_info["snoozed_until"] = reminder.snoozed_until

                        reminders_data.append(reminder_info)

                    gear_info["reminders"] = reminders_data

                gear_data.append(gear_info)

            return ResponseBuilder.build_response(
                {"gear": gear_data}, metadata={"count": len(gear_list), "type": "gear_list"}
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(str(e), error_type="unexpected_error")


async def create_gear(
    name: Annotated[str, "Name of the gear item"],
    gear_type: Annotated[str, "Type of gear (e.g., 'BIKE', 'SHOE', 'TRAINER', 'WETSUIT', 'OTHER')"],
    brand: Annotated[str | None, "Brand name"] = None,
    model: Annotated[str | None, "Model name"] = None,
    active: Annotated[bool, "Whether this gear is actively used"] = True,
    primary: Annotated[bool, "Whether this is the primary gear of this type"] = False,
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Create a new gear item for tracking equipment usage and maintenance (bikes, shoes, trainers, etc.)."""
    config = load_config()
    if not validate_credentials(config):
        return (
            "Error: Intervals.icu credentials not configured. Run intervals-icu-mcp-auth to set up."
        )

    try:
        async with ICUClient(config) as client:
            gear_data: dict[str, Any] = {
                "name": name,
                "gear_type": gear_type,
                "active": active,
                "primary": primary,
            }

            if brand:
                gear_data["brand"] = brand
            if model:
                gear_data["model"] = model

            gear = await client.create_gear(gear_data, athlete_id=athlete_id)

            result: dict[str, Any] = {
                "id": gear.id,
                "name": gear.name,
                "type": gear.gear_type,
                "active": gear.active,
                "primary": gear.primary,
            }

            if gear.brand:
                result["brand"] = gear.brand
            if gear.model:
                result["model"] = gear.model

            return ResponseBuilder.build_response(
                result,
                metadata={"type": "gear_created", "message": "Gear item created successfully"},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(str(e), error_type="unexpected_error")


async def update_gear(
    gear_id: Annotated[str, "ID of the gear item to update"],
    name: Annotated[str | None, "Updated name"] = None,
    gear_type: Annotated[str | None, "Updated type (BIKE, SHOE, TRAINER, etc.)"] = None,
    brand: Annotated[str | None, "Updated brand"] = None,
    model: Annotated[str | None, "Updated model"] = None,
    active: Annotated[bool | None, "Whether this gear is actively used"] = None,
    primary: Annotated[bool | None, "Whether this is the primary gear of this type"] = None,
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Update an existing gear item. Only fields you pass are sent."""
    config = load_config()
    if not validate_credentials(config):
        return (
            "Error: Intervals.icu credentials not configured. Run intervals-icu-mcp-auth to set up."
        )

    try:
        async with ICUClient(config) as client:
            gear_data: dict[str, Any] = {}

            if name is not None:
                gear_data["name"] = name
            if gear_type is not None:
                gear_data["gear_type"] = gear_type
            if brand is not None:
                gear_data["brand"] = brand
            if model is not None:
                gear_data["model"] = model
            if active is not None:
                gear_data["active"] = active
            if primary is not None:
                gear_data["primary"] = primary

            if not gear_data:
                return ResponseBuilder.build_error_response(
                    "No fields provided to update", error_type="validation_error"
                )

            gear = await client.update_gear(gear_id, gear_data, athlete_id=athlete_id)

            result: dict[str, Any] = {
                "id": gear.id,
                "name": gear.name,
                "type": gear.gear_type,
                "active": gear.active,
                "primary": gear.primary,
            }

            if gear.brand:
                result["brand"] = gear.brand
            if gear.model:
                result["model"] = gear.model

            # Usage statistics
            if gear.distance is not None or gear.moving_time is not None:
                usage: dict[str, Any] = {}
                if gear.distance is not None:
                    usage["total_distance_km"] = round(gear.distance / 1000, 2)
                if gear.moving_time is not None:
                    hours = gear.moving_time // 3600
                    minutes = (gear.moving_time % 3600) // 60
                    usage["total_time"] = f"{hours}h {minutes}m"
                if gear.activity_count is not None:
                    usage["activity_count"] = gear.activity_count
                result["usage"] = usage

            return ResponseBuilder.build_response(
                result,
                metadata={"type": "gear_updated", "message": "Gear item updated successfully"},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(str(e), error_type="unexpected_error")


async def delete_gear(
    gear_id: Annotated[str, "ID of the gear item to delete"],
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Permanently delete a gear item and its maintenance reminders. Activities that used this gear are not affected."""
    config = load_config()
    if not validate_credentials(config):
        return (
            "Error: Intervals.icu credentials not configured. Run intervals-icu-mcp-auth to set up."
        )

    try:
        async with ICUClient(config) as client:
            await client.delete_gear(gear_id, athlete_id=athlete_id)

            return ResponseBuilder.build_response(
                {"gear_id": gear_id, "deleted": True},
                metadata={"type": "gear_deleted", "message": "Gear item deleted successfully"},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(str(e), error_type="unexpected_error")


async def create_gear_reminder(
    gear_id: Annotated[str, "ID of the gear item"],
    text: Annotated[str, "Reminder text (e.g., 'Replace chain', 'New shoes')"],
    distance_alert: Annotated[
        float | None, "Alert every N kilometers (e.g., 500 for every 500km)"
    ] = None,
    time_alert: Annotated[int | None, "Alert every N hours (e.g., 100 for every 100 hours)"] = None,
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Create a maintenance reminder for a gear item, triggered by distance, time, or both."""
    config = load_config()
    if not validate_credentials(config):
        return (
            "Error: Intervals.icu credentials not configured. Run intervals-icu-mcp-auth to set up."
        )

    try:
        async with ICUClient(config) as client:
            reminder_data: dict[str, Any] = {"text": text}

            if distance_alert is not None:
                # Convert km to meters
                reminder_data["distance_alert"] = int(distance_alert * 1000)

            if time_alert is not None:
                # Convert hours to seconds
                reminder_data["time_alert"] = time_alert * 3600

            if distance_alert is None and time_alert is None:
                return ResponseBuilder.build_error_response(
                    "Must specify at least one alert threshold (distance_alert or time_alert)",
                    error_type="validation_error",
                )

            reminder = await client.create_gear_reminder(
                gear_id, reminder_data, athlete_id=athlete_id
            )

            result: dict[str, Any] = {
                "id": reminder.id,
                "gear_id": gear_id,
                "text": reminder.text,
            }

            if reminder.distance_alert is not None:
                result["alert_every_km"] = round(reminder.distance_alert / 1000, 2)
            if reminder.time_alert is not None:
                result["alert_every_hours"] = reminder.time_alert // 3600

            return ResponseBuilder.build_response(
                result,
                metadata={
                    "type": "reminder_created",
                    "message": "Gear reminder created successfully",
                },
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(str(e), error_type="unexpected_error")


async def update_gear_reminder(
    gear_id: Annotated[str, "ID of the gear item"],
    reminder_id: Annotated[int, "ID of the reminder to update"],
    text: Annotated[str | None, "Updated reminder text"] = None,
    distance_alert: Annotated[float | None, "Updated distance alert in kilometers"] = None,
    time_alert: Annotated[int | None, "Updated time alert in hours"] = None,
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Update an existing gear maintenance reminder. Only fields you pass are sent."""
    config = load_config()
    if not validate_credentials(config):
        return (
            "Error: Intervals.icu credentials not configured. Run intervals-icu-mcp-auth to set up."
        )

    try:
        async with ICUClient(config) as client:
            reminder_data: dict[str, Any] = {}

            if text is not None:
                reminder_data["text"] = text

            if distance_alert is not None:
                # Convert km to meters
                reminder_data["distance_alert"] = int(distance_alert * 1000)

            if time_alert is not None:
                # Convert hours to seconds
                reminder_data["time_alert"] = time_alert * 3600

            if not reminder_data:
                return ResponseBuilder.build_error_response(
                    "No fields provided to update", error_type="validation_error"
                )

            reminder = await client.update_gear_reminder(
                gear_id, reminder_id, reminder_data, athlete_id=athlete_id
            )

            result: dict[str, Any] = {
                "id": reminder.id,
                "gear_id": gear_id,
                "text": reminder.text,
            }

            if reminder.distance_alert is not None:
                result["alert_every_km"] = round(reminder.distance_alert / 1000, 2)
            if reminder.time_alert is not None:
                result["alert_every_hours"] = reminder.time_alert // 3600

            if reminder.is_due is not None:
                result["is_due"] = reminder.is_due

            if reminder.due_distance is not None:
                result["due_in_km"] = round(reminder.due_distance / 1000, 2)
            if reminder.due_time is not None:
                result["due_in_hours"] = reminder.due_time // 3600

            return ResponseBuilder.build_response(
                result,
                metadata={
                    "type": "reminder_updated",
                    "message": "Gear reminder updated successfully",
                },
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(str(e), error_type="unexpected_error")
