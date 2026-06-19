"""Tests for Annual Training Plan (ATP) periodization tools."""

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from httpx import Response

from intervals_icu_mcp.tools.periodization import get_annual_training_plan


def _make_ctx(mock_config):
    ctx = MagicMock()
    ctx.get_state = AsyncMock(return_value=mock_config)
    return ctx


def _date_offset(days: int) -> str:
    return (datetime.now() + timedelta(days=days)).date().isoformat() + "T00:00:00"


ATP_FIXTURE = [
    {
        "id": 9001,
        "start_date_local": _date_offset(30),
        "end_date_local": _date_offset(60),
        "category": "PLAN",
        "name": "Race Plan",
        "description": "fase Base: aerobic capacity",
        "tags": ["Base"],
        "color": "#4CAF50",
        "type": "Ride",
    },
    {
        "id": 9002,
        "start_date_local": _date_offset(30),
        "end_date_local": _date_offset(36),
        "category": "TARGET",
        "name": "Weekly",
        "load_target": 320,
        "time_target": 36000,
        "distance_target": 85000,
        "type": "Ride",
    },
    {
        "id": 9003,
        "start_date_local": _date_offset(37),
        "end_date_local": _date_offset(43),
        "category": "TARGET",
        "name": "Weekly",
        "load_target": 280,
        "type": "Ride",
    },
    {
        "id": 9004,
        "start_date_local": _date_offset(37),
        "end_date_local": _date_offset(43),
        "category": "NOTE",
        "name": "Recovery week",
        "description": "Reduce volume 30%",
    },
    {
        "id": 9005,
        "start_date_local": _date_offset(10),
        "category": "WORKOUT",
        "name": "Sweet Spot",
        "icu_training_load": 85,
    },
]


class TestGetAnnualTrainingPlan:
    async def test_happy_path(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/events").mock(return_value=Response(200, json=ATP_FIXTURE))

        result = await get_annual_training_plan(days_ahead=90, ctx=_make_ctx(mock_config))
        response = json.loads(result)
        data = response["data"]

        assert len(data["phases"]) == 1
        assert data["phases"][0]["plan_name"] == "Race Plan"
        assert data["phases"][0]["phase"] == "Base"

        assert len(data["weeks"]) == 2
        week1 = data["weeks"][0]
        assert week1["load_target_tss"] == 320
        assert week1["time_target_seconds"] == 36000
        assert week1["distance_target_meters"] == 85000
        assert week1["plan_name"] == "Race Plan"
        assert week1["phase"] == "Base"
        assert week1.get("recovery_note") is None

        week2 = data["weeks"][1]
        assert week2["load_target_tss"] == 280
        assert week2["recovery_note"] == "Reduce volume 30%"
        assert week2["plan_name"] == "Race Plan"
        assert week2["phase"] == "Base"

        assert data["summary"]["phase_count"] == 1
        assert data["summary"]["plan_name"] == "Race Plan"
        assert data["summary"]["week_count"] == 2
        assert data["summary"]["recovery_week_count"] == 1
        assert data["summary"]["total_load_target_tss"] == 600

    async def test_empty(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/events").mock(return_value=Response(200, json=[]))

        result = await get_annual_training_plan(ctx=_make_ctx(mock_config))
        response = json.loads(result)
        data = response["data"]

        assert data["phases"] == []
        assert data["weeks"] == []
        assert data["summary"]["week_count"] == 0
        assert "No Annual Training Plan events found" in response["metadata"]["message"]

    async def test_workouts_excluded_from_atp_view(self, mock_config, respx_mock):
        """Only PLAN/TARGET/NOTE are returned; WORKOUT entries are ignored."""
        respx_mock.get("/athlete/i123456/events").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 1,
                        "start_date_local": _date_offset(1),
                        "category": "WORKOUT",
                        "name": "Ride",
                    }
                ],
            )
        )

        result = await get_annual_training_plan(ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["data"]["summary"]["week_count"] == 0
        assert "No Annual Training Plan events found" in response["metadata"]["message"]

    async def test_api_error(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/events").mock(return_value=Response(500, json={}))

        result = await get_annual_training_plan(ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["error"]["type"] == "api_error"

    async def test_athlete_id_override(self, mock_config, respx_mock):
        route = respx_mock.get("/athlete/i999999/events").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 1,
                        "start_date_local": _date_offset(1),
                        "end_date_local": _date_offset(7),
                        "category": "TARGET",
                        "load_target": 200,
                    }
                ],
            )
        )

        result = await get_annual_training_plan(athlete_id="i999999", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["data"]["weeks"][0]["load_target_tss"] == 200
        assert route.called
