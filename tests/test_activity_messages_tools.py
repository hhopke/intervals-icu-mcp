"""Tests for activity message tools."""

import json
from unittest.mock import AsyncMock, MagicMock

from httpx import Response

from intervals_icu_mcp.tools.activity_messages import (
    add_activity_message,
    delete_activity_message,
    get_activity_messages,
    update_activity_message,
)

OWN_NOTE = {
    "id": 7,
    "athlete_id": "i123456",
    "name": "Me",
    "type": "TEXT",
    "content": "Old text",
    "created": "2026-04-20T10:00:00",
}


DELETED_NOTE = {
    **OWN_NOTE,
    "content": "(deleted)",
    "deleted": "2026-04-21T08:00:00",
    "deleted_by_id": "i123456",
}


def _mock_activity(
    respx_mock, chat_id: int | None = 555, note: dict[str, object] = OWN_NOTE
) -> None:
    """Mock the activity (carrying its chat ID) and its message list."""
    respx_mock.get("/activity/12345").mock(
        return_value=Response(
            200,
            json={"id": "12345", "start_date_local": "2026-04-20T09:00:00", "icu_chat_id": chat_id},
        )
    )
    respx_mock.get("/activity/12345/messages").mock(
        return_value=Response(200, json=[note] if chat_id is not None else [])
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


class TestUpdateActivityMessage:
    """Tests for icu_update_activity_message."""

    async def test_update_returns_old_and_new_text(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)
        _mock_activity(respx_mock)
        route = respx_mock.put("/chats/555/messages/7").mock(return_value=Response(200, json={}))

        result = await update_activity_message(
            activity_id="12345", message_id=7, content="New text", ctx=mock_ctx
        )
        response = json.loads(result)

        assert route.called
        assert json.loads(route.calls.last.request.content) == {"content": "New text"}
        assert response["data"]["old_content"] == "Old text"
        assert response["data"]["new_content"] == "New text"
        assert response["data"]["message_id"] == 7

    async def test_update_empty_content_rejected(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await update_activity_message(
            activity_id="12345", message_id=7, content="  ", ctx=mock_ctx
        )

        assert json.loads(result)["error"]["type"] == "validation_error"

    async def test_update_unknown_message_rejected(self, mock_config, respx_mock):
        """A message ID that is not on the activity never reaches the PUT."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)
        _mock_activity(respx_mock)
        route = respx_mock.put("/chats/555/messages/8").mock(return_value=Response(200))

        result = await update_activity_message(
            activity_id="12345", message_id=8, content="New text", ctx=mock_ctx
        )
        response = json.loads(result)

        assert not route.called
        assert response["error"]["type"] == "validation_error"
        assert "not found on activity" in response["error"]["message"]

    async def test_update_activity_without_chat_rejected(self, mock_config, respx_mock):
        """An activity without notes has no chat ID yet."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)
        _mock_activity(respx_mock, chat_id=None)

        result = await update_activity_message(
            activity_id="12345", message_id=7, content="New text", ctx=mock_ctx
        )

        error = json.loads(result)["error"]
        assert error["type"] == "validation_error"
        assert "has no notes yet" in error["message"]

    async def test_update_foreign_note_explained(self, mock_config, respx_mock):
        """A refused write (someone else's note) says only own notes can be changed."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)
        _mock_activity(respx_mock)
        respx_mock.put("/chats/555/messages/7").mock(return_value=Response(403))

        result = await update_activity_message(
            activity_id="12345", message_id=7, content="New text", ctx=mock_ctx
        )
        response = json.loads(result)

        assert response["error"]["type"] == "api_error"
        assert "Only your own notes" in response["error"]["message"]


class TestDeleteActivityMessage:
    """Tests for icu_delete_activity_message."""

    async def test_delete_returns_deleted_text(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)
        _mock_activity(respx_mock)
        route = respx_mock.delete("/chats/555/messages/7").mock(return_value=Response(200, json={}))

        result = await delete_activity_message(activity_id="12345", message_id=7, ctx=mock_ctx)
        response = json.loads(result)

        assert route.called
        assert response["data"]["deleted_content"] == "Old text"
        assert "Successfully deleted message 7" in response["metadata"]["message"]

    async def test_delete_unknown_message_rejected(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)
        _mock_activity(respx_mock)
        route = respx_mock.delete("/chats/555/messages/8").mock(return_value=Response(200))

        result = await delete_activity_message(activity_id="12345", message_id=8, ctx=mock_ctx)

        assert not route.called
        assert json.loads(result)["error"]["type"] == "validation_error"

    async def test_delete_foreign_note_explained(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)
        _mock_activity(respx_mock)
        respx_mock.delete("/chats/555/messages/7").mock(return_value=Response(404))

        result = await delete_activity_message(activity_id="12345", message_id=7, ctx=mock_ctx)
        response = json.loads(result)

        assert response["error"]["type"] == "api_error"
        assert "Only your own notes" in response["error"]["message"]

    async def test_delete_other_api_error_passed_through(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)
        _mock_activity(respx_mock)
        respx_mock.delete("/chats/555/messages/7").mock(return_value=Response(500, text="boom"))

        result = await delete_activity_message(activity_id="12345", message_id=7, ctx=mock_ctx)
        response = json.loads(result)

        assert response["error"]["type"] == "api_error"
        assert "HTTP 500" in response["error"]["message"]


class TestDeletedActivityMessages:
    """Intervals.icu soft-deletes notes: a "(deleted)" placeholder stays in the thread."""

    async def test_get_exposes_deleted_timestamp(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)
        _mock_activity(respx_mock, note=DELETED_NOTE)

        result = await get_activity_messages(activity_id="12345", ctx=mock_ctx)
        message = json.loads(result)["data"]["messages"][0]

        assert message["content"] == "(deleted)"
        assert message["deleted"] == "2026-04-21T08:00:00"

    async def test_update_deleted_note_rejected(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)
        _mock_activity(respx_mock, note=DELETED_NOTE)
        route = respx_mock.put("/chats/555/messages/7").mock(return_value=Response(200))

        result = await update_activity_message(
            activity_id="12345", message_id=7, content="New text", ctx=mock_ctx
        )
        response = json.loads(result)

        assert not route.called
        assert response["error"]["type"] == "validation_error"
        assert "already deleted" in response["error"]["message"]

    async def test_delete_deleted_note_rejected(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)
        _mock_activity(respx_mock, note=DELETED_NOTE)
        route = respx_mock.delete("/chats/555/messages/7").mock(return_value=Response(200))

        result = await delete_activity_message(activity_id="12345", message_id=7, ctx=mock_ctx)
        response = json.loads(result)

        assert not route.called
        assert "already deleted" in response["error"]["message"]
