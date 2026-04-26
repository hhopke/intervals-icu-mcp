"""Tests for custom item tools."""

import json
from unittest.mock import AsyncMock, MagicMock

from httpx import Response

from intervals_icu_mcp.tools.custom_items import (
    create_custom_item,
    delete_custom_item,
    get_custom_item,
    get_custom_items,
    update_custom_item,
)


class TestCustomItemTools:
    """Tests for custom item tools."""

    async def test_get_custom_items_success(self, mock_config, respx_mock):
        """List custom items for the configured athlete."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/custom-item").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 7,
                        "athlete_id": "i123456",
                        "type": "ZONES",
                        "visibility": "PRIVATE",
                        "name": "My Zones",
                    }
                ],
            )
        )

        result = await get_custom_items(ctx=mock_ctx)
        response = json.loads(result)

        assert response["metadata"]["count"] == 1
        assert response["data"]["items"][0]["id"] == 7
        assert response["data"]["items"][0]["type"] == "ZONES"

    async def test_get_custom_items_with_athlete_override(self, mock_config, respx_mock):
        """athlete_id parameter overrides config default."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i999999/custom-item").mock(return_value=Response(200, json=[]))

        result = await get_custom_items(athlete_id="i999999", ctx=mock_ctx)
        response = json.loads(result)

        assert response["metadata"]["count"] == 0

    async def test_get_custom_item_success(self, mock_config, respx_mock):
        """Get a single custom item by ID."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/custom-item/42").mock(
            return_value=Response(
                200,
                json={
                    "id": 42,
                    "athlete_id": "i123456",
                    "type": "ACTIVITY_FIELD",
                    "name": "Bike Weight",
                    "content": {"type": "numeric"},
                },
            )
        )

        result = await get_custom_item(item_id=42, ctx=mock_ctx)
        response = json.loads(result)

        assert response["data"]["id"] == 42
        assert response["data"]["content"] == {"type": "numeric"}

    async def test_create_custom_item_success(self, mock_config, respx_mock):
        """Create a new custom item."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.post("/athlete/i123456/custom-item").mock(
            return_value=Response(
                200,
                json={
                    "id": 100,
                    "athlete_id": "i123456",
                    "type": "INPUT_FIELD",
                    "name": "RPE",
                    "visibility": "PRIVATE",
                },
            )
        )

        result = await create_custom_item(
            name="RPE",
            item_type="INPUT_FIELD",
            visibility="PRIVATE",
            ctx=mock_ctx,
        )
        response = json.loads(result)

        assert response["data"]["id"] == 100
        assert response["data"]["name"] == "RPE"
        assert "Successfully created" in response["metadata"]["message"]

    async def test_create_custom_item_invalid_type(self, mock_config):
        """Invalid item_type is rejected without an HTTP call."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await create_custom_item(name="X", item_type="NOT_A_REAL_TYPE", ctx=mock_ctx)
        response = json.loads(result)

        assert response["error"]["type"] == "validation_error"
        assert "Invalid item_type" in response["error"]["message"]

    async def test_create_custom_item_invalid_visibility(self, mock_config):
        """Invalid visibility is rejected without an HTTP call."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await create_custom_item(
            name="X", item_type="ZONES", visibility="SECRET", ctx=mock_ctx
        )
        response = json.loads(result)

        assert response["error"]["type"] == "validation_error"
        assert "Invalid visibility" in response["error"]["message"]

    async def test_update_custom_item_success(self, mock_config, respx_mock):
        """Update an existing custom item."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.put("/athlete/i123456/custom-item/42").mock(
            return_value=Response(
                200,
                json={
                    "id": 42,
                    "athlete_id": "i123456",
                    "type": "ACTIVITY_FIELD",
                    "name": "Renamed Field",
                },
            )
        )

        result = await update_custom_item(item_id=42, name="Renamed Field", ctx=mock_ctx)
        response = json.loads(result)

        assert response["data"]["id"] == 42
        assert response["data"]["name"] == "Renamed Field"

    async def test_update_custom_item_no_fields_rejected(self, mock_config):
        """Update with no fields is rejected without an HTTP call."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await update_custom_item(item_id=42, ctx=mock_ctx)
        response = json.loads(result)

        assert response["error"]["type"] == "validation_error"
        assert "No fields" in response["error"]["message"]

    async def test_delete_custom_item_success(self, mock_config, respx_mock):
        """Delete a custom item."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.delete("/athlete/i123456/custom-item/42").mock(
            return_value=Response(200, json={})
        )

        result = await delete_custom_item(item_id=42, ctx=mock_ctx)
        response = json.loads(result)

        assert response["data"]["item_id"] == 42
        assert response["data"]["deleted"] is True

    async def test_get_custom_items_api_error(self, mock_config, respx_mock):
        """API errors surface as error responses."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/custom-item").mock(return_value=Response(401))

        result = await get_custom_items(ctx=mock_ctx)
        response = json.loads(result)

        assert response["error"]["type"] == "api_error"
