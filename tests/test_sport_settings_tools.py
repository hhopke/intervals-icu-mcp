"""Tests for sport settings tools (FTP, FTHR, pace thresholds)."""

import json

import pytest
from httpx import Response

from intervals_icu_mcp.tools import sport_settings as sport_settings_tool
from intervals_icu_mcp.tools.sport_settings import (
    apply_sport_settings,
    create_sport_settings,
    delete_sport_settings,
    get_sport_settings,
    update_sport_settings,
)


@pytest.fixture
def patch_config(monkeypatch, mock_config):
    """sport_settings uses load_config() directly, so patch the module-level imports."""
    monkeypatch.setattr(sport_settings_tool, "load_config", lambda: mock_config)
    monkeypatch.setattr(sport_settings_tool, "validate_credentials", lambda _config: True)


class TestSportSettingsTools:
    """Tests for sport-specific settings tools."""

    async def test_get_sport_settings_success(self, patch_config, respx_mock):
        """Returns a list of sport settings with formatted pace/swim thresholds."""
        respx_mock.get("/athlete/i123456/sport-settings").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "type": "Ride", "ftp": 250, "fthr": 165},
                    {
                        "id": 2,
                        "type": "Run",
                        "fthr": 170,
                        "pace_threshold": 4.5,
                    },
                    {
                        "id": 3,
                        "type": "Swim",
                        "swim_threshold": 1.5,
                    },
                ],
            )
        )

        result = await get_sport_settings()

        response = json.loads(result)
        assert "data" in response
        settings = response["data"]["sport_settings"]
        assert len(settings) == 3
        assert settings[0]["ftp_watts"] == 250
        assert settings[0]["fthr_bpm"] == 165
        assert settings[1]["pace_threshold"] == "4:30 /km"
        assert settings[2]["swim_threshold"] == "1:30 /100m"
        assert response["metadata"]["count"] == 3

    async def test_get_sport_settings_empty(self, patch_config, respx_mock):
        """Empty result returns a friendly message with count=0."""
        respx_mock.get("/athlete/i123456/sport-settings").mock(return_value=Response(200, json=[]))

        result = await get_sport_settings()

        response = json.loads(result)
        assert response["data"]["message"] == "No sport settings found"
        assert response["metadata"]["count"] == 0

    async def test_get_sport_settings_api_error(self, patch_config, respx_mock):
        """API errors are surfaced via ResponseBuilder.build_error_response."""
        respx_mock.get("/athlete/i123456/sport-settings").mock(return_value=Response(401, json={}))

        result = await get_sport_settings()

        response = json.loads(result)
        assert "error" in response
        assert "Unauthorized" in response["error"]["message"]

    async def test_get_sport_settings_missing_credentials(self, monkeypatch, mock_config):
        """When validate_credentials returns False, no API call is made."""
        monkeypatch.setattr(sport_settings_tool, "load_config", lambda: mock_config)
        monkeypatch.setattr(sport_settings_tool, "validate_credentials", lambda _config: False)

        result = await get_sport_settings()

        assert "credentials not configured" in result

    async def test_update_sport_settings_success(self, patch_config, respx_mock):
        """Successful FTP update returns formatted settings."""
        respx_mock.put("/athlete/i123456/sport-settings/1").mock(
            return_value=Response(
                200,
                json={"id": 1, "type": "Ride", "ftp": 275, "fthr": 165},
            )
        )

        result = await update_sport_settings(sport_id=1, ftp=275)

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["ftp_watts"] == 275
        assert response["metadata"]["message"] == "Sport settings updated successfully"

    async def test_update_sport_settings_requires_a_field(self, patch_config):
        """Validation: update with no thresholds returns a validation error."""
        result = await update_sport_settings(sport_id=1)

        response = json.loads(result)
        assert "error" in response
        assert "No fields provided" in response["error"]["message"]

    async def test_update_sport_settings_api_error(self, patch_config, respx_mock):
        """404 from the API surfaces as an error response."""
        respx_mock.put("/athlete/i123456/sport-settings/999").mock(
            return_value=Response(404, json={})
        )

        result = await update_sport_settings(sport_id=999, ftp=300)

        response = json.loads(result)
        assert "error" in response
        assert "Resource not found" in response["error"]["message"]

    async def test_apply_sport_settings_success(self, patch_config, respx_mock):
        """Apply settings returns the API payload verbatim with metadata."""
        respx_mock.post("/athlete/i123456/sport-settings/1/apply").mock(
            return_value=Response(200, json={"applied": 42})
        )

        result = await apply_sport_settings(sport_id=1, oldest_date="2026-01-01")

        response = json.loads(result)
        assert response["data"]["applied"] == 42
        assert response["metadata"]["message"] == (
            "Sport settings applied to activities successfully"
        )

    async def test_create_sport_settings_success(self, patch_config, respx_mock):
        """Successfully creating a new Run settings object."""
        respx_mock.post("/athlete/i123456/sport-settings").mock(
            return_value=Response(
                200,
                json={
                    "id": 7,
                    "type": "Run",
                    "fthr": 170,
                    "pace_threshold": 4.5,
                },
            )
        )

        result = await create_sport_settings(
            sport_type="Run",
            fthr=170,
            pace_threshold=4.5,
        )

        response = json.loads(result)
        assert response["data"]["id"] == 7
        assert response["data"]["type"] == "Run"
        assert response["data"]["pace_threshold"] == "4:30 /km"
        assert response["metadata"]["message"] == "Sport settings created successfully"

    async def test_delete_sport_settings_success(self, patch_config, respx_mock):
        """Delete returns a confirmation payload."""
        respx_mock.delete("/athlete/i123456/sport-settings/7").mock(
            return_value=Response(200, json={})
        )

        result = await delete_sport_settings(sport_id=7)

        response = json.loads(result)
        assert response["data"]["sport_id"] == 7
        assert response["data"]["deleted"] is True
        assert response["metadata"]["message"] == "Sport settings deleted successfully"

    async def test_delete_sport_settings_api_error(self, patch_config, respx_mock):
        """404 on delete surfaces as an error response."""
        respx_mock.delete("/athlete/i123456/sport-settings/9999").mock(
            return_value=Response(404, json={})
        )

        result = await delete_sport_settings(sport_id=9999)

        response = json.loads(result)
        assert "error" in response
        assert "Resource not found" in response["error"]["message"]
