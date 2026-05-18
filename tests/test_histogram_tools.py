"""Tests for histogram tools — power, HR, pace, GAP.

Regression coverage for #39: the API returns a bare JSON array of Bucket
objects (not a wrapper object), and `Bucket(**...)` was previously called as
`Histogram(**...)`. Feeding non-empty payloads through end-to-end here would
have caught the original bug; the previous Strava-stub tests mocked empty
responses and never exercised deserialization.
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

# Realistic HR histogram payload: 5-bpm buckets from 60 to 90, time-in-bucket.
HR_BUCKETS = [
    {"start": 60, "secs": 120, "movingSecs": 120, "hr": 62.5, "watts": 0, "cadence": 0},
    {"start": 65, "secs": 240, "movingSecs": 240, "hr": 67.5, "watts": 0, "cadence": 0},
    {"start": 70, "secs": 600, "movingSecs": 540, "hr": 72.5, "watts": 0, "cadence": 0},
    {"start": 75, "secs": 300, "movingSecs": 300, "hr": 77.5, "watts": 0, "cadence": 0},
]

POWER_BUCKETS = [
    {"start": 100, "secs": 60, "movingSecs": 60, "watts": 110, "hr": 0, "cadence": 0},
    {"start": 150, "secs": 300, "movingSecs": 300, "watts": 165, "hr": 0, "cadence": 0},
    {"start": 200, "secs": 90, "movingSecs": 90, "watts": 215, "hr": 0, "cadence": 0},
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
        assert data["total_time_seconds"] == 120 + 240 + 600 + 300
        assert data["total_moving_time_seconds"] == 120 + 240 + 540 + 300

    async def test_bucket_end_derived_from_next_start(self, mock_config, respx_mock):
        ctx = MagicMock()
        ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get(f"/activity/{ACTIVITY_ID}/hr-histogram").mock(
            return_value=Response(200, json=HR_BUCKETS)
        )

        result = await get_hr_histogram(activity_id=ACTIVITY_ID, ctx=ctx)
        buckets = json.loads(result)["data"]["buckets"]

        # Middle buckets: end == next bucket's start.
        assert buckets[0]["hr_range"] == {"min_bpm": 60, "max_bpm": 65}
        assert buckets[1]["hr_range"] == {"min_bpm": 65, "max_bpm": 70}
        assert buckets[2]["hr_range"] == {"min_bpm": 70, "max_bpm": 75}
        # Last bucket: width inferred from the first consecutive pair (5 bpm).
        assert buckets[3]["hr_range"] == {"min_bpm": 75, "max_bpm": 80}

    async def test_per_bucket_times_surface(self, mock_config, respx_mock):
        ctx = MagicMock()
        ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get(f"/activity/{ACTIVITY_ID}/hr-histogram").mock(
            return_value=Response(200, json=HR_BUCKETS)
        )

        result = await get_hr_histogram(activity_id=ACTIVITY_ID, ctx=ctx)
        buckets = json.loads(result)["data"]["buckets"]

        # The middle bucket had moving_secs < secs (some non-moving time).
        assert buckets[2]["time_seconds"] == 600
        assert buckets[2]["moving_time_seconds"] == 540

    async def test_empty_payload_returns_empty_buckets(self, mock_config, respx_mock):
        """Activity with no HR data — API returns [] (not {bins: []})."""
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
        assert data["buckets"][0]["power_range"] == {"min_watts": 100, "max_watts": 150}
        assert data["buckets"][1]["power_range"] == {"min_watts": 150, "max_watts": 200}
        # Last bucket: width inferred (50 W).
        assert data["buckets"][2]["power_range"] == {"min_watts": 200, "max_watts": 250}
        assert data["total_time_seconds"] == 60 + 300 + 90


@pytest.mark.asyncio
class TestPaceAndGapHistograms:
    async def test_pace_non_empty_payload_round_trips(self, mock_config, respx_mock):
        ctx = MagicMock()
        ctx.get_state = AsyncMock(return_value=mock_config)

        # Pace bucket `start` unit is API-defined; emit raw values without speculative formatting.
        payload = [
            {"start": 240, "secs": 100, "movingSecs": 100},
            {"start": 270, "secs": 400, "movingSecs": 400},
            {"start": 300, "secs": 150, "movingSecs": 150},
        ]
        respx_mock.get(f"/activity/{ACTIVITY_ID}/pace-histogram").mock(
            return_value=Response(200, json=payload)
        )

        result = await get_pace_histogram(activity_id=ACTIVITY_ID, ctx=ctx)
        buckets = json.loads(result)["data"]["buckets"]
        assert buckets[0]["pace_range"] == {"start": 240, "end": 270}
        assert buckets[2]["pace_range"] == {"start": 300, "end": 330}

    async def test_gap_non_empty_payload_round_trips(self, mock_config, respx_mock):
        ctx = MagicMock()
        ctx.get_state = AsyncMock(return_value=mock_config)

        payload = [
            {"start": 240, "secs": 200, "movingSecs": 200},
            {"start": 270, "secs": 300, "movingSecs": 300},
        ]
        respx_mock.get(f"/activity/{ACTIVITY_ID}/gap-histogram").mock(
            return_value=Response(200, json=payload)
        )

        result = await get_gap_histogram(activity_id=ACTIVITY_ID, ctx=ctx)
        data = json.loads(result)["data"]
        assert data["buckets"][0]["gap_range"] == {"start": 240, "end": 270}
        assert "GAP" in data["note"]
