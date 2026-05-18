"""Tests for histogram tools — power, HR, pace, GAP.

Regression coverage for #39: the API returns a bare JSON array of bucket
objects shaped `{min, max, secs}` (not a wrapper object, not the richer shape
the OpenAPI spec advertises). Feeding non-empty payloads through end-to-end
here would have caught the original bug; the previous Strava-stub tests
mocked empty responses and never exercised deserialization.

The fixtures below mirror the actual `/activity/{id}/{hr,power,pace,gap}-histogram`
responses observed against the live Intervals.icu API.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import Response

from intervals_icu_mcp.tools.activity_analysis import (
    get_gap_histogram,
    get_hr_histogram,
    get_pace_histogram,
    get_power_histogram,
)

ACTIVITY_ID = "i123"

HR_BUCKETS = [
    {"min": 130, "max": 134, "secs": 2},
    {"min": 135, "max": 139, "secs": 49},
    {"min": 140, "max": 144, "secs": 210},
    {"min": 145, "max": 149, "secs": 600},
]

POWER_BUCKETS = [
    {"min": 0, "max": 24, "secs": 66},
    {"min": 25, "max": 49, "secs": 300},
    {"min": 50, "max": 74, "secs": 90},
]


@pytest.mark.asyncio
class TestHrHistogram:
    async def test_non_empty_payload_round_trips(self, mock_config, respx_mock):
        """Previously crashed with `argument after ** must be a mapping, not list`."""
        ctx = MagicMock()
        ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get(f"/activity/{ACTIVITY_ID}/hr-histogram").mock(
            return_value=Response(200, json=HR_BUCKETS)
        )

        result = await get_hr_histogram(activity_id=ACTIVITY_ID, ctx=ctx)
        data = json.loads(result)["data"]

        assert data["activity_id"] == ACTIVITY_ID
        assert len(data["buckets"]) == 4
        assert data["total_time_seconds"] == 2 + 49 + 210 + 600

    async def test_bucket_boundaries_populated_from_api(self, mock_config, respx_mock):
        """The bug after the first fix: min_bpm/max_bpm were null because the
        model used `start` instead of the actual `min`/`max` API fields."""
        ctx = MagicMock()
        ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get(f"/activity/{ACTIVITY_ID}/hr-histogram").mock(
            return_value=Response(200, json=HR_BUCKETS)
        )

        result = await get_hr_histogram(activity_id=ACTIVITY_ID, ctx=ctx)
        buckets = json.loads(result)["data"]["buckets"]

        assert buckets[0]["hr_range"] == {"min_bpm": 130, "max_bpm": 134}
        assert buckets[1]["hr_range"] == {"min_bpm": 135, "max_bpm": 139}
        assert buckets[3]["hr_range"] == {"min_bpm": 145, "max_bpm": 149}

    async def test_per_bucket_time_surfaces(self, mock_config, respx_mock):
        ctx = MagicMock()
        ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get(f"/activity/{ACTIVITY_ID}/hr-histogram").mock(
            return_value=Response(200, json=HR_BUCKETS)
        )

        result = await get_hr_histogram(activity_id=ACTIVITY_ID, ctx=ctx)
        buckets = json.loads(result)["data"]["buckets"]

        assert buckets[2]["time_seconds"] == 210
        assert buckets[3]["time_seconds"] == 600

    async def test_empty_payload_returns_empty_buckets(self, mock_config, respx_mock):
        """Activity with no HR data — API returns []."""
        ctx = MagicMock()
        ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get(f"/activity/{ACTIVITY_ID}/hr-histogram").mock(
            return_value=Response(200, json=[])
        )
        respx_mock.get(f"/activity/{ACTIVITY_ID}").mock(
            return_value=Response(
                200,
                json={
                    "id": ACTIVITY_ID,
                    "source": "MANUAL",
                    "start_date_local": "2025-11-04T12:00:00",
                },
            )
        )

        result = await get_hr_histogram(activity_id=ACTIVITY_ID, ctx=ctx)
        data = json.loads(result)["data"]
        assert data["buckets"] == []


@pytest.mark.asyncio
class TestPowerHistogram:
    async def test_non_empty_payload_round_trips(self, mock_config, respx_mock):
        ctx = MagicMock()
        ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get(f"/activity/{ACTIVITY_ID}/power-histogram").mock(
            return_value=Response(200, json=POWER_BUCKETS)
        )

        result = await get_power_histogram(activity_id=ACTIVITY_ID, ctx=ctx)
        data = json.loads(result)["data"]

        assert len(data["buckets"]) == 3
        assert data["buckets"][0]["power_range"] == {"min_watts": 0, "max_watts": 24}
        assert data["buckets"][1]["power_range"] == {"min_watts": 25, "max_watts": 49}
        assert data["buckets"][2]["power_range"] == {"min_watts": 50, "max_watts": 74}
        assert data["total_time_seconds"] == 66 + 300 + 90


@pytest.mark.asyncio
class TestPaceAndGapHistograms:
    async def test_pace_non_empty_payload_round_trips(self, mock_config, respx_mock):
        ctx = MagicMock()
        ctx.get_state = AsyncMock(return_value=mock_config)

        payload = [
            {"min": 240, "max": 269, "secs": 100},
            {"min": 270, "max": 299, "secs": 400},
        ]
        respx_mock.get(f"/activity/{ACTIVITY_ID}/pace-histogram").mock(
            return_value=Response(200, json=payload)
        )

        result = await get_pace_histogram(activity_id=ACTIVITY_ID, ctx=ctx)
        buckets = json.loads(result)["data"]["buckets"]
        assert buckets[0]["pace_range"] == {"min": 240, "max": 269}
        assert buckets[1]["pace_range"] == {"min": 270, "max": 299}

    async def test_gap_non_empty_payload_round_trips(self, mock_config, respx_mock):
        ctx = MagicMock()
        ctx.get_state = AsyncMock(return_value=mock_config)

        payload = [
            {"min": 240, "max": 269, "secs": 200},
            {"min": 270, "max": 299, "secs": 300},
        ]
        respx_mock.get(f"/activity/{ACTIVITY_ID}/gap-histogram").mock(
            return_value=Response(200, json=payload)
        )

        result = await get_gap_histogram(activity_id=ACTIVITY_ID, ctx=ctx)
        data = json.loads(result)["data"]
        assert data["buckets"][0]["gap_range"] == {"min": 240, "max": 269}
        assert "GAP" in data["note"]
