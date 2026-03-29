"""Tests for event management tools."""

import json
from unittest.mock import AsyncMock, MagicMock

from httpx import Response

from intervals_icu_mcp.tools.event_management import (
    apply_training_plan,
    create_event,
    delete_event,
    update_event,
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

    async def test_delete_event_success(self, mock_config, respx_mock):
        """Test successful event deletion."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.delete("/athlete/i123456/events/1001").mock(return_value=Response(200, json={}))

        result = await delete_event(
            event_id=1001,
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["deleted"] is True
        assert response["metadata"]["message"] == "Successfully deleted event 1001"

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
