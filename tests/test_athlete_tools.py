"""Tests for athlete tools."""

import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import Response

from intervals_icu_mcp.tools.athlete import (
    get_athlete_profile,
    get_fitness_chart,
    get_fitness_summary,
    list_athletes,
)


def _ctx(config):
    ctx = MagicMock()
    ctx.get_state = AsyncMock(return_value=config)
    return ctx


class TestListAthletes:
    """Tests for the icu_list_athletes discovery tool."""

    ROSTER = [
        {"id": "i999888", "name": "Coached", "icu_permission": "WRITE", "icu_coach": True},
        {"id": "i777666", "name": "Followed", "icu_permission": "READ", "icu_coach": False},
        {"id": "i123456", "name": "Me", "icu_permission": None, "icu_coach": False},
    ]

    async def test_projects_roster_with_access_levels(self, mock_config, respx_mock):
        """Maps icu_permission/icu_coach onto access labels and a can_write flag."""
        respx_mock.get("/athletes").mock(return_value=Response(200, json=self.ROSTER))

        response = json.loads(await list_athletes(ctx=_ctx(mock_config)))
        data = response["data"]

        assert data["count"] == 3
        assert data["default_athlete_id"] == "i123456"
        by_id = {a["athlete_id"]: a for a in data["athletes"]}
        assert (by_id["i999888"]["access"], by_id["i999888"]["can_write"]) == ("coach", True)
        assert (by_id["i777666"]["access"], by_id["i777666"]["can_write"]) == ("follower", False)
        assert (by_id["i123456"]["access"], by_id["i123456"]["can_write"]) == ("self", True)

    async def test_default_athlete_sorts_first(self, mock_config, respx_mock):
        """The caller's own account must not be buried in a long roster."""
        respx_mock.get("/athletes").mock(return_value=Response(200, json=self.ROSTER))

        response = json.loads(await list_athletes(ctx=_ctx(mock_config)))
        athletes = response["data"]["athletes"]

        assert athletes[0]["athlete_id"] == "i123456"
        assert athletes[0]["is_default"] is True
        # Remaining entries alphabetical
        assert [a["name"] for a in athletes[1:]] == ["Coached", "Followed"]

    async def test_projection_drops_the_bulk_of_the_payload(self, mock_config, respx_mock):
        """The API returns ~160 fields per athlete; only the useful ones survive."""
        fat = {**self.ROSTER[1], "city": "Zurich", "bikes": [{"id": "b1"}], "email": "x@y.z"}
        respx_mock.get("/athletes").mock(return_value=Response(200, json=[fat]))

        response = json.loads(await list_athletes(ctx=_ctx(mock_config)))
        entry = response["data"]["athletes"][0]

        assert set(entry) == {"athlete_id", "name", "access", "can_write"}

    async def test_empty_roster(self, mock_config, respx_mock):
        respx_mock.get("/athletes").mock(return_value=Response(200, json=[]))

        response = json.loads(await list_athletes(ctx=_ctx(mock_config)))

        assert response["data"]["count"] == 0
        assert "message" in response["metadata"]

    async def test_tolerates_wrapped_payload(self, mock_config, respx_mock):
        """Documented as a bare array; an envelope must not crash the tool."""
        respx_mock.get("/athletes").mock(return_value=Response(200, json={"athletes": self.ROSTER}))

        response = json.loads(await list_athletes(ctx=_ctx(mock_config)))

        assert response["data"]["count"] == 3

    async def test_api_error_suggests_the_actual_causes(self, mock_config, respx_mock):
        respx_mock.get("/athletes").mock(return_value=Response(403, json={"error": "denied"}))

        response = json.loads(await list_athletes(ctx=_ctx(mock_config)))

        assert response["error"]["type"] == "api_error"
        assert any("API key" in s for s in response["error"]["suggestions"])


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
