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
                        "brand": "Specialized",
                        "model": "Tarmac",
                        "gear_type": "BIKE",
                        "active": True,
                        "distance": 12500000.0,  # 12,500 km in meters
                        "moving_time": 360000,  # 100h
                        "activity_count": 142,
                        "reminders": [
                            {
                                "id": 101,
                                "text": "Replace chain",
                                "distance_alert": 5000000.0,  # 5000 km
                                "due_distance": 250000.0,  # 250 km
                                "is_due": False,
                            },
                            {
                                "id": 102,
                                "text": "Service",
                                "time_alert": 360000,  # 100h
                                "due_time": 3600,  # 1h
                                "is_due": True,
                                "snoozed_until": "2026-06-01",
                            },
                        ],
                    },
                    {
                        "id": "g2",
                        "name": "Trail Shoes",
                        "gear_type": "SHOE",
                        "active": True,
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
        assert bike["brand"] == "Specialized"
        assert bike["usage"]["total_distance_km"] == 12500.0
        assert bike["usage"]["total_time"] == "100h 0m"
        assert bike["usage"]["activity_count"] == 142
        assert len(bike["reminders"]) == 2
        chain = bike["reminders"][0]
        assert chain["alert_every_km"] == 5000.0
        assert chain["due_in_km"] == 250.0
        assert chain["is_due"] is False
        service = bike["reminders"][1]
        assert service["alert_every_hours"] == 100
        assert service["due_in_hours"] == 1
        assert service["snoozed_until"] == "2026-06-01"
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
    async def test_success_with_all_fields(self, patch_config, respx_mock):
        respx_mock.post("/athlete/i123456/gear").mock(
            return_value=Response(
                200,
                json={
                    "id": "g99",
                    "name": "New Bike",
                    "brand": "Trek",
                    "model": "Madone",
                    "gear_type": "BIKE",
                    "active": True,
                    "primary": True,
                },
            )
        )

        result = await create_gear(
            name="New Bike", gear_type="BIKE", brand="Trek", model="Madone", primary=True
        )

        response = json.loads(result)
        data = response["data"]
        assert data["id"] == "g99"
        assert data["brand"] == "Trek"
        assert data["primary"] is True
        assert response["metadata"]["type"] == "gear_created"

    async def test_success_minimal_fields(self, patch_config, respx_mock):
        """Optional brand/model are omitted from the request and response when not provided."""
        respx_mock.post("/athlete/i123456/gear").mock(
            return_value=Response(
                200,
                json={"id": "g100", "name": "Trainer", "gear_type": "TRAINER", "active": True},
            )
        )

        result = await create_gear(name="Trainer", gear_type="TRAINER")

        response = json.loads(result)
        data = response["data"]
        assert data["name"] == "Trainer"
        assert "brand" not in data
        assert "model" not in data

    async def test_missing_credentials(self, monkeypatch, mock_config):
        monkeypatch.setattr(gear_tool, "load_config", lambda: mock_config)
        monkeypatch.setattr(gear_tool, "validate_credentials", lambda _config: False)

        result = await create_gear(name="X", gear_type="BIKE")

        assert "credentials not configured" in result


class TestUpdateGear:
    async def test_success_partial_update(self, patch_config, respx_mock):
        """Only non-None fields are sent; usage block returned when distance is set."""
        route = respx_mock.put("/athlete/i123456/gear/g1").mock(
            return_value=Response(
                200,
                json={
                    "id": "g1",
                    "name": "Renamed Bike",
                    "gear_type": "BIKE",
                    "active": False,
                    "primary": False,
                    "distance": 12500000.0,
                    "moving_time": 360000,
                    "activity_count": 142,
                },
            )
        )

        result = await update_gear(gear_id="g1", name="Renamed Bike", active=False)

        # Confirm only the two passed fields hit the wire
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body == {"name": "Renamed Bike", "active": False}

        response = json.loads(result)
        data = response["data"]
        assert data["name"] == "Renamed Bike"
        assert data["usage"]["total_distance_km"] == 12500.0
        assert data["usage"]["activity_count"] == 142

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
        """Distance is converted km → meters on send and back to km on response."""
        route = respx_mock.post("/athlete/i123456/gear/g1/reminders").mock(
            return_value=Response(
                200,
                json={"id": 200, "text": "Replace chain", "distance_alert": 5000000.0},
            )
        )

        result = await create_gear_reminder(
            gear_id="g1", text="Replace chain", distance_alert=5000.0
        )

        sent = json.loads(route.calls[0].request.content)
        assert sent == {"text": "Replace chain", "distance_alert": 5000000}
        response = json.loads(result)
        assert response["data"]["alert_every_km"] == 5000.0

    async def test_success_with_time_alert(self, patch_config, respx_mock):
        """Time is converted hours → seconds on send and back to hours on response."""
        route = respx_mock.post("/athlete/i123456/gear/g1/reminders").mock(
            return_value=Response(
                200,
                json={"id": 201, "text": "Service", "time_alert": 360000},
            )
        )

        result = await create_gear_reminder(gear_id="g1", text="Service", time_alert=100)

        sent = json.loads(route.calls[0].request.content)
        assert sent == {"text": "Service", "time_alert": 360000}
        response = json.loads(result)
        assert response["data"]["alert_every_hours"] == 100

    async def test_no_alert_validation_error(self, patch_config):
        result = await create_gear_reminder(gear_id="g1", text="Need a service")

        response = json.loads(result)
        assert response["error"]["type"] == "validation_error"
        assert "at least one alert threshold" in response["error"]["message"]


class TestUpdateGearReminder:
    async def test_success_partial_update(self, patch_config, respx_mock):
        route = respx_mock.put("/athlete/i123456/gear/g1/reminders/200").mock(
            return_value=Response(
                200,
                json={
                    "id": 200,
                    "text": "New text",
                    "distance_alert": 3000000.0,
                    "due_distance": 100000.0,
                    "is_due": True,
                },
            )
        )

        result = await update_gear_reminder(
            gear_id="g1", reminder_id=200, text="New text", distance_alert=3000.0
        )

        sent = json.loads(route.calls[0].request.content)
        assert sent == {"text": "New text", "distance_alert": 3000000}
        response = json.loads(result)
        data = response["data"]
        assert data["text"] == "New text"
        assert data["alert_every_km"] == 3000.0
        assert data["due_in_km"] == 100.0
        assert data["is_due"] is True

    async def test_no_fields_validation_error(self, patch_config):
        result = await update_gear_reminder(gear_id="g1", reminder_id=200)

        response = json.loads(result)
        assert response["error"]["type"] == "validation_error"
