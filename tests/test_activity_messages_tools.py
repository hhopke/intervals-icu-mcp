"""Tests for activity message tools."""

import json
from unittest.mock import AsyncMock, MagicMock

from httpx import Response

from intervals_icu_mcp.tools.activity_messages import (
    add_activity_message,
    get_activity_messages,
)


class TestActivityMessageTools:
    """Tests for activity message tools."""

    async def test_get_activity_messages_success(self, mock_config, respx_mock):
        """Test fetching messages for an activity."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/activity/12345/messages").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 1,
                        "athlete_id": "i123456",
                        "name": "Coach",
                        "type": "TEXT",
                        "content": "Great ride!",
                        "activity_id": "12345",
                        "created": "2026-04-20T10:00:00",
                        "seen": True,
                    }
                ],
            )
        )

        result = await get_activity_messages(activity_id="12345", ctx=mock_ctx)
        response = json.loads(result)

        assert response["data"]["activity_id"] == "12345"
        assert len(response["data"]["messages"]) == 1
        assert response["data"]["messages"][0]["id"] == 1
        assert response["data"]["messages"][0]["content"] == "Great ride!"
        assert response["metadata"]["count"] == 1

    async def test_get_activity_messages_empty(self, mock_config, respx_mock):
        """Empty message list returns count=0."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/activity/12345/messages").mock(return_value=Response(200, json=[]))

        result = await get_activity_messages(activity_id="12345", ctx=mock_ctx)
        response = json.loads(result)

        assert response["data"]["messages"] == []
        assert response["metadata"]["count"] == 0

    async def test_add_activity_message_success(self, mock_config, respx_mock):
        """Test adding a message to an activity."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.post("/activity/12345/messages").mock(
            return_value=Response(200, json={"id": 42})
        )

        result = await add_activity_message(
            activity_id="12345", content="Felt strong today", ctx=mock_ctx
        )
        response = json.loads(result)

        assert response["data"]["activity_id"] == "12345"
        assert response["data"]["message_id"] == 42
        assert "Successfully added message" in response["metadata"]["message"]

    async def test_add_activity_message_empty_content_rejected(self, mock_config):
        """Empty content is rejected without an HTTP call."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await add_activity_message(activity_id="12345", content="   ", ctx=mock_ctx)
        response = json.loads(result)

        assert response["error"]["type"] == "validation_error"

    async def test_get_activity_messages_api_error(self, mock_config, respx_mock):
        """API errors are surfaced as error responses."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/activity/99999/messages").mock(return_value=Response(404))

        result = await get_activity_messages(activity_id="99999", ctx=mock_ctx)
        response = json.loads(result)

        assert response["error"]["type"] == "api_error"
