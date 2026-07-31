"""Tests for gear management tools (bikes, shoes, maintenance reminders)."""

import json

import pytest
from httpx import Response

from intervals_icu_mcp.tools import gear as gear_tool
from intervals_icu_mcp.tools.gear import (
    create_gear,
    create_gear_reminder,
    delete_gear,
    get_gear_list,
    update_gear,
    update_gear_reminder,
)


@pytest.fixture
def patch_config(monkeypatch, mock_config):
    """gear uses load_config() directly, so patch the module-level imports."""
    monkeypatch.setattr(gear_tool, "load_config", lambda: mock_config)
    monkeypatch.setattr(gear_tool, "validate_credentials", lambda _config: True)


class TestGetGearList:
    async def test_success_with_full_data(self, patch_config, respx_mock):
        """Returns gear with usage stats and maintenance reminders."""
        respx_mock.get("/athlete/i123456/gear").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": "g1",
                        "name": "Road Bike",
                        "type": "Bike",
                        "purchased": "2024-05-01",
                        "notes": "Specialized Tarmac",
                        "distance": 12500000.0,  # 12,500 km in meters
                        "time": 360000.0,  # 100h
                        "activities": 142,
                        "reminders": [
                            {
                                "id": 101,
                                "name": "Replace chain",
                                "distance": 5000000.0,  # every 5000 km
                                "time": 0.0,
                                "distance_used": 4750000.0,  # 4750 km since reset
                                "percent_used": 95.0,
                            },
                            {
                                "id": 102,
                                "name": "Service",
                                "distance": 0.0,
                                "time": 360000.0,  # every 100h
                                "time_used": 356400.0,  # 99h since reset
                                "percent_used": 99.0,
                                "snoozed_until": "2026-06-01",
                            },
                        ],
                    },
                    {
                        "id": "g2",
                        "name": "Trail Shoes",
                        "type": "Shoes",
                        "retired": "2026-05-01",
                    },
                ],
            )
        )

        result = await get_gear_list()

        response = json.loads(result)
        gear = response["data"]["gear"]
        assert len(gear) == 2
        bike = gear[0]
        assert bike["name"] == "Road Bike"
        assert bike["type"] == "Bike"
        assert bike["active"] is True
        assert bike["purchased_on"] == "2024-05-01"
        assert bike["notes"] == "Specialized Tarmac"
        assert bike["usage"]["total_distance_km"] == 12500.0
        assert bike["usage"]["total_time"] == "100h 0m"
        assert bike["usage"]["activity_count"] == 142
        # retired gear derives active=False and shows the retirement date
        shoes = gear[1]
        assert shoes["active"] is False
        assert shoes["retired_on"] == "2026-05-01"
        assert len(bike["reminders"]) == 2
        chain = bike["reminders"][0]
        assert chain["text"] == "Replace chain"
        assert chain["alert_every_km"] == 5000.0
        assert chain["used_km"] == 4750.0
        assert chain["percent_used"] == 95.0
        service = bike["reminders"][1]
        assert service["alert_every_hours"] == 100
        assert service["used_hours"] == 99.0
        assert service["snoozed_until"] == "2026-06-01"
        # zero thresholds (API's "unused") are omitted, not shown as 0
        assert "alert_every_hours" not in chain
        assert "alert_every_km" not in service
        # Minimal gear has no usage block
        assert "usage" not in gear[1]
        assert response["metadata"]["count"] == 2

    async def test_empty_list(self, patch_config, respx_mock):
        respx_mock.get("/athlete/i123456/gear").mock(return_value=Response(200, json=[]))

        result = await get_gear_list()

        response = json.loads(result)
        assert response["data"]["message"] == "No gear items found"
        assert response["metadata"]["count"] == 0

    async def test_missing_credentials(self, monkeypatch, mock_config):
        monkeypatch.setattr(gear_tool, "load_config", lambda: mock_config)
        monkeypatch.setattr(gear_tool, "validate_credentials", lambda _config: False)

        result = await get_gear_list()

        assert "credentials not configured" in result

    async def test_api_error(self, patch_config, respx_mock):
        respx_mock.get("/athlete/i123456/gear").mock(return_value=Response(401, json={}))

        result = await get_gear_list()

        response = json.loads(result)
        assert "error" in response
        assert response["error"]["type"] == "api_error"


class TestCreateGear:
    async def test_success_maps_type_and_warns_on_unsupported(self, patch_config, respx_mock):
        """gear_type maps to the API's CamelCase `type` enum (regression for
        #110 — `gear_type`/`brand`/`model`/`primary` are not API fields);
        unsupported params are reported as ignored, not silently dropped."""
        route = respx_mock.post("/athlete/i123456/gear").mock(
            return_value=Response(
                200,
                json={"id": "g99", "name": "New Bike", "type": "Bike"},
            )
        )

        result = await create_gear(
            name="New Bike", gear_type="BIKE", brand="Trek", model="Madone", primary=True
        )

        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body == {"name": "New Bike", "type": "Bike"}
        response = json.loads(result)
        data = response["data"]
        assert data["id"] == "g99"
        assert data["type"] == "Bike"
        assert data["active"] is True
        assert "brand" not in data and "primary" not in data
        warning = response["metadata"]["warning"]
        assert "brand" in warning and "model" in warning and "primary" in warning
        assert response["metadata"]["type"] == "gear_created"

    async def test_success_minimal_fields_no_warning(self, patch_config, respx_mock):
        """SHOE alias maps to Shoes; no warning when no unsupported params given."""
        route = respx_mock.post("/athlete/i123456/gear").mock(
            return_value=Response(
                200,
                json={"id": "g100", "name": "Trail Shoes", "type": "Shoes"},
            )
        )

        result = await create_gear(name="Trail Shoes", gear_type="SHOE")

        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body == {"name": "Trail Shoes", "type": "Shoes"}
        response = json.loads(result)
        assert response["data"]["type"] == "Shoes"
        assert "warning" not in response["metadata"]

    async def test_create_inactive_sets_retired_date(self, patch_config, respx_mock):
        route = respx_mock.post("/athlete/i123456/gear").mock(
            return_value=Response(
                200,
                json={"id": "g101", "name": "Old Bike", "type": "Bike", "retired": "2026-07-31"},
            )
        )

        result = await create_gear(name="Old Bike", gear_type="Bike", active=False)

        sent_body = json.loads(route.calls[0].request.content)
        assert "retired" in sent_body
        response = json.loads(result)
        assert response["data"]["active"] is False

    async def test_invalid_gear_type_rejected(self, patch_config, respx_mock):
        route = respx_mock.post("/athlete/i123456/gear").mock(return_value=Response(200, json={}))

        result = await create_gear(name="X", gear_type="OTHER")

        response = json.loads(result)
        assert response["error"]["type"] == "validation_error"
        assert "Bike" in response["error"]["message"]
        assert not route.called

    async def test_missing_credentials(self, monkeypatch, mock_config):
        monkeypatch.setattr(gear_tool, "load_config", lambda: mock_config)
        monkeypatch.setattr(gear_tool, "validate_credentials", lambda _config: False)

        result = await create_gear(name="X", gear_type="BIKE")

        assert "credentials not configured" in result


class TestUpdateGear:
    async def test_success_partial_update(self, patch_config, respx_mock):
        """Only mapped fields hit the wire; active=False becomes a retired date."""
        route = respx_mock.put("/athlete/i123456/gear/g1").mock(
            return_value=Response(
                200,
                json={
                    "id": "g1",
                    "name": "Renamed Bike",
                    "type": "Bike",
                    "retired": "2026-07-31",
                    "distance": 12500000.0,
                    "time": 360000.0,
                    "activities": 142,
                },
            )
        )

        result = await update_gear(gear_id="g1", name="Renamed Bike", active=False)

        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["name"] == "Renamed Bike"
        assert "retired" in sent_body and sent_body["retired"] is not None
        assert "active" not in sent_body

        response = json.loads(result)
        data = response["data"]
        assert data["name"] == "Renamed Bike"
        assert data["active"] is False
        assert data["retired_on"] == "2026-07-31"
        assert data["usage"]["total_distance_km"] == 12500.0
        assert data["usage"]["total_time"] == "100h 0m"
        assert data["usage"]["activity_count"] == 142

    async def test_unretire_sends_empty_string(self, patch_config, respx_mock):
        """active=True clears `retired` via empty string — the API ignores
        null (live-verified), so sending None would silently no-op."""
        route = respx_mock.put("/athlete/i123456/gear/g1").mock(
            return_value=Response(200, json={"id": "g1", "name": "Bike", "type": "Bike"})
        )

        result = await update_gear(gear_id="g1", active=True)

        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body == {"retired": ""}
        response = json.loads(result)
        assert response["data"]["active"] is True

    async def test_no_fields_validation_error(self, patch_config):
        result = await update_gear(gear_id="g1")

        response = json.loads(result)
        assert response["error"]["type"] == "validation_error"
        assert "No fields provided" in response["error"]["message"]

    async def test_missing_credentials(self, monkeypatch, mock_config):
        monkeypatch.setattr(gear_tool, "load_config", lambda: mock_config)
        monkeypatch.setattr(gear_tool, "validate_credentials", lambda _config: False)

        result = await update_gear(gear_id="g1", name="X")

        assert "credentials not configured" in result


class TestDeleteGear:
    async def test_success(self, patch_config, respx_mock):
        respx_mock.delete("/athlete/i123456/gear/g1").mock(return_value=Response(200, json={}))

        result = await delete_gear(gear_id="g1")

        response = json.loads(result)
        assert response["data"]["deleted"] is True
        assert response["data"]["gear_id"] == "g1"

    async def test_api_error(self, patch_config, respx_mock):
        respx_mock.delete("/athlete/i123456/gear/g1").mock(return_value=Response(404, json={}))

        result = await delete_gear(gear_id="g1")

        response = json.loads(result)
        assert response["error"]["type"] == "api_error"


class TestCreateGearReminder:
    async def test_success_with_distance_alert(self, patch_config, respx_mock):
        """POSTs the singular /reminder path with API field names (regression
        for #107 — the plural path 404s and `text`/`distance_alert` 422).
        Distance is converted km → meters on send and back to km on response;
        the API responds with the full gear object, not the reminder."""
        route = respx_mock.post("/athlete/i123456/gear/g1/reminder").mock(
            return_value=Response(
                200,
                json={
                    "id": "g1",
                    "name": "Road Bike",
                    "reminders": [
                        {"id": 199, "name": "Replace chain", "distance": 1000000.0},
                        {"id": 200, "name": "Replace chain", "distance": 5000000.0, "time": 0.0},
                    ],
                },
            )
        )

        result = await create_gear_reminder(
            gear_id="g1", text="Replace chain", distance_alert=5000.0
        )

        sent = json.loads(route.calls[0].request.content)
        assert sent == {"name": "Replace chain", "distance": 5000000}
        response = json.loads(result)
        # newest matching reminder (id 200) is reported, not the older duplicate
        assert response["data"]["id"] == 200
        assert response["data"]["alert_every_km"] == 5000.0

    async def test_success_with_time_alert(self, patch_config, respx_mock):
        """Time is converted hours → seconds on send and back to hours on response."""
        route = respx_mock.post("/athlete/i123456/gear/g1/reminder").mock(
            return_value=Response(
                200,
                json={
                    "id": "g1",
                    "reminders": [{"id": 201, "name": "Service", "time": 360000.0}],
                },
            )
        )

        result = await create_gear_reminder(gear_id="g1", text="Service", time_alert=100)

        sent = json.loads(route.calls[0].request.content)
        assert sent == {"name": "Service", "time": 360000}
        response = json.loads(result)
        assert response["data"]["id"] == 201
        assert response["data"]["alert_every_hours"] == 100

    async def test_no_alert_validation_error(self, patch_config):
        result = await create_gear_reminder(gear_id="g1", text="Need a service")

        response = json.loads(result)
        assert response["error"]["type"] == "validation_error"
        assert "at least one alert threshold" in response["error"]["message"]


class TestUpdateGearReminder:
    async def test_success_partial_update(self, patch_config, respx_mock):
        """PUTs the singular /reminder/{id} path; the response gear's matching
        reminder is reported back."""
        route = respx_mock.put("/athlete/i123456/gear/g1/reminder/200").mock(
            return_value=Response(
                200,
                json={
                    "id": "g1",
                    "reminders": [
                        {"id": 199, "name": "Other", "distance": 1000000.0},
                        {
                            "id": 200,
                            "name": "New text",
                            "distance": 3000000.0,
                            "percent_used": 42.5,
                        },
                    ],
                },
            )
        )

        result = await update_gear_reminder(
            gear_id="g1", reminder_id=200, text="New text", distance_alert=3000.0
        )

        sent = json.loads(route.calls[0].request.content)
        assert sent == {"name": "New text", "distance": 3000000}
        response = json.loads(result)
        data = response["data"]
        assert data["id"] == 200
        assert data["text"] == "New text"
        assert data["alert_every_km"] == 3000.0
        assert data["percent_used"] == 42.5

    async def test_no_fields_validation_error(self, patch_config):
        result = await update_gear_reminder(gear_id="g1", reminder_id=200)

        response = json.loads(result)
        assert response["error"]["type"] == "validation_error"
