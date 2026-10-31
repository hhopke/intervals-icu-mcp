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
        # 5.0.0: estimated_ftp stays — it is a real signal icu_get_sport_settings cannot
        # give — but the zone bands derived from it are gone (#119).
        assert "power_zones" not in data["ftp_analysis"]
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


def _curve(curve_id: str, label: str, watts: int) -> dict:
    return {
        "id": curve_id,
        "label": label,
        "secs": [5, 1200],
        "values": [watts * 3, watts],
        "activity_id": ["a1", "a2"],
    }


class TestGetPowerCurvesWindows:
    async def test_date_range(self, mock_config, respx_mock):
        """start_date/end_date map to the API's r.<start>.<end> curve ID."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        route = respx_mock.get("/athlete/i123456/power-curves").mock(
            return_value=Response(
                200, json={"list": [_curve("r.2025-10-06.2026-09-30", "6-Oct-2025", 300)]}
            )
        )

        result = await get_power_curves(
            start_date="2025-10-06", end_date="2026-09-30", ctx=mock_ctx
        )

        assert route.calls[0].request.url.params["curves"] == "r.2025-10-06.2026-09-30"
        data = json.loads(result)["data"]
        assert data["period"] == "2025-10-06..2026-09-30"
        assert data["peak_efforts"]["20_min"]["watts"] == 300

    async def test_season_includes_label(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        route = respx_mock.get("/athlete/i123456/power-curves").mock(
            return_value=Response(200, json={"list": [_curve("s1", "Last season", 310)]})
        )

        result = await get_power_curves(season="S1", ctx=mock_ctx)

        assert route.calls[0].request.url.params["curves"] == "s1"
        data = json.loads(result)["data"]
        assert data["period"] == "season_s1"
        assert data["label"] == "Last season"

    async def test_periods_compare_in_one_call(self, mock_config, respx_mock):
        """periods returns one entry per curve and flags curves the API dropped."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        route = respx_mock.get("/athlete/i123456/power-curves").mock(
            return_value=Response(
                200,
                json={
                    "list": [
                        _curve("s0", "This season", 290),
                        _curve("all", "All time", 320),
                    ]
                },
            )
        )

        result = await get_power_curves(periods=["s0", "s9", "all"], ctx=mock_ctx)

        assert route.calls[0].request.url.params["curves"] == "s0,s9,all"
        response = json.loads(result)
        curves = response["data"]["curves"]
        assert [c["period"] for c in curves] == ["season_s0", "all_time"]
        assert curves[0]["label"] == "This season"
        assert curves[1]["ftp_analysis"]["estimated_ftp"] == 304
        assert response["metadata"]["missing_periods"] == ["s9"]

    async def test_mixed_windows_rejected(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await get_power_curves(days_back=30, season="s0", ctx=mock_ctx)

        assert json.loads(result)["error"]["type"] == "validation_error"

    async def test_invalid_inputs_rejected(self, mock_config, respx_mock):
        """Bad specs fail validation before any API call."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)
        route = respx_mock.get("/athlete/i123456/power-curves")

        cases = [
            {"periods": ["s0", "fortnight"]},
            {"periods": []},
            {"periods": ["s0", "s1", "s2", "s3", "s4", "s5"]},
            {"season": "last"},
            {"end_date": "2026-09-30"},
            {"start_date": "2026-10-01", "end_date": "2026-09-30"},
            {"start_date": "2026-13-01"},
        ]
        for kwargs in cases:
            result = await get_power_curves(ctx=mock_ctx, **kwargs)
            assert json.loads(result)["error"]["type"] == "validation_error", kwargs

        assert not route.called


class TestGetPowerCurvesExtras:
    async def test_long_durations_wkg_dates_and_models(self, mock_config, respx_mock):
        """Durations up to 6 h carry W/kg and the activity date; power models,
        VO2max, MAP and the period's weight are passed through."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/power-curves").mock(
            return_value=Response(
                200,
                json={
                    "list": [
                        {
                            "id": "all",
                            "secs": [5, 1200, 21600],
                            "values": [900, 300, 180],
                            "activity_id": ["a1", "a2", "a3"],
                            "watts_per_kg": [11.25, 3.8, 2.25],
                            "wkg_activity_id": ["a1", "a9", "a3"],
                            "weight": 79.625,
                            "powerModels": [
                                {
                                    "type": "MORTON_3P",
                                    "criticalPower": 286,
                                    "wPrime": 33823,
                                    "pMax": 1025,
                                    "ftp": 286,
                                    "inputPointIndexes": [1, 2],
                                }
                            ],
                            "vo2max_5m": 59.088,
                            "mapPlot": {"map": 4.4858, "mapSecs": 470, "mapWatts": 359},
                        }
                    ],
                    "activities": {
                        "a3": {"id": "a3", "start_date_local": "2021-10-17T08:00:00"},
                    },
                },
            )
        )

        result = await get_power_curves(time_period="all", ctx=mock_ctx)

        data = json.loads(result)["data"]
        six_hour = data["peak_efforts"]["6_hour"]
        assert six_hour == {
            "watts": 180,
            "duration_seconds": 21600,
            "activity_id": "a3",
            "date": "2021-10-17",
            "watts_per_kg": 2.25,
        }
        # Best W/kg from a different activity than the best watts is attributed.
        assert data["peak_efforts"]["20_min"]["watts_per_kg_activity_id"] == "a9"
        assert "watts_per_kg_activity_id" not in data["peak_efforts"]["5_sec"]
        assert data["summary"]["weight_kg"] == 79.6
        assert data["power_models"] == [
            {
                "type": "MORTON_3P",
                "critical_power": 286,
                "w_prime": 33823,
                "p_max": 1025,
                "ftp": 286,
            }
        ]
        assert data["vo2max_5m"] == 59.1
        assert data["map"] == {"watts": 359, "watts_per_kg": 4.49, "duration_seconds": 470}
        assert "curve" not in data

    async def test_fractional_model_values_do_not_break_response(self, mock_config, respx_mock):
        """Fractional model and MAP values are accepted; whole numbers stay whole."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/power-curves").mock(
            return_value=Response(
                200,
                json={
                    "list": [
                        {
                            "id": "all",
                            "secs": [5, 1200],
                            "values": [900, 300],
                            "activity_id": ["a1", "a2"],
                            "powerModels": [
                                {
                                    "type": "MORTON_3P",
                                    "criticalPower": 251.3,
                                    "wPrime": 20123.5,
                                    "pMax": 1025,
                                    "ftp": 286.75,
                                }
                            ],
                            "mapPlot": {"map": 4.4, "mapSecs": 470.5, "mapWatts": 359.25},
                        }
                    ],
                },
            )
        )

        result = await get_power_curves(time_period="all", ctx=mock_ctx)

        data = json.loads(result)["data"]
        assert data["power_models"] == [
            {
                "type": "MORTON_3P",
                "critical_power": 251.3,
                "w_prime": 20123.5,
                "p_max": 1025,
                "ftp": 286.75,
            }
        ]
        assert data["peak_efforts"]["5_sec"]["watts"] == 900

    async def test_missing_season_single_window_hints_at_seasons(self, mock_config, respx_mock):
        """A season the API drops points at icu_get_seasons, not at 'complete some rides'."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/power-curves").mock(
            return_value=Response(200, json={"list": []})
        )

        result = await get_power_curves(season="s9", ctx=mock_ctx)

        message = json.loads(result)["metadata"]["message"]
        assert "icu_get_seasons" in message
        assert "Complete some rides" not in message

    async def test_full_curve_and_zero_map_omitted(self, mock_config, respx_mock):
        """full_curve returns every point; a zero MAP (not fittable) is left out."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/power-curves").mock(
            return_value=Response(
                200,
                json={
                    "list": [
                        {
                            "secs": [1, 2, 3],
                            "values": [1000, 950, 900],
                            "mapPlot": {"map": 0.0, "mapSecs": 0, "mapWatts": 0},
                        }
                    ]
                },
            )
        )

        result = await get_power_curves(full_curve=True, ctx=mock_ctx)

        data = json.loads(result)["data"]
        assert data["curve"] == {"secs": [1, 2, 3], "watts": [1000, 950, 900]}
        assert "map" not in data
        assert "power_models" not in data
