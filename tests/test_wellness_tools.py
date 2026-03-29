"""Tests for wellness tools."""

import json
from unittest.mock import AsyncMock, MagicMock

from httpx import Response

from intervals_icu_mcp.tools.wellness import update_wellness


class TestWellnessTools:
    """Tests for wellness tools."""

    async def test_update_wellness_success(self, mock_config, respx_mock):
        """Test successful wellness record update."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.put("/athlete/i123456/wellness").mock(
            return_value=Response(
                200,
                json={"id": "2026-03-17", "weight": 71.5, "restingHR": 45},
            )
        )

        result = await update_wellness(
            date="2026-03-17",
            weight=71.5,
            resting_hr=45,
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["date"] == "2026-03-17"
        assert response["data"]["body"]["weight_kg"] == 71.5
        assert response["data"]["heart"]["resting_hr"] == 45
        assert response["metadata"]["message"] == "Successfully updated wellness for 2026-03-17"

    async def test_update_wellness_validation_error(self, mock_config, respx_mock):
        """Test updating wellness with invalid date."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await update_wellness(
            date="invalid-date",
            weight=71.5,
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "error" in response
        assert "Invalid date format" in response["error"]["message"]

    async def test_update_wellness_no_data(self, mock_config, respx_mock):
        """Test updating wellness with no data fields."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await update_wellness(
            date="2026-03-17",
            ctx=mock_ctx,  # No other args provided
        )

        response = json.loads(result)
        assert "error" in response
        assert "No wellness data provided" in response["error"]["message"]
