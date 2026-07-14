"""Event/calendar management tools for Intervals.icu MCP server."""

import asyncio
from datetime import date, datetime
from typing import Annotated, Any, cast

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..models import Event
from ..response_builder import ResponseBuilder

PAST_EVENT_HINT = (
    "Past events (today and earlier) require INTERVALS_ICU_DELETE_MODE=full. "
    "Safe mode only deletes events dated tomorrow or later, to absorb "
    "server-vs-athlete timezone skew. This is a server-side env var set by the "
    "operator, not a tool parameter."
)
MISSING_DATE_HINT = (
    "Event has no start_date_local; cannot verify it is in the future. "
    "Use INTERVALS_ICU_DELETE_MODE=full to override."
)


def _classify_event_date(start_date_local: str | None) -> str:
    """Classify an event's date for safe-mode gating.

    Compares at date granularity (planned events typically lack meaningful times).
    Today is classified as 'past' so safe mode only deletes events dated tomorrow
    or later. The one-day buffer absorbs server-vs-athlete timezone skew (e.g.,
    UTC server with non-UTC athlete profile) without an extra API call.

    Returns one of: 'future', 'past', 'unknown'.
    """
    if not start_date_local:
        return "unknown"
    try:
        parsed = datetime.fromisoformat(start_date_local).date()
    except (ValueError, TypeError):
        return "unknown"
    return "future" if parsed > date.today() else "past"


def _delete_envelope(
    deleted: list[int],
    skipped: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the uniform deleted/skipped response envelope."""
    return {
        "deleted": deleted,
        "deleted_count": len(deleted),
        "skipped": skipped,
        "skipped_count": len(skipped),
    }


def _skipped_entry_for(event_id: int, event: Event | None) -> dict[str, Any]:
    """Build a `skipped` entry for an event refused in safe mode."""
    classification = _classify_event_date(event.start_date_local if event else None)
    if classification == "past":
        return {
            "id": event_id,
            "reason": "past_event",
            "start_date_local": event.start_date_local if event else None,
            "hint": PAST_EVENT_HINT,
        }
    return {
        "id": event_id,
        "reason": "missing_date",
        "start_date_local": event.start_date_local if event else None,
        "hint": MISSING_DATE_HINT,
    }


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

# Compact, in-context workout-syntax cheat-sheet for the `description` field.
# Inlined (not only pointed at via the intervals-icu://workout-syntax resource)
# because many hosts — notably Claude Desktop — never surface MCP resources to the
# model, so weaker models fall back to inventing non-native formats. Each "NOT"
# clause targets a failure mode observed in real model output.
WORKOUT_SYNTAX_HINT = (
    "For WORKOUT events the server parses this into structured, device-syncable "
    "steps with zones and a training load. Use Intervals.icu workout syntax: one "
    "step per line as '- <duration> <target>' (duration FIRST), grouped under "
    "Warmup / Main / Cooldown headers. Targets: bike '- 5m 85%', '- 5m Z4', or "
    "absolute '- 5m 210w'; HR '- 10m 70-80% HR' or '- 10m 145bpm'; run pace "
    "'- 5m 5:00/km' or '- 5m Z2 Pace'. Add cadence to any step: '- 3m Z2 90rpm'. "
    "No target: '- 20m free'. Repeats: put "
    "'Nx' after a section name with steps flat beneath, and leave a blank line "
    "before and after the repeat block (without it the repeat silently runs only "
    "once) — e.g. 'Main 5x' then '- 3m 110%' / '- 3m 50%'. Ramps: '- 10m ramp "
    "50-70%'. Rest: append 'Ns rest' "
    "to a step ('- 200mtr Z2 20s rest') or use a separate '- 20s intensity=rest' "
    "step (only intensity=rest exports as a device rest step) — never a bare "
    "'- 20s' step (that becomes work, not rest). Durations: 'm'=minutes, 's'=seconds; "
    "distance steps use 'mtr'=meters / 'km' / 'yrd' (e.g. swim '- 400mtr Z2 Pace'). "
    "Do NOT write '[repeat 5x ...]', nested bullets, or 'Z5 3m' (target before "
    "duration). Runs need a pace or HR target — a bare 'Z2' gives no load. Full "
    "reference: intervals-icu://workout-syntax resource."
)


def _count_workout_steps(steps: list[Any]) -> int:
    """Count total steps in a parsed workout_doc, expanding repeat blocks.

    Each entry in workout_doc["steps"] is either a plain step or a repeat block
    (has `reps` plus a nested `steps` list). Repeats count as reps × nested count.
    """
    total = 0
    for step in steps:
        if isinstance(step, dict):
            step_dict = cast(dict[str, Any], step)
            nested = step_dict.get("steps")
            if isinstance(nested, list):
                total += int(step_dict.get("reps", 1)) * len(cast(list[Any], nested))
                continue
        total += 1
    return total


def _swim_work_lacks_intensity(steps: list[Any]) -> bool:
    """True if a swim's work steps carry no pace/HR target.

    Swim load comes from a pace target (needs a swim CSS/threshold) or an HR target
    (needs swim FTHR). Warmup/cooldown steps are excluded so a warmup pace zone
    can't mask a main set with no intensity, and repeat blocks are flattened to
    their steps. Flat steps under a Warmup/Cooldown header carry a `warmup`/
    `cooldown` flag — as do steps tagged `intensity=warmup`/`cooldown`, at any
    nesting level — but a repeated header ("Warmup 4x") never does — the header
    survives only in the block's `text` — so repeat blocks are matched on that
    (same case-insensitive exact word the API recognizes; live-verified).
    Returns False when there are no work steps to judge. Keying the
    swim load hint on this (rather than total load) catches a main set that parsed
    structurally but dropped its target — e.g. an unrecognized `CSS` token — even
    when a stray misapplied zone leaves a token training load behind.
    """
    work: list[dict[str, Any]] = []

    def _collect(items: list[Any], excluded: bool) -> None:
        for step in items:
            if not isinstance(step, dict):
                continue
            step_dict = cast(dict[str, Any], step)
            nested = step_dict.get("steps")
            if isinstance(nested, list):
                text = str(step_dict.get("text") or "").lower()
                _collect(
                    cast(list[Any], nested),
                    excluded or text.startswith(("warmup", "cooldown")),
                )
            elif (
                not excluded and not step_dict.get("warmup") and not step_dict.get("cooldown")
            ):
                work.append(step_dict)

    _collect(steps, False)
    if not work:
        return False
    return not any(s.get("pace") or s.get("hr") for s in work)


def _workout_parse_info(event: Event) -> dict[str, Any] | None:
    """Echo whether a WORKOUT `description` parsed into a structured workout.

    Intervals.icu always returns a workout_doc object, but its `steps` list is
    empty when the description could not be parsed (prose, or a non-native format
    a model invented). Surfacing this lets the caller tell a real structured
    workout — one that syncs to devices and gets a computed load — from free text
    stored verbatim, instead of a silent "success". Returns None for non-WORKOUT
    events or WORKOUT events with no description (nothing to parse).
    """
    if event.category != "WORKOUT" or not event.description:
        return None
    doc: dict[str, Any] = event.workout_doc or {}
    steps: list[Any] = doc.get("steps") or []
    if steps:
        info: dict[str, Any] = {
            "workout_parsed": True,
            "workout_steps": _count_workout_steps(steps),
        }
        # Swim-specific: a swim can parse into steps yet get no usable training load,
        # because pace targets need a swim CSS/threshold (commonly unset) while HR
        # targets load fine off swim FTHR. Key on whether the *work* steps carry an
        # intensity target rather than on total load — a warmup pace zone or a stray
        # misapplied zone can leave a token load on an otherwise intensity-less set.
        if event.type == "Swim" and _swim_work_lacks_intensity(steps):
            info["workout_load_hint"] = (
                "Swim parsed but its work steps have no pace or HR target, so it "
                "won't get a meaningful training load. Swim load needs an intensity "
                "target: pace ('- 200mtr Z3 Pace' / '- 200mtr 95% pace') requires a "
                "swim CSS/threshold to be set; HR targets ('- 200mtr Z2 HR') compute "
                "load from swim FTHR without a CSS. Distance steps also can't be timed "
                "without a CSS (duration is a placeholder) — prefer HR or time-based "
                "steps, or set a CSS via icu_update_sport_settings."
            )
        return info
    return {
        "workout_parsed": False,
        "workout_parse_hint": (
            "Description saved as plain text, not a structured workout (no steps "
            "parsed, no training load). For device-syncable steps/zones use "
            "Intervals.icu workout syntax: '- 5m 85%' / '- 3m Z5' lines under "
            "Warmup/Main/Cooldown headers, 'Nx' after a section name for repeats. "
            "See intervals-icu://workout-syntax."
        ),
    }


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

    parse_info = _workout_parse_info(event)
    if parse_info:
        result.update(parse_info)

    return result


async def create_event(
    start_date: Annotated[str, "Start date in YYYY-MM-DD format"],
    name: Annotated[str, "Event name"],
    category: Annotated[
        str,
        "Event category enum. Common: WORKOUT, NOTE, RACE_A/B/C, TARGET, PLAN, "
        "HOLIDAY, SICK, INJURED. Full list with use-case guidance and the "
        "training_availability enum: intervals-icu://event-categories resource. "
        "Legacy aliases RACE→RACE_A, GOAL→TARGET accepted.",
    ],
    description: Annotated[
        str | None,
        "Event description (plain text for non-workouts). " + WORKOUT_SYNTAX_HINT,
    ] = None,
    event_type: Annotated[
        str | None,
        "Activity discipline (NOT the category): Ride, Run, Swim, Walk, Hike, "
        "VirtualRide, VirtualRun, Other. Required for RACE_A/B/C events.",
    ] = None,
    duration_seconds: Annotated[int | None, "Planned duration in seconds"] = None,
    distance_meters: Annotated[float | None, "Planned distance in meters"] = None,
    training_load: Annotated[int | None, "Planned training load"] = None,
    end_date: Annotated[
        str | None,
        "End date in YYYY-MM-DD format. Use for ranged categories (INJURED, "
        "SICK, HOLIDAY, SEASON_START) to mark a multi-day block.",
    ] = None,
    training_availability: Annotated[
        str | None,
        "Training availability: NORMAL, LIMITED, or UNAVAILABLE. Typical for "
        "INJURED/SICK/HOLIDAY blocks.",
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
    """Create ONE new calendar event from scratch.

    For two or more events in a single call, prefer icu_bulk_create_events
    over a loop. For copying existing events forward in time (repeating
    a workout for N weeks), use icu_duplicate_events — that tool reuses an
    existing event's payload instead of taking new fields.

    For category guidance and the training_availability enum, read the
    intervals-icu://event-categories resource. For structured WORKOUT events,
    put workout-syntax text in `description` — see intervals-icu://workout-syntax.
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
    description: Annotated[str | None, "Updated description. " + WORKOUT_SYNTAX_HINT] = None,
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

    Only fields you pass are sent — other fields remain unchanged. For category
    and training_availability semantics, see intervals-icu://event-categories.
    For WORKOUT `description` syntax, see intervals-icu://workout-syntax.
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
    """Permanently delete ONE calendar event by ID. Destructive — cannot be undone.

    In `safe` delete mode (default), past events are refused and reported
    in the `skipped` envelope with a hint about INTERVALS_ICU_DELETE_MODE=full.
    Returns a `deleted` / `skipped` envelope either way.
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            if config.intervals_icu_delete_mode == "safe":
                event = await client.get_event(event_id, athlete_id=athlete_id)
                if _classify_event_date(event.start_date_local) != "future":
                    return ResponseBuilder.build_response(
                        data=_delete_envelope(
                            deleted=[],
                            skipped=[_skipped_entry_for(event_id, event)],
                        ),
                        query_type="delete_event",
                        metadata={"message": f"Skipped event {event_id} in safe mode"},
                    )

            success = await client.delete_event(event_id, athlete_id=athlete_id)
            if not success:
                return ResponseBuilder.build_error_response(
                    f"Failed to delete event {event_id}",
                    error_type="api_error",
                )
            return ResponseBuilder.build_response(
                data=_delete_envelope(deleted=[event_id], skipped=[]),
                query_type="delete_event",
                metadata={"message": f"Successfully deleted event {event_id}"},
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
        "JSON array of event objects. Required per event: start_date_local, "
        "name, category. Optional: description, event_type (activity discipline "
        "Ride/Run/Swim/…; raw `type` also accepted), moving_time, distance, "
        "icu_training_load, end_date_local, training_availability, color, "
        "show_as_note, not_on_fitness_chart, show_on_ctl_line. See "
        "intervals-icu://event-categories for the category enum. " + WORKOUT_SYNTAX_HINT,
    ],
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Create MANY new calendar events in a single batch call (more efficient than looping create_event).

    Accepts a JSON array of event objects, each shaped like an icu_create_event
    payload. For copying existing events forward use icu_duplicate_events
    instead — that reuses payloads rather than taking new fields. See
    intervals-icu://event-categories and intervals-icu://workout-syntax
    for the referenced enums and DSL.
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

            # Accept `event_type` (the icu_create_event / icu_update_event parameter
            # name) as an alias for the API's `type` field, so bulk payloads can mirror
            # the singular tools. Raw `type` still works and wins if both are present.
            if "event_type" in event_data:
                event_data.setdefault("type", event_data.pop("event_type"))

            if normalized_category in RACE_CATEGORIES and not event_data.get("type"):
                return ResponseBuilder.build_error_response(
                    f"Event {i}: 'event_type' is required for {normalized_category} events. "
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
    """Delete MANY calendar events in a single batch call. Destructive — cannot be undone.

    In `safe` delete mode (default), the call partitions the input list
    into `deleted` (future) and `skipped` (past or undated) and returns
    both. INTERVALS_ICU_DELETE_MODE=full disables the partition.

    Args:
        event_ids: JSON array of event IDs (integers)

    Returns:
        JSON string with `deleted` / `skipped` envelope
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        import json

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

        ids_list: list[int] = parsed_data  # type: ignore[assignment]

        async with ICUClient(config) as client:
            if config.intervals_icu_delete_mode == "safe":
                fetched = await asyncio.gather(
                    *(client.get_event(eid, athlete_id=athlete_id) for eid in ids_list),
                    return_exceptions=True,
                )

                ids_to_delete: list[int] = []
                skipped: list[dict[str, Any]] = []
                for eid, fetched_event in zip(ids_list, fetched, strict=True):
                    if isinstance(fetched_event, BaseException):
                        if isinstance(fetched_event, ICUAPIError):
                            return ResponseBuilder.build_error_response(
                                fetched_event.message, error_type="api_error"
                            )
                        raise fetched_event
                    if _classify_event_date(fetched_event.start_date_local) == "future":
                        ids_to_delete.append(eid)
                    else:
                        skipped.append(_skipped_entry_for(eid, fetched_event))

                if ids_to_delete:
                    await client.bulk_delete_events(ids_to_delete, athlete_id=athlete_id)

                return ResponseBuilder.build_response(
                    data=_delete_envelope(deleted=ids_to_delete, skipped=skipped),
                    query_type="bulk_delete_events",
                    metadata={
                        "message": (
                            f"Deleted {len(ids_to_delete)} event(s); "
                            f"skipped {len(skipped)} in safe mode"
                        ),
                    },
                )

            await client.bulk_delete_events(ids_list, athlete_id=athlete_id)
            return ResponseBuilder.build_response(
                data=_delete_envelope(deleted=ids_list, skipped=[]),
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
    """COPY existing events forward in time by N weeks.

    Use when the user says "repeat this workout for the next 4 weeks",
    "duplicate Monday's run on the next 3 Mondays". Reuses the existing
    events' payloads — different from icu_create_event / icu_bulk_create_events,
    which both build NEW events from scratch.
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
    """Schedule an entire training plan (workout-library folder) onto the athlete's calendar starting on a chosen date.

    Use after icu_get_workout_library to find a plan's folder_id. Different
    from icu_create_event / icu_bulk_create_events (which build new events) and
    from icu_duplicate_events (which copies existing).
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
