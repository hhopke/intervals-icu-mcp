"""Tests for activity analysis tools — streams, intervals, best efforts, search_intervals."""

import json
from unittest.mock import AsyncMock, MagicMock

from httpx import Response

from intervals_icu_mcp.tools.activity_analysis import (
    get_activity_intervals,
    get_activity_streams,
    get_best_efforts,
    search_intervals,
)


def _make_ctx(mock_config):
    ctx = MagicMock()
    ctx.get_state = AsyncMock(return_value=mock_config)
    return ctx


class TestGetActivityStreams:
    async def test_success(self, mock_config, respx_mock):
        respx_mock.get("/activity/a1/streams.json").mock(
            return_value=Response(
                200,
                json=[
                    {"type": "watts", "data": [100, 200, 250]},
                    {"type": "heartrate", "data": [120, 140, 160]},
                    {"name": "no_type_stream", "data": [1, 2]},
                ],
            )
        )

        result = await get_activity_streams(activity_id="a1", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        data = response["data"]
        assert data["activity_id"] == "a1"
        assert "watts" in data["available_streams"]
        assert "heartrate" in data["available_streams"]
        assert "no_type_stream" in data["available_streams"]
        assert data["stream_lengths"]["watts"] == 3
        assert data["streams"]["heartrate"] == [120, 140, 160]

    async def test_with_stream_filter(self, mock_config, respx_mock):
        """Stream filter is forwarded as comma-separated `types` query param."""
        route = respx_mock.get("/activity/a1/streams.json").mock(
            return_value=Response(200, json=[])
        )

        await get_activity_streams(
            activity_id="a1", streams=["watts", "heartrate"], ctx=_make_ctx(mock_config)
        )
        assert route.calls[0].request.url.params["types"] == "watts,heartrate"

    async def test_empty_streams_no_strava_note(self, mock_config, respx_mock):
        """Empty streams + no Strava limitation → message but no analysis block."""
        # Empty streams response
        respx_mock.get("/activity/a1/streams.json").mock(return_value=Response(200, json=[]))
        # Activity is not from Strava (no Strava limitation note)
        respx_mock.get("/activity/a1").mock(
            return_value=Response(
                200,
                json={
                    "id": "a1",
                    "name": "Garmin Ride",
                    "type": "Ride",
                    "start_date_local": "2026-05-19T08:00:00",
                    "external_id": "garmin_12345",
                },
            )
        )

        result = await get_activity_streams(activity_id="a1", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["data"]["streams"] == {}
        assert "No stream data available" in response["metadata"]["message"]

    async def test_api_error(self, mock_config, respx_mock):
        respx_mock.get("/activity/a1/streams.json").mock(return_value=Response(404, json={}))

        result = await get_activity_streams(activity_id="a1", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["error"]["type"] == "api_error"


class TestGetActivityIntervals:
    async def test_success_categorizes_work_rest(self, mock_config, respx_mock):
        respx_mock.get("/activity/a1/intervals").mock(
            return_value=Response(
                200,
                json={
                    "id": "a1",
                    "icu_intervals": [
                        {
                            "id": 1,
                            "type": "WARM_UP",
                            "start": 0,
                            "end": 600,
                            "duration": 600,
                            "average_watts": 150,
                            "average_heartrate": 120,
                            "average_cadence": 85,
                            "average_speed": 8.5,
                            "distance": 5000,
                        },
                        {
                            "id": 2,
                            "type": "WORK",
                            "start": 600,
                            "end": 1200,
                            "duration": 600,
                            "average_watts": 280,
                            "normalized_power": 285,
                            "max_heartrate": 175,
                            "target": "Threshold",
                            "target_min": 270,
                            "target_max": 290,
                        },
                        {
                            "id": 3,
                            "type": "REST",
                            "duration": 300,
                        },
                        {
                            "id": 4,
                            "type": "WORK",
                            "duration": 600,
                        },
                    ],
                },
            )
        )

        result = await get_activity_intervals(activity_id="a1", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        data = response["data"]
        # Total counts categorized correctly
        assert data["summary"]["total_intervals"] == 4
        assert data["summary"]["work_intervals"] == 2
        assert data["summary"]["rest_intervals"] == 1
        assert data["summary"]["total_work_time_seconds"] == 1200
        # Work interval carries target info
        work_with_target = data["intervals"][1]
        assert work_with_target["target_description"] == "Threshold"
        assert work_with_target["target_range"] == {"min": 270, "max": 290}
        assert work_with_target["performance"]["normalized_power"] == 285

    async def test_empty_intervals_no_strava_note(self, mock_config, respx_mock):
        respx_mock.get("/activity/a1/intervals").mock(
            return_value=Response(200, json={"id": "a1", "icu_intervals": []})
        )
        respx_mock.get("/activity/a1").mock(
            return_value=Response(
                200,
                json={
                    "id": "a1",
                    "name": "Ride",
                    "type": "Ride",
                    "start_date_local": "2026-05-19T08:00:00",
                },
            )
        )

        result = await get_activity_intervals(activity_id="a1", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["data"]["count"] == 0
        assert "No intervals found" in response["metadata"]["message"]

    async def test_api_error(self, mock_config, respx_mock):
        respx_mock.get("/activity/a1/intervals").mock(return_value=Response(500, json={}))

        result = await get_activity_intervals(activity_id="a1", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["error"]["type"] == "api_error"


class TestGetBestEfforts:
    async def test_success_with_duration(self, mock_config, respx_mock):
        route = respx_mock.get("/activity/a1/best-efforts").mock(
            return_value=Response(
                200,
                json={
                    "efforts": [
                        {
                            "average": 280.5,
                            "duration": 1200,
                            "start_index": 100,
                            "end_index": 1300,
                        },
                        {"average": 270.0, "duration": 1200},
                    ]
                },
            )
        )

        result = await get_best_efforts(
            activity_id="a1", stream="watts", duration=1200, count=5, ctx=_make_ctx(mock_config)
        )

        params = route.calls[0].request.url.params
        assert params["duration"] == "1200"
        assert params["count"] == "5"
        assert params["stream"] == "watts"

        response = json.loads(result)
        assert response["data"]["count"] == 2
        assert response["data"]["stream"] == "watts"

    async def test_success_with_distance(self, mock_config, respx_mock):
        respx_mock.get("/activity/a1/best-efforts").mock(
            return_value=Response(
                200,
                json={
                    "efforts": [
                        {"average": 200.0, "distance": 5000, "duration": 1500},
                    ]
                },
            )
        )

        result = await get_best_efforts(
            activity_id="a1", stream="pace", distance=5000, ctx=_make_ctx(mock_config)
        )
        response = json.loads(result)
        assert response["data"]["best_efforts"][0]["distance_meters"] == 5000

    async def test_missing_both_duration_and_distance(self, mock_config):
        result = await get_best_efforts(activity_id="a1", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["error"]["type"] == "validation_error"
        assert "duration" in response["error"]["message"]

    async def test_empty_efforts(self, mock_config, respx_mock):
        respx_mock.get("/activity/a1/best-efforts").mock(
            return_value=Response(200, json={"efforts": []})
        )
        # Mock the strava check too
        respx_mock.get("/activity/a1").mock(
            return_value=Response(
                200,
                json={"id": "a1", "name": "X", "type": "Ride", "start_date_local": "2026-05-19"},
            )
        )

        result = await get_best_efforts(
            activity_id="a1", duration=1200, ctx=_make_ctx(mock_config)
        )
        response = json.loads(result)
        assert response["data"]["count"] == 0

    async def test_api_error(self, mock_config, respx_mock):
        respx_mock.get("/activity/a1/best-efforts").mock(return_value=Response(401, json={}))

        result = await get_best_efforts(
            activity_id="a1", duration=1200, ctx=_make_ctx(mock_config)
        )
        response = json.loads(result)
        assert response["error"]["type"] == "api_error"


class TestSearchIntervals:
    async def test_success_with_all_filters(self, mock_config, respx_mock):
        route = respx_mock.get("/athlete/i123456/activities/interval-search").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "type": "WORK", "duration": 300, "activity_id": "a1"},
                    {"id": 2, "type": "WORK", "duration": 600, "activity_id": "a2"},
                ],
            )
        )

        result = await search_intervals(
            interval_type="WORK",
            min_duration=120,
            max_duration=1200,
            limit=10,
            ctx=_make_ctx(mock_config),
        )

        params = route.calls[0].request.url.params
        assert params["type"] == "WORK"
        assert params["minDuration"] == "120"
        assert params["maxDuration"] == "1200"

        response = json.loads(result)
        data = response["data"]
        assert data["count"] == 2
        assert data["search_criteria"]["interval_type"] == "WORK"
        assert data["search_criteria"]["min_duration_seconds"] == 120

    async def test_no_results_with_criteria_string(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/activities/interval-search").mock(
            return_value=Response(200, json=[])
        )

        result = await search_intervals(
            interval_type="THRESHOLD", min_duration=600, ctx=_make_ctx(mock_config)
        )
        response = json.loads(result)
        assert response["data"]["count"] == 0
        assert "THRESHOLD" in response["metadata"]["message"]
        assert "600" in response["metadata"]["message"]

    async def test_no_results_no_criteria_uses_default_string(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/activities/interval-search").mock(
            return_value=Response(200, json=[])
        )

        result = await search_intervals(ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert "your criteria" in response["metadata"]["message"]

    async def test_api_error(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/activities/interval-search").mock(
            return_value=Response(500, json={})
        )

        result = await search_intervals(interval_type="WORK", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["error"]["type"] == "api_error"
