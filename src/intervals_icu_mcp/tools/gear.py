"""Gear management tools for tracking equipment and maintenance."""

from datetime import date
from typing import Annotated, Any

from fastmcp import Context

from ..auth import load_config, validate_credentials
from ..client import ICUAPIError, ICUClient
from ..response_builder import ResponseBuilder

# The API's gear `type` enum (CamelCase). Includes whole items (Bike, Shoes,
# Trainer, ...) and component types (Chain, Cassette, Wheel, ...).
GEAR_TYPES = [
    "Bike", "Shoes", "Wetsuit", "RowingMachine", "Skis", "Snowboard", "Boat",
    "Board", "Equipment", "Accessories", "Apparel", "Computer", "Light",
    "Battery", "Brake", "BrakePads", "Rotor", "Drivetrain", "BottomBracket",
    "Cassette", "Chain", "Chainrings", "Crankset", "Derailleur", "Pedals",
    "Lever", "Cable", "Frame", "Fork", "Handlebar", "Headset", "Saddle",
    "Seatpost", "Shock", "Stem", "Axel", "Hub", "Trainer", "Tube", "Tyre",
    "Wheel", "Wheelset", "PowerMeter", "Cleats", "CyclingShoes", "Paddle",
]  # fmt: skip

# Case-insensitive lookup, plus the singular "SHOE" spelling the tool docs
# previously taught.
_GEAR_TYPE_LOOKUP = {v.upper(): v for v in GEAR_TYPES} | {"SHOE": "Shoes"}

def _ignored_params_note(**params: Any) -> str | None:
    """Warning for tool params with no API-side field — accepted for
    compatibility, reported as ignored (#110; removal deferred to next major)."""
    ignored = [name for name, value in params.items() if value]
    if not ignored:
        return None
    return (
        f"Ignored parameter(s) {', '.join(ignored)}: the Intervals.icu API has no "
        "brand/model/primary fields on gear. Put such details in the gear name."
    )


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
                    "type": gear.type,
                    "active": gear.retired is None,
                }

                if gear.retired:
                    gear_info["retired_on"] = gear.retired
                if gear.purchased:
                    gear_info["purchased_on"] = gear.purchased
                if gear.notes:
                    gear_info["notes"] = gear.notes

                # Usage statistics
                usage: dict[str, Any] = {}
                if gear.distance is not None:
                    usage["total_distance_km"] = round(gear.distance / 1000, 2)
                if gear.time is not None:
                    total_secs = int(gear.time)
                    hours = total_secs // 3600
                    minutes = (total_secs % 3600) // 60
                    usage["total_time"] = f"{hours}h {minutes}m"
                if gear.activities is not None:
                    usage["activity_count"] = gear.activities

                if usage:
                    gear_info["usage"] = usage

                # Maintenance reminders
                if gear.reminders:
                    reminders_data: list[dict[str, Any]] = []
                    for reminder in gear.reminders:
                        reminder_info: dict[str, Any] = {
                            "id": reminder.id,
                            "text": reminder.name,
                        }

                        # Recurring trigger thresholds (API sends 0 for unused)
                        if reminder.distance:
                            reminder_info["alert_every_km"] = round(reminder.distance / 1000, 2)
                        if reminder.time:
                            reminder_info["alert_every_hours"] = int(reminder.time // 3600)
                        if reminder.activities:
                            reminder_info["alert_every_activities"] = reminder.activities
                        if reminder.days:
                            reminder_info["alert_every_days"] = reminder.days

                        # Consumption since the reminder was last reset
                        if reminder.percent_used is not None:
                            reminder_info["percent_used"] = round(reminder.percent_used, 1)
                        if reminder.distance and reminder.distance_used is not None:
                            reminder_info["used_km"] = round(reminder.distance_used / 1000, 2)
                        if reminder.time and reminder.time_used is not None:
                            reminder_info["used_hours"] = round(reminder.time_used / 3600, 1)

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
    gear_type: Annotated[
        str,
        "Gear type, case-insensitive. Whole items: Bike, Shoes, Wetsuit, Trainer, "
        "RowingMachine, Skis, Snowboard, Boat, Board, Equipment, Accessories, "
        "Apparel, Computer. Components: Chain, Cassette, Wheel, Tyre, Frame, "
        "Pedals, PowerMeter, and more.",
    ],
    brand: Annotated[str | None, "IGNORED — the API has no brand field; put it in the name"] = None,
    model: Annotated[str | None, "IGNORED — the API has no model field; put it in the name"] = None,
    active: Annotated[bool, "Whether this gear is actively used (False = retired)"] = True,
    primary: Annotated[bool | None, "IGNORED — the API has no primary flag on gear"] = None,
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Create a new gear item for tracking equipment usage and maintenance (bikes, shoes, trainers, etc.)."""
    config = load_config()
    if not validate_credentials(config):
        return (
            "Error: Intervals.icu credentials not configured. Run intervals-icu-mcp-auth to set up."
        )

    api_type = _GEAR_TYPE_LOOKUP.get(gear_type.upper())
    if api_type is None:
        return ResponseBuilder.build_error_response(
            f"Invalid gear_type '{gear_type}'. Must be one of: {', '.join(GEAR_TYPES)}.",
            error_type="validation_error",
        )

    try:
        async with ICUClient(config) as client:
            gear_data: dict[str, Any] = {"name": name, "type": api_type}
            if not active:
                gear_data["retired"] = date.today().isoformat()

            gear = await client.create_gear(gear_data, athlete_id=athlete_id)

            result: dict[str, Any] = {
                "id": gear.id,
                "name": gear.name,
                "type": gear.type,
                "active": gear.retired is None,
            }

            metadata: dict[str, Any] = {
                "type": "gear_created",
                "message": "Gear item created successfully",
            }
            note = _ignored_params_note(brand=brand, model=model, primary=primary)
            if note:
                metadata["warning"] = note

            return ResponseBuilder.build_response(result, metadata=metadata)

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(str(e), error_type="unexpected_error")


async def update_gear(
    gear_id: Annotated[str, "ID of the gear item to update"],
    name: Annotated[str | None, "Updated name"] = None,
    gear_type: Annotated[
        str | None, "Updated type, case-insensitive (Bike, Shoes, Trainer, Chain, ...)"
    ] = None,
    brand: Annotated[str | None, "IGNORED — the API has no brand field; put it in the name"] = None,
    model: Annotated[str | None, "IGNORED — the API has no model field; put it in the name"] = None,
    active: Annotated[
        bool | None, "False retires the gear (dated today); True un-retires it"
    ] = None,
    primary: Annotated[bool | None, "IGNORED — the API has no primary flag on gear"] = None,
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Update an existing gear item. Only fields you pass are sent."""
    config = load_config()
    if not validate_credentials(config):
        return (
            "Error: Intervals.icu credentials not configured. Run intervals-icu-mcp-auth to set up."
        )

    api_type: str | None = None
    if gear_type is not None:
        api_type = _GEAR_TYPE_LOOKUP.get(gear_type.upper())
        if api_type is None:
            return ResponseBuilder.build_error_response(
                f"Invalid gear_type '{gear_type}'. Must be one of: {', '.join(GEAR_TYPES)}.",
                error_type="validation_error",
            )

    try:
        async with ICUClient(config) as client:
            gear_data: dict[str, Any] = {}

            if name is not None:
                gear_data["name"] = name
            if api_type is not None:
                gear_data["type"] = api_type
            if active is False:
                gear_data["retired"] = date.today().isoformat()
            elif active is True:
                # Live-verified: the API ignores null for `retired` (Jackson
                # treats it as absent); empty string is what clears it.
                gear_data["retired"] = ""

            if not gear_data:
                return ResponseBuilder.build_error_response(
                    "No fields provided to update", error_type="validation_error"
                )

            gear = await client.update_gear(gear_id, gear_data, athlete_id=athlete_id)

            result: dict[str, Any] = {
                "id": gear.id,
                "name": gear.name,
                "type": gear.type,
                "active": gear.retired is None,
            }
            if gear.retired:
                result["retired_on"] = gear.retired

            # Usage statistics
            if gear.distance is not None or gear.time is not None:
                usage: dict[str, Any] = {}
                if gear.distance is not None:
                    usage["total_distance_km"] = round(gear.distance / 1000, 2)
                if gear.time is not None:
                    total_secs = int(gear.time)
                    usage["total_time"] = f"{total_secs // 3600}h {(total_secs % 3600) // 60}m"
                if gear.activities is not None:
                    usage["activity_count"] = gear.activities
                result["usage"] = usage

            metadata: dict[str, Any] = {
                "type": "gear_updated",
                "message": "Gear item updated successfully",
            }
            note = _ignored_params_note(brand=brand, model=model, primary=primary)
            if note:
                metadata["warning"] = note

            return ResponseBuilder.build_response(result, metadata=metadata)

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
            # API field names: name, distance (meters), time (seconds)
            reminder_data: dict[str, Any] = {"name": text}

            if distance_alert is not None:
                reminder_data["distance"] = int(distance_alert * 1000)

            if time_alert is not None:
                reminder_data["time"] = time_alert * 3600

            if distance_alert is None and time_alert is None:
                return ResponseBuilder.build_error_response(
                    "Must specify at least one alert threshold (distance_alert or time_alert)",
                    error_type="validation_error",
                )

            # The API returns the full Gear object; the new reminder is the
            # newest entry carrying the name we just sent.
            gear = await client.create_gear_reminder(gear_id, reminder_data, athlete_id=athlete_id)
            reminder = next(
                (
                    r
                    for r in sorted(gear.reminders, key=lambda r: r.id, reverse=True)
                    if r.name == text
                ),
                None,
            )

            result: dict[str, Any] = {"gear_id": gear_id, "text": text}

            if reminder is not None:
                result["id"] = reminder.id
                if reminder.distance:
                    result["alert_every_km"] = round(reminder.distance / 1000, 2)
                if reminder.time:
                    result["alert_every_hours"] = int(reminder.time // 3600)

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
            # API field names: name, distance (meters), time (seconds)
            reminder_data: dict[str, Any] = {}

            if text is not None:
                reminder_data["name"] = text

            if distance_alert is not None:
                reminder_data["distance"] = int(distance_alert * 1000)

            if time_alert is not None:
                reminder_data["time"] = time_alert * 3600

            if not reminder_data:
                return ResponseBuilder.build_error_response(
                    "No fields provided to update", error_type="validation_error"
                )

            # The API returns the full Gear object; report the reminder we updated.
            gear = await client.update_gear_reminder(
                gear_id, reminder_id, reminder_data, athlete_id=athlete_id
            )
            reminder = next((r for r in gear.reminders if r.id == reminder_id), None)

            result: dict[str, Any] = {"id": reminder_id, "gear_id": gear_id}

            if reminder is not None:
                result["text"] = reminder.name
                if reminder.distance:
                    result["alert_every_km"] = round(reminder.distance / 1000, 2)
                if reminder.time:
                    result["alert_every_hours"] = int(reminder.time // 3600)
                if reminder.percent_used is not None:
                    result["percent_used"] = round(reminder.percent_used, 1)

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
