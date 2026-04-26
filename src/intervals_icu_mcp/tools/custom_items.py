"""Tools for the user's customizations on Intervals.icu.

These cover everything a user has added to personalize their account:
custom charts (fitness, trace, activity), custom data fields (on wellness,
activities, intervals), custom power/HR/pace zone configurations, custom
activity streams, and custom dashboard panels/maps/heatmaps. The API calls
this collection "custom items".
"""

from typing import Annotated, Any

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..response_builder import ResponseBuilder

VALID_CUSTOM_ITEM_TYPES = {
    "FITNESS_CHART",
    "FITNESS_TABLE",
    "TRACE_CHART",
    "INPUT_FIELD",
    "ACTIVITY_FIELD",
    "INTERVAL_FIELD",
    "ACTIVITY_STREAM",
    "ACTIVITY_CHART",
    "ACTIVITY_HISTOGRAM",
    "ACTIVITY_HEATMAP",
    "ACTIVITY_MAP",
    "ACTIVITY_PANEL",
    "ZONES",
}

VALID_VISIBILITY = {"PRIVATE", "FOLLOWERS", "PUBLIC"}


def _custom_item_to_dict(item: dict[str, Any]) -> dict[str, Any]:
    """Extract a stable subset of custom item fields for tool responses."""
    result: dict[str, Any] = {}
    for key in (
        "id",
        "athlete_id",
        "type",
        "visibility",
        "name",
        "description",
        "usage_count",
        "index",
        "updated",
    ):
        if key in item and item[key] is not None:
            result[key] = item[key]
    if item.get("content") is not None:
        result["content"] = item["content"]
    return result


def _validate_type(item_type: str | None) -> str | None:
    """Return an error message if item_type is invalid, or None if valid/absent."""
    if item_type is None:
        return None
    if item_type not in VALID_CUSTOM_ITEM_TYPES:
        valid = ", ".join(sorted(VALID_CUSTOM_ITEM_TYPES))
        return f"Invalid item_type. Must be one of: {valid}"
    return None


def _validate_visibility(visibility: str | None) -> str | None:
    """Return an error message if visibility is invalid, or None if valid/absent."""
    if visibility is None:
        return None
    if visibility not in VALID_VISIBILITY:
        return f"Invalid visibility. Must be one of: {', '.join(sorted(VALID_VISIBILITY))}"
    return None


async def get_custom_items(
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """List the user's custom additions to their Intervals.icu account.

    Use this when the user asks about THEIR OWN customizations: "show my
    custom charts", "list my custom fields", "what custom zones do I have",
    "what's on my dashboard", "do I have any custom activity panels".

    Returns every custom item across all types in one call: custom charts
    (FITNESS_CHART, TRACE_CHART, ACTIVITY_CHART, ACTIVITY_HISTOGRAM,
    ACTIVITY_HEATMAP, ACTIVITY_MAP, ACTIVITY_PANEL, FITNESS_TABLE), custom
    data fields (INPUT_FIELD on wellness, ACTIVITY_FIELD on activities,
    INTERVAL_FIELD on intervals), custom ACTIVITY_STREAM definitions, and
    custom ZONES configurations. Each item has a `type` field so you can
    filter client-side if the user asked about a specific kind.

    Do NOT use this for built-in zones, built-in fields, or athlete profile
    data — those have dedicated tools (icu_get_sport_settings, etc.).

    Args:
        athlete_id: Athlete ID (uses configured default if not provided)

    Returns:
        JSON string with the list of custom items and total count
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            items = await client.get_custom_items(athlete_id=athlete_id)

            return ResponseBuilder.build_response(
                data={"items": [_custom_item_to_dict(i) for i in items]},
                metadata={"count": len(items)},
                query_type="custom_items",
            )
    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def get_custom_item(
    item_id: Annotated[int, "Custom item ID"],
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Fetch the full configuration of one of the user's custom additions.

    Use this AFTER icu_get_custom_items has returned an ID, when the user
    wants to inspect a specific custom chart/field/zone/panel in detail
    (the `content` field carries the full configuration which the list
    endpoint also returns but is easier to focus on here).

    Args:
        item_id: Custom item ID (from icu_get_custom_items)
        athlete_id: Athlete ID (uses configured default if not provided)

    Returns:
        JSON string with the custom item details including its `content` config
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            item = await client.get_custom_item(item_id, athlete_id=athlete_id)
            return ResponseBuilder.build_response(
                data=_custom_item_to_dict(item),
                query_type="custom_item",
            )
    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def create_custom_item(
    name: Annotated[str, "Display name (e.g., 'RPE', 'Bike Weight', 'Custom Power Zones')"],
    item_type: Annotated[
        str,
        "What the user wants to add. Pick by intent: "
        "INPUT_FIELD (extra input on the wellness page, e.g. RPE, mood), "
        "ACTIVITY_FIELD (extra field on each activity, e.g. bike weight), "
        "INTERVAL_FIELD (extra field on each interval), "
        "ZONES (custom power/HR/pace zone set), "
        "FITNESS_CHART / TRACE_CHART / FITNESS_TABLE (custom dashboard "
        "chart/table), "
        "ACTIVITY_CHART / ACTIVITY_HISTOGRAM / ACTIVITY_HEATMAP / "
        "ACTIVITY_MAP / ACTIVITY_PANEL (custom visual on the activity page), "
        "ACTIVITY_STREAM (computed time-series). Use the literal API value.",
    ],
    description: Annotated[str | None, "Optional description shown to the user"] = None,
    content: Annotated[
        dict[str, Any] | None,
        "Configuration object whose schema depends on item_type. "
        "REQUIRED for INPUT_FIELD, ACTIVITY_FIELD, INTERVAL_FIELD; for these "
        "the schema is: `code` (machine identifier — must match regex "
        "[A-Z][A-Za-z0-9]+, i.e. start with uppercase and contain only "
        "alphanumerics, no spaces/underscores), `type` ('numeric', 'text', "
        "or 'select' — NOT 'number'), `aggregate` ('MIN', 'SUM', 'MAX', or "
        "'AVERAGE' — NOT 'AVG'). Example: "
        "{'code': 'Rpe', 'type': 'numeric', 'aggregate': 'AVERAGE'}. "
        "Optional for chart/panel/zones/stream types where the API uses "
        "defaults — you can omit and configure in the Intervals.icu UI later.",
    ] = None,
    visibility: Annotated[
        str | None,
        "Who can see it: PRIVATE (default, only you), FOLLOWERS, or PUBLIC.",
    ] = None,
    athlete_id: Annotated[
        str | None, "Athlete ID (only for coaches; uses configured default otherwise)"
    ] = None,
    ctx: Context | None = None,
) -> str:
    """Create a custom addition to the user's Intervals.icu account.

    Use when the user says things like: "add a custom field for RPE", "create
    a custom power zone set", "add a chart for monthly distance to my
    dashboard", "add a bike-weight field to activities". Match the user's
    intent to the right `item_type` enum value (see that param's description
    for the mapping).

    Args:
        name: Display name shown in the Intervals.icu UI
        item_type: One of the API enum values matching the user's intent
        description: Optional human-readable description
        content: Configuration object. REQUIRED for INPUT_FIELD, ACTIVITY_FIELD,
            INTERVAL_FIELD — see the parameter's annotation for the inner schema
            (`code`, `type`, `aggregate`) and validation rules. Optional for
            chart/panel/zones/stream types.
        visibility: PRIVATE, FOLLOWERS, or PUBLIC
        athlete_id: Athlete ID (uses configured default if not provided)

    Returns:
        JSON string with the created custom item including its new ID
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    type_error = _validate_type(item_type)
    if type_error:
        return ResponseBuilder.build_error_response(type_error, error_type="validation_error")
    visibility_error = _validate_visibility(visibility)
    if visibility_error:
        return ResponseBuilder.build_error_response(visibility_error, error_type="validation_error")

    item_data: dict[str, Any] = {"name": name, "type": item_type}
    if description is not None:
        item_data["description"] = description
    if content is not None:
        item_data["content"] = content
    if visibility is not None:
        item_data["visibility"] = visibility

    try:
        async with ICUClient(config) as client:
            created = await client.create_custom_item(item_data, athlete_id=athlete_id)
            return ResponseBuilder.build_response(
                data=_custom_item_to_dict(created),
                metadata={"message": f"Successfully created custom item: {name}"},
                query_type="create_custom_item",
            )
    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def update_custom_item(
    item_id: Annotated[int, "Custom item ID to update"],
    name: Annotated[str | None, "Updated name"] = None,
    item_type: Annotated[str | None, "Updated type (see create_custom_item for values)"] = None,
    description: Annotated[str | None, "Updated description"] = None,
    content: Annotated[
        dict[str, Any] | None,
        "Updated configuration content (replaces existing content). Same "
        "schema rules as create_custom_item.content — for field-type items "
        "the inner shape is {`code`, `type`, `aggregate`} with the same "
        "validation constraints (code regex [A-Z][A-Za-z0-9]+, type in "
        "numeric/text/select, aggregate in MIN/SUM/MAX/AVERAGE).",
    ] = None,
    visibility: Annotated[str | None, "Updated visibility: PRIVATE, FOLLOWERS, or PUBLIC"] = None,
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Modify an existing custom chart/field/zones/panel.

    Use when the user wants to change one of their existing customizations:
    "rename my custom field", "make this chart public", "change the
    description on my zones". You usually need icu_get_custom_items first to
    find the right `item_id`. Only fields you pass are sent — others are
    left unchanged.

    Args:
        item_id: Custom item ID (from icu_get_custom_items)
        name: New display name (optional)
        item_type: New API type (optional, rare)
        description: New description (optional)
        content: New configuration object — REPLACES the existing one (optional)
        visibility: New visibility: PRIVATE, FOLLOWERS, or PUBLIC (optional)
        athlete_id: Athlete ID (uses configured default if not provided)

    Returns:
        JSON string with the updated custom item
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    type_error = _validate_type(item_type)
    if type_error:
        return ResponseBuilder.build_error_response(type_error, error_type="validation_error")
    visibility_error = _validate_visibility(visibility)
    if visibility_error:
        return ResponseBuilder.build_error_response(visibility_error, error_type="validation_error")

    item_data: dict[str, Any] = {}
    if name is not None:
        item_data["name"] = name
    if item_type is not None:
        item_data["type"] = item_type
    if description is not None:
        item_data["description"] = description
    if content is not None:
        item_data["content"] = content
    if visibility is not None:
        item_data["visibility"] = visibility

    if not item_data:
        return ResponseBuilder.build_error_response(
            "No fields provided to update", error_type="validation_error"
        )

    try:
        async with ICUClient(config) as client:
            updated = await client.update_custom_item(item_id, item_data, athlete_id=athlete_id)
            return ResponseBuilder.build_response(
                data=_custom_item_to_dict(updated),
                metadata={"message": f"Successfully updated custom item {item_id}"},
                query_type="update_custom_item",
            )
    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def delete_custom_item(
    item_id: Annotated[int, "Custom item ID to delete"],
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Permanently remove one of the user's custom additions.

    Use when the user says "delete my custom field for X", "remove that
    chart from my dashboard", "drop the custom zones I made last week".
    You usually need icu_get_custom_items first to find the right `item_id`.
    This is destructive and cannot be undone — confirm with the user before
    calling if you are unsure.

    Args:
        item_id: Custom item ID (from icu_get_custom_items)
        athlete_id: Athlete ID (uses configured default if not provided)

    Returns:
        JSON string confirming deletion
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            await client.delete_custom_item(item_id, athlete_id=athlete_id)
            return ResponseBuilder.build_response(
                data={"item_id": item_id, "deleted": True},
                metadata={"message": f"Successfully deleted custom item {item_id}"},
                query_type="delete_custom_item",
            )
    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )
