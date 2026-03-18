"""Tests for multi-athlete support, Pydantic model aliases, and date handling."""

import json
from unittest.mock import AsyncMock, MagicMock

from httpx import Response

from intervals_icu_mcp.tools.activities import get_recent_activities, search_activities
from intervals_icu_mcp.tools.event_management import (
    bulk_create_events,
    bulk_delete_events,
    create_event,
    delete_event,
    duplicate_events,
    update_event,
)
from intervals_icu_mcp.tools.events import get_calendar_events, get_event, get_upcoming_workouts

# ==================== Fixtures ====================


def make_ctx(config):
    ctx = MagicMock()
    ctx.get_state = AsyncMock(return_value=config)
    return ctx


COACH_ATHLETE = "i999888"


# ==================== Multi-athlete: Activities ====================


class TestMultiAthleteActivities:
    """Test athlete_id passthrough on activity tools."""

    async def test_get_recent_activities_with_athlete_id(self, mock_config, respx_mock):
        """athlete_id routes the request to the correct athlete endpoint."""
        respx_mock.get(f"/athlete/{COACH_ATHLETE}/activities").mock(
            return_value=Response(200, json=[])
        )

        result = await get_recent_activities(
            limit=5, days_back=7, athlete_id=COACH_ATHLETE, ctx=make_ctx(mock_config)
        )
        response = json.loads(result)
        assert response["data"]["count"] == 0

        # Verify the request went to the coach's athlete, not the default
        assert respx_mock.calls.last.request.url.path == f"/api/v1/athlete/{COACH_ATHLETE}/activities"

    async def test_get_recent_activities_default_athlete(self, mock_config, respx_mock):
        """Without athlete_id, uses the configured default."""
        respx_mock.get("/athlete/i123456/activities").mock(
            return_value=Response(200, json=[])
        )

        result = await get_recent_activities(limit=5, days_back=7, ctx=make_ctx(mock_config))
        response = json.loads(result)
        assert response["data"]["count"] == 0
        assert respx_mock.calls.last.request.url.path == "/api/v1/athlete/i123456/activities"

    async def test_search_activities_with_athlete_id(self, mock_config, respx_mock):
        """search_activities passes athlete_id to the API."""
        respx_mock.get(f"/athlete/{COACH_ATHLETE}/activities/search").mock(
            return_value=Response(200, json=[])
        )

        result = await search_activities(
            query="tempo", athlete_id=COACH_ATHLETE, ctx=make_ctx(mock_config)
        )
        response = json.loads(result)
        assert "data" in response
        assert respx_mock.calls.last.request.url.path == f"/api/v1/athlete/{COACH_ATHLETE}/activities/search"


# ==================== Multi-athlete: Events ====================


class TestMultiAthleteEvents:
    """Test athlete_id passthrough on event tools."""

    async def test_get_calendar_events_with_athlete_id(self, mock_config, respx_mock):
        respx_mock.get(f"/athlete/{COACH_ATHLETE}/events").mock(
            return_value=Response(200, json=[])
        )

        result = await get_calendar_events(
            days_ahead=7, athlete_id=COACH_ATHLETE, ctx=make_ctx(mock_config)
        )
        response = json.loads(result)
        assert response["data"]["count"] == 0
        assert COACH_ATHLETE in respx_mock.calls.last.request.url.path

    async def test_get_upcoming_workouts_with_athlete_id(self, mock_config, respx_mock):
        respx_mock.get(f"/athlete/{COACH_ATHLETE}/events").mock(
            return_value=Response(200, json=[])
        )

        result = await get_upcoming_workouts(
            limit=5, athlete_id=COACH_ATHLETE, ctx=make_ctx(mock_config)
        )
        json.loads(result)  # verify valid JSON response
        assert COACH_ATHLETE in respx_mock.calls.last.request.url.path

    async def test_get_event_with_athlete_id(self, mock_config, respx_mock, mock_event_data):
        respx_mock.get(f"/athlete/{COACH_ATHLETE}/events/1001").mock(
            return_value=Response(200, json=mock_event_data)
        )

        result = await get_event(
            event_id=1001, athlete_id=COACH_ATHLETE, ctx=make_ctx(mock_config)
        )
        response = json.loads(result)
        assert response["data"]["id"] == 1001
        assert COACH_ATHLETE in respx_mock.calls.last.request.url.path


# ==================== Multi-athlete: Event Management ====================


class TestMultiAthleteEventManagement:
    """Test athlete_id passthrough on event management tools."""

    async def test_create_event_with_athlete_id(self, mock_config, respx_mock, mock_event_data):
        respx_mock.post(f"/athlete/{COACH_ATHLETE}/events").mock(
            return_value=Response(200, json=mock_event_data)
        )

        result = await create_event(
            start_date="2026-03-20",
            name="Test Workout",
            category="WORKOUT",
            athlete_id=COACH_ATHLETE,
            ctx=make_ctx(mock_config),
        )
        response = json.loads(result)
        assert "data" in response
        assert COACH_ATHLETE in respx_mock.calls.last.request.url.path

    async def test_update_event_with_athlete_id(self, mock_config, respx_mock, mock_event_data):
        respx_mock.put(f"/athlete/{COACH_ATHLETE}/events/1001").mock(
            return_value=Response(200, json=mock_event_data)
        )

        result = await update_event(
            event_id=1001,
            name="Updated Workout",
            athlete_id=COACH_ATHLETE,
            ctx=make_ctx(mock_config),
        )
        response = json.loads(result)
        assert "data" in response
        assert COACH_ATHLETE in respx_mock.calls.last.request.url.path

    async def test_delete_event_with_athlete_id(self, mock_config, respx_mock):
        respx_mock.delete(f"/athlete/{COACH_ATHLETE}/events/1001").mock(
            return_value=Response(200, json={})
        )

        result = await delete_event(
            event_id=1001, athlete_id=COACH_ATHLETE, ctx=make_ctx(mock_config)
        )
        response = json.loads(result)
        assert response["data"]["deleted"] is True
        assert COACH_ATHLETE in respx_mock.calls.last.request.url.path

    async def test_duplicate_events_with_athlete_id(self, mock_config, respx_mock, mock_event_data):
        dup_data = [{**mock_event_data, "id": 1002, "start_date_local": "2026-03-25"}]
        respx_mock.post(f"/athlete/{COACH_ATHLETE}/duplicate-events").mock(
            return_value=Response(200, json=dup_data)
        )

        result = await duplicate_events(
            event_ids="[1001]",
            num_copies=1,
            weeks_between=1,
            athlete_id=COACH_ATHLETE,
            ctx=make_ctx(mock_config),
        )
        response = json.loads(result)
        assert response["data"]["duplicated_count"] == 1
        assert COACH_ATHLETE in respx_mock.calls.last.request.url.path

    async def test_bulk_create_events_with_athlete_id(self, mock_config, respx_mock):
        created = [
            {"id": 2001, "start_date_local": "2026-03-20", "category": "WORKOUT", "name": "W1"},
            {"id": 2002, "start_date_local": "2026-03-21", "category": "WORKOUT", "name": "W2"},
        ]
        respx_mock.post(f"/athlete/{COACH_ATHLETE}/events/bulk").mock(
            return_value=Response(200, json=created)
        )

        events_json = json.dumps([
            {"start_date_local": "2026-03-20", "name": "W1", "category": "WORKOUT"},
            {"start_date_local": "2026-03-21", "name": "W2", "category": "WORKOUT"},
        ])

        result = await bulk_create_events(
            events=events_json, athlete_id=COACH_ATHLETE, ctx=make_ctx(mock_config)
        )
        response = json.loads(result)
        assert len(response["data"]["events"]) == 2
        assert COACH_ATHLETE in respx_mock.calls.last.request.url.path

    async def test_bulk_delete_events_with_athlete_id(self, mock_config, respx_mock):
        respx_mock.put(f"/athlete/{COACH_ATHLETE}/events/bulk-delete").mock(
            return_value=Response(200, json={"deleted": 2})
        )

        result = await bulk_delete_events(
            event_ids="[2001, 2002]",
            athlete_id=COACH_ATHLETE,
            ctx=make_ctx(mock_config),
        )
        response = json.loads(result)
        assert response["data"]["deleted_count"] == 2
        assert COACH_ATHLETE in respx_mock.calls.last.request.url.path


# ==================== Pydantic Aliases (watts fields) ====================


class TestPydanticAliases:
    """Test that icu_average_watts / icu_weighted_avg_watts map correctly."""

    async def test_activity_watts_aliases(self, mock_config, respx_mock):
        """API returns icu_average_watts; model should populate average_watts."""
        activity_data = [
            {
                "id": "a1",
                "start_date_local": "2026-03-17T08:00:00",
                "name": "Power Ride",
                "type": "Ride",
                "icu_average_watts": 220,
                "distance": 50000.0,
                "moving_time": 3600,
            }
        ]
        respx_mock.get("/athlete/i123456/activities").mock(
            return_value=Response(200, json=activity_data)
        )

        result = await get_recent_activities(limit=1, days_back=7, ctx=make_ctx(mock_config))
        response = json.loads(result)

        activities = response["data"]["activities"]
        assert len(activities) == 1
        assert activities[0]["average_watts"] == 220


# ==================== Date Handling ====================


class TestDateHandling:
    """Test ISO-8601 date parsing and T00:00:00 suffix."""

    async def test_calendar_events_parses_full_iso_dates(self, mock_config, respx_mock):
        """get_calendar_events handles full ISO-8601 datetime strings from API."""
        events = [
            {
                "id": 3001,
                "start_date_local": "2026-03-18T00:00:00",
                "category": "WORKOUT",
                "name": "Morning Run",
                "type": "Run",
            }
        ]
        respx_mock.get("/athlete/i123456/events").mock(
            return_value=Response(200, json=events)
        )

        result = await get_calendar_events(days_ahead=7, ctx=make_ctx(mock_config))
        response = json.loads(result)
        assert response["data"]["summary"]["total_events"] == 1

    async def test_create_event_adds_time_suffix(self, mock_config, respx_mock, mock_event_data):
        """create_event adds T00:00:00 suffix to date-only strings."""
        respx_mock.post("/athlete/i123456/events").mock(
            return_value=Response(200, json=mock_event_data)
        )

        await create_event(
            start_date="2026-03-20",
            name="Test",
            category="WORKOUT",
            ctx=make_ctx(mock_config),
        )

        request_body = json.loads(respx_mock.calls.last.request.content)
        assert request_body["start_date_local"] == "2026-03-20T00:00:00"

    async def test_duplicate_events_sends_correct_body(self, mock_config, respx_mock, mock_event_data):
        """duplicate_events sends eventIds, numCopies, weeksBetween to the correct endpoint."""
        dup_data = [{**mock_event_data, "id": 1002}]
        respx_mock.post("/athlete/i123456/duplicate-events").mock(
            return_value=Response(200, json=dup_data)
        )

        await duplicate_events(
            event_ids="[1001]", num_copies=2, weeks_between=3, ctx=make_ctx(mock_config)
        )

        request_body = json.loads(respx_mock.calls.last.request.content)
        assert request_body["eventIds"] == [1001]
        assert request_body["numCopies"] == 2
        assert request_body["weeksBetween"] == 3
