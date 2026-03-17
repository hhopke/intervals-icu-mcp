"""Tests for athlete tools."""

from unittest.mock import AsyncMock, MagicMock

from httpx import Response

from intervals_icu_mcp.tools.athlete import get_athlete_profile, get_fitness_summary


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

    async def test_get_fitness_summary_success(
        self,
        mock_config,
        respx_mock,
        mock_athlete_data,
    ):
        """Test successful fitness summary retrieval."""
        # Create mock context with config
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        # Mock the API endpoint
        respx_mock.get("/athlete/i123456").mock(return_value=Response(200, json=mock_athlete_data))

        result = await get_fitness_summary(ctx=mock_ctx)

        # Check for JSON response with expected fields
        import json

        response = json.loads(result)
        assert "data" in response
        assert "fitness_metrics" in response["data"]
        assert "ctl" in response["data"]["fitness_metrics"]

    async def test_get_fitness_summary_with_high_ramp_rate(
        self,
        mock_config,
        respx_mock,
        mock_athlete_data,
    ):
        """Test fitness summary with high ramp rate warning."""
        # Create mock context with config
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        # Modify athlete data to have high ramp rate
        athlete_data = mock_athlete_data.copy()
        athlete_data["ramp_rate"] = 10.0

        respx_mock.get("/athlete/i123456").mock(return_value=Response(200, json=athlete_data))

        result = await get_fitness_summary(ctx=mock_ctx)

        # Check for JSON response with ramp rate analysis
        import json

        response = json.loads(result)
        assert "analysis" in response
        assert "ramp_rate_status" in response["analysis"]
        assert response["analysis"]["ramp_rate_status"] == "high_risk"
