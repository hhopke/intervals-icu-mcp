"""Tests for activity tools."""

import json
from unittest.mock import AsyncMock, MagicMock

from httpx import Response

from intervals_icu_mcp.tools.activities import (
    bulk_create_manual_activities,
    delete_activity,
    get_activity_details,
    update_activity,
    update_activity_streams,
)


class TestActivityTools:
    """Tests for activity tools."""

    async def test_update_activity_success(self, mock_config, respx_mock):
        """Test successful activity update."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.put("/activity/a123").mock(
            return_value=Response(
                200,
                json={
                    "id": "a123",
                    "start_date_local": "2026-03-20T10:00:00",
                    "name": "Updated Ride",
                    "type": "Ride",
                    "icu_training_load": 100,
                },
            )
        )

        result = await update_activity(
            activity_id="a123",
            name="Updated Ride",
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["id"] == "a123"
        assert response["data"]["name"] == "Updated Ride"
        assert response["metadata"]["message"] == "Successfully updated activity a123"

    async def test_update_activity_writes_icu_rpe(self, mock_config, respx_mock):
        """RPE is written to the API's native `icu_rpe` field, not to the
        read-only `perceived_exertion` mirror, so it round-trips."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        route = respx_mock.put("/activity/a123").mock(
            return_value=Response(
                200,
                json={
                    "id": "a123",
                    "start_date_local": "2026-03-20T10:00:00",
                    "name": "Updated Ride",
                    "type": "Ride",
                    "feel": 4,
                    "icu_rpe": 7,
                },
            )
        )

        result = await update_activity(
            activity_id="a123",
            feel=4,
            perceived_exertion=7,
            ctx=mock_ctx,
        )

        sent = json.loads(route.calls[0].request.content)
        assert sent["icu_rpe"] == 7
        assert sent["feel"] == 4
        assert "perceived_exertion" not in sent

        response = json.loads(result)
        assert response["data"]["rpe"] == 7
        assert response["data"]["feel"] == 4

    async def test_update_activity_not_found(self, mock_config, respx_mock):
        """Test updating a non-existent activity."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.put("/activity/a123").mock(
            return_value=Response(
                404,
                json={"error": "Activity not found"},
            )
        )

        result = await update_activity(
            activity_id="a123",
            name="Updated Ride",
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "error" in response
        assert "Resource not found" in response["error"]["message"]

    async def test_delete_activity_success(self, mock_config, respx_mock):
        """Test successful activity deletion."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.delete("/activity/a123").mock(return_value=Response(200, json={}))

        result = await delete_activity(
            activity_id="a123",
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["deleted"] is True
        assert response["metadata"]["message"] == "Successfully deleted activity a123"

    async def test_delete_activity_error(self, mock_config, respx_mock):
        """Test activity deletion error."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.delete("/activity/a123").mock(return_value=Response(500, json={}))

        result = await delete_activity(
            activity_id="a123",
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "error" in response
        assert "HTTP 500" in response["error"]["message"]

    async def test_update_activity_streams_json(self, mock_config, respx_mock):
        """Test updating activity streams with JSON."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.put("/activity/a123/streams").mock(
            return_value=Response(200, json={"message": "ok"})
        )

        result = await update_activity_streams(
            activity_id="a123",
            format="json",
            payload_string='[{"time": 0, "watts": 100}]',
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["message"] == "ok"
        assert response["metadata"]["message"] == "Successfully updated streams for activity a123"

    async def test_bulk_create_manual_activities(self, mock_config, respx_mock):
        """Test bulk creating manual activities."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.post("/athlete/i123456/activities/manual/bulk").mock(
            return_value=Response(
                200,
                json=[
                    {"id": "a123", "name": "Bulk Ride", "start_date_local": "2026-03-20T10:00:00"}
                ],
            )
        )

        result = await bulk_create_manual_activities(
            activities_json='[{"start_date_local": "2026-03-20T10:00:00", "type": "Ride", "name": "Bulk Ride"}]',
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["count"] == 1
        assert response["data"]["activities"][0]["name"] == "Bulk Ride"

    async def test_get_activity_details_nutrition_section(self, mock_config, respx_mock):
        """Nutrition fields are grouped, calories renamed to calories_burned."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/activity/a123").mock(
            return_value=Response(
                200,
                json={
                    "id": "a123",
                    "start_date_local": "2026-03-20T10:00:00",
                    "name": "Test Ride",
                    "type": "Ride",
                    "calories": 500,
                    "carbs_ingested": 45,
                    "carbs_used": 60,
                },
            )
        )

        result = await get_activity_details(activity_id="a123", ctx=mock_ctx)
        response = json.loads(result)

        nutrition = response["data"]["nutrition"]
        assert nutrition["calories_burned"] == 500
        assert nutrition["carbs_ingested_g"] == 45
        assert nutrition["carbs_used_g"] == 60
        # Old key must be gone from output (breaking change documented in CHANGELOG)
        assert "calories" not in response["data"].get("other", {})
        assert "calories" not in nutrition

    async def test_get_activity_details_subjective_scale_metadata(self, mock_config, respx_mock):
        """Scale metadata accompanies feel (1-5) and RPE (1-10)."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/activity/a123").mock(
            return_value=Response(
                200,
                json={
                    "id": "a123",
                    "start_date_local": "2026-03-20T10:00:00",
                    "name": "Test Ride",
                    "type": "Ride",
                    "feel": 4,
                    "perceived_exertion": 7,
                },
            )
        )

        result = await get_activity_details(activity_id="a123", ctx=mock_ctx)
        response = json.loads(result)

        assert response["data"]["subjective"] == {"feel": 4, "rpe": 7}
        assert response["metadata"]["subjective_scales"] == {"feel": "1-5", "rpe": "1-10"}

    async def test_get_activity_details_maps_icu_rpe(self, mock_config, respx_mock):
        """The native icu_rpe response field is exposed as subjective RPE."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/activity/a123").mock(
            return_value=Response(
                200,
                json={
                    "id": "a123",
                    "start_date_local": "2026-03-20T10:00:00",
                    "name": "Test Ride",
                    "type": "Ride",
                    "feel": 3,
                    "icu_rpe": 3,
                },
            )
        )

        result = await get_activity_details(activity_id="a123", ctx=mock_ctx)
        response = json.loads(result)

        assert response["data"]["subjective"] == {"feel": 3, "rpe": 3}
        assert response["metadata"]["subjective_scales"] == {"feel": "1-5", "rpe": "1-10"}

    async def test_get_activity_details_icu_rpe_wins_over_perceived_exertion(
        self, mock_config, respx_mock
    ):
        """`icu_rpe` is the athlete-entered value and takes precedence over the
        Strava-imported `perceived_exertion` float."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/activity/a123").mock(
            return_value=Response(
                200,
                json={
                    "id": "a123",
                    "start_date_local": "2026-03-20T10:00:00",
                    "name": "Test Ride",
                    "type": "Ride",
                    "icu_rpe": 7,
                    "perceived_exertion": 6.5,
                },
            )
        )

        result = await get_activity_details(activity_id="a123", ctx=mock_ctx)
        response = json.loads(result)

        assert response["data"]["subjective"] == {"rpe": 7}

    async def test_get_activity_details_fractional_perceived_exertion(
        self, mock_config, respx_mock
    ):
        """A fractional `perceived_exertion` (typed float by the API) is rounded
        onto the 1-10 scale instead of failing validation for the whole activity."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/activity/a123").mock(
            return_value=Response(
                200,
                json={
                    "id": "a123",
                    "start_date_local": "2026-03-20T10:00:00",
                    "name": "Test Ride",
                    "type": "Ride",
                    "perceived_exertion": 6.5,
                },
            )
        )

        result = await get_activity_details(activity_id="a123", ctx=mock_ctx)
        response = json.loads(result)

        assert response["data"]["subjective"] == {"rpe": 7}

    async def test_get_activity_details_null_icu_rpe_falls_back(self, mock_config, respx_mock):
        """The API always sends `icu_rpe`, explicitly null when the athlete has
        not entered an RPE — so an imported `perceived_exertion` must still be
        read. AliasChoices resolves on key presence, hence the model validator."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/activity/a123").mock(
            return_value=Response(
                200,
                json={
                    "id": "a123",
                    "start_date_local": "2026-03-20T10:00:00",
                    "name": "Test Ride",
                    "type": "Ride",
                    "icu_rpe": None,
                    "perceived_exertion": 6.5,
                },
            )
        )

        result = await get_activity_details(activity_id="a123", ctx=mock_ctx)
        response = json.loads(result)

        assert response["data"]["subjective"] == {"rpe": 7}
        assert response["metadata"]["subjective_scales"] == {"rpe": "1-10"}

    async def test_get_activity_details_both_rpe_fields_null(self, mock_config, respx_mock):
        """Both RPE fields null — the shape of most real activities — reports no
        RPE rather than inventing one."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/activity/a123").mock(
            return_value=Response(
                200,
                json={
                    "id": "a123",
                    "start_date_local": "2026-03-20T10:00:00",
                    "name": "Test Ride",
                    "type": "Ride",
                    "icu_rpe": None,
                    "perceived_exertion": None,
                },
            )
        )

        result = await get_activity_details(activity_id="a123", ctx=mock_ctx)
        response = json.loads(result)

        assert "subjective" not in response["data"]
        assert "subjective_scales" not in response.get("metadata", {})

    async def test_get_activity_details_partial_nutrition(self, mock_config, respx_mock):
        """Nutrition section omits null fields; preserves zero values."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/activity/a123").mock(
            return_value=Response(
                200,
                json={
                    "id": "a123",
                    "start_date_local": "2026-03-20T10:00:00",
                    "name": "Test Ride",
                    "type": "Ride",
                    "calories": 400,
                    "carbs_ingested": 0,
                    # carbs_used omitted entirely
                },
            )
        )

        result = await get_activity_details(activity_id="a123", ctx=mock_ctx)
        response = json.loads(result)

        nutrition = response["data"]["nutrition"]
        assert nutrition["calories_burned"] == 400
        assert nutrition["carbs_ingested_g"] == 0  # zero is meaningful, must be preserved
        assert "carbs_used_g" not in nutrition

    async def test_get_activity_details_no_subjective_no_scale_metadata(self, mock_config, respx_mock):
        """When feel/RPE are absent, subjective_scales metadata is also absent."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/activity/a123").mock(
            return_value=Response(
                200,
                json={
                    "id": "a123",
                    "start_date_local": "2026-03-20T10:00:00",
                    "name": "Test Ride",
                    "type": "Ride",
                },
            )
        )

        result = await get_activity_details(activity_id="a123", ctx=mock_ctx)
        response = json.loads(result)

        assert "subjective" not in response["data"]
        assert "subjective_scales" not in response.get("metadata", {})
