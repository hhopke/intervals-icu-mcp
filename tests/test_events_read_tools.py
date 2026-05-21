"""Read-side tests for events tools — get_calendar_events, get_upcoming_workouts, get_event.

Complements `test_event_tools.py` which covers write/update/delete paths.
"""

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from httpx import Response

from intervals_icu_mcp.tools.events import (
    get_calendar_events,
    get_event,
    get_upcoming_workouts,
)


def _make_ctx(mock_config):
    ctx = MagicMock()
    ctx.get_state = AsyncMock(return_value=mock_config)
    return ctx


def _date_offset(days: int) -> str:
    """Return YYYY-MM-DD for today + `days`. Matches the tool's `datetime.now()` usage."""
    return (datetime.now() + timedelta(days=days)).date().isoformat()


class TestGetCalendarEvents:
    async def test_success_groups_by_date_and_summarizes(self, mock_config, respx_mock):
        """Events are grouped by date, relative timing labeled, and categorized in summary."""
        respx_mock.get("/athlete/i123456/events").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 1,
                        "start_date_local": _date_offset(0),
                        "category": "WORKOUT",
                        "name": "Today Workout",
                        "type": "Ride",
                        "moving_time": 3600,
                        "icu_training_load": 80,
                        "icu_intensity": 0.85,
                    },
                    {
                        "id": 2,
                        "start_date_local": _date_offset(-2),
                        "category": "NOTE",
                        "name": "Past Note",
                    },
                    {
                        "id": 3,
                        "start_date_local": _date_offset(3),
                        "category": "RACE_A",
                        "name": "A Race",
                        "type": "Run",
                    },
                    {
                        "id": 4,
                        "start_date_local": _date_offset(5),
                        "end_date_local": _date_offset(10),
                        "category": "HOLIDAY",
                        "training_availability": "LIMITED",
                    },
                    {
                        "id": 5,
                        "start_date_local": _date_offset(2),
                        "category": "TARGET",
                        "name": "Target",
                    },
                ],
            )
        )

        result = await get_calendar_events(days_ahead=14, days_back=7, ctx=_make_ctx(mock_config))
        response = json.loads(result)
        data = response["data"]

        # Summary categorizes correctly
        assert data["summary"]["by_category"]["workouts"] == 1
        assert data["summary"]["by_category"]["races"] == 1
        assert data["summary"]["by_category"]["notes"] == 1
        assert data["summary"]["by_category"]["targets"] == 1
        assert data["summary"]["by_category"]["blocks"] == 1

        # Relative timing labels
        by_date = data["events_by_date"]
        today_events = by_date[_date_offset(0)]
        assert today_events[0]["relative_timing"] == "today"

        past_events = by_date[_date_offset(-2)]
        assert past_events[0]["relative_timing"] == "2_days_ago"

        future_events = by_date[_date_offset(3)]
        assert future_events[0]["relative_timing"] == "in_3_days"

        # Holiday block surfaces its end_date and availability
        holiday_events = by_date[_date_offset(5)]
        assert holiday_events[0]["end_date"] == _date_offset(10)
        assert holiday_events[0]["training_availability"] == "LIMITED"

    async def test_empty(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/events").mock(return_value=Response(200, json=[]))

        result = await get_calendar_events(ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["data"]["count"] == 0
        assert "No events found" in response["metadata"]["message"]

    async def test_api_error(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/events").mock(return_value=Response(500, json={}))

        result = await get_calendar_events(ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["error"]["type"] == "api_error"


class TestGetUpcomingWorkouts:
    async def test_filters_to_workouts_only(self, mock_config, respx_mock):
        """Notes/races/etc are filtered out; only WORKOUT category is returned."""
        respx_mock.get("/athlete/i123456/events").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 1,
                        "start_date_local": _date_offset(1),
                        "category": "WORKOUT",
                        "name": "Tomorrow's Ride",
                        "type": "Ride",
                        "moving_time": 3600,
                        "distance": 30000,
                        "icu_training_load": 100,
                        "icu_intensity": 0.85,
                        "description": "  5x5min @ FTP  ",
                    },
                    {
                        "id": 2,
                        "start_date_local": _date_offset(0),
                        "category": "WORKOUT",
                        "name": "Today's Run",
                        "type": "Run",
                    },
                    {
                        "id": 3,
                        "start_date_local": _date_offset(3),
                        "category": "WORKOUT",
                        "name": "In 3 days",
                        "type": "Ride",
                    },
                    # Should be filtered out:
                    {
                        "id": 4,
                        "start_date_local": _date_offset(1),
                        "category": "NOTE",
                        "name": "Note",
                    },
                    {
                        "id": 5,
                        "start_date_local": _date_offset(2),
                        "category": "RACE_A",
                        "name": "Race",
                    },
                ],
            )
        )

        result = await get_upcoming_workouts(limit=10, ctx=_make_ctx(mock_config))
        response = json.loads(result)
        data = response["data"]

        # Only 3 workouts (not race, not note)
        assert data["count"] == 3
        # Total load is summed
        assert data["total_planned_load"] == 100
        # Sorted by date — today first
        workouts = data["workouts"]
        assert workouts[0]["relative_timing"] == "today"
        assert workouts[1]["relative_timing"] == "tomorrow"
        assert workouts[2]["relative_timing"] == "in_3_days"
        # Description is stripped
        assert workouts[1]["description"] == "5x5min @ FTP"
        assert workouts[1]["distance_meters"] == 30000

    async def test_limit_truncates_after_sort(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/events").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": i,
                        "start_date_local": _date_offset(i),
                        "category": "WORKOUT",
                        "name": f"Day {i}",
                    }
                    for i in range(1, 10)
                ],
            )
        )

        result = await get_upcoming_workouts(limit=3, ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["data"]["count"] == 3
        # First three are days 1, 2, 3
        assert [w["relative_timing"] for w in response["data"]["workouts"]] == [
            "tomorrow",
            "in_2_days",
            "in_3_days",
        ]

    async def test_no_workouts(self, mock_config, respx_mock):
        """API returns non-workout events only → empty workout list."""
        respx_mock.get("/athlete/i123456/events").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 1,
                        "start_date_local": _date_offset(1),
                        "category": "NOTE",
                        "name": "Note",
                    }
                ],
            )
        )

        result = await get_upcoming_workouts(ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["data"]["count"] == 0
        assert "No workouts planned" in response["metadata"]["message"]

    async def test_zero_total_load_omitted(self, mock_config, respx_mock):
        """total_planned_load is None (omitted) when sum is 0."""
        respx_mock.get("/athlete/i123456/events").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 1,
                        "start_date_local": _date_offset(1),
                        "category": "WORKOUT",
                        "name": "No load",
                    }
                ],
            )
        )

        result = await get_upcoming_workouts(ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["data"]["total_planned_load"] is None

    async def test_api_error(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/events").mock(return_value=Response(500, json={}))

        result = await get_upcoming_workouts(ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["error"]["type"] == "api_error"


class TestGetEvent:
    async def test_full_event_with_all_blocks(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/events/42").mock(
            return_value=Response(
                200,
                json={
                    "id": 42,
                    "start_date_local": "2026-05-25",
                    "category": "WORKOUT",
                    "name": "Threshold Test",
                    "type": "Ride",
                    "description": "5x5 @ FTP",
                    "moving_time": 3600,
                    "distance_target": 30000,
                    "icu_training_load": 100,
                    "icu_intensity": 0.95,
                    "joules": 800000,
                    "joules_above_ftp": 200000,
                    "icu_ctl": 50.5,
                    "icu_atl": 40.2,
                    "color": "#ff0000",
                    "external_id": "ext_42",
                },
            )
        )

        result = await get_event(event_id=42, ctx=_make_ctx(mock_config))
        response = json.loads(result)
        data = response["data"]
        assert data["id"] == 42
        assert data["metrics"]["distance_meters"] == 30000
        assert data["metrics"]["joules_above_ftp"] == 200000
        assert data["fitness_context"] == {"ctl": 50.5, "atl": 40.2}
        assert data["color"] == "#ff0000"
        assert data["external_id"] == "ext_42"

    async def test_holiday_with_end_date_and_availability(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/events/50").mock(
            return_value=Response(
                200,
                json={
                    "id": 50,
                    "start_date_local": "2026-06-01",
                    "end_date_local": "2026-06-08",
                    "category": "HOLIDAY",
                    "training_availability": "LIMITED",
                    "show_as_note": True,
                    "not_on_fitness_chart": False,
                    "show_on_ctl_line": True,
                },
            )
        )

        result = await get_event(event_id=50, ctx=_make_ctx(mock_config))
        response = json.loads(result)
        data = response["data"]
        # No metrics or fitness_context — they're absent in the API response
        assert "metrics" not in data
        assert "fitness_context" not in data
        # Range + display fields surface
        assert data["end_date"] == "2026-06-08"
        assert data["training_availability"] == "LIMITED"
        assert data["show_as_note"] is True
        assert data["show_on_ctl_line"] is True
        # Falls back to category as name when name is missing
        assert data["name"] == "HOLIDAY"

    async def test_api_error(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/events/999").mock(return_value=Response(404, json={}))

        result = await get_event(event_id=999, ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["error"]["type"] == "api_error"
