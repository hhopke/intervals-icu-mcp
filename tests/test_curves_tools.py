"""Tests for HR and pace curve tools."""

import json
from unittest.mock import AsyncMock, MagicMock

from httpx import Response

from intervals_icu_mcp.tools.curves import (
    _find_nearest_index,
    _find_value_at_duration,
    _format_pace,
    _resolve_period,
    get_hr_curves,
    get_pace_curves,
)


class TestFindValueAtDuration:
    """Pure helper — closest data point within ±10% of target."""

    def test_exact_match(self):
        assert _find_value_at_duration([5, 60, 300], [180, 165, 150], 60) == (60, 165)

    def test_within_tolerance(self):
        # target=60, 10% tolerance = ±6s; 58 is within 6 of 60
        assert _find_value_at_duration([5, 58, 300], [180, 165, 150], 60) == (58, 165)

    def test_outside_tolerance_returns_none(self):
        # target=120, closest is 60 (delta=60), tolerance = ±12, 60 > 12
        assert _find_value_at_duration([5, 60, 300], [180, 165, 150], 120) is None

    def test_empty_returns_none(self):
        assert _find_value_at_duration([], [], 60) is None


class TestResolvePeriod:
    """Pure helper — maps user-facing period args to (curves, label) tuple."""

    def test_days_back_takes_precedence(self):
        assert _resolve_period(90, "year") == ("90d", "90_days")

    def test_default_is_90_days(self):
        assert _resolve_period(None, None) == ("90d", "90_days")

    def test_time_period_week(self):
        assert _resolve_period(None, "week") == ("7d", "week")

    def test_time_period_year(self):
        assert _resolve_period(None, "year") == ("1y", "year")

    def test_time_period_all(self):
        assert _resolve_period(None, "all") == ("all", "all_time")

    def test_time_period_case_insensitive(self):
        assert _resolve_period(None, "MONTH") == ("30d", "month")

    def test_invalid_time_period_returns_error_string(self):
        result = _resolve_period(None, "decade")
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed["error"]["type"] == "validation_error"


class TestGetHRCurves:
    async def test_success_with_peak_efforts(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/hr-curves").mock(
            return_value=Response(
                200,
                json={
                    "list": [
                        {
                            "secs": [5, 60, 300, 1200, 3600],
                            "values": [195, 188, 175, 165, 155],
                            "activity_id": ["a1", "a2", "a3", "a4", "a5"],
                            "start_date_local": "2026-02-19",
                            "end_date_local": "2026-05-19",
                        }
                    ]
                },
            )
        )

        result = await get_hr_curves(sport_type="Ride", time_period="month", ctx=mock_ctx)

        response = json.loads(result)
        data = response["data"]
        assert data["period"] == "month"
        # Peak efforts for matching key durations
        assert data["peak_efforts"]["5_sec"] == {
            "bpm": 195,
            "duration_seconds": 5,
            "activity_id": "a1",
        }
        assert data["peak_efforts"]["1_min"]["bpm"] == 188
        assert data["peak_efforts"]["20_min"]["bpm"] == 165
        # Summary stats
        # Named peak_hr, not max_hr: this is the top of THIS curve, which Intervals.icu
        # has already clipped to the configured max HR at import (#119).
        assert data["summary"]["peak_hr_bpm"] == 195
        assert data["summary"]["peak_hr_duration_seconds"] == 5
        assert "max_hr_bpm" not in data["summary"]
        assert data["summary"]["effort_date_range"]["oldest"] == "2026-02-19"
        # 5.0.0: no synthesized zones. They were a fixed percentage of the curve peak,
        # which Intervals.icu has already clipped to the configured max HR at import —
        # so they could only echo a stale copy of the setting they stood in for.
        # icu_get_sport_settings returns the athlete's real zones (#119).
        assert "hr_zones" not in data

    async def test_skips_zero_points_and_keeps_activity_ids_aligned(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)
        respx_mock.get("/athlete/i123456/pace-curves").mock(
            return_value=Response(
                200,
                json={
                    "list": [
                        {
                            "distance": [0.0, 400.0, 1000.0],
                            "values": [0, 126, 330],
                            "activity_id": ["bad", "a400", "a1k"],
                        }
                    ]
                },
            )
        )

        data = json.loads(await get_pace_curves(ctx=mock_ctx))["data"]
        assert data["summary"]["total_data_points"] == 2
        assert data["peak_efforts"]["400m"]["activity_id"] == "a400"
        assert data["peak_efforts"]["1km"]["activity_id"] == "a1k"

    async def test_empty_curve_data(self, mock_config, respx_mock):
        """Empty values list returns a friendly message, not a crash."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/hr-curves").mock(
            return_value=Response(
                200,
                json={"list": [{"secs": [], "values": [], "activity_id": []}]},
            )
        )

        result = await get_hr_curves(ctx=mock_ctx)
        response = json.loads(result)
        assert response["data"]["hr_curve"] == []
        assert "No HR curve data available" in response["metadata"]["message"]

    async def test_no_curves_in_response(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/hr-curves").mock(
            return_value=Response(200, json={"list": []})
        )

        result = await get_hr_curves(ctx=mock_ctx)
        response = json.loads(result)
        assert response["data"]["hr_curve"] == []

    async def test_invalid_time_period(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await get_hr_curves(time_period="forever", ctx=mock_ctx)
        response = json.loads(result)
        assert response["error"]["type"] == "validation_error"

    async def test_api_error(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/hr-curves").mock(
            return_value=Response(500, json={})
        )

        result = await get_hr_curves(ctx=mock_ctx)
        response = json.loads(result)
        assert response["error"]["type"] == "api_error"


class TestFindNearestIndex:
    """Pure helper — index of the closest point within ±10% of target."""

    def test_exact_match(self):
        assert _find_nearest_index([400.0, 1000.0, 5000.0], 1000) == 1

    def test_within_tolerance(self):
        assert _find_nearest_index([400.0, 1015.0, 5000.0], 1000) == 1

    def test_nearby_distance_is_not_labelled_as_the_standard_one(self):
        # A 4,600 m best time must not be reported as the 5 km time
        assert _find_nearest_index([1000.0, 4600.0, 10000.0], 5000) is None

    def test_outside_tolerance_returns_none(self):
        # Curve stops at 10 km, so a half marathon is not on it
        assert _find_nearest_index([400.0, 1000.0, 10000.0], 21097.5) is None

    def test_empty_returns_none(self):
        assert _find_nearest_index([], 1000) is None


class TestFormatPace:
    def test_zero_pads_seconds(self):
        assert _format_pace(305.0) == "5:05 /km"

    def test_rounds_before_splitting_minutes(self):
        # 299.6 s/km rounds to 300 s, which is 5:00, not 4:60
        assert _format_pace(299.6) == "5:00 /km"


# Real response shape of GET /athlete/{id}/pace-curves (trimmed from a live run curve):
# the curve is distance-based. `distance` is metres, `values` is the best time in
# seconds to cover that distance, and there is no `secs` array.
PACE_CURVE_RESPONSE = {
    "list": [
        {
            "id": "30d",
            "label": "30 days",
            "type": "PACE",
            "distance": [45.719997, 400.0, 1000.0, 1609.34, 5000.0, 10000.0],
            "values": [10, 126, 330, 548, 1984, 4098],
            "activity_id": ["a1", "a2", "a3", "a3", "a4", "a5"],
            "start_date_local": "2026-04-19",
            "end_date_local": "2026-05-19",
        }
    ]
}


class TestGetPaceCurves:
    async def test_success_with_gap(self, mock_config, respx_mock):
        """use_gap=True is forwarded to the client as gap=true."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        route = respx_mock.get("/athlete/i123456/pace-curves").mock(
            return_value=Response(200, json=PACE_CURVE_RESPONSE)
        )

        result = await get_pace_curves(sport_type="Run", days_back=30, use_gap=True, ctx=mock_ctx)

        # GAP flag forwarded
        assert route.calls[0].request.url.params["gap"] == "true"

        data = json.loads(result)["data"]
        assert data["period"] == "30_days"
        assert data["summary"]["gap_enabled"] is True

    async def test_peak_efforts_keyed_on_distance(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)
        respx_mock.get("/athlete/i123456/pace-curves").mock(
            return_value=Response(200, json=PACE_CURVE_RESPONSE)
        )

        data = json.loads(await get_pace_curves(ctx=mock_ctx))["data"]
        efforts = data["peak_efforts"]

        # 1 km in 330 s is 5:30 /km
        assert efforts["1km"] == {
            "distance_meters": 1000.0,
            "time_seconds": 330,
            "pace_seconds_per_km": 330.0,
            "pace_formatted": "5:30 /km",
            "activity_id": "a3",
        }
        # 5 km in 1984 s is 396.8 s/km
        assert efforts["5km"]["pace_seconds_per_km"] == 396.8
        assert efforts["5km"]["pace_formatted"] == "6:37 /km"
        assert efforts["400m"]["pace_formatted"] == "5:15 /km"
        assert efforts["10km"]["time_seconds"] == 4098
        # The curve stops at 10 km, so longer distances are omitted, not guessed
        assert "half_marathon" not in efforts
        assert "marathon" not in efforts

    async def test_summary_reports_best_pace_with_its_distance(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)
        respx_mock.get("/athlete/i123456/pace-curves").mock(
            return_value=Response(200, json=PACE_CURVE_RESPONSE)
        )

        summary = json.loads(await get_pace_curves(ctx=mock_ctx))["data"]["summary"]

        # Fastest pace is over the shortest distance: 10 s for 45.72 m = 218.7 s/km.
        # Before the fix this was reported as "0:10 /km" (raw seconds read as pace).
        assert summary["best_pace_seconds_per_km"] == 218.7
        assert summary["best_pace_formatted"] == "3:39 /km"
        assert summary["best_pace_distance_meters"] == 45.72
        assert summary["distance_range"] == {"min_meters": 45.72, "max_meters": 10000.0}
        assert summary["total_data_points"] == 6
        assert summary["effort_date_range"] == {"oldest": "2026-04-19", "newest": "2026-05-19"}

    async def test_empty_curve_data(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/pace-curves").mock(
            return_value=Response(
                200, json={"list": [{"distance": [], "values": [], "activity_id": []}]}
            )
        )

        result = await get_pace_curves(ctx=mock_ctx)
        response = json.loads(result)
        assert response["data"]["pace_curve"] == []
        assert response["data"]["gap_enabled"] is False

    async def test_null_curve_arrays(self, mock_config, respx_mock):
        """When a period has no pace data, the API sends null arrays rather than []."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/pace-curves").mock(
            return_value=Response(
                200, json={"list": [{"distance": None, "values": None, "activity_id": None}]}
            )
        )

        result = await get_pace_curves(ctx=mock_ctx)
        response = json.loads(result)
        assert response["data"]["pace_curve"] == []
        assert "No pace curve data available" in response["metadata"]["message"]

    async def test_api_error(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/pace-curves").mock(return_value=Response(404, json={}))

        result = await get_pace_curves(ctx=mock_ctx)
        response = json.loads(result)
        assert response["error"]["type"] == "api_error"
