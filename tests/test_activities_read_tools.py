"""Read-side activity tools — get_recent, search, search_full, around, downloads.

Complements `test_activity_tools.py` which covers write/update paths.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from httpx import Response

from intervals_icu_mcp.tools.activities import (
    download_activity_file,
    download_fit_file,
    download_gpx_file,
    get_activities_around,
    get_recent_activities,
    search_activities,
    search_activities_full,
)


def _make_ctx(mock_config):
    ctx = MagicMock()
    ctx.get_state = AsyncMock(return_value=mock_config)
    return ctx


class TestGetRecentActivities:
    async def test_success_with_full_metrics(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/activities").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": "a1",
                        "name": "Morning Ride",
                        "start_date_local": "2026-05-19T08:00:00",
                        "type": "Ride",
                        "distance": 30000,
                        "moving_time": 3600,
                        "total_elevation_gain": 250,
                        "average_watts": 200,
                        "normalized_power": 220,
                        "average_heartrate": 150,
                        "average_cadence": 88,
                        "icu_training_load": 75,
                        "icu_intensity": 0.85,
                    },
                    {
                        "id": "a2",
                        "name": None,  # Triggers "Untitled" fallback
                        "start_date_local": "2026-05-18T07:00:00",
                        "type": "Run",
                    },
                ],
            )
        )

        result = await get_recent_activities(limit=10, days_back=7, ctx=_make_ctx(mock_config))

        response = json.loads(result)
        assert response["data"]["count"] == 2
        first = response["data"]["activities"][0]
        assert first["average_watts"] == 200
        assert first["normalized_power"] == 220
        assert first["training_load"] == 75
        # Untitled fallback when name is None
        assert response["data"]["activities"][1]["name"] == "Untitled"

    async def test_empty(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/activities").mock(return_value=Response(200, json=[]))

        result = await get_recent_activities(ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["data"]["count"] == 0
        assert "No activities found" in response["metadata"]["message"]

    async def test_limit_capped_at_100(self, mock_config, respx_mock):
        """Tool caps limit at 100 even if user asks for more — slicing is client-side."""
        # Server returns 150 results; client.get_activities slices to 100
        many = [
            {
                "id": f"a{i}",
                "name": f"Ride {i}",
                "start_date_local": "2026-05-19",
                "type": "Ride",
            }
            for i in range(150)
        ]
        respx_mock.get("/athlete/i123456/activities").mock(
            return_value=Response(200, json=many)
        )

        result = await get_recent_activities(limit=500, ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["data"]["count"] == 100

    async def test_api_error(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/activities").mock(
            return_value=Response(500, json={})
        )

        result = await get_recent_activities(ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["error"]["type"] == "api_error"


class TestSearchActivities:
    async def test_success(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/activities/search").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": "a1",
                        "name": "Threshold Intervals",
                        "start_date_local": "2026-05-15",
                        "type": "Ride",
                        "distance": 25000,
                        "moving_time": 3000,
                    }
                ],
            )
        )

        result = await search_activities(query="threshold", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["data"]["query"] == "threshold"
        assert response["data"]["count"] == 1

    async def test_empty_query_validation(self, mock_config):
        result = await search_activities(query="   ", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["error"]["type"] == "validation_error"
        assert "cannot be empty" in response["error"]["message"]

    async def test_no_results(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/activities/search").mock(
            return_value=Response(200, json=[])
        )

        result = await search_activities(query="nonexistent", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["data"]["count"] == 0
        assert "nonexistent" in response["metadata"]["message"]

    async def test_api_error(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/activities/search").mock(
            return_value=Response(401, json={})
        )

        result = await search_activities(query="x", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["error"]["type"] == "api_error"


class TestSearchActivitiesFull:
    async def test_success_with_performance_block(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/activities/search-full").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": "a1",
                        "name": "FTP Test",
                        "start_date_local": "2026-05-15T08:00:00",
                        "type": "Ride",
                        "distance": 25000,
                        "moving_time": 1800,
                        "total_elevation_gain": 100,
                        "average_watts": 270,
                        "normalized_power": 285,
                        "average_heartrate": 168,
                        "average_cadence": 92,
                        "icu_training_load": 60,
                        "icu_intensity": 0.95,
                    }
                ],
            )
        )

        result = await search_activities_full(query="FTP", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        activity = response["data"]["activities"][0]
        assert activity["performance"]["normalized_power"] == 285
        assert activity["training_load"] == 60
        assert activity["intensity_factor"] == 0.95

    async def test_empty_query_validation(self, mock_config):
        result = await search_activities_full(query="", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["error"]["type"] == "validation_error"

    async def test_no_results(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/activities/search-full").mock(
            return_value=Response(200, json=[])
        )

        result = await search_activities_full(query="zzz", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["data"]["count"] == 0


class TestGetActivitiesAround:
    async def test_success_positions_around_reference(self, mock_config, respx_mock):
        """Activities before/after reference get position+days_before/after labels."""
        respx_mock.get("/athlete/i123456/activities-around").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": "ref",
                        "name": "Race Day",
                        "start_date_local": "2026-05-15",
                        "type": "Ride",
                        "distance": 50000,
                        "moving_time": 5400,
                        "icu_training_load": 150,
                        "average_watts": 240,
                        "average_heartrate": 160,
                    },
                    {
                        "id": "before1",
                        "name": "Taper",
                        "start_date_local": "2026-05-14",
                        "type": "Ride",
                        "distance": 20000,
                    },
                    {
                        "id": "after1",
                        "name": "Recovery",
                        "start_date_local": "2026-05-16",
                        "type": "Ride",
                    },
                ],
            )
        )

        result = await get_activities_around(activity_id="ref", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        data = response["data"]
        assert data["reference_activity_id"] == "ref"
        # After sort by date, before1 < ref < after1
        by_id = {a["id"]: a for a in data["activities"]}
        assert by_id["ref"]["is_reference"] is True
        assert by_id["before1"]["position"] == "before"
        assert by_id["before1"]["days_before"] == 1
        assert by_id["after1"]["position"] == "after"
        assert by_id["after1"]["days_after"] == 1
        # Reference activity carries its performance block
        assert by_id["ref"]["performance"]["average_watts"] == 240

    async def test_empty(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/activities-around").mock(
            return_value=Response(200, json=[])
        )

        result = await get_activities_around(activity_id="missing", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["data"]["count"] == 0

    async def test_reference_missing_from_results(self, mock_config, respx_mock):
        """If reference activity isn't in the result list, no position labels are added."""
        respx_mock.get("/athlete/i123456/activities-around").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": "other",
                        "name": "Random",
                        "start_date_local": "2026-05-14",
                        "type": "Ride",
                    }
                ],
            )
        )

        result = await get_activities_around(activity_id="missing", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        # No reference_position when ref activity wasn't found
        assert "reference_position" not in response["data"]
        assert "position" not in response["data"]["activities"][0]


class TestDownloadActivityFile:
    async def test_returns_base64_when_no_path(self, mock_config, respx_mock):
        respx_mock.get("/activity/a1/file").mock(
            return_value=Response(200, content=b"FIT_BINARY_BYTES")
        )

        result = await download_activity_file(activity_id="a1", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        # 16 bytes, base64 encoded
        import base64

        decoded = base64.b64decode(response["data"]["content_base64"])
        assert decoded == b"FIT_BINARY_BYTES"
        assert response["data"]["size_bytes"] == 16

    async def test_saves_to_disk_when_path_given(self, mock_config, respx_mock):
        respx_mock.get("/activity/a1/file").mock(
            return_value=Response(200, content=b"BINARY_CONTENT")
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "subdir" / "activity.fit"
            result = await download_activity_file(
                activity_id="a1", output_path=str(target), ctx=_make_ctx(mock_config)
            )
            response = json.loads(result)
            assert response["data"]["saved_to"] == str(target)
            assert target.read_bytes() == b"BINARY_CONTENT"

    async def test_api_error(self, mock_config, respx_mock):
        respx_mock.get("/activity/a1/file").mock(return_value=Response(404, json={}))

        result = await download_activity_file(activity_id="a1", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["error"]["type"] == "api_error"


class TestDownloadFitFile:
    async def test_includes_format_label(self, mock_config, respx_mock):
        respx_mock.get("/activity/a1/fit-file").mock(
            return_value=Response(200, content=b"\x0eFIT\x00\x00")
        )

        result = await download_fit_file(activity_id="a1", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["data"]["format"] == "FIT"

    async def test_api_error(self, mock_config, respx_mock):
        respx_mock.get("/activity/a1/fit-file").mock(return_value=Response(404, json={}))

        result = await download_fit_file(activity_id="a1", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["error"]["type"] == "api_error"


class TestDownloadGpxFile:
    async def test_saves_with_format_label(self, mock_config, respx_mock):
        respx_mock.get("/activity/a1/gpx-file").mock(
            return_value=Response(200, content=b"<?xml version='1.0'?><gpx></gpx>")
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "out.gpx"
            result = await download_gpx_file(
                activity_id="a1", output_path=str(target), ctx=_make_ctx(mock_config)
            )
            response = json.loads(result)
            assert response["data"]["format"] == "GPX"
            assert response["data"]["saved_to"] == str(target)
            # Confirm the file was actually written
            assert target.exists()

    async def test_api_error(self, mock_config, respx_mock):
        respx_mock.get("/activity/a1/gpx-file").mock(return_value=Response(401, json={}))

        result = await download_gpx_file(activity_id="a1", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["error"]["type"] == "api_error"
