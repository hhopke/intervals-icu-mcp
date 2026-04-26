"""Tests for event management tools."""

import json
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import Response

from intervals_icu_mcp.auth import ICUConfig
from intervals_icu_mcp.tools.event_management import (
    apply_training_plan,
    bulk_create_events,
    bulk_delete_events,
    create_event,
    delete_event,
    duplicate_events,
    update_event,
)


def _future_date(days: int = 7) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def _past_date(days: int = 7) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


@pytest.fixture
def mock_config_full():
    """Config with delete_mode=full for tests that bypass the safe-mode guard."""
    return ICUConfig(
        intervals_icu_api_key="test_api_key_12345",
        intervals_icu_athlete_id="i123456",
        intervals_icu_delete_mode="full",
    )


class TestEventTools:
    """Tests for event tools."""

    async def test_create_event_success(self, mock_config, respx_mock):
        """Test successful event creation."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.post("/athlete/i123456/events").mock(
            return_value=Response(
                200,
                json={
                    "id": 1001,
                    "name": "New Workout",
                    "start_date_local": "2026-03-20",
                    "category": "WORKOUT",
                },
            )
        )

        result = await create_event(
            start_date="2026-03-20",
            name="New Workout",
            category="WORKOUT",
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["id"] == 1001
        assert response["data"]["name"] == "New Workout"
        assert response["metadata"]["message"] == "Successfully created workout: New Workout"

    async def test_update_event_success(self, mock_config, respx_mock):
        """Test successful event update."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.put("/athlete/i123456/events/1001").mock(
            return_value=Response(
                200,
                json={
                    "id": 1001,
                    "name": "Updated Workout",
                    "start_date_local": "2026-03-20",
                    "category": "WORKOUT",
                },
            )
        )

        result = await update_event(
            event_id=1001,
            name="Updated Workout",
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["id"] == 1001
        assert response["data"]["name"] == "Updated Workout"
        assert response["metadata"]["message"] == "Successfully updated event 1001"

    async def test_delete_event_safe_allows_future(self, mock_config, respx_mock):
        """Safe mode (default): future event is fetched, then deleted."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/events/1001").mock(
            return_value=Response(
                200,
                json={
                    "id": 1001,
                    "start_date_local": _future_date(),
                    "name": "Tomorrow's workout",
                    "category": "WORKOUT",
                },
            )
        )
        respx_mock.delete("/athlete/i123456/events/1001").mock(return_value=Response(200, json={}))

        result = await delete_event(event_id=1001, ctx=mock_ctx)

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["deleted"] == [1001]
        assert response["data"]["deleted_count"] == 1
        assert response["data"]["skipped"] == []
        assert response["data"]["skipped_count"] == 0

    async def test_delete_event_safe_refuses_past(self, mock_config, respx_mock):
        """Safe mode: past event is skipped with reason=past_event."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        past = _past_date()
        respx_mock.get("/athlete/i123456/events/1001").mock(
            return_value=Response(
                200,
                json={
                    "id": 1001,
                    "start_date_local": past,
                    "name": "Last week",
                    "category": "WORKOUT",
                },
            )
        )
        delete_route = respx_mock.delete("/athlete/i123456/events/1001").mock(
            return_value=Response(200, json={})
        )

        result = await delete_event(event_id=1001, ctx=mock_ctx)

        response = json.loads(result)
        assert response["data"]["deleted"] == []
        assert response["data"]["deleted_count"] == 0
        assert len(response["data"]["skipped"]) == 1
        skip = response["data"]["skipped"][0]
        assert skip["id"] == 1001
        assert skip["reason"] == "past_event"
        assert skip["start_date_local"] == past
        assert "INTERVALS_ICU_DELETE_MODE=full" in skip["hint"]
        assert delete_route.call_count == 0

    async def test_delete_event_safe_treats_today_as_past(self, mock_config, respx_mock):
        """One-day buffer: today's events are refused to absorb TZ skew."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        today = date.today().isoformat()
        respx_mock.get("/athlete/i123456/events/1001").mock(
            return_value=Response(
                200,
                json={
                    "id": 1001,
                    "start_date_local": today,
                    "name": "Today",
                    "category": "WORKOUT",
                },
            )
        )
        delete_route = respx_mock.delete("/athlete/i123456/events/1001").mock(
            return_value=Response(200, json={})
        )

        result = await delete_event(event_id=1001, ctx=mock_ctx)

        response = json.loads(result)
        assert response["data"]["deleted"] == []
        assert response["data"]["skipped"][0]["reason"] == "past_event"
        assert delete_route.call_count == 0

    async def test_delete_event_safe_skips_unparseable_date(self, mock_config, respx_mock):
        """Safe mode: event with an unparseable date is skipped (cannot verify)."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/events/1001").mock(
            return_value=Response(
                200,
                json={
                    "id": 1001,
                    "start_date_local": "not-a-date",
                    "name": "Bad date",
                    "category": "NOTE",
                },
            )
        )

        result = await delete_event(event_id=1001, ctx=mock_ctx)

        response = json.loads(result)
        assert response["data"]["deleted_count"] == 0
        assert response["data"]["skipped"][0]["reason"] == "missing_date"

    async def test_delete_event_full_skips_date_check(self, mock_config_full, respx_mock):
        """Full mode: no fetch, deletes regardless of date."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config_full)

        get_route = respx_mock.get("/athlete/i123456/events/1001")
        respx_mock.delete("/athlete/i123456/events/1001").mock(return_value=Response(200, json={}))

        result = await delete_event(event_id=1001, ctx=mock_ctx)

        response = json.loads(result)
        assert response["data"]["deleted"] == [1001]
        assert get_route.call_count == 0

    async def test_apply_training_plan_success(self, mock_config, respx_mock):
        """Test successful training plan application."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.post("/athlete/i123456/events/apply-plan").mock(
            return_value=Response(200, json=[{"id": 1002, "name": "Plan Workout"}])
        )

        result = await apply_training_plan(
            folder_id=500,
            start_date_local="2026-04-01",
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "data" in response
        assert response["data"][0]["name"] == "Plan Workout"
        assert response["metadata"]["message"] == "Successfully applied training plan folder 500"

    async def test_create_event_rejects_invalid_category(self, mock_config):
        """Validation: invalid category returns an error without hitting the API."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await create_event(
            start_date="2026-03-20",
            name="Bad Event",
            category="PARTY",
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "error" in response
        assert "Invalid category" in response["error"]["message"]
        # Error message lists the new category enum
        assert "INJURED" in response["error"]["message"]
        assert "HOLIDAY" in response["error"]["message"]

    async def test_create_event_injury_with_date_range(self, mock_config, respx_mock):
        """INJURED block with end_date and training_availability is forwarded correctly."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        route = respx_mock.post("/athlete/i123456/events").mock(
            return_value=Response(
                200,
                json={
                    "id": 5001,
                    "name": "Knieprobleme",
                    "start_date_local": "2026-04-25T00:00:00",
                    "end_date_local": "2026-05-05T00:00:00",
                    "category": "INJURED",
                    "training_availability": "LIMITED",
                },
            )
        )

        result = await create_event(
            start_date="2026-04-25",
            name="Knieprobleme",
            category="INJURED",
            end_date="2026-05-05",
            training_availability="limited",
            ctx=mock_ctx,
        )

        # Outgoing payload assertions
        sent = json.loads(route.calls.last.request.content)
        assert sent["category"] == "INJURED"
        assert sent["start_date_local"] == "2026-04-25T00:00:00"
        assert sent["end_date_local"] == "2026-05-05T00:00:00"
        assert sent["training_availability"] == "LIMITED"

        # Response shape
        response = json.loads(result)
        assert response["data"]["category"] == "INJURED"
        assert response["data"]["end_date"] == "2026-05-05T00:00:00"
        assert response["data"]["training_availability"] == "LIMITED"

    async def test_create_event_holiday_with_unavailable(self, mock_config, respx_mock):
        """HOLIDAY with training_availability=UNAVAILABLE is accepted."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        route = respx_mock.post("/athlete/i123456/events").mock(
            return_value=Response(
                200,
                json={
                    "id": 5002,
                    "name": "Spring Break",
                    "start_date_local": "2026-05-01T00:00:00",
                    "end_date_local": "2026-05-08T00:00:00",
                    "category": "HOLIDAY",
                    "training_availability": "UNAVAILABLE",
                },
            )
        )

        await create_event(
            start_date="2026-05-01",
            name="Spring Break",
            category="HOLIDAY",
            end_date="2026-05-08",
            training_availability="UNAVAILABLE",
            ctx=mock_ctx,
        )

        sent = json.loads(route.calls.last.request.content)
        assert sent["category"] == "HOLIDAY"
        assert sent["training_availability"] == "UNAVAILABLE"

    async def test_create_event_legacy_race_alias(self, mock_config, respx_mock):
        """Legacy 'RACE' is normalized to 'RACE_A' before sending."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        route = respx_mock.post("/athlete/i123456/events").mock(
            return_value=Response(
                200,
                json={
                    "id": 5003,
                    "name": "Goal Race",
                    "start_date_local": "2026-06-01T00:00:00",
                    "category": "RACE_A",
                    "type": "Run",
                },
            )
        )

        await create_event(
            start_date="2026-06-01",
            name="Goal Race",
            category="RACE",
            event_type="Run",
            ctx=mock_ctx,
        )

        sent = json.loads(route.calls.last.request.content)
        assert sent["category"] == "RACE_A"
        assert sent["type"] == "Run"

    async def test_create_event_race_without_type_is_rejected(self, mock_config):
        """Validation: RACE_A/B/C without event_type returns helpful error pre-flight."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await create_event(
            start_date="2026-09-13",
            name="Otztaler",
            category="RACE_A",
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "error" in response
        message = response["error"]["message"]
        assert "event_type" in message
        assert "RACE_A" in message
        # Hint lists the valid disciplines
        assert "Ride" in message and "Run" in message

    async def test_bulk_create_events_race_without_type_is_rejected(self, mock_config):
        """Validation: bulk RACE_A entry without 'type' is rejected pre-flight."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        events_payload = json.dumps(
            [
                {
                    "start_date_local": "2026-09-13",
                    "name": "Otztaler",
                    "category": "RACE_A",
                },
            ]
        )

        result = await bulk_create_events(events=events_payload, ctx=mock_ctx)

        response = json.loads(result)
        assert "error" in response
        assert "type" in response["error"]["message"]
        assert "RACE_A" in response["error"]["message"]

    async def test_create_event_legacy_goal_alias(self, mock_config, respx_mock):
        """Legacy 'GOAL' is normalized to 'TARGET' before sending."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        route = respx_mock.post("/athlete/i123456/events").mock(
            return_value=Response(
                200,
                json={
                    "id": 5004,
                    "name": "Sub-3 marathon",
                    "start_date_local": "2026-09-01T00:00:00",
                    "category": "TARGET",
                },
            )
        )

        await create_event(
            start_date="2026-09-01",
            name="Sub-3 marathon",
            category="goal",
            ctx=mock_ctx,
        )

        sent = json.loads(route.calls.last.request.content)
        assert sent["category"] == "TARGET"

    async def test_create_event_rejects_invalid_availability(self, mock_config):
        """Validation: bogus training_availability is rejected without API call."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await create_event(
            start_date="2026-04-25",
            name="Knee",
            category="INJURED",
            training_availability="MAYBE",
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "error" in response
        assert "training_availability" in response["error"]["message"]

    async def test_create_event_rejects_invalid_end_date(self, mock_config):
        """Validation: malformed end_date is rejected without API call."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await create_event(
            start_date="2026-04-25",
            name="Knee",
            category="INJURED",
            end_date="not-a-date",
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "error" in response
        assert "end_date" in response["error"]["message"]

    async def test_update_event_can_set_end_date_and_availability(self, mock_config, respx_mock):
        """Updating an injury block to extend its end_date and change availability."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        route = respx_mock.put("/athlete/i123456/events/5001").mock(
            return_value=Response(
                200,
                json={
                    "id": 5001,
                    "name": "Knieprobleme",
                    "start_date_local": "2026-04-25T00:00:00",
                    "end_date_local": "2026-05-15T00:00:00",
                    "category": "INJURED",
                    "training_availability": "NORMAL",
                },
            )
        )

        result = await update_event(
            event_id=5001,
            end_date="2026-05-15",
            training_availability="NORMAL",
            ctx=mock_ctx,
        )

        sent = json.loads(route.calls.last.request.content)
        assert sent["end_date_local"] == "2026-05-15T00:00:00"
        assert sent["training_availability"] == "NORMAL"

        response = json.loads(result)
        assert response["data"]["end_date"] == "2026-05-15T00:00:00"
        assert response["data"]["training_availability"] == "NORMAL"

    async def test_create_event_rejects_invalid_date(self, mock_config):
        """Validation: malformed start_date returns an error without hitting the API."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await create_event(
            start_date="not-a-date",
            name="Workout",
            category="WORKOUT",
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "error" in response
        assert "Invalid date format" in response["error"]["message"]

    async def test_update_event_requires_at_least_one_field(self, mock_config):
        """Validation: update with no fields returns an error."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await update_event(event_id=1001, ctx=mock_ctx)

        response = json.loads(result)
        assert "error" in response
        assert "No fields provided" in response["error"]["message"]

    async def test_delete_event_api_error(self, mock_config_full, respx_mock):
        """API 404 on delete surfaces as error response (full mode bypasses get_event)."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config_full)

        respx_mock.delete("/athlete/i123456/events/9999").mock(
            return_value=Response(404, json={"error": "Event not found"})
        )

        result = await delete_event(event_id=9999, ctx=mock_ctx)

        response = json.loads(result)
        assert "error" in response
        assert "Resource not found" in response["error"]["message"]

    async def test_bulk_create_events_success(self, mock_config, respx_mock):
        """Bulk create events returns the full list with count metadata."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.post("/athlete/i123456/events/bulk").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 2001,
                        "start_date_local": "2026-04-01",
                        "name": "Mon Workout",
                        "category": "WORKOUT",
                        "type": "Ride",
                    },
                    {
                        "id": 2002,
                        "start_date_local": "2026-04-03",
                        "name": "Wed Workout",
                        "category": "WORKOUT",
                        "type": "Ride",
                    },
                ],
            )
        )

        events_payload = json.dumps(
            [
                {
                    "start_date_local": "2026-04-01",
                    "name": "Mon Workout",
                    "category": "workout",
                    "type": "Ride",
                },
                {
                    "start_date_local": "2026-04-03",
                    "name": "Wed Workout",
                    "category": "WORKOUT",
                    "type": "Ride",
                },
            ]
        )

        result = await bulk_create_events(events=events_payload, ctx=mock_ctx)

        response = json.loads(result)
        assert "data" in response
        assert len(response["data"]["events"]) == 2
        assert response["metadata"]["count"] == 2
        assert response["metadata"]["message"] == "Successfully created 2 events"

    async def test_bulk_create_events_supports_injury_block(self, mock_config, respx_mock):
        """Bulk create forwards INJURED + end_date_local + training_availability."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        route = respx_mock.post("/athlete/i123456/events/bulk").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 6001,
                        "start_date_local": "2026-04-25T00:00:00",
                        "end_date_local": "2026-05-05T00:00:00",
                        "name": "Knee",
                        "category": "INJURED",
                        "training_availability": "LIMITED",
                    },
                ],
            )
        )

        events_payload = json.dumps(
            [
                {
                    "start_date_local": "2026-04-25",
                    "end_date_local": "2026-05-05",
                    "name": "Knee",
                    "category": "injured",
                    "training_availability": "limited",
                },
            ]
        )

        result = await bulk_create_events(events=events_payload, ctx=mock_ctx)

        sent = json.loads(route.calls.last.request.content)
        assert sent[0]["category"] == "INJURED"
        assert sent[0]["start_date_local"] == "2026-04-25T00:00:00"
        assert sent[0]["end_date_local"] == "2026-05-05T00:00:00"
        assert sent[0]["training_availability"] == "LIMITED"

        response = json.loads(result)
        assert response["data"]["events"][0]["category"] == "INJURED"
        assert response["data"]["events"][0]["end_date"] == "2026-05-05T00:00:00"
        assert response["data"]["events"][0]["training_availability"] == "LIMITED"

    async def test_bulk_create_events_rejects_invalid_availability(self, mock_config):
        """Validation: bogus training_availability in a bulk entry is rejected."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        events_payload = json.dumps(
            [
                {
                    "start_date_local": "2026-04-25",
                    "name": "Knee",
                    "category": "INJURED",
                    "training_availability": "SOMETIMES",
                },
            ]
        )

        result = await bulk_create_events(events=events_payload, ctx=mock_ctx)

        response = json.loads(result)
        assert "error" in response
        assert "training_availability" in response["error"]["message"]

    async def test_bulk_create_events_rejects_invalid_json(self, mock_config):
        """Validation: non-JSON input is rejected before any API call."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await bulk_create_events(events="not json", ctx=mock_ctx)

        response = json.loads(result)
        assert "error" in response
        assert "Invalid JSON format" in response["error"]["message"]

    async def test_bulk_create_events_requires_fields(self, mock_config):
        """Validation: missing required per-event fields is rejected."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await bulk_create_events(
            events=json.dumps([{"name": "Missing date and category"}]),
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "error" in response
        assert "start_date_local" in response["error"]["message"]

    async def test_bulk_delete_events_full_mode(self, mock_config_full, respx_mock):
        """Full mode: deletes all IDs without per-event date check."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config_full)

        respx_mock.put("/athlete/i123456/events/bulk-delete").mock(
            return_value=Response(200, json={"deleted": 2})
        )

        result = await bulk_delete_events(event_ids=json.dumps([1001, 1002]), ctx=mock_ctx)

        response = json.loads(result)
        assert response["data"]["deleted"] == [1001, 1002]
        assert response["data"]["deleted_count"] == 2
        assert response["data"]["skipped"] == []
        assert response["metadata"]["message"] == "Successfully deleted 2 events"

    async def test_bulk_delete_events_safe_partition(self, mock_config, respx_mock):
        """Safe mode: partitions input into deleted (future) and skipped (past)."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        future = _future_date()
        past = _past_date()
        respx_mock.get("/athlete/i123456/events/1001").mock(
            return_value=Response(
                200,
                json={
                    "id": 1001,
                    "start_date_local": future,
                    "name": "Future workout",
                    "category": "WORKOUT",
                },
            )
        )
        respx_mock.get("/athlete/i123456/events/1002").mock(
            return_value=Response(
                200,
                json={
                    "id": 1002,
                    "start_date_local": past,
                    "name": "Past workout",
                    "category": "WORKOUT",
                },
            )
        )
        bulk_route = respx_mock.put("/athlete/i123456/events/bulk-delete").mock(
            return_value=Response(200, json={"deleted": 1})
        )

        result = await bulk_delete_events(event_ids=json.dumps([1001, 1002]), ctx=mock_ctx)

        response = json.loads(result)
        assert response["data"]["deleted"] == [1001]
        assert response["data"]["deleted_count"] == 1
        assert len(response["data"]["skipped"]) == 1
        assert response["data"]["skipped"][0]["id"] == 1002
        assert response["data"]["skipped"][0]["reason"] == "past_event"
        sent = json.loads(bulk_route.calls.last.request.content)
        sent_ids = [entry["id"] if isinstance(entry, dict) else entry for entry in sent]
        assert sent_ids == [1001]

    async def test_bulk_delete_events_safe_all_past(self, mock_config, respx_mock):
        """Safe mode: when every input is past, no bulk-delete call is made."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        past = _past_date()
        for eid in (1001, 1002):
            respx_mock.get(f"/athlete/i123456/events/{eid}").mock(
                return_value=Response(
                    200,
                    json={
                        "id": eid,
                        "start_date_local": past,
                        "name": "Past",
                        "category": "WORKOUT",
                    },
                )
            )
        bulk_route = respx_mock.put("/athlete/i123456/events/bulk-delete").mock(
            return_value=Response(200, json={"deleted": 0})
        )

        result = await bulk_delete_events(event_ids=json.dumps([1001, 1002]), ctx=mock_ctx)

        response = json.loads(result)
        assert response["data"]["deleted_count"] == 0
        assert response["data"]["skipped_count"] == 2
        assert bulk_route.call_count == 0

    async def test_bulk_delete_events_requires_non_empty(self, mock_config):
        """Validation: empty array is rejected."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await bulk_delete_events(event_ids=json.dumps([]), ctx=mock_ctx)

        response = json.loads(result)
        assert "error" in response
        assert "at least one event ID" in response["error"]["message"]

    async def test_duplicate_events_success(self, mock_config, respx_mock):
        """Duplicate events returns each copy with metadata echoing parameters."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.post("/athlete/i123456/duplicate-events").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 3001,
                        "start_date_local": "2026-04-08",
                        "name": "Copy 1",
                        "category": "WORKOUT",
                    },
                    {
                        "id": 3002,
                        "start_date_local": "2026-04-15",
                        "name": "Copy 2",
                        "category": "WORKOUT",
                    },
                ],
            )
        )

        result = await duplicate_events(
            event_ids=json.dumps([1001]),
            num_copies=2,
            weeks_between=1,
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["duplicated_count"] == 2
        assert response["metadata"]["num_copies"] == 2
        assert response["metadata"]["weeks_between"] == 1
        assert response["metadata"]["original_event_ids"] == [1001]

    async def test_duplicate_events_rejects_non_integer_ids(self, mock_config):
        """Validation: non-integer entries in event_ids are rejected."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await duplicate_events(
            event_ids=json.dumps(["not-an-int"]),
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "error" in response
        assert "array of integers" in response["error"]["message"]

    async def test_duplicate_events_rejects_zero_copies(self, mock_config):
        """Validation: num_copies must be >= 1."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await duplicate_events(
            event_ids=json.dumps([1001]),
            num_copies=0,
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "error" in response
        assert "num_copies must be at least 1" in response["error"]["message"]
