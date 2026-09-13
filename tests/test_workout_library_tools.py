"""Tests for workout library tools (folders and training plans)."""

import json
from unittest.mock import AsyncMock, MagicMock

from httpx import Response

from intervals_icu_mcp.tools.workout_library import (
    bulk_create_workouts,
    create_workout,
    create_workout_folder,
    delete_workout,
    get_workout_library,
    get_workouts_in_folder,
    update_workout,
)


class TestGetWorkoutLibrary:
    async def test_success_mixed_folders_and_plans(self, mock_config, respx_mock):
        """Categorizes plans (duration_weeks set) vs regular folders, sums workouts."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/folders").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 1,
                        "name": "Base Plan",
                        "description": "12-week base",
                        "num_workouts": 36,
                        "start_date_local": "2026-06-01",
                        "duration_weeks": 12,
                        "hours_per_week_min": 8,
                        "hours_per_week_max": 12,
                    },
                    {
                        "id": 2,
                        "name": "My Saved Workouts",
                        "num_workouts": 10,
                    },
                    {
                        "id": 3,
                        "name": "Empty Folder",
                    },
                ],
            )
        )

        result = await get_workout_library(ctx=mock_ctx)

        response = json.loads(result)
        data = response["data"]
        assert len(data["folders"]) == 3
        # Training plan retains plan-specific fields
        plan = data["folders"][0]
        assert plan["duration_weeks"] == 12
        assert plan["hours_per_week"] == {"min": 8, "max": 12}
        assert plan["start_date"] == "2026-06-01"
        # Regular folder omits plan-specific fields
        regular = data["folders"][1]
        assert "duration_weeks" not in regular
        assert "hours_per_week" not in regular
        # Summary
        assert data["summary"]["total_folders"] == 3
        assert data["summary"]["training_plans"] == 1
        assert data["summary"]["regular_folders"] == 2
        assert data["summary"]["total_workouts"] == 46  # 36 + 10 + 0

    async def test_hours_per_week_only_min(self, mock_config, respx_mock):
        """A folder with hours_per_week_min but no max still emits the hours_per_week block."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/folders").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 1,
                        "name": "Flexible Plan",
                        "duration_weeks": 8,
                        "hours_per_week_min": 5,
                    }
                ],
            )
        )

        result = await get_workout_library(ctx=mock_ctx)

        data = json.loads(result)["data"]
        assert data["folders"][0]["hours_per_week"] == {"min": 5, "max": None}

    async def test_empty_folders(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/folders").mock(return_value=Response(200, json=[]))

        result = await get_workout_library(ctx=mock_ctx)
        response = json.loads(result)
        assert response["data"]["folders"] == []
        assert response["data"]["count"] == 0
        assert "No workout folders found" in response["metadata"]["message"]

    async def test_api_error(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/folders").mock(return_value=Response(500, json={}))

        result = await get_workout_library(ctx=mock_ctx)
        response = json.loads(result)
        assert response["error"]["type"] == "api_error"


class TestGetWorkoutsInFolder:
    async def test_success_with_metrics_and_summary(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/workouts").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 100,
                        "name": "Threshold Intervals",
                        "description": "5x5min @ FTP",
                        "type": "Ride",
                        "folder_id": 1,
                        "moving_time": 3600,
                        "distance": 30000.0,
                        "icu_training_load": 100,
                        "icu_intensity": 0.9,
                        "joules": 800000,
                        "joules_above_ftp": 150000,
                        "indoor": True,
                        "color": "#ff0000",
                    },
                    {
                        "id": 101,
                        "name": "Easy Spin",
                        "folder_id": 1,
                        "moving_time": 1800,
                        "indoor": False,
                    },
                    {
                        "id": 102,
                        "name": "Other Folder Workout",
                        "folder_id": 7,
                        "moving_time": 900,
                    },
                ],
            )
        )

        result = await get_workouts_in_folder(folder_id=1, ctx=mock_ctx)

        response = json.loads(result)
        data = response["data"]
        assert data["folder_id"] == 1
        # Workout 102 lives in folder 7 and must be filtered out
        assert len(data["workouts"]) == 2
        threshold = data["workouts"][0]
        assert threshold["metrics"]["training_load"] == 100
        assert threshold["metrics"]["intensity_factor"] == 0.9
        assert threshold["metrics"]["joules_above_ftp"] == 150000
        assert threshold["indoor"] is True
        assert threshold["color"] == "#ff0000"
        # Workout without metrics omits the metrics block
        easy = data["workouts"][1]
        assert "metrics" in easy  # has moving_time, so metrics block exists
        assert easy["metrics"]["duration_seconds"] == 1800
        # Summary
        assert data["summary"]["total_workouts"] == 2
        assert data["summary"]["total_duration_seconds"] == 5400
        assert data["summary"]["total_training_load"] == 100
        assert data["summary"]["indoor_workouts"] == 1

    async def test_workout_with_no_metrics(self, mock_config, respx_mock):
        """A workout with no metric fields omits the metrics dict."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/workouts").mock(
            return_value=Response(200, json=[{"id": 200, "name": "Placeholder", "folder_id": 2}])
        )

        result = await get_workouts_in_folder(folder_id=2, ctx=mock_ctx)
        data = json.loads(result)["data"]
        assert "metrics" not in data["workouts"][0]

    async def test_empty_folder(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        # A non-empty library where nothing belongs to folder 99
        respx_mock.get("/athlete/i123456/workouts").mock(
            return_value=Response(200, json=[{"id": 300, "name": "Elsewhere", "folder_id": 1}])
        )

        result = await get_workouts_in_folder(folder_id=99, ctx=mock_ctx)
        response = json.loads(result)
        assert response["data"]["workouts"] == []
        assert response["data"]["count"] == 0
        assert response["data"]["folder_id"] == 99

    async def test_api_error(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/workouts").mock(return_value=Response(404, json={}))

        result = await get_workouts_in_folder(folder_id=1, ctx=mock_ctx)
        response = json.loads(result)
        assert response["error"]["type"] == "api_error"

    async def test_plan_day_emitted(self, mock_config, respx_mock):
        """Plan workouts expose their day offset; day 0 is kept, not dropped as falsy."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/workouts").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "name": "Day one", "folder_id": 5, "day": 0},
                    {"id": 2, "name": "Week two", "folder_id": 5, "day": 7},
                ],
            )
        )

        result = await get_workouts_in_folder(folder_id=5, ctx=mock_ctx)
        workouts = json.loads(result)["data"]["workouts"]
        assert [w["day"] for w in workouts] == [0, 7]


class TestCreateWorkout:
    async def test_success_translates_fields_and_echoes_parse(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        steps_text = "Main 3x\n- 10m 95%\n- 5m 55%"
        route = respx_mock.post("/athlete/i123456/workouts").mock(
            return_value=Response(
                200,
                json={
                    "id": 500,
                    "name": "Threshold 3x10",
                    "folder_id": 7,
                    "type": "Ride",
                    "day": 3,
                    "description": steps_text,
                    "moving_time": 2700,
                    "icu_training_load": 60,
                    "target": "POWER",
                    "tags": ["threshold"],
                    "workout_doc": {
                        "steps": [{"reps": 3, "steps": [{"duration": 600}, {"duration": 300}]}]
                    },
                },
            )
        )

        result = await create_workout(
            folder_id=7,
            name="Threshold 3x10",
            description=steps_text,
            workout_type="Ride",
            day=3,
            duration_seconds=2700,
            target="power",
            tags=["threshold"],
            ctx=mock_ctx,
        )

        sent = json.loads(route.calls[0].request.content)
        assert sent == {
            "folder_id": 7,
            "name": "Threshold 3x10",
            "description": steps_text,
            "type": "Ride",
            "day": 3,
            "moving_time": 2700,
            "target": "POWER",
            "tags": ["threshold"],
        }
        data = json.loads(result)["data"]
        assert data["id"] == 500
        assert data["folder_id"] == 7
        assert data["day"] == 3
        assert data["duration_seconds"] == 2700
        assert data["training_load"] == 60
        assert data["tags"] == ["threshold"]
        assert data["workout_parsed"] is True
        assert data["workout_steps"] == 6

    async def test_unparsed_description_flagged(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.post("/athlete/i123456/workouts").mock(
            return_value=Response(
                200,
                json={
                    "id": 501,
                    "name": "Prose",
                    "folder_id": 7,
                    "description": "do some hard efforts",
                    "workout_doc": {"steps": []},
                },
            )
        )

        result = await create_workout(
            folder_id=7, name="Prose", description="do some hard efforts", ctx=mock_ctx
        )
        data = json.loads(result)["data"]
        assert data["workout_parsed"] is False
        assert "workout_parse_hint" in data

    async def test_invalid_target_rejected(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await create_workout(folder_id=7, name="X", target="WATTS", ctx=mock_ctx)
        response = json.loads(result)
        assert response["error"]["type"] == "validation_error"
        assert "target" in response["error"]["message"]

    async def test_negative_day_rejected(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await create_workout(folder_id=7, name="X", day=-1, ctx=mock_ctx)
        response = json.loads(result)
        assert response["error"]["type"] == "validation_error"

    async def test_athlete_id_override(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        route = respx_mock.post("/athlete/i999/workouts").mock(
            return_value=Response(200, json={"id": 9, "name": "X", "folder_id": 7})
        )

        result = await create_workout(folder_id=7, name="X", athlete_id="i999", ctx=mock_ctx)
        assert route.called
        assert json.loads(result)["data"]["id"] == 9

    async def test_zero_metrics_omitted_but_day_zero_kept(self, mock_config, respx_mock):
        """The API returns distance 0.0 for a Ride; zero metrics drop, day 0 stays."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.post("/athlete/i123456/workouts").mock(
            return_value=Response(
                200,
                json={
                    "id": 10,
                    "name": "Ride",
                    "folder_id": 7,
                    "type": "Ride",
                    "day": 0,
                    "distance": 0.0,
                    "moving_time": 1800,
                    "icu_training_load": 0,
                },
            )
        )

        result = await create_workout(folder_id=7, name="Ride", day=0, ctx=mock_ctx)
        data = json.loads(result)["data"]
        assert "distance_meters" not in data
        assert "training_load" not in data
        assert data["duration_seconds"] == 1800
        assert data["day"] == 0

    async def test_api_error(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.post("/athlete/i123456/workouts").mock(return_value=Response(422, json={}))

        result = await create_workout(folder_id=7, name="X", ctx=mock_ctx)
        assert json.loads(result)["error"]["type"] == "api_error"


class TestUpdateWorkout:
    async def test_sends_only_provided_fields(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        route = respx_mock.put("/athlete/i123456/workouts/500").mock(
            return_value=Response(
                200,
                json={"id": 500, "name": "Shorter Recovery", "folder_id": 7, "moving_time": 1800},
            )
        )

        result = await update_workout(
            workout_id=500,
            name="Shorter Recovery",
            duration_seconds=1800,
            target="hr",
            ctx=mock_ctx,
        )

        sent = json.loads(route.calls[0].request.content)
        assert sent == {"name": "Shorter Recovery", "moving_time": 1800, "target": "HR"}
        data = json.loads(result)["data"]
        assert data["name"] == "Shorter Recovery"
        assert data["duration_seconds"] == 1800

    async def test_no_fields_rejected(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await update_workout(workout_id=500, ctx=mock_ctx)
        response = json.loads(result)
        assert response["error"]["type"] == "validation_error"
        assert "No fields" in response["error"]["message"]

    async def test_invalid_target_rejected(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await update_workout(workout_id=500, target="WATTS", ctx=mock_ctx)
        assert json.loads(result)["error"]["type"] == "validation_error"

    async def test_api_error_not_found(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.put("/athlete/i123456/workouts/999").mock(return_value=Response(404, json={}))

        result = await update_workout(workout_id=999, name="X", ctx=mock_ctx)
        assert json.loads(result)["error"]["type"] == "api_error"


class TestDeleteWorkout:
    async def test_success(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.delete("/athlete/i123456/workouts/500").mock(
            return_value=Response(200, json=[500])
        )

        result = await delete_workout(workout_id=500, ctx=mock_ctx)
        data = json.loads(result)["data"]
        assert data == {"deleted": [500], "deleted_count": 1}

    async def test_athlete_id_override(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        route = respx_mock.delete("/athlete/i999/workouts/500").mock(
            return_value=Response(200, json=[500])
        )

        await delete_workout(workout_id=500, athlete_id="i999", ctx=mock_ctx)
        assert route.called

    async def test_api_error_not_found(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.delete("/athlete/i123456/workouts/999").mock(return_value=Response(404, json={}))

        result = await delete_workout(workout_id=999, ctx=mock_ctx)
        assert json.loads(result)["error"]["type"] == "api_error"


class TestBulkCreateWorkouts:
    async def test_success_with_event_type_alias(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        route = respx_mock.post("/athlete/i123456/workouts/bulk").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "name": "Easy", "folder_id": 5, "type": "Ride", "day": 0},
                    {"id": 2, "name": "Tempo", "folder_id": 5, "type": "Run", "day": 2},
                ],
            )
        )

        payload = [
            {"folder_id": 5, "name": "Easy", "workout_type": "Ride", "day": 0},
            {
                "folder_id": 5,
                "name": "Tempo",
                "event_type": "Run",
                "day": 2,
                "duration_seconds": 3000,
            },
        ]
        result = await bulk_create_workouts(workouts=json.dumps(payload), ctx=mock_ctx)

        sent = json.loads(route.calls[0].request.content)
        assert sent[0] == {"folder_id": 5, "name": "Easy", "type": "Ride", "day": 0}
        assert sent[1] == {
            "folder_id": 5,
            "name": "Tempo",
            "type": "Run",
            "day": 2,
            "moving_time": 3000,
        }
        response = json.loads(result)
        assert [w["day"] for w in response["data"]["workouts"]] == [0, 2]
        assert response["metadata"]["count"] == 2

    async def test_invalid_json(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await bulk_create_workouts(workouts="not json", ctx=mock_ctx)
        assert json.loads(result)["error"]["type"] == "validation_error"

    async def test_not_an_array(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await bulk_create_workouts(workouts='{"name": "X"}', ctx=mock_ctx)
        assert json.loads(result)["error"]["type"] == "validation_error"

    async def test_missing_name_reports_index(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        payload = [{"folder_id": 5, "name": "Ok"}, {"folder_id": 5}]
        result = await bulk_create_workouts(workouts=json.dumps(payload), ctx=mock_ctx)
        error = json.loads(result)["error"]
        assert error["type"] == "validation_error"
        assert error["message"].startswith("Workout 1:")
        assert "name" in error["message"]

    async def test_missing_folder_id(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await bulk_create_workouts(workouts='[{"name": "X"}]', ctx=mock_ctx)
        error = json.loads(result)["error"]
        assert error["type"] == "validation_error"
        assert "folder_id" in error["message"]

    async def test_non_integer_day_rejected(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        payload = [{"folder_id": 5, "name": "X", "day": "monday"}]
        result = await bulk_create_workouts(workouts=json.dumps(payload), ctx=mock_ctx)
        assert json.loads(result)["error"]["type"] == "validation_error"

    async def test_raw_api_field_rejected(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        payload = [{"folder_id": 5, "name": "X", "moving_time": 3600}]
        result = await bulk_create_workouts(workouts=json.dumps(payload), ctx=mock_ctx)
        error = json.loads(result)["error"]
        assert error["type"] == "validation_error"
        assert "moving_time -> duration_seconds" in error["message"]

    async def test_api_error(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.post("/athlete/i123456/workouts/bulk").mock(return_value=Response(500, json={}))

        result = await bulk_create_workouts(
            workouts='[{"folder_id": 5, "name": "X"}]', ctx=mock_ctx
        )
        assert json.loads(result)["error"]["type"] == "api_error"


class TestCreateWorkoutFolder:
    async def test_success_plan(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        route = respx_mock.post("/athlete/i123456/folders").mock(
            return_value=Response(
                200,
                json={
                    "id": 42,
                    "name": "Base Build",
                    "type": "PLAN",
                    "description": "4 weeks",
                    "num_workouts": 0,
                },
            )
        )

        result = await create_workout_folder(
            name="Base Build", folder_type="plan", description="4 weeks", ctx=mock_ctx
        )

        sent = json.loads(route.calls[0].request.content)
        assert sent == {"name": "Base Build", "type": "PLAN", "description": "4 weeks"}
        data = json.loads(result)["data"]
        assert data == {
            "id": 42,
            "name": "Base Build",
            "type": "PLAN",
            "description": "4 weeks",
            "num_workouts": 0,
        }

    async def test_defaults_to_folder(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        route = respx_mock.post("/athlete/i123456/folders").mock(
            return_value=Response(200, json={"id": 43, "name": "Saved", "type": "FOLDER"})
        )

        await create_workout_folder(name="Saved", ctx=mock_ctx)
        assert json.loads(route.calls[0].request.content) == {"name": "Saved", "type": "FOLDER"}

    async def test_invalid_folder_type(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await create_workout_folder(name="X", folder_type="BLOCK", ctx=mock_ctx)
        assert json.loads(result)["error"]["type"] == "validation_error"

    async def test_blank_name_rejected(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await create_workout_folder(name="  ", ctx=mock_ctx)
        assert json.loads(result)["error"]["type"] == "validation_error"

    async def test_api_error(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.post("/athlete/i123456/folders").mock(return_value=Response(403, json={}))

        result = await create_workout_folder(name="X", ctx=mock_ctx)
        assert json.loads(result)["error"]["type"] == "api_error"
