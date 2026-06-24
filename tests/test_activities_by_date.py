"""Date-range activity listing + the activities-around query-param fix.

These complement test_activities_read_tools.py. The around tests here assert
the *outgoing query parameters* (not just the path), which is what the
HTTP 422 fix is about — the API requires `activity_id`/`limit`, not `id`/`count`.
"""

import json
from unittest.mock import AsyncMock, MagicMock

from httpx import Response

from intervals_icu_mcp.tools.activities import (
    get_activities_around,
    get_activities_by_date,
)


def _make_ctx(mock_config):
    ctx = MagicMock()
    ctx.get_state = AsyncMock(return_value=mock_config)
    return ctx


class TestGetActivitiesByDate:
    async def test_success_with_full_metrics(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/activities").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": "a1",
                        "name": "Evening Run",
                        "start_date_local": "2025-11-12T19:08:13",
                        "type": "Run",
                        "distance": 9600,
                        "moving_time": 2764,
                        "average_heartrate": 150,
                        "icu_training_load": 60,
                        "icu_intensity": 0.97,
                    },
                    {
                        "id": "a2",
                        "name": None,  # Untitled fallback
                        "start_date_local": "2025-06-03T07:00:00",
                        "type": "Ride",
                    },
                ],
            )
        )

        result = await get_activities_by_date(
            oldest="2025-06-01", newest="2025-11-30", ctx=_make_ctx(mock_config)
        )

        response = json.loads(result)
        assert response["data"]["count"] == 2
        first = response["data"]["activities"][0]
        assert first["training_load"] == 60
        assert first["intensity_factor"] == 0.97
        assert response["data"]["activities"][1]["name"] == "Untitled"

    async def test_sends_oldest_and_newest_params(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/activities").mock(
            return_value=Response(200, json=[])
        )

        await get_activities_by_date(
            oldest="2025-06-01", newest="2025-11-30", ctx=_make_ctx(mock_config)
        )

        params = respx_mock.calls.last.request.url.params
        assert params["oldest"] == "2025-06-01"
        assert params["newest"] == "2025-11-30"

    async def test_newest_optional(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/activities").mock(
            return_value=Response(200, json=[])
        )

        await get_activities_by_date(oldest="2025-06-01", ctx=_make_ctx(mock_config))

        params = respx_mock.calls.last.request.url.params
        assert params["oldest"] == "2025-06-01"
        assert "newest" not in params

    async def test_empty(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/activities").mock(
            return_value=Response(200, json=[])
        )

        result = await get_activities_by_date(
            oldest="2025-06-01", ctx=_make_ctx(mock_config)
        )
        response = json.loads(result)
        assert response["data"]["count"] == 0
        assert "No activities found" in response["metadata"]["message"]


class TestActivitiesAroundParams:
    """Regression guard for the HTTP 422 fix: correct query-param names."""

    async def test_sends_activity_id_and_limit_not_id_count(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/activities-around").mock(
            return_value=Response(200, json=[])
        )

        await get_activities_around(
            activity_id="i159947305", count=30, ctx=_make_ctx(mock_config)
        )

        params = respx_mock.calls.last.request.url.params
        # The fix: API-correct names are sent...
        assert params["activity_id"] == "i159947305"
        assert params["limit"] == "30"
        # ...and the old wrong names are gone.
        assert "id" not in params
        assert "count" not in params
