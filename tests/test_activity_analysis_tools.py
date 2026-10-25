"""Tests for activity analysis tools — streams, intervals, best efforts, search_intervals."""

import json
from unittest.mock import AsyncMock, MagicMock

from httpx import Response

from intervals_icu_mcp.tools.activity_analysis import (
    get_activity_intervals,
    get_activity_streams,
    get_best_efforts,
    get_stream_stats,
    search_intervals,
)


def _make_ctx(mock_config):
    ctx = MagicMock()
    ctx.get_state = AsyncMock(return_value=mock_config)
    return ctx


class TestGetActivityStreams:
    async def test_success(self, mock_config, respx_mock):
        respx_mock.get("/activity/a1/streams.json").mock(
            return_value=Response(
                200,
                json=[
                    {"type": "watts", "data": [100, 200, 250]},
                    {"type": "heartrate", "data": [120, 140, 160]},
                    {"name": "no_type_stream", "data": [1, 2]},
                ],
            )
        )

        result = await get_activity_streams(activity_id="a1", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        data = response["data"]
        assert data["activity_id"] == "a1"
        assert "watts" in data["available_streams"]
        assert "heartrate" in data["available_streams"]
        assert "no_type_stream" in data["available_streams"]
        assert data["stream_lengths"]["watts"] == 3
        assert data["streams"]["heartrate"] == [120, 140, 160]

    async def test_latlng_zips_longitude_from_data2(self, mock_config, respx_mock):
        """latlng returns [lat, lng] pairs; an empty data2 on other streams is ignored."""
        respx_mock.get("/activity/a1/streams.json").mock(
            return_value=Response(
                200,
                json=[
                    {"type": "time", "data": [0, 1, 2], "data2": []},
                    {
                        "type": "latlng",
                        "data": [51.84981, None, 51.849823],
                        "data2": [10.332473, None, 10.332453],
                    },
                ],
            )
        )

        result = await get_activity_streams(
            activity_id="a1", streams=["latlng", "time"], ctx=_make_ctx(mock_config)
        )
        data = json.loads(result)["data"]
        assert data["streams"]["latlng"] == [[51.84981, 10.332473], None, [51.849823, 10.332453]]
        assert data["streams"]["time"] == [0, 1, 2]
        assert data["stream_lengths"]["latlng"] == 3

    async def test_left_right_balance_gets_side_note(self, mock_config, respx_mock):
        """The raw balance stream is labelled as the right pedal's share (#153)."""
        respx_mock.get("/activity/a1/streams.json").mock(
            return_value=Response(200, json=[{"type": "left_right_balance", "data": [48, 47, 49]}])
        )

        result = await get_activity_streams(activity_id="a1", ctx=_make_ctx(mock_config))

        data = json.loads(result)["data"]
        assert data["streams"]["left_right_balance"] == [48, 47, 49]
        note = data["stream_notes"]["left_right_balance"]
        assert "RIGHT" in note
        assert "100 - value" in note

    async def test_no_stream_notes_without_balance(self, mock_config, respx_mock):
        respx_mock.get("/activity/a1/streams.json").mock(
            return_value=Response(200, json=[{"type": "watts", "data": [100, 110]}])
        )

        result = await get_activity_streams(activity_id="a1", ctx=_make_ctx(mock_config))

        assert "stream_notes" not in json.loads(result)["data"]

    async def test_latlng_length_mismatch_pads_instead_of_truncating(self, mock_config, respx_mock):
        respx_mock.get("/activity/a1/streams.json").mock(
            return_value=Response(
                200,
                json=[{"type": "latlng", "data": [1.0, 2.0, 3.0], "data2": [10.0, 20.0]}],
            )
        )

        result = await get_activity_streams(activity_id="a1", ctx=_make_ctx(mock_config))
        data = json.loads(result)["data"]
        assert data["streams"]["latlng"] == [[1.0, 10.0], [2.0, 20.0], [3.0, None]]

    async def test_max_points_thins_all_streams_with_one_step(self, mock_config, respx_mock):
        respx_mock.get("/activity/a1/streams.json").mock(
            return_value=Response(
                200,
                json=[
                    {"type": "time", "data": list(range(10))},
                    {"type": "latlng", "data": list(range(10)), "data2": list(range(10, 20))},
                ],
            )
        )

        result = await get_activity_streams(
            activity_id="a1", max_points=4, ctx=_make_ctx(mock_config)
        )
        data = json.loads(result)["data"]
        # ceil(10 / 4) = 3 → indices 0, 3, 6, 9
        assert data["streams"]["time"] == [0, 3, 6, 9]
        assert data["streams"]["latlng"] == [[0, 10], [3, 13], [6, 16], [9, 19]]
        assert data["stream_lengths"] == {"time": 4, "latlng": 4}
        assert data["downsampling"]["step"] == 3
        assert data["downsampling"]["original_length"] == 10

    async def test_max_points_above_length_is_noop(self, mock_config, respx_mock):
        respx_mock.get("/activity/a1/streams.json").mock(
            return_value=Response(200, json=[{"type": "watts", "data": [1, 2, 3]}])
        )

        result = await get_activity_streams(
            activity_id="a1", max_points=100, ctx=_make_ctx(mock_config)
        )
        data = json.loads(result)["data"]
        assert data["streams"]["watts"] == [1, 2, 3]
        assert "downsampling" not in data

    async def test_max_points_below_one_rejected(self, mock_config, respx_mock):
        route = respx_mock.get("/activity/a1/streams.json").mock(
            return_value=Response(200, json=[])
        )

        result = await get_activity_streams(
            activity_id="a1", max_points=0, ctx=_make_ctx(mock_config)
        )
        response = json.loads(result)
        assert response["error"]["type"] == "validation_error"
        assert not route.called

    async def test_with_stream_filter(self, mock_config, respx_mock):
        """Stream filter is forwarded as comma-separated `types` query param."""
        route = respx_mock.get("/activity/a1/streams.json").mock(
            return_value=Response(200, json=[])
        )

        await get_activity_streams(
            activity_id="a1", streams=["watts", "heartrate"], ctx=_make_ctx(mock_config)
        )
        assert route.calls[0].request.url.params["types"] == "watts,heartrate"

    async def test_empty_streams_no_strava_note(self, mock_config, respx_mock):
        """Empty streams + no Strava limitation → message but no analysis block."""
        # Empty streams response
        respx_mock.get("/activity/a1/streams.json").mock(return_value=Response(200, json=[]))
        # Activity is not from Strava (no Strava limitation note)
        respx_mock.get("/activity/a1").mock(
            return_value=Response(
                200,
                json={
                    "id": "a1",
                    "name": "Garmin Ride",
                    "type": "Ride",
                    "start_date_local": "2026-05-19T08:00:00",
                    "external_id": "garmin_12345",
                },
            )
        )

        result = await get_activity_streams(activity_id="a1", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["data"]["streams"] == {}
        assert "No stream data available" in response["metadata"]["message"]

    async def test_api_error(self, mock_config, respx_mock):
        respx_mock.get("/activity/a1/streams.json").mock(return_value=Response(404, json={}))

        result = await get_activity_streams(activity_id="a1", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["error"]["type"] == "api_error"


class TestGetActivityIntervals:
    async def test_success_categorizes_work_rest(self, mock_config, respx_mock):
        respx_mock.get("/activity/a1/intervals").mock(
            return_value=Response(
                200,
                json={
                    "id": "a1",
                    "icu_intervals": [
                        {
                            "id": 1,
                            "type": "WARM_UP",
                            "start": 0,
                            "end": 600,
                            "duration": 600,
                            "average_watts": 150,
                            "average_heartrate": 120,
                            "average_cadence": 85,
                            "average_speed": 8.5,
                            "distance": 5000,
                        },
                        {
                            "id": 2,
                            "type": "WORK",
                            "start": 600,
                            "end": 1200,
                            "duration": 600,
                            "average_watts": 280,
                            "normalized_power": 285,
                            "max_heartrate": 175,
                            "target": "Threshold",
                            "target_min": 270,
                            "target_max": 290,
                        },
                        {
                            "id": 3,
                            "type": "REST",
                            "duration": 300,
                        },
                        {
                            "id": 4,
                            "type": "WORK",
                            "duration": 600,
                        },
                    ],
                },
            )
        )

        result = await get_activity_intervals(activity_id="a1", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        data = response["data"]
        # Total counts categorized correctly
        assert data["summary"]["total_intervals"] == 4
        assert data["summary"]["work_intervals"] == 2
        assert data["summary"]["rest_intervals"] == 1
        assert data["summary"]["total_work_time_seconds"] == 1200
        # Work interval carries target info
        work_with_target = data["intervals"][1]
        assert work_with_target["target_description"] == "Threshold"
        assert work_with_target["target_range"] == {"min": 270, "max": 290}
        assert work_with_target["performance"]["normalized_power"] == 285

    async def test_empty_intervals_no_strava_note(self, mock_config, respx_mock):
        respx_mock.get("/activity/a1/intervals").mock(
            return_value=Response(200, json={"id": "a1", "icu_intervals": []})
        )
        respx_mock.get("/activity/a1").mock(
            return_value=Response(
                200,
                json={
                    "id": "a1",
                    "name": "Ride",
                    "type": "Ride",
                    "start_date_local": "2026-05-19T08:00:00",
                },
            )
        )

        result = await get_activity_intervals(activity_id="a1", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["data"]["count"] == 0
        assert "No intervals found" in response["metadata"]["message"]

    async def test_api_error(self, mock_config, respx_mock):
        respx_mock.get("/activity/a1/intervals").mock(return_value=Response(500, json={}))

        result = await get_activity_intervals(activity_id="a1", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["error"]["type"] == "api_error"


class TestGetBestEfforts:
    async def test_success_with_duration(self, mock_config, respx_mock):
        route = respx_mock.get("/activity/a1/best-efforts").mock(
            return_value=Response(
                200,
                json={
                    "efforts": [
                        {
                            "average": 280.5,
                            "duration": 1200,
                            "start_index": 100,
                            "end_index": 1300,
                        },
                        {"average": 270.0, "duration": 1200},
                    ]
                },
            )
        )

        result = await get_best_efforts(
            activity_id="a1", stream="watts", duration=1200, count=5, ctx=_make_ctx(mock_config)
        )

        params = route.calls[0].request.url.params
        assert params["duration"] == "1200"
        assert params["count"] == "5"
        assert params["stream"] == "watts"

        response = json.loads(result)
        assert response["data"]["count"] == 2
        assert response["data"]["stream"] == "watts"

    async def test_success_with_distance(self, mock_config, respx_mock):
        respx_mock.get("/activity/a1/best-efforts").mock(
            return_value=Response(
                200,
                json={
                    "efforts": [
                        {"average": 200.0, "distance": 5000, "duration": 1500},
                    ]
                },
            )
        )

        result = await get_best_efforts(
            activity_id="a1", stream="pace", distance=5000, ctx=_make_ctx(mock_config)
        )
        response = json.loads(result)
        assert response["data"]["best_efforts"][0]["distance_meters"] == 5000

    async def test_missing_both_duration_and_distance(self, mock_config):
        result = await get_best_efforts(activity_id="a1", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["error"]["type"] == "validation_error"
        assert "duration" in response["error"]["message"]

    async def test_empty_efforts(self, mock_config, respx_mock):
        respx_mock.get("/activity/a1/best-efforts").mock(
            return_value=Response(200, json={"efforts": []})
        )
        # Mock the strava check too
        respx_mock.get("/activity/a1").mock(
            return_value=Response(
                200,
                json={"id": "a1", "name": "X", "type": "Ride", "start_date_local": "2026-05-19"},
            )
        )

        result = await get_best_efforts(activity_id="a1", duration=1200, ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["data"]["count"] == 0

    async def test_api_error(self, mock_config, respx_mock):
        respx_mock.get("/activity/a1/best-efforts").mock(return_value=Response(401, json={}))

        result = await get_best_efforts(activity_id="a1", duration=1200, ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["error"]["type"] == "api_error"


class TestSearchIntervals:
    async def test_success_with_all_filters(self, mock_config, respx_mock):
        """Filters map to the API's required param names (regression for #102)."""
        route = respx_mock.get("/athlete/i123456/activities/interval-search").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": "i1",
                        "name": "Sweet Spot 2x8",
                        "type": "Ride",
                        "start_date_local": "2026-04-08T20:54:11",
                        "moving_time": 3622,
                        "icu_training_load": 51,
                        "interval_summary": ["2x 8m 162w"],
                        "average_stride": 1.2,
                        "athlete_max_hr": 190,
                    },
                    {
                        "id": "i2",
                        "name": "Threshold",
                        "type": "Run",
                        "interval_summary": ["4x 5m 4:10/km"],
                    },
                ],
            )
        )

        result = await search_intervals(
            interval_type="power",
            min_duration=120,
            max_duration=1200,
            min_intensity=80,
            max_intensity=105,
            limit=10,
            ctx=_make_ctx(mock_config),
        )

        params = route.calls[0].request.url.params
        assert params["type"] == "POWER"
        assert params["minSecs"] == "120"
        assert params["maxSecs"] == "1200"
        assert params["minIntensity"] == "80"
        assert params["maxIntensity"] == "105"
        assert params["limit"] == "10"

        response = json.loads(result)
        data = response["data"]
        assert data["count"] == 2
        assert data["search_criteria"]["interval_type"] == "power"
        assert data["search_criteria"]["min_duration_seconds"] == 120
        assert data["search_criteria"]["min_intensity_percent"] == 80
        # Full Activity objects are projected down to the interval-relevant fields
        first = data["activities"][0]
        assert first["interval_summary"] == ["2x 8m 162w"]
        assert "average_stride" not in first
        assert "athlete_max_hr" not in first

    async def test_required_params_sent_on_default_call(self, mock_config, respx_mock):
        """The API 422s without all four bounds — a bare call must send defaults."""
        route = respx_mock.get("/athlete/i123456/activities/interval-search").mock(
            return_value=Response(200, json=[])
        )

        await search_intervals(ctx=_make_ctx(mock_config))

        params = route.calls[0].request.url.params
        assert params["minSecs"] == "0"
        assert params["maxSecs"] == "86400"
        assert params["minIntensity"] == "0"
        assert params["maxIntensity"] == "999"
        assert params["limit"] == "30"
        assert "type" not in params

    async def test_invalid_interval_type_rejected_before_api_call(self, mock_config, respx_mock):
        """Values like WORK or Ride are not target types — fail fast, no request."""
        route = respx_mock.get("/athlete/i123456/activities/interval-search").mock(
            return_value=Response(200, json=[])
        )

        result = await search_intervals(interval_type="WORK", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["error"]["type"] == "validation_error"
        assert "AUTO" in response["error"]["message"]
        assert not route.called

    async def test_no_results_with_criteria_string(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/activities/interval-search").mock(
            return_value=Response(200, json=[])
        )

        result = await search_intervals(
            interval_type="PACE", min_duration=600, ctx=_make_ctx(mock_config)
        )
        response = json.loads(result)
        assert response["data"]["count"] == 0
        assert "PACE" in response["metadata"]["message"]
        assert "600" in response["metadata"]["message"]

    async def test_no_results_no_criteria_uses_default_string(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/activities/interval-search").mock(
            return_value=Response(200, json=[])
        )

        result = await search_intervals(ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert "your criteria" in response["metadata"]["message"]

    async def test_api_error(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456/activities/interval-search").mock(
            return_value=Response(500, json={})
        )

        result = await search_intervals(interval_type="HR", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert response["error"]["type"] == "api_error"


def _streams_route(streams: dict[str, list]):
    """Serve only the requested stream types; 422 for unknown lower-case names."""

    def handler(request):
        types = request.url.params.get("types")
        names = types.split(",") if types else list(streams)
        for name in names:
            if name not in streams and name[:1].islower():
                return Response(422, json={"status": 422, "error": f"Invalid stream type [{name}]"})
        return Response(200, json=[{"type": n, "data": streams[n]} for n in names if n in streams])

    return handler


class TestGetActivityStreamsWindowing:
    async def test_start_end_slice_and_alias(self, mock_config, respx_mock):
        respx_mock.get("/activity/a1/streams.json").mock(
            side_effect=_streams_route(
                {"time": [0, 1, 2, 10, 11], "watts": [100, 110, 120, 130, 140]}
            )
        )

        result = await get_activity_streams(
            activity_id="a1",
            streams=["power"],
            start_s=1,
            end_s=11,
            ctx=_make_ctx(mock_config),
        )

        data = json.loads(result)["data"]
        assert data["streams"]["watts"] == [110, 120, 130]
        assert data["streams"]["time"] == [1, 2, 10]
        assert data["aliases_applied"] == {"power": "watts"}
        assert data["window"]["start_index"] == 1

    async def test_names_only_and_missing(self, mock_config, respx_mock):
        respx_mock.get("/activity/a1/streams.json").mock(
            side_effect=_streams_route({"time": [0, 1], "watts": [100, 110]})
        )

        result = await get_activity_streams(
            activity_id="a1",
            streams=["watts", "ventilation_typo"],
            ctx=_make_ctx(mock_config),
        )
        data = json.loads(result)["data"]
        assert data["missing_streams"] == ["ventilation_typo"]

        result = await get_activity_streams(
            activity_id="a1", names_only=True, ctx=_make_ctx(mock_config)
        )
        data = json.loads(result)["data"]
        assert "streams" not in data
        assert data["stream_lengths"] == {"time": 2, "watts": 2}

    async def test_end_before_start_rejected(self, mock_config):
        result = await get_activity_streams(
            activity_id="a1", start_s=10, end_s=5, ctx=_make_ctx(mock_config)
        )
        assert json.loads(result)["error"]["type"] == "validation_error"


_RIDE = {
    "time": list(range(8)),
    "watts": [200, 200, 50, 200, 100, 100, 300, 100],
    "heartrate": [120, 120, 110, 130, 130, 140, 140, 150],
    "tidal_volume_min": [60, 60, 40, 70, 50, 50, 90, 60],
    "TymeVentilation": [60, 60, 40, 70, 50, 50, 90, 60],
}


def _interval_stats_route(request):
    start = int(request.url.params["start_index"])
    end = int(request.url.params["end_index"])
    watts = _RIDE["watts"][start:end]
    hr = _RIDE["heartrate"][start:end]
    return Response(
        200,
        json={
            "start_index": start,
            "end_index": end,
            "average_watts": sum(watts) / len(watts),
            "average_heartrate": sum(hr) / len(hr),
            "decoupling": 1.5,
            "max_power_unused": None,
        },
    )


class TestGetStreamStats:
    def _mock(self, respx_mock, pvhr_status: int = 200):
        respx_mock.get("/activity/a1/streams.json").mock(side_effect=_streams_route(_RIDE))
        stats = respx_mock.get("/activity/a1/interval-stats").mock(
            side_effect=_interval_stats_route
        )
        respx_mock.get("/activity/a1/power-vs-hr.json").mock(
            return_value=Response(
                pvhr_status,
                json={
                    "powerHr": 1.4,
                    "powerHrFirst": 1.5,
                    "powerHrSecond": 1.3,
                    "decoupling": 8.7,
                    "hrLag": 15,
                    "warmup": 600,
                    "cooldown": 600,
                },
            )
        )
        return stats

    async def test_parts_use_intervals_icu_stats(self, mock_config, respx_mock):
        stats = self._mock(respx_mock)

        result = await get_stream_stats(activity_id="a1", parts=2, ctx=_make_ctx(mock_config))
        response = json.loads(result)

        windows = response["data"]["windows"]
        assert [(w["start_s"], w["end_s"]) for w in windows] == [(0, 4), (4, 8)]
        assert stats.call_count == 2
        first = windows[0]["icu"]
        assert first["avg_watts"] == 162.5
        assert first["decoupling_pct"] == 1.5
        assert first["hr_per_watt"] == round(120 / 162.5, 3)
        assert "filtered" not in windows[0]
        drift = response["analysis"]["ratio_drift_pct_vs_first_window"]["icu.hr_per_watt"]
        assert drift[0] == 0.0
        assert response["analysis"]["power_hr_whole_activity"]["decoupling_pct"] == 8.7

    async def test_filtered_with_min_power_lag_and_aliases(self, mock_config, respx_mock):
        self._mock(respx_mock)

        result = await get_stream_stats(
            activity_id="a1",
            streams=["VE"],
            min_power=150,
            lag_s=1,
            ctx=_make_ctx(mock_config),
        )
        data = json.loads(result)["data"]

        filtered = data["windows"][0]["filtered"]
        # Kept samples: indices 0, 1, 3, 6 (power >= 150)
        assert filtered["kept_s"] == 4
        assert filtered["excluded_s"] == 4
        assert filtered["streams"]["watts"]["mean"] == 225.0
        # HR paired one second later: indices 1, 2, 4, 7 -> 120, 110, 130, 150
        assert filtered["streams"]["heartrate"]["mean"] == 127.5
        assert filtered["ratios"]["heartrate_per_watt"] == round(127.5 / 225, 3)
        assert data["aliases_applied"] == {"VE": "tidal_volume_min"}

    async def test_power_smoothing_applies_to_filter(self, mock_config, respx_mock):
        self._mock(respx_mock)

        result = await get_stream_stats(
            activity_id="a1",
            min_power=150,
            power_smoothing_s=2,
            ctx=_make_ctx(mock_config),
        )
        filtered = json.loads(result)["data"]["windows"][0]["filtered"]
        # 2-s trailing means: 200, 200, 125, 125, 150, 100, 200, 200
        assert filtered["kept_s"] == 5

    async def test_missing_streams_reported_with_suggestions(self, mock_config, respx_mock):
        self._mock(respx_mock)

        result = await get_stream_stats(
            activity_id="a1",
            streams=["tymeventilation", "SmO2"],
            ctx=_make_ctx(mock_config),
        )
        data = json.loads(result)["data"]

        assert data["missing_streams"]["tymeventilation"]["did_you_mean"] == ["TymeVentilation"]
        assert data["missing_streams"]["SmO2"]["did_you_mean"] == []
        assert "filtered" in data["windows"][0]

    async def test_power_hr_failure_is_skipped(self, mock_config, respx_mock):
        self._mock(respx_mock, pvhr_status=404)

        result = await get_stream_stats(activity_id="a1", ctx=_make_ctx(mock_config))
        response = json.loads(result)
        assert len(response["data"]["windows"]) == 1
        assert "analysis" not in response or "power_hr_whole_activity" not in (
            response["analysis"] or {}
        )

    async def test_validation_errors(self, mock_config, respx_mock):
        self._mock(respx_mock)
        ctx = _make_ctx(mock_config)

        both = await get_stream_stats(activity_id="a1", parts=2, block_minutes=1, ctx=ctx)
        assert json.loads(both)["error"]["type"] == "validation_error"

        bad_window = await get_stream_stats(activity_id="a1", windows=[[5, 2]], ctx=ctx)
        assert json.loads(bad_window)["error"]["type"] == "validation_error"

        too_many = await get_stream_stats(activity_id="a1", parts=25, ctx=ctx)
        assert "limit" in json.loads(too_many)["error"]["message"]

        bad_power = await get_stream_stats(activity_id="a1", min_power=200, max_power=100, ctx=ctx)
        assert json.loads(bad_power)["error"]["type"] == "validation_error"

    async def test_no_streams(self, mock_config, respx_mock):
        respx_mock.get("/activity/a1/streams.json").mock(return_value=Response(200, json=[]))
        respx_mock.get("/activity/a1").mock(
            return_value=Response(
                200,
                json={"id": "a1", "type": "Ride", "start_date_local": "2026-05-19T08:00:00"},
            )
        )

        result = await get_stream_stats(activity_id="a1", ctx=_make_ctx(mock_config))
        assert json.loads(result)["data"]["windows"] == []


_RIDE_NO_TYME = {
    "time": list(range(4)),
    "watts": [200, 200, 200, 200],
    "heartrate": [120, 120, 120, 120],
    "respiration": [18.0, 18.0, 18.0, 18.0],
    "HrvBreath": [30, 32, None, 34],
}

_HRV_CUSTOM_STREAM = {
    "id": 7,
    "type": "ACTIVITY_STREAM",
    "name": "Respiration (HRV app)",
    "content": {"code": "HrvBreath", "fit_record_field": "RespirationRate"},
}


class TestStreamStatsBreathSource:
    def _mock(self, respx_mock, streams, custom_items):
        respx_mock.get("/activity/a1/streams.json").mock(side_effect=_streams_route(streams))
        respx_mock.get("/activity/a1/interval-stats").mock(
            return_value=Response(
                200,
                json={
                    "average_watts": 200,
                    "average_heartrate": 120,
                    "average_respiration": 18.0,
                    "average_tidal_volume": 183.3,
                },
            )
        )
        respx_mock.get("/activity/a1/power-vs-hr.json").mock(return_value=Response(404))
        return respx_mock.get("/athlete/i123456/custom-item").mock(
            return_value=Response(200, json=custom_items)
        )

    async def test_tyme_present_skips_custom_item_lookup(self, mock_config, respx_mock):
        items = self._mock(respx_mock, _RIDE, [_HRV_CUSTOM_STREAM])

        result = await get_stream_stats(activity_id="a1", ctx=_make_ctx(mock_config))
        data = json.loads(result)["data"]

        assert data["breath_rate_source"] == {"source": "tyme", "measured": True}
        assert data["windows"][0]["icu"]["avg_tidal_volume_l"] == 1.83
        assert items.call_count == 0

    async def test_hrv_app_used_without_tyme(self, mock_config, respx_mock):
        self._mock(respx_mock, _RIDE_NO_TYME, [_HRV_CUSTOM_STREAM])

        result = await get_stream_stats(
            activity_id="a1", streams=["BR"], ctx=_make_ctx(mock_config)
        )
        data = json.loads(result)["data"]

        assert data["breath_rate_source"]["source"] == "hrv_app"
        assert data["breath_rate_source"]["stream"] == "HrvBreath"
        assert data["breath_rate_source"]["measured"] is False
        icu = data["windows"][0]["icu"]
        assert icu["avg_breath_rate"] == 32.0  # mean of 30, 32, 34 (null skipped)
        assert icu["br_per_watt"] == 0.16
        assert data["aliases_applied"] == {"BR": "HrvBreath"}
        assert "HrvBreath" in data["windows"][0]["filtered"]["streams"]
        assert "respiration" not in data["windows"][0]["filtered"]["streams"]

    async def test_watch_estimate_labelled_without_tyme_or_hrv(self, mock_config, respx_mock):
        self._mock(respx_mock, _RIDE_NO_TYME, [])

        result = await get_stream_stats(activity_id="a1", ctx=_make_ctx(mock_config))
        data = json.loads(result)["data"]

        assert data["breath_rate_source"]["source"] == "watch"
        assert "Estimated" in data["breath_rate_source"]["note"]
        assert data["windows"][0]["icu"]["avg_breath_rate"] == 18.0
