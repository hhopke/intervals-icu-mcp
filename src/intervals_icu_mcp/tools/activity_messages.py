"""Tools for notes, comments, and coach feedback attached to an activity.

Intervals.icu calls these "messages" — they are the threaded comments that
appear under an activity (the user's own training notes, comments from
followers, or feedback from a coach). Use these tools when the user wants to
read, post, edit or delete such notes/comments on a specific activity.
"""

from typing import Annotated, Any

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..response_builder import ResponseBuilder


def _message_to_dict(message: dict[str, Any]) -> dict[str, Any]:
    """Extract a stable subset of message fields for tool responses."""
    result: dict[str, Any] = {}
    for key in (
        "id",
        "athlete_id",
        "name",
        "type",
        "content",
        "activity_id",
        "created",
        "seen",
        "deleted",
    ):
        if key in message and message[key] is not None:
            result[key] = message[key]
    if message.get("attachment_url"):
        result["attachment_url"] = message["attachment_url"]
    return result


async def get_activity_messages(
    activity_id: Annotated[str, "The Intervals.icu activity ID"],
    ctx: Context | None = None,
) -> str:
    """Read the notes and comments attached to a specific activity (plural = READ).

    Use when the user asks: "what did my coach say about that ride?",
    "show me the comments on yesterday's run", "any feedback on this
    workout?". Returns every message in chronological order with author,
    content, timestamp, and seen-flag. Deleted notes stay in the thread as a
    "(deleted)" placeholder with a `deleted` timestamp. To POST a new message use
    icu_add_activity_message (singular = WRITE).
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            messages = await client.get_activity_messages(activity_id)

            return ResponseBuilder.build_response(
                data={
                    "activity_id": activity_id,
                    "messages": [_message_to_dict(m) for m in messages],
                },
                metadata={"count": len(messages)},
                query_type="activity_messages",
            )
    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def _find_message(
    client: ICUClient, activity_id: str, message_id: int
) -> tuple[int, dict[str, Any]] | str:
    """Resolve the activity's chat ID and the message, or return an error response.

    Notes live in the activity's chat (`icu_chat_id`), which the message list
    does not expose, so the activity itself is fetched as well.
    """
    activity = await client.get_activity(activity_id=activity_id)
    messages = await client.get_activity_messages(activity_id)
    message = next((m for m in messages if m.get("id") == message_id), None)
    if activity.icu_chat_id is None:
        return ResponseBuilder.build_error_response(
            f"Activity {activity_id} has no notes yet, so message {message_id} does not exist",
            error_type="validation_error",
            suggestions=["Use icu_add_activity_message to add the first note"],
        )
    if message is None:
        return ResponseBuilder.build_error_response(
            f"Message {message_id} not found on activity {activity_id}",
            error_type="validation_error",
            suggestions=["Use icu_get_activity_messages to list the activity's message IDs"],
        )
    if message.get("deleted"):
        # Intervals.icu soft-deletes: the message stays with content "(deleted)".
        return ResponseBuilder.build_error_response(
            f"Message {message_id} on activity {activity_id} was already deleted",
            error_type="validation_error",
        )
    return activity.icu_chat_id, message


def _write_error(e: ICUAPIError, message_id: int) -> str:
    """Explain a refused write: the API only lets authors change their own notes."""
    if e.status_code in (403, 404):
        return ResponseBuilder.build_error_response(
            f"Intervals.icu refused to change message {message_id} (HTTP {e.status_code}). "
            "Only your own notes can be changed.",
            error_type="api_error",
        )
    return ResponseBuilder.build_error_response(e.message, error_type="api_error")


async def update_activity_message(
    activity_id: Annotated[str, "The Intervals.icu activity ID"],
    message_id: Annotated[int, "ID of the note to change (from icu_get_activity_messages)"],
    content: Annotated[str, "New note text; replaces the old text entirely"],
    ctx: Context | None = None,
) -> str:
    """REPLACE the text of an existing note on an activity (edit, not add).

    Use when the user wants to fix or rewrite a note they already left:
    "correct my note on that ride", "change the comment to say...". Only the
    author's own notes can be changed. Returns the old and the new text — the
    old text is not recoverable otherwise. To post an additional note use
    icu_add_activity_message.
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    if not content.strip():
        return ResponseBuilder.build_error_response(
            "content must not be empty", error_type="validation_error"
        )

    try:
        async with ICUClient(config) as client:
            found = await _find_message(client, activity_id, message_id)
            if isinstance(found, str):
                return found
            chat_id, message = found

            try:
                await client.update_message(chat_id, message_id, content)
            except ICUAPIError as e:
                return _write_error(e, message_id)

            return ResponseBuilder.build_response(
                data={
                    "activity_id": activity_id,
                    "message_id": message_id,
                    "old_content": message.get("content"),
                    "new_content": content,
                },
                metadata={"message": f"Successfully updated message {message_id}"},
                query_type="update_activity_message",
            )
    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def delete_activity_message(
    activity_id: Annotated[str, "The Intervals.icu activity ID"],
    message_id: Annotated[int, "ID of the note to delete (from icu_get_activity_messages)"],
    ctx: Context | None = None,
) -> str:
    """DELETE one of your own notes from an activity.

    Use when the user wants a note removed: "delete my comment on that run",
    "remove the note I left yesterday". Only the author's own notes can be
    deleted. Intervals.icu keeps a "(deleted)" placeholder in the thread.
    Returns the deleted text so it can be re-posted with
    icu_add_activity_message if needed (the original timestamp is lost).
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            found = await _find_message(client, activity_id, message_id)
            if isinstance(found, str):
                return found
            chat_id, message = found

            try:
                await client.delete_message(chat_id, message_id)
            except ICUAPIError as e:
                return _write_error(e, message_id)

            return ResponseBuilder.build_response(
                data={
                    "activity_id": activity_id,
                    "message_id": message_id,
                    "deleted_content": message.get("content"),
                },
                metadata={"message": f"Successfully deleted message {message_id}"},
                query_type="delete_activity_message",
            )
    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def add_activity_message(
    activity_id: Annotated[str, "The Intervals.icu activity ID"],
    content: Annotated[str, "Message content (note or comment text)"],
    ctx: Context | None = None,
) -> str:
    """POST a new note or comment on a specific activity (singular = WRITE).

    Use when the user wants to leave a note on one of their activities:
    "add a note to this ride that I felt strong", "comment on yesterday's
    run", "leave a training note saying...". Attributed to the authenticated
    user. To READ existing notes use icu_get_activity_messages (plural).
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    if not content.strip():
        return ResponseBuilder.build_error_response(
            "content must not be empty", error_type="validation_error"
        )

    try:
        async with ICUClient(config) as client:
            result = await client.add_activity_message(activity_id, content)

            data: dict[str, Any] = {"activity_id": activity_id}
            if "id" in result:
                data["message_id"] = result["id"]

            return ResponseBuilder.build_response(
                data=data,
                metadata={"message": f"Successfully added message to activity {activity_id}"},
                query_type="add_activity_message",
            )
    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )
