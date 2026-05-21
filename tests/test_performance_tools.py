"""Tests for power-curve performance analysis tool."""

import json
from unittest.mock import AsyncMock, MagicMock

from httpx import Response

from intervals_icu_mcp.tools.performance import get_power_curves


class TestGetPowerCurves:
    async def test_success_with_ftp_estimation(self, mock_config, respx_mock):
        """A 20-minute data point triggers FTP estimation (95%) and power zones."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/power-curves").mock(
            return_value=Response(
                200,
                json={
                    "list": [
                        {
                            "secs": [5, 60, 300, 1200, 3600],
                            "values": [1200, 700, 400, 300, 250],
                            "activity_id": ["a1", "a2", "a3", "a4", "a5"],
                            "start_date_local": "2026-02-19",
                            "end_date_local": "2026-05-19",
                        }
                    ]
                },
            )
        )

        result = await get_power_curves(sport_type="Ride", days_back=90, ctx=mock_ctx)

        response = json.loads(result)
        data = response["data"]
        assert data["period"] == "90_days"
        # FTP = 20-min power * 0.95 = 300 * 0.95 = 285
        assert data["ftp_analysis"]["twenty_min_power"] == 300
        assert data["ftp_analysis"]["estimated_ftp"] == 285
        zones = data["ftp_analysis"]["power_zones"]
        assert zones["threshold"]["min_percent_ftp"] == 91
        assert zones["threshold"]["max_percent_ftp"] == 105
        assert zones["threshold"]["min_watts"] == int(285 * 0.91)
        # Peak efforts
        assert data["peak_efforts"]["5_sec"]["watts"] == 1200
        assert data["peak_efforts"]["5_sec"]["activity_id"] == "a1"
        assert data["peak_efforts"]["20_min"]["watts"] == 300
        # Summary
        assert data["summary"]["max_power_watts"] == 1200
        assert data["summary"]["max_power_duration_seconds"] == 5

    async def test_success_without_20min_no_ftp_block(self, mock_config, respx_mock):
        """Curve missing a near-20-min point omits the ftp_analysis block."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/power-curves").mock(
            return_value=Response(
                200,
                json={
                    "list": [
                        {
                            "secs": [5, 60, 300],  # No point near 1200s
                            "values": [1200, 700, 400],
                            "activity_id": ["a1", "a2", "a3"],
                        }
                    ]
                },
            )
        )

        result = await get_power_curves(time_period="week", ctx=mock_ctx)

        response = json.loads(result)
        data = response["data"]
        assert data["period"] == "week"
        assert "ftp_analysis" not in data
        # Peak efforts still computed for the durations present
        assert "5_sec" in data["peak_efforts"]
        assert "20_min" not in data["peak_efforts"]

    async def test_empty_curve_data(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/power-curves").mock(
            return_value=Response(
                200, json={"list": [{"secs": [], "values": [], "activity_id": []}]}
            )
        )

        result = await get_power_curves(ctx=mock_ctx)
        response = json.loads(result)
        assert response["data"]["power_curve"] == []
        assert response["data"]["period"] == "90_days"  # default
        assert "No power curve data available" in response["metadata"]["message"]

    async def test_no_curves_in_response(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/power-curves").mock(
            return_value=Response(200, json={"list": []})
        )

        result = await get_power_curves(ctx=mock_ctx)
        response = json.loads(result)
        assert response["data"]["power_curve"] == []

    async def test_invalid_time_period(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await get_power_curves(time_period="decade", ctx=mock_ctx)
        response = json.loads(result)
        assert response["error"]["type"] == "validation_error"

    async def test_time_period_all(self, mock_config, respx_mock):
        """'all' shorthand maps to curves='all' and period_label='all_time'."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        route = respx_mock.get("/athlete/i123456/power-curves").mock(
            return_value=Response(200, json={"list": []})
        )

        result = await get_power_curves(time_period="all", ctx=mock_ctx)
        assert route.calls[0].request.url.params["type"] == "Ride"
        assert "all" in route.calls[0].request.url.params["curves"]
        response = json.loads(result)
        assert response["data"]["period"] == "all_time"

    async def test_api_error(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/power-curves").mock(
            return_value=Response(401, json={})
        )

        result = await get_power_curves(ctx=mock_ctx)
        response = json.loads(result)
        assert response["error"]["type"] == "api_error"
