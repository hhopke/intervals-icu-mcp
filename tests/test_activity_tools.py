"""Tests for activity tools."""

import json
from unittest.mock import AsyncMock, MagicMock

from httpx import Response

from intervals_icu_mcp.tools.activities import (
    bulk_create_manual_activities,
    delete_activity,
    update_activity,
    update_activity_streams,
)


class TestActivityTools:
    """Tests for activity tools."""

    async def test_update_activity_success(self, mock_config, respx_mock):
        """Test successful activity update."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.put("/activity/a123").mock(
            return_value=Response(
                200,
                json={
                    "id": "a123",
                    "start_date_local": "2026-03-20T10:00:00",
                    "name": "Updated Ride",
                    "type": "Ride",
                    "icu_training_load": 100,
                },
            )
        )

        result = await update_activity(
            activity_id="a123",
            name="Updated Ride",
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["id"] == "a123"
        assert response["data"]["name"] == "Updated Ride"
        assert response["metadata"]["message"] == "Successfully updated activity a123"

    async def test_update_activity_not_found(self, mock_config, respx_mock):
        """Test updating a non-existent activity."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.put("/activity/a123").mock(
            return_value=Response(
                404,
                json={"error": "Activity not found"},
            )
        )

        result = await update_activity(
            activity_id="a123",
            name="Updated Ride",
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "error" in response
        assert "Resource not found" in response["error"]["message"]

    async def test_delete_activity_success(self, mock_config, respx_mock):
        """Test successful activity deletion."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.delete("/activity/a123").mock(return_value=Response(200, json={}))

        result = await delete_activity(
            activity_id="a123",
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["deleted"] is True
        assert response["metadata"]["message"] == "Successfully deleted activity a123"

    async def test_delete_activity_error(self, mock_config, respx_mock):
        """Test activity deletion error."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.delete("/activity/a123").mock(return_value=Response(500, json={}))

        result = await delete_activity(
            activity_id="a123",
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "error" in response
        assert "HTTP 500" in response["error"]["message"]

    async def test_update_activity_streams_json(self, mock_config, respx_mock):
        """Test updating activity streams with JSON."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.put("/activity/a123/streams").mock(
            return_value=Response(200, json={"message": "ok"})
        )

        result = await update_activity_streams(
            activity_id="a123",
            format="json",
            payload_string='[{"time": 0, "watts": 100}]',
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["message"] == "ok"
        assert response["metadata"]["message"] == "Successfully updated streams for activity a123"

    async def test_bulk_create_manual_activities(self, mock_config, respx_mock):
        """Test bulk creating manual activities."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.post("/athlete/i123456/activities/manual/bulk").mock(
            return_value=Response(
                200,
                json=[{"id": "a123", "name": "Bulk Ride", "start_date_local": "2026-03-20T10:00:00"}],
            )
        )

        result = await bulk_create_manual_activities(
            activities_json='[{"start_date_local": "2026-03-20T10:00:00", "type": "Ride", "name": "Bulk Ride"}]',
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["count"] == 1
        assert response["data"]["activities"][0]["name"] == "Bulk Ride"
