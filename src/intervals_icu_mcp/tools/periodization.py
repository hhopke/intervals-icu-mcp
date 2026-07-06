"""Annual Training Plan (ATP) periodization tools for Intervals.icu MCP server."""

from datetime import date, datetime, timedelta
from typing import Annotated, Any

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..models import Event
from ..response_builder import ResponseBuilder

_ATP_CATEGORIES = frozenset({"PLAN", "TARGET", "NOTE"})


def _primary_tag(tags: list[str] | None) -> str | None:
    return tags[0] if tags else None


def _event_date(value: str) -> date:
    """Parse an ISO-8601 date or datetime string to a date."""
    return datetime.fromisoformat(value).date()


def _atp_week_end(week_start: date) -> date:
    """Return the Sunday ending a Mon-anchored ATP training week.

    Intervals.icu TARGET events are 1-day calendar anchors (Mon→Tue in the API);
    the UI treats them as full weeks. We mirror that here.
    """
    return week_start + timedelta(days=6)


def _phase_for_week(
    week_start: date,
    phases: list[dict[str, Any]],
) -> tuple[str | None, str | None]:
    """Return (plan_name, phase) for a week start date.

    When phase blocks share a boundary date (e.g. Base ends Aug 10, Build starts
    Aug 10), prefer the phase that starts latest — the week belongs to the new phase.
    """
    matches: list[tuple[date, dict[str, Any]]] = []
    for phase in phases:
        start = _event_date(phase["start_date"])
        end_raw = phase.get("end_date")
        end = _event_date(end_raw) if end_raw else start
        if start <= week_start <= end:
            matches.append((start, phase))

    if not matches:
        return None, None

    _, best = max(matches, key=lambda item: item[0])
    plan_name = best.get("plan_name")
    phase_label = best.get("phase")
    return (
        str(plan_name) if plan_name else None,
        str(phase_label) if phase_label else None,
    )


def _note_overlaps_week(note: Event, week_start: date, week_end: date) -> bool:
    """True when a NOTE event overlaps the TARGET week window."""
    note_start = _event_date(note.start_date_local)
    note_end_raw = note.end_date_local or note.start_date_local
    note_end = _event_date(note_end_raw)
    return note_start <= week_end and note_end >= week_start


def _note_to_week_dict(note: Event) -> dict[str, Any] | None:
    """Build structured week_note payload from an ATP-generated NOTE event."""
    note_text = note.description or note.name
    if not note_text:
        return None
    item: dict[str, Any] = {
        "event_id": note.id,
        "text": note_text.strip(),
    }
    if note.name:
        item["name"] = note.name.strip()
    return item


def _phase_to_dict(event: Event) -> dict[str, Any]:
    phase_label = _primary_tag(event.tags)
    item: dict[str, Any] = {
        "event_id": event.id,
        "plan_name": event.name or "PLAN",
        "start_date": _event_date(event.start_date_local).isoformat(),
    }
    if phase_label:
        item["phase"] = phase_label
    if event.end_date_local:
        item["end_date"] = _event_date(event.end_date_local).isoformat()
    if event.description:
        item["description"] = event.description.strip()
    if event.color:
        item["color"] = event.color
    if event.type:
        item["type"] = event.type
    return item


def _week_to_dict(
    event: Event,
    phases: list[dict[str, Any]],
    notes: list[Event],
) -> dict[str, Any]:
    week_start = _event_date(event.start_date_local)
    week_end = _atp_week_end(week_start)
    plan_name, phase = _phase_for_week(week_start, phases)

    item: dict[str, Any] = {
        "event_id": event.id,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
    }
    if event.name:
        item["name"] = event.name
    if event.load_target is not None:
        item["load_target_tss"] = event.load_target
    if event.time_target is not None:
        item["time_target_seconds"] = event.time_target
    if event.distance_target is not None:
        item["distance_target_meters"] = event.distance_target
    if plan_name:
        item["plan_name"] = plan_name
    if phase:
        item["phase"] = phase

    for note in notes:
        if _note_overlaps_week(note, week_start, week_end):
            week_note = _note_to_week_dict(note)
            if week_note:
                item["week_note"] = week_note
            break

    return item


async def get_annual_training_plan(
    days_ahead: Annotated[
        int,
        "Days to look ahead (default 365 — full annual plan). Narrow for month/week queries, e.g. 31 for July.",
    ] = 365,
    days_back: Annotated[int, "Number of days to look back"] = 0,
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Read the Annual Training Plan (ATP) on the calendar — weekly load targets (TSS), Base/Build/Peak phases, and ATP week notes.

    Use when the user asks: "what's my weekly TSS target?", "what training phase
    am I in?", "show my periodization plan", "when are my recovery weeks?",
    "what's the note on this training week?".
    Defaults to a 365-day forward window so the full ATP is returned; pass a
    smaller days_ahead/days_back when the user asks about a specific month or week.
    NOT individual planned workouts (icu_get_upcoming_workouts), NOT all calendar
    entries (icu_get_calendar_events), NOT workout-library plan folders
    (icu_get_workout_library / icu_apply_training_plan).
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
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

            atp_events = [e for e in events if e.category in _ATP_CATEGORIES]
            if not atp_events:
                return ResponseBuilder.build_response(
                    data={
                        "phases": [],
                        "weeks": [],
                        "date_range": {"oldest": oldest, "newest": newest},
                        "summary": {
                            "phase_count": 0,
                            "week_count": 0,
                            "week_note_count": 0,
                            "total_load_target_tss": None,
                        },
                    },
                    metadata={
                        "message": (
                            "No Annual Training Plan events found for the specified period. "
                            "Place an ATP on the calendar in Intervals.icu first."
                        )
                    },
                )

            plan_events = sorted(
                (e for e in atp_events if e.category == "PLAN"),
                key=lambda e: e.start_date_local,
            )
            target_events = sorted(
                (e for e in atp_events if e.category == "TARGET"),
                key=lambda e: e.start_date_local,
            )
            note_events = [
                e for e in atp_events if e.category == "NOTE" and e.plan_applied is not None
            ]

            phases = [_phase_to_dict(e) for e in plan_events]
            weeks = [_week_to_dict(e, phases, note_events) for e in target_events]

            total_tss = sum(e.load_target for e in target_events if e.load_target is not None)
            week_note_count = sum(1 for week in weeks if week.get("week_note") is not None)

            plan_names = {p["plan_name"] for p in phases if p.get("plan_name")}
            summary: dict[str, Any] = {
                "phase_count": len(phases),
                "week_count": len(weeks),
                "week_note_count": week_note_count,
                "total_load_target_tss": total_tss if total_tss > 0 else None,
            }
            if len(plan_names) == 1:
                summary["plan_name"] = next(iter(plan_names))

            return ResponseBuilder.build_response(
                data={
                    "phases": phases,
                    "weeks": weeks,
                    "date_range": {"oldest": oldest, "newest": newest},
                    "summary": summary,
                },
                query_type="annual_training_plan",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )
