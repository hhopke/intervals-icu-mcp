"""Tools for notes, comments, and coach feedback attached to an activity.

Intervals.icu calls these "messages" — they are the threaded comments that
appear under an activity (the user's own training notes, comments from
followers, or feedback from a coach). Use these tools when the user wants to
read or post such notes/comments on a specific activity.
"""

from typing import Annotated, Any

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..response_builder import ResponseBuilder


def _message_to_dict(message: dict[str, Any]) -> dict[str, Any]:
    """Extract a stable subset of message fields for tool responses."""
    result: dict[str, Any] = {}
    for key in ("id", "athlete_id", "name", "type", "content", "activity_id", "created", "seen"):
        if key in message and message[key] is not None:
            result[key] = message[key]
    if message.get("attachment_url"):
        result["attachment_url"] = message["attachment_url"]
    return result


async def get_activity_messages(
    activity_id: Annotated[str, "The Intervals.icu activity ID"],
    ctx: Context | None = None,
) -> str:
    """Read the notes and comments attached to a specific activity.

    Use when the user asks: "what did my coach say about that ride?",
    "show me the comments on yesterday's run", "read my notes on activity
    X", "any feedback on this workout?". Returns every message on the
    activity in chronological order, including the author name, content,
    timestamp, and whether the user has seen it.

    Args:
        activity_id: The Intervals.icu activity ID (use icu_search_activities
            or icu_get_recent_activities to find one if you only have a
            description)

    Returns:
        JSON string with the list of messages and total count
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


async def add_activity_message(
    activity_id: Annotated[str, "The Intervals.icu activity ID"],
    content: Annotated[str, "Message content (note or comment text)"],
    ctx: Context | None = None,
) -> str:
    """Post a note or comment on a specific activity.

    Use when the user wants to leave a note on one of their activities:
    "add a note to this ride that I felt strong", "comment on yesterday's
    run", "leave a training note saying...". The post is attributed to the
    authenticated user. Use icu_get_activity_messages first if you need to
    see existing comments before adding to the thread.

    Args:
        activity_id: The Intervals.icu activity ID (use icu_search_activities
            or icu_get_recent_activities to find one)
        content: The message text to post (cannot be empty)

    Returns:
        JSON string with the new message ID and confirmation
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
