"""Tests for athlete tools."""

import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import Response

from intervals_icu_mcp.tools.athlete import (
    get_athlete_profile,
    get_fitness_chart,
    get_fitness_summary,
)


class TestGetAthleteProfile:
    """Tests for get_athlete_profile tool."""

    async def test_get_athlete_profile_success(
        self,
        mock_config,
        respx_mock,
        mock_athlete_data,
    ):
        """Test successful athlete profile retrieval."""
        # Create mock context with config
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        # Mock the API endpoint
        respx_mock.get("/athlete/i123456").mock(return_value=Response(200, json=mock_athlete_data))

        result = await get_athlete_profile(ctx=mock_ctx)

        # Check for JSON response with expected fields
        import json

        response = json.loads(result)
        assert "data" in response
        assert "profile" in response["data"]
        assert response["data"]["profile"]["name"] == "Test Athlete"
        assert response["data"]["profile"]["id"] == "i123456"
        assert response["data"]["profile"]["email"] == "test@example.com"
        assert response["data"]["profile"]["weight_kg"] == 70.0


class TestGetFitnessSummary:
    """Tests for get_fitness_summary tool."""

    @patch("intervals_icu_mcp.tools.athlete.date")
    async def test_get_fitness_summary_success(
        self,
        mock_date,
        mock_config,
        respx_mock,
    ):
        """Test successful fitness summary retrieval via wellness endpoint."""
        mock_date.today.return_value = date(2026, 3, 17)
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        wellness_data = {
            "id": "2026-03-17",
            "ctl": 50.0,
            "atl": 35.0,
            "tsb": 15.0,
            "rampRate": 3.5,
        }
        respx_mock.get("/athlete/i123456/wellness/2026-03-17").mock(
            return_value=Response(200, json=wellness_data)
        )

        result = await get_fitness_summary(ctx=mock_ctx)

        import json

        response = json.loads(result)
        assert "data" in response
        assert "fitness_metrics" in response["data"]
        assert "ctl" in response["data"]["fitness_metrics"]
        assert response["data"]["fitness_metrics"]["ctl"]["value"] == 50.0

    @patch("intervals_icu_mcp.tools.athlete.date")
    async def test_get_fitness_summary_with_high_ramp_rate(
        self,
        mock_date,
        mock_config,
        respx_mock,
    ):
        """Test fitness summary with high ramp rate warning."""
        mock_date.today.return_value = date(2026, 3, 17)
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        wellness_data = {
            "id": "2026-03-17",
            "ctl": 50.0,
            "atl": 35.0,
            "tsb": 15.0,
            "rampRate": 10.0,
        }
        respx_mock.get("/athlete/i123456/wellness/2026-03-17").mock(
            return_value=Response(200, json=wellness_data)
        )

        result = await get_fitness_summary(ctx=mock_ctx)

        import json

        response = json.loads(result)
        assert "analysis" in response
        assert "ramp_rate_status" in response["analysis"]
        assert response["analysis"]["ramp_rate_status"] == "high_risk"


class TestGetFitnessChart:
    """Tests for get_fitness_chart tool."""

    @patch("intervals_icu_mcp.tools.athlete.date")
    async def test_get_fitness_chart_success(self, mock_date, mock_config, respx_mock):
        """Past and future records are tagged, sorted ascending, and summarized."""
        mock_date.today.return_value = date(2026, 3, 17)
        mock_date.fromisoformat.side_effect = date.fromisoformat
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/wellness").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": "2026-03-20",
                        "ctl": 55.0,
                        "atl": 60.0,
                        "ctlLoad": 80,
                        "atlLoad": 90,
                    },
                    {
                        "id": "2026-03-15",
                        "ctl": 48.0,
                        "atl": 42.0,
                        "rampRate": 2.5,
                    },
                    {
                        "id": "2026-03-17",
                        "ctl": 50.0,
                        "atl": 35.0,
                        "tsb": 15.0,
                    },
                ],
            )
        )

        result = await get_fitness_chart(days_back=7, days_ahead=3, ctx=mock_ctx)
        response = json.loads(result)

        assert response["data"]["count"] == 3
        series = response["data"]["series"]
        assert [point["date"] for point in series] == [
            "2026-03-15",
            "2026-03-17",
            "2026-03-20",
        ]
        assert series[0]["ctl"] == 48.0
        assert series[0]["tsb"] == 6.0  # computed from ctl - atl
        assert series[1]["is_projected"] is False
        assert series[2]["is_projected"] is True
        assert series[2]["tsb"] == -5.0
        assert response["data"]["summary"]["today"]["ctl"] == 50.0
        assert response["data"]["summary"]["end"]["ctl"] == 55.0
        assert "projections_note" in response["metadata"]

    @patch("intervals_icu_mcp.tools.athlete.date")
    async def test_get_fitness_chart_fields_param(self, mock_date, mock_config, respx_mock):
        """Fitness-only fields are requested from the wellness API."""
        mock_date.today.return_value = date(2026, 3, 17)
        mock_date.fromisoformat.side_effect = date.fromisoformat
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        route = respx_mock.get("/athlete/i123456/wellness").mock(
            return_value=Response(
                200,
                json=[{"id": "2026-03-17", "ctl": 50.0, "atl": 35.0}],
            )
        )

        await get_fitness_chart(days_back=7, days_ahead=0, ctx=mock_ctx)

        assert route.calls.last.request.url.params["fields"] == (
            "id,ctl,atl,rampRate,ctlLoad,atlLoad"
        )

    async def test_get_fitness_chart_negative_days(self, mock_config):
        """Negative windows are rejected before any HTTP call."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await get_fitness_chart(days_back=-1, days_ahead=7, ctx=mock_ctx)
        response = json.loads(result)

        assert response["error"]["type"] == "validation_error"

    async def test_get_fitness_chart_exceeds_cap(self, mock_config):
        """Total window over 365 days is rejected."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await get_fitness_chart(days_back=200, days_ahead=200, ctx=mock_ctx)
        response = json.loads(result)

        assert response["error"]["type"] == "validation_error"
        assert "365" in response["error"]["message"]

    @patch("intervals_icu_mcp.tools.athlete.date")
    async def test_get_fitness_chart_empty(self, mock_date, mock_config, respx_mock):
        """Empty API response returns count 0 without error."""
        mock_date.today.return_value = date(2026, 3, 17)
        mock_date.fromisoformat.side_effect = date.fromisoformat
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/wellness").mock(return_value=Response(200, json=[]))

        result = await get_fitness_chart(days_back=7, days_ahead=0, ctx=mock_ctx)
        response = json.loads(result)

        assert response["data"]["count"] == 0
        assert response["data"]["series"] == []
        assert "message" in response["metadata"]
