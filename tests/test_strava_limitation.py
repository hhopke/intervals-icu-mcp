"""Tests for Strava-restricted activity detection and messaging."""

import json
from unittest.mock import AsyncMock, MagicMock

from httpx import Response

from intervals_icu_mcp.models import Activity
from intervals_icu_mcp.tools._strava import STRAVA_LIMITATION_NOTE, strava_limitation_note
from intervals_icu_mcp.tools.activities import get_activity_details
from intervals_icu_mcp.tools.activity_analysis import (
    get_activity_intervals,
    get_activity_streams,
    get_best_efforts,
    get_gap_histogram,
    get_hr_histogram,
    get_pace_histogram,
    get_power_histogram,
)

STRAVA_STUB = {
    "id": "16358453283",
    "source": "STRAVA",
    "_note": "STRAVA activities are not available via the API",
    "start_date_local": "2025-11-04T19:21:15",
}

NON_STRAVA_EMPTY = {
    "id": "12345",
    "source": "MANUAL",
    "start_date_local": "2025-11-04T19:21:15",
}

STRAVA_WITH_METRICS = {
    "id": "999",
    "source": "STRAVA",
    "start_date_local": "2025-11-04T19:21:15",
    "distance": 30000.0,
    "moving_time": 3600,
    "average_heartrate": 140,
}


class TestStravaLimitationHelper:
    """Pure-function tests for strava_limitation_note."""

    def test_detects_strava_stub(self):
        activity = Activity.model_validate(STRAVA_STUB)
        assert activity.source == "STRAVA"
        assert activity.note == "STRAVA activities are not available via the API"
        assert strava_limitation_note(activity) == STRAVA_LIMITATION_NOTE

    def test_no_false_positive_on_non_strava_empty_activity(self):
        activity = Activity.model_validate(NON_STRAVA_EMPTY)
        assert strava_limitation_note(activity) is None

    def test_no_false_positive_on_strava_with_metrics(self):
        activity = Activity.model_validate(STRAVA_WITH_METRICS)
        assert strava_limitation_note(activity) is None

    def test_message_includes_workaround(self):
        # Sanity-check the user-facing copy mentions the direct-sync workaround.
        assert "directly to Intervals.icu" in STRAVA_LIMITATION_NOTE
        assert "Garmin" in STRAVA_LIMITATION_NOTE


class TestActivityDetailsStravaSurface:
    """get_activity_details surfaces the limitation message in analysis."""

    async def test_strava_stub_surfaces_message(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/activity/16358453283").mock(
            return_value=Response(200, json=STRAVA_STUB)
        )

        result = await get_activity_details(activity_id="16358453283", ctx=mock_ctx)
        response = json.loads(result)

        assert "analysis" in response
        assert response["analysis"]["data_availability"] == STRAVA_LIMITATION_NOTE

    async def test_non_strava_no_message(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/activity/12345").mock(
            return_value=Response(200, json=NON_STRAVA_EMPTY)
        )

        result = await get_activity_details(activity_id="12345", ctx=mock_ctx)
        response = json.loads(result)

        assert "analysis" not in response


class TestAnalysisToolsStravaSurface:
    """Streams/intervals/best-efforts/histograms surface message on empty results."""

    async def test_streams_strava_stub(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/activity/16358453283/streams.json").mock(
            return_value=Response(200, json=[])
        )
        respx_mock.get("/activity/16358453283").mock(
            return_value=Response(200, json=STRAVA_STUB)
        )

        result = await get_activity_streams(activity_id="16358453283", ctx=mock_ctx)
        response = json.loads(result)

        assert response["analysis"]["data_availability"] == STRAVA_LIMITATION_NOTE

    async def test_streams_non_strava_no_followup_call(self, mock_config, respx_mock):
        """Empty streams on a non-Strava activity should not surface the message."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/activity/12345/streams.json").mock(
            return_value=Response(200, json=[])
        )
        respx_mock.get("/activity/12345").mock(
            return_value=Response(200, json=NON_STRAVA_EMPTY)
        )

        result = await get_activity_streams(activity_id="12345", ctx=mock_ctx)
        response = json.loads(result)

        assert "analysis" not in response

    async def test_intervals_strava_stub(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/activity/16358453283/intervals").mock(
            return_value=Response(200, json={"id": "16358453283", "icu_intervals": []})
        )
        respx_mock.get("/activity/16358453283").mock(
            return_value=Response(200, json=STRAVA_STUB)
        )

        result = await get_activity_intervals(activity_id="16358453283", ctx=mock_ctx)
        response = json.loads(result)

        assert response["analysis"]["data_availability"] == STRAVA_LIMITATION_NOTE

    async def test_best_efforts_strava_stub(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/activity/16358453283/best-efforts").mock(
            return_value=Response(200, json={"efforts": []})
        )
        respx_mock.get("/activity/16358453283").mock(
            return_value=Response(200, json=STRAVA_STUB)
        )

        result = await get_best_efforts(
            activity_id="16358453283", duration=60, ctx=mock_ctx
        )
        response = json.loads(result)

        assert response["analysis"]["data_availability"] == STRAVA_LIMITATION_NOTE

    async def test_power_histogram_strava_stub(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/activity/16358453283/power-histogram").mock(
            return_value=Response(200, json={"bins": []})
        )
        respx_mock.get("/activity/16358453283").mock(
            return_value=Response(200, json=STRAVA_STUB)
        )

        result = await get_power_histogram(activity_id="16358453283", ctx=mock_ctx)
        response = json.loads(result)

        assert response["analysis"]["data_availability"] == STRAVA_LIMITATION_NOTE

    async def test_hr_histogram_strava_stub(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/activity/16358453283/hr-histogram").mock(
            return_value=Response(200, json={"bins": []})
        )
        respx_mock.get("/activity/16358453283").mock(
            return_value=Response(200, json=STRAVA_STUB)
        )

        result = await get_hr_histogram(activity_id="16358453283", ctx=mock_ctx)
        response = json.loads(result)

        assert response["analysis"]["data_availability"] == STRAVA_LIMITATION_NOTE

    async def test_pace_histogram_strava_stub(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/activity/16358453283/pace-histogram").mock(
            return_value=Response(200, json={"bins": []})
        )
        respx_mock.get("/activity/16358453283").mock(
            return_value=Response(200, json=STRAVA_STUB)
        )

        result = await get_pace_histogram(activity_id="16358453283", ctx=mock_ctx)
        response = json.loads(result)

        assert response["analysis"]["data_availability"] == STRAVA_LIMITATION_NOTE

    async def test_gap_histogram_strava_stub(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/activity/16358453283/gap-histogram").mock(
            return_value=Response(200, json={"bins": []})
        )
        respx_mock.get("/activity/16358453283").mock(
            return_value=Response(200, json=STRAVA_STUB)
        )

        result = await get_gap_histogram(activity_id="16358453283", ctx=mock_ctx)
        response = json.loads(result)

        assert response["analysis"]["data_availability"] == STRAVA_LIMITATION_NOTE
