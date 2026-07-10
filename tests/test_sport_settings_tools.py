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

RIDE_SETTINGS = {
    "id": 1,
    "types": ["Ride", "VirtualRide"],
    "ftp": 250,
    "indoor_ftp": 235,
    "lthr": 165,
}
RUN_SETTINGS = {
    "id": 2,
    "types": ["Run"],
    "lthr": 170,
    "threshold_pace": 4.5,
    "pace_units": "MINS_KM",
    "pace_load_type": "RUN",
}
SWIM_SETTINGS = {
    "id": 3,
    "types": ["Swim"],
    "threshold_pace": 90,
    "pace_units": "SECS_100M",
    "pace_load_type": "SWIM",
}


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
            return_value=Response(200, json=[RIDE_SETTINGS, RUN_SETTINGS, SWIM_SETTINGS])
        )

        result = await get_sport_settings()

        response = json.loads(result)
        assert "data" in response
        settings = response["data"]["sport_settings"]
        assert len(settings) == 3
        assert settings[0]["type"] == "Ride"
        assert settings[0]["ftp_watts"] == 250
        assert settings[0]["indoor_ftp_watts"] == 235
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
        """Successful outdoor and indoor FTP update returns formatted settings."""
        route = respx_mock.put("/athlete/i123456/sport-settings/1").mock(
            return_value=Response(
                200,
                json={
                    "id": 1,
                    "types": ["Ride"],
                    "ftp": 275,
                    "indoor_ftp": 265,
                    "lthr": 165,
                },
            )
        )

        result = await update_sport_settings(sport_id=1, ftp=275, indoor_ftp=265)

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["ftp_watts"] == 275
        assert response["data"]["indoor_ftp_watts"] == 265
        assert json.loads(route.calls.last.request.content) == {
            "ftp": 275,
            "indoor_ftp": 265,
        }
        assert route.calls.last.request.url.params["recalcHrZones"] == "true"
        assert response["metadata"]["message"] == "Sport settings updated successfully"

    async def test_update_sport_settings_sends_lthr(self, patch_config, respx_mock):
        """FTHR updates are sent to the API as lthr."""
        route = respx_mock.put("/athlete/i123456/sport-settings/2").mock(
            return_value=Response(
                200,
                json={
                    "id": 2,
                    "types": ["Run"],
                    "lthr": 172,
                    "threshold_pace": 4.5,
                    "pace_units": "MINS_KM",
                    "pace_load_type": "RUN",
                },
            )
        )

        result = await update_sport_settings(sport_id=2, fthr=172, pace_threshold=4.5)

        response = json.loads(result)
        assert response["data"]["fthr_bpm"] == 172
        assert json.loads(route.calls.last.request.content) == {
            "lthr": 172,
            "threshold_pace": 4.5,
            "pace_units": "MINS_KM",
            "pace_load_type": "RUN",
        }

    async def test_update_sport_settings_requires_a_field(self, patch_config):
        """Validation: update with no thresholds returns a validation error."""
        result = await update_sport_settings(sport_id=1)

        response = json.loads(result)
        assert "error" in response
        assert "No fields provided" in response["error"]["message"]

    async def test_update_sport_settings_rejects_both_pace_params(self, patch_config, respx_mock):
        """Validation: pace_threshold and swim_threshold cannot be set in the same call."""
        route = respx_mock.put("/athlete/i123456/sport-settings/2").mock(
            return_value=Response(200, json={"id": 2, "types": ["Run"]})
        )

        result = await update_sport_settings(sport_id=2, pace_threshold=4.5, swim_threshold=1.5)

        response = json.loads(result)
        assert "error" in response
        assert response["error"]["type"] == "validation_error"
        assert "pace_threshold" in response["error"]["message"]
        assert "swim_threshold" in response["error"]["message"]
        assert not route.called

    async def test_update_sport_settings_api_error(self, patch_config, respx_mock):
        """404 from the API surfaces as an error response."""
        respx_mock.put("/athlete/i123456/sport-settings/999").mock(
            return_value=Response(404, json={})
        )

        result = await update_sport_settings(sport_id=999, ftp=300)

        response = json.loads(result)
        assert "error" in response
        assert "Resource not found" in response["error"]["message"]

    async def test_update_sport_settings_recalc_hr_zones_false(self, patch_config, respx_mock):
        """recalc_hr_zones=false is forwarded as recalcHrZones query param."""
        route = respx_mock.put("/athlete/i123456/sport-settings/2").mock(
            return_value=Response(200, json={"id": 2, "types": ["Run"], "lthr": 170})
        )

        await update_sport_settings(sport_id=2, fthr=170, recalc_hr_zones=False)

        assert route.calls.last.request.url.params["recalcHrZones"] == "false"

    async def test_apply_sport_settings_success(self, patch_config, respx_mock):
        """Apply settings uses PUT and returns the API payload with metadata."""
        respx_mock.put("/athlete/i123456/sport-settings/1/apply").mock(
            return_value=Response(200, json={"applied": 42})
        )

        result = await apply_sport_settings(sport_id=1)

        response = json.loads(result)
        assert response["data"]["applied"] == 42
        assert response["metadata"]["message"] == (
            "Sport settings applied to activities successfully"
        )

    async def test_create_sport_settings_success(self, patch_config, respx_mock):
        """Successfully creating a new Run settings object."""
        route = respx_mock.post("/athlete/i123456/sport-settings").mock(
            return_value=Response(
                200,
                json={
                    "id": 7,
                    "types": ["Run"],
                    "lthr": 170,
                    "threshold_pace": 4.5,
                    "pace_units": "MINS_KM",
                    "pace_load_type": "RUN",
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
        assert json.loads(route.calls.last.request.content) == {
            "types": ["Run"],
            "lthr": 170,
            "threshold_pace": 4.5,
            "pace_units": "MINS_KM",
            "pace_load_type": "RUN",
        }
        assert response["metadata"]["message"] == "Sport settings created successfully"

    async def test_create_sport_settings_rejects_both_pace_params(self, patch_config, respx_mock):
        """Validation: pace_threshold and swim_threshold cannot be set in the same call."""
        route = respx_mock.post("/athlete/i123456/sport-settings").mock(
            return_value=Response(200, json={"id": 7, "types": ["Run"]})
        )

        result = await create_sport_settings(
            sport_type="Run",
            pace_threshold=4.5,
            swim_threshold=1.5,
        )

        response = json.loads(result)
        assert "error" in response
        assert response["error"]["type"] == "validation_error"
        assert "pace_threshold" in response["error"]["message"]
        assert "swim_threshold" in response["error"]["message"]
        assert not route.called

    async def test_create_sport_settings_with_indoor_ftp(self, patch_config, respx_mock):
        """Indoor FTP is sent to the API and returned in the created settings."""
        route = respx_mock.post("/athlete/i123456/sport-settings").mock(
            return_value=Response(
                200,
                json={"id": 8, "types": ["Ride"], "ftp": 275, "indoor_ftp": 265},
            )
        )

        result = await create_sport_settings(sport_type="Ride", ftp=275, indoor_ftp=265)

        response = json.loads(result)
        assert response["data"]["indoor_ftp_watts"] == 265
        assert json.loads(route.calls.last.request.content) == {
            "types": ["Ride"],
            "ftp": 275,
            "indoor_ftp": 265,
        }

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
