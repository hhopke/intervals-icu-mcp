"""Tests for HR and pace curve tools."""

import json
from unittest.mock import AsyncMock, MagicMock

from httpx import Response

from intervals_icu_mcp.tools.curves import (
    _find_value_at_duration,
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
    async def test_success_with_zones_and_peak_efforts(self, mock_config, respx_mock):
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
        assert data["summary"]["max_hr_bpm"] == 195
        assert data["summary"]["max_hr_duration_seconds"] == 5
        assert data["summary"]["effort_date_range"]["oldest"] == "2026-02-19"
        # HR zones derived from max HR
        zone2 = data["hr_zones"]["zone_2_endurance"]
        assert zone2["min_bpm"] == int(195 * 0.60)
        assert zone2["max_bpm"] == int(195 * 0.70)
        assert zone2["min_percent_max"] == 60

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


class TestGetPaceCurves:
    async def test_success_with_gap(self, mock_config, respx_mock):
        """use_gap=True is forwarded to the client as gap=true."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        route = respx_mock.get("/athlete/i123456/pace-curves").mock(
            return_value=Response(
                200,
                json={
                    "list": [
                        {
                            "secs": [60, 300, 600, 1200, 1800, 3600],
                            # Pace in s/km: lower=faster
                            "values": [180, 200, 220, 240, 260, 280],
                            "activity_id": ["a1", "a2", "a3", "a4", "a5", "a6"],
                            "start_date_local": "2026-04-19",
                            "end_date_local": "2026-05-19",
                        }
                    ]
                },
            )
        )

        result = await get_pace_curves(
            sport_type="Run", days_back=30, use_gap=True, ctx=mock_ctx
        )

        # GAP flag forwarded
        assert route.calls[0].request.url.params["gap"] == "true"

        response = json.loads(result)
        data = response["data"]
        assert data["period"] == "30_days"
        # Best pace = lowest value
        assert data["summary"]["best_pace_seconds_per_km"] == 180
        assert data["summary"]["best_pace_formatted"] == "3:00 /km"
        assert data["summary"]["gap_enabled"] is True
        # 5-minute pace formatted
        assert data["peak_efforts"]["5_min"]["pace_formatted"] == "3:20 /km"
        # 1-hour pace formatted, with seconds zero-padded
        assert data["peak_efforts"]["1_hour"]["pace_formatted"] == "4:40 /km"

    async def test_empty_curve_data(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/pace-curves").mock(
            return_value=Response(
                200, json={"list": [{"secs": [], "values": [], "activity_id": []}]}
            )
        )

        result = await get_pace_curves(ctx=mock_ctx)
        response = json.loads(result)
        assert response["data"]["pace_curve"] == []
        assert response["data"]["gap_enabled"] is False

    async def test_api_error(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/pace-curves").mock(
            return_value=Response(404, json={})
        )

        result = await get_pace_curves(ctx=mock_ctx)
        response = json.loads(result)
        assert response["error"]["type"] == "api_error"
