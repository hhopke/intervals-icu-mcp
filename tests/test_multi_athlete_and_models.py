"""Tests for multi-athlete support, Pydantic model aliases, and date handling."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import Response

from intervals_icu_mcp.tools.activities import get_recent_activities, search_activities
from intervals_icu_mcp.tools.athlete import (
    get_athlete_profile,
    get_fitness_chart,
    get_fitness_summary,
)
from intervals_icu_mcp.tools.event_management import (
    bulk_create_events,
    bulk_delete_events,
    create_event,
    delete_event,
    duplicate_events,
    update_event,
)
from intervals_icu_mcp.tools.events import get_calendar_events, get_event, get_upcoming_workouts
from intervals_icu_mcp.tools.wellness import (
    get_wellness_data,
    get_wellness_for_date,
    update_wellness,
)

# ==================== Fixtures ====================


def make_ctx(config):
    ctx = MagicMock()
    ctx.get_state = AsyncMock(return_value=config)
    return ctx


COACH_ATHLETE = "i999888"


def _patch_direct_config(monkeypatch, mod, config):
    """gear.py and sport_settings.py bypass the middleware and call load_config()
    themselves; validate_credentials() also rejects the fixture's placeholder
    athlete id, so both have to be patched for those modules."""
    if hasattr(mod, "load_config"):
        monkeypatch.setattr(mod, "load_config", lambda: config)
        monkeypatch.setattr(mod, "validate_credentials", lambda _c: True)


# ==================== Multi-athlete: Activities ====================


class TestMultiAthleteActivities:
    """Test athlete_id passthrough on activity tools."""

    async def test_get_recent_activities_with_athlete_id(self, mock_config, respx_mock):
        """athlete_id routes the request to the correct athlete endpoint."""
        respx_mock.get(f"/athlete/{COACH_ATHLETE}/activities").mock(
            return_value=Response(200, json=[])
        )

        result = await get_recent_activities(
            limit=5, days_back=7, athlete_id=COACH_ATHLETE, ctx=make_ctx(mock_config)
        )
        response = json.loads(result)
        assert response["data"]["count"] == 0

        # Verify the request went to the coach's athlete, not the default
        assert (
            respx_mock.calls.last.request.url.path == f"/api/v1/athlete/{COACH_ATHLETE}/activities"
        )

    async def test_get_recent_activities_default_athlete(self, mock_config, respx_mock):
        """Without athlete_id, uses the configured default."""
        respx_mock.get("/athlete/i123456/activities").mock(return_value=Response(200, json=[]))

        result = await get_recent_activities(limit=5, days_back=7, ctx=make_ctx(mock_config))
        response = json.loads(result)
        assert response["data"]["count"] == 0
        assert respx_mock.calls.last.request.url.path == "/api/v1/athlete/i123456/activities"

    async def test_search_activities_with_athlete_id(self, mock_config, respx_mock):
        """search_activities passes athlete_id to the API."""
        respx_mock.get(f"/athlete/{COACH_ATHLETE}/activities/search").mock(
            return_value=Response(200, json=[])
        )

        result = await search_activities(
            query="tempo", athlete_id=COACH_ATHLETE, ctx=make_ctx(mock_config)
        )
        response = json.loads(result)
        assert "data" in response
        assert (
            respx_mock.calls.last.request.url.path
            == f"/api/v1/athlete/{COACH_ATHLETE}/activities/search"
        )


# ==================== Multi-athlete: Fitness / Wellness ====================


class TestMultiAthleteFitness:
    """Test athlete_id passthrough on the fitness/fatigue/form (CTL/ATL/TSB) tools.

    Regression guard for #99: these tools previously exposed no athlete_id at all,
    so a coach's request silently returned the default profile's numbers.
    """

    async def test_get_fitness_summary_with_athlete_id(
        self, mock_config, respx_mock, mock_wellness_data
    ):
        from datetime import date

        today = date.today().isoformat()
        respx_mock.get(f"/athlete/{COACH_ATHLETE}/wellness/{today}").mock(
            return_value=Response(200, json={**mock_wellness_data, "id": today, "ctl": 71.0})
        )

        result = await get_fitness_summary(athlete_id=COACH_ATHLETE, ctx=make_ctx(mock_config))
        response = json.loads(result)

        assert response["data"]["fitness_metrics"]["ctl"]["value"] == 71.0
        # The response must name whose numbers these are — the #99 failure was
        # undetectable precisely because it never did.
        assert response["data"]["athlete_id"] == COACH_ATHLETE
        assert (
            respx_mock.calls.last.request.url.path
            == f"/api/v1/athlete/{COACH_ATHLETE}/wellness/{today}"
        )

    async def test_fitness_summary_no_data_names_the_athlete(self, mock_config, respx_mock):
        """The no-data message must not tell a coach to go do the athlete's training."""
        from datetime import date

        today = date.today().isoformat()
        respx_mock.get(f"/athlete/{COACH_ATHLETE}/wellness/{today}").mock(
            return_value=Response(200, json={"id": today})
        )

        result = await get_fitness_summary(athlete_id=COACH_ATHLETE, ctx=make_ctx(mock_config))
        response = json.loads(result)

        assert response["error"]["type"] == "no_data"
        assert COACH_ATHLETE in response["error"]["message"]
        assert "Complete some activities" not in response["error"]["message"]

    async def test_get_fitness_summary_default_athlete(
        self, mock_config, respx_mock, mock_wellness_data
    ):
        """Without athlete_id, uses the configured default."""
        from datetime import date

        today = date.today().isoformat()
        respx_mock.get(f"/athlete/i123456/wellness/{today}").mock(
            return_value=Response(200, json={**mock_wellness_data, "id": today})
        )

        result = await get_fitness_summary(ctx=make_ctx(mock_config))
        response = json.loads(result)
        assert response["data"]["athlete_id"] == "i123456"
        assert respx_mock.calls.last.request.url.path == f"/api/v1/athlete/i123456/wellness/{today}"

    async def test_get_athlete_profile_with_athlete_id(
        self, mock_config, respx_mock, mock_athlete_data
    ):
        respx_mock.get(f"/athlete/{COACH_ATHLETE}").mock(
            return_value=Response(
                200, json={**mock_athlete_data, "id": COACH_ATHLETE, "name": "Coached Athlete"}
            )
        )

        result = await get_athlete_profile(athlete_id=COACH_ATHLETE, ctx=make_ctx(mock_config))
        response = json.loads(result)

        assert response["data"]["profile"]["id"] == COACH_ATHLETE
        assert response["data"]["profile"]["name"] == "Coached Athlete"
        assert respx_mock.calls.last.request.url.path == f"/api/v1/athlete/{COACH_ATHLETE}"

    async def test_get_athlete_profile_default_athlete(
        self, mock_config, respx_mock, mock_athlete_data
    ):
        respx_mock.get("/athlete/i123456").mock(return_value=Response(200, json=mock_athlete_data))

        result = await get_athlete_profile(ctx=make_ctx(mock_config))
        response = json.loads(result)

        assert response["data"]["profile"]["id"] == "i123456"
        assert respx_mock.calls.last.request.url.path == "/api/v1/athlete/i123456"

    async def test_get_fitness_chart_with_athlete_id(self, mock_config, respx_mock):
        respx_mock.get(f"/athlete/{COACH_ATHLETE}/wellness").mock(
            return_value=Response(200, json=[])
        )

        result = await get_fitness_chart(
            days_back=7, days_ahead=0, athlete_id=COACH_ATHLETE, ctx=make_ctx(mock_config)
        )
        response = json.loads(result)

        assert response["data"]["count"] == 0
        assert response["data"]["athlete_id"] == COACH_ATHLETE
        assert respx_mock.calls.last.request.url.path == f"/api/v1/athlete/{COACH_ATHLETE}/wellness"


class TestMultiAthleteWellness:
    """Test athlete_id passthrough on wellness tools (records carry CTL/ATL)."""

    async def test_get_wellness_data_with_athlete_id(self, mock_config, respx_mock):
        respx_mock.get(f"/athlete/{COACH_ATHLETE}/wellness").mock(
            return_value=Response(200, json=[])
        )

        result = await get_wellness_data(
            days_back=7, athlete_id=COACH_ATHLETE, ctx=make_ctx(mock_config)
        )
        json.loads(result)
        assert respx_mock.calls.last.request.url.path == f"/api/v1/athlete/{COACH_ATHLETE}/wellness"

    async def test_get_wellness_for_date_with_athlete_id(
        self, mock_config, respx_mock, mock_wellness_data
    ):
        respx_mock.get(f"/athlete/{COACH_ATHLETE}/wellness/2026-04-20").mock(
            return_value=Response(200, json={**mock_wellness_data, "id": "2026-04-20"})
        )

        result = await get_wellness_for_date(
            date="2026-04-20", athlete_id=COACH_ATHLETE, ctx=make_ctx(mock_config)
        )
        json.loads(result)
        assert (
            respx_mock.calls.last.request.url.path
            == f"/api/v1/athlete/{COACH_ATHLETE}/wellness/2026-04-20"
        )

    async def test_update_wellness_with_athlete_id(
        self, mock_config, respx_mock, mock_wellness_data
    ):
        """Writes must land on the coached athlete, not the authenticated one."""
        respx_mock.put(f"/athlete/{COACH_ATHLETE}/wellness").mock(
            return_value=Response(200, json={**mock_wellness_data, "id": "2026-04-20"})
        )

        result = await update_wellness(
            date="2026-04-20", hrv=68.0, athlete_id=COACH_ATHLETE, ctx=make_ctx(mock_config)
        )
        json.loads(result)
        assert respx_mock.calls.last.request.url.path == f"/api/v1/athlete/{COACH_ATHLETE}/wellness"


# ==================== Multi-athlete: remaining read surface ====================


class TestMultiAthleteRemainingReads:
    """athlete_id passthrough on curves, sport settings, gear, library and search.

    Covers the tools closed out by #101. Each asserts the request path, since a
    silently-dropped parameter still returns a valid-looking 200.
    """

    @pytest.mark.parametrize(
        "tool_path,func_name,route,kwargs",
        [
            ("performance", "get_power_curves", "power-curves", {}),
            ("curves", "get_hr_curves", "hr-curves", {}),
            ("curves", "get_pace_curves", "pace-curves", {}),
            ("sport_settings", "get_sport_settings", "sport-settings", {}),
            ("gear", "get_gear_list", "gear", {}),
            ("workout_library", "get_workout_library", "folders", {}),
            ("workout_library", "get_workouts_in_folder", "workouts", {"folder_id": 1}),
            ("activities", "search_activities_full", "activities/search-full", {"query": "x"}),
            ("activities", "get_activities_around", "activities-around", {"activity_id": "a1"}),
        ],
    )
    async def test_read_tool_routes_to_requested_athlete(
        self, mock_config, respx_mock, monkeypatch, tool_path, func_name, route, kwargs
    ):
        import importlib

        mod = importlib.import_module(f"intervals_icu_mcp.tools.{tool_path}")
        func = getattr(mod, func_name)
        # gear.py and sport_settings.py read credentials via load_config() instead of
        # the middleware-injected ctx state, so mock_config alone does not reach them.
        _patch_direct_config(monkeypatch, mod, mock_config)

        respx_mock.get(f"/athlete/{COACH_ATHLETE}/{route}").mock(
            return_value=Response(200, json=[])
        )

        await func(athlete_id=COACH_ATHLETE, ctx=make_ctx(mock_config), **kwargs)

        assert respx_mock.calls.last.request.url.path == f"/api/v1/athlete/{COACH_ATHLETE}/{route}"

    async def test_gear_write_routes_to_requested_athlete(
        self, mock_config, respx_mock, monkeypatch
    ):
        """Writes must land on the coached athlete, not the authenticated one."""
        from intervals_icu_mcp.tools import gear

        _patch_direct_config(monkeypatch, gear, mock_config)
        respx_mock.put(f"/athlete/{COACH_ATHLETE}/gear/b1").mock(
            return_value=Response(200, json={"id": "b1", "name": "Bike"})
        )

        await gear.update_gear(
            gear_id="b1", name="Bike", athlete_id=COACH_ATHLETE, ctx=make_ctx(mock_config)
        )

        assert respx_mock.calls.last.request.url.path == f"/api/v1/athlete/{COACH_ATHLETE}/gear/b1"

    async def test_sport_settings_write_routes_to_requested_athlete(
        self, mock_config, respx_mock, monkeypatch
    ):
        from intervals_icu_mcp.tools import sport_settings

        _patch_direct_config(monkeypatch, sport_settings, mock_config)
        respx_mock.put(f"/athlete/{COACH_ATHLETE}/sport-settings/7").mock(
            return_value=Response(200, json={"id": 7, "types": ["Ride"], "ftp": 260})
        )

        await sport_settings.update_sport_settings(
            sport_id=7, ftp=260, athlete_id=COACH_ATHLETE, ctx=make_ctx(mock_config)
        )

        assert COACH_ATHLETE in respx_mock.calls.last.request.url.path


# ==================== Multi-athlete: Events ====================


class TestMultiAthleteEvents:
    """Test athlete_id passthrough on event tools."""

    async def test_get_calendar_events_with_athlete_id(self, mock_config, respx_mock):
        respx_mock.get(f"/athlete/{COACH_ATHLETE}/events").mock(return_value=Response(200, json=[]))

        result = await get_calendar_events(
            days_ahead=7, athlete_id=COACH_ATHLETE, ctx=make_ctx(mock_config)
        )
        response = json.loads(result)
        assert response["data"]["count"] == 0
        assert COACH_ATHLETE in respx_mock.calls.last.request.url.path

    async def test_get_upcoming_workouts_with_athlete_id(self, mock_config, respx_mock):
        respx_mock.get(f"/athlete/{COACH_ATHLETE}/events").mock(return_value=Response(200, json=[]))

        result = await get_upcoming_workouts(
            limit=5, athlete_id=COACH_ATHLETE, ctx=make_ctx(mock_config)
        )
        json.loads(result)  # verify valid JSON response
        assert COACH_ATHLETE in respx_mock.calls.last.request.url.path

    async def test_get_event_with_athlete_id(self, mock_config, respx_mock, mock_event_data):
        respx_mock.get(f"/athlete/{COACH_ATHLETE}/events/1001").mock(
            return_value=Response(200, json=mock_event_data)
        )

        result = await get_event(event_id=1001, athlete_id=COACH_ATHLETE, ctx=make_ctx(mock_config))
        response = json.loads(result)
        assert response["data"]["id"] == 1001
        assert COACH_ATHLETE in respx_mock.calls.last.request.url.path


# ==================== Multi-athlete: Event Management ====================


class TestMultiAthleteEventManagement:
    """Test athlete_id passthrough on event management tools."""

    async def test_create_event_with_athlete_id(self, mock_config, respx_mock, mock_event_data):
        respx_mock.post(f"/athlete/{COACH_ATHLETE}/events").mock(
            return_value=Response(200, json=mock_event_data)
        )

        result = await create_event(
            start_date="2026-03-20",
            name="Test Workout",
            category="WORKOUT",
            athlete_id=COACH_ATHLETE,
            ctx=make_ctx(mock_config),
        )
        response = json.loads(result)
        assert "data" in response
        assert COACH_ATHLETE in respx_mock.calls.last.request.url.path

    async def test_update_event_with_athlete_id(self, mock_config, respx_mock, mock_event_data):
        respx_mock.put(f"/athlete/{COACH_ATHLETE}/events/1001").mock(
            return_value=Response(200, json=mock_event_data)
        )

        result = await update_event(
            event_id=1001,
            name="Updated Workout",
            athlete_id=COACH_ATHLETE,
            ctx=make_ctx(mock_config),
        )
        response = json.loads(result)
        assert "data" in response
        assert COACH_ATHLETE in respx_mock.calls.last.request.url.path

    async def test_delete_event_with_athlete_id(self, mock_config, respx_mock):
        from datetime import date, timedelta

        future = (date.today() + timedelta(days=7)).isoformat()
        respx_mock.get(f"/athlete/{COACH_ATHLETE}/events/1001").mock(
            return_value=Response(
                200,
                json={
                    "id": 1001,
                    "start_date_local": future,
                    "name": "Future",
                    "category": "WORKOUT",
                },
            )
        )
        respx_mock.delete(f"/athlete/{COACH_ATHLETE}/events/1001").mock(
            return_value=Response(200, json={})
        )

        result = await delete_event(
            event_id=1001, athlete_id=COACH_ATHLETE, ctx=make_ctx(mock_config)
        )
        response = json.loads(result)
        assert response["data"]["deleted"] == [1001]
        assert COACH_ATHLETE in respx_mock.calls.last.request.url.path

    async def test_duplicate_events_with_athlete_id(self, mock_config, respx_mock, mock_event_data):
        dup_data = [{**mock_event_data, "id": 1002, "start_date_local": "2026-03-25"}]
        respx_mock.post(f"/athlete/{COACH_ATHLETE}/duplicate-events").mock(
            return_value=Response(200, json=dup_data)
        )

        result = await duplicate_events(
            event_ids="[1001]",
            num_copies=1,
            weeks_between=1,
            athlete_id=COACH_ATHLETE,
            ctx=make_ctx(mock_config),
        )
        response = json.loads(result)
        assert response["data"]["duplicated_count"] == 1
        assert COACH_ATHLETE in respx_mock.calls.last.request.url.path

    async def test_bulk_create_events_with_athlete_id(self, mock_config, respx_mock):
        created = [
            {"id": 2001, "start_date_local": "2026-03-20", "category": "WORKOUT", "name": "W1"},
            {"id": 2002, "start_date_local": "2026-03-21", "category": "WORKOUT", "name": "W2"},
        ]
        respx_mock.post(f"/athlete/{COACH_ATHLETE}/events/bulk").mock(
            return_value=Response(200, json=created)
        )

        events_json = json.dumps(
            [
                {"start_date_local": "2026-03-20", "name": "W1", "category": "WORKOUT"},
                {"start_date_local": "2026-03-21", "name": "W2", "category": "WORKOUT"},
            ]
        )

        result = await bulk_create_events(
            events=events_json, athlete_id=COACH_ATHLETE, ctx=make_ctx(mock_config)
        )
        response = json.loads(result)
        assert len(response["data"]["events"]) == 2
        assert COACH_ATHLETE in respx_mock.calls.last.request.url.path

    async def test_bulk_delete_events_with_athlete_id(self, mock_config, respx_mock):
        from datetime import date, timedelta

        future = (date.today() + timedelta(days=7)).isoformat()
        for eid in (2001, 2002):
            respx_mock.get(f"/athlete/{COACH_ATHLETE}/events/{eid}").mock(
                return_value=Response(
                    200,
                    json={
                        "id": eid,
                        "start_date_local": future,
                        "name": f"E{eid}",
                        "category": "WORKOUT",
                    },
                )
            )
        respx_mock.put(f"/athlete/{COACH_ATHLETE}/events/bulk-delete").mock(
            return_value=Response(200, json={"deleted": 2})
        )

        result = await bulk_delete_events(
            event_ids="[2001, 2002]",
            athlete_id=COACH_ATHLETE,
            ctx=make_ctx(mock_config),
        )
        response = json.loads(result)
        assert response["data"]["deleted"] == [2001, 2002]
        assert response["data"]["deleted_count"] == 2
        assert COACH_ATHLETE in respx_mock.calls.last.request.url.path


# ==================== Pydantic Aliases (watts fields) ====================


class TestSportSettingsModelMapping:
    """SportSettings and Athlete parse Intervals.icu API field names."""

    def test_sport_settings_maps_lthr_types_and_threshold_pace(self):
        from intervals_icu_mcp.models import SportSettings

        settings = SportSettings.model_validate(
            {
                "id": 1,
                "types": ["Ride", "VirtualRide"],
                "ftp": 242,
                "indoor_ftp": 232,
                "lthr": 176,
            }
        )

        assert settings.type == "Ride"
        assert settings.ftp == 242
        assert settings.indoor_ftp == 232
        assert settings.fthr == 176

    def test_sport_settings_maps_swim_threshold_from_mps(self):
        from intervals_icu_mcp.models import SportSettings

        # API stores swim threshold as SPEED (m/s); 1:30/100m == 100/90 m/s -> 1.5 min.
        settings = SportSettings.model_validate(
            {
                "id": 3,
                "types": ["Swim"],
                "threshold_pace": 100 / 90,
                "pace_units": "SECS_100M",
                "pace_load_type": "SWIM",
            }
        )

        assert settings.type == "Swim"
        assert settings.swim_threshold == pytest.approx(1.5)
        assert settings.pace_threshold is None

    def test_sport_settings_coerces_null_zone_arrays(self):
        from intervals_icu_mcp.models import SportSettings

        # A Run record carries power_zones: null, not [].
        settings = SportSettings.model_validate(
            {
                "id": 2,
                "types": ["Run"],
                "power_zones": None,
                "power_zone_names": None,
                "hr_zones": [145, 153],
                "pace_zones": None,
            }
        )

        assert settings.power_zones == []
        assert settings.power_zone_names == []
        assert settings.pace_zones == []
        assert settings.hr_zones == [145, 153]

    def test_sport_settings_parses_zone_config(self):
        from intervals_icu_mcp.models import SportSettings

        settings = SportSettings.model_validate(
            {
                "id": 1,
                "types": ["Ride"],
                "max_hr": 204,
                "hr_zones": [138, 204],
                "hr_zone_names": ["Recovery", "Anaerobic"],
                "hr_load_type": "HRSS",
                "hrrc_min_percent": 100.0,
                "power_zones": [55, 999],
                "sweet_spot_min": 84,
                "sweet_spot_max": 97,
                "warmup_time": 1200,
                "cooldown_time": 600,
            }
        )

        assert settings.max_hr == 204
        assert settings.hr_zones == [138, 204]
        assert settings.hr_zone_names == ["Recovery", "Anaerobic"]
        assert settings.hr_load_type == "HRSS"
        assert settings.hrrc_min_percent == 100.0
        assert settings.power_zones == [55, 999]
        assert settings.sweet_spot_min == 84
        assert settings.sweet_spot_max == 97
        assert settings.warmup_time == 1200
        assert settings.cooldown_time == 600

    def test_build_sport_settings_api_payload_swim_sends_mps(self):
        from intervals_icu_mcp.sport_settings_format import build_sport_settings_api_payload

        # 1:30/100m (1.5 min) is stored as SPEED: 100 m / 90 s = 100/90 m/s.
        payload = build_sport_settings_api_payload(swim_threshold=1.5)
        assert payload["threshold_pace"] == pytest.approx(100 / 90)
        assert payload["pace_units"] == "SECS_100M"
        assert payload["pace_load_type"] == "SWIM"

    def test_build_sport_settings_api_payload_rejects_both_pace_params(self):
        from intervals_icu_mcp.sport_settings_format import build_sport_settings_api_payload

        with pytest.raises(ValueError, match="pace_threshold and swim_threshold"):
            build_sport_settings_api_payload(pace_threshold=4.5, swim_threshold=1.5)

    def test_athlete_maps_sport_settings_camel_case(self):
        from intervals_icu_mcp.models import Athlete

        athlete = Athlete.model_validate(
            {
                "id": "i123456",
                "name": "Test",
                "sportSettings": [
                    {
                        "id": 1,
                        "types": ["Ride"],
                        "ftp": 250,
                        "indoor_ftp": 235,
                        "lthr": 165,
                    }
                ],
            }
        )

        assert len(athlete.sport_settings) == 1
        assert athlete.sport_settings[0].type == "Ride"
        assert athlete.sport_settings[0].indoor_ftp == 235
        assert athlete.sport_settings[0].fthr == 165


class TestNullListDictFieldCoercion:
    """Several endpoints return explicit `null` (not a missing key) for list/dict fields
    when there's no computed data yet for that record — e.g. sportInfo on wellness days
    without processed activities. Pydantic's `default_factory` only applies when the key
    is absent, so each of these fields needs a `mode="before"` validator to coerce None
    to an empty list/dict instead of raising a validation error. Wellness.sport_info has
    its own dedicated test in test_wellness_tools.py; this covers the rest."""

    def test_athlete_handles_null_sport_settings(self):
        from intervals_icu_mcp.models import Athlete

        athlete = Athlete.model_validate({"id": "i123456", "name": "Test", "sportSettings": None})
        assert athlete.sport_settings == []

    def test_curve_data_handles_null_list_fields(self):
        from intervals_icu_mcp.models import CurveData

        curve = CurveData.model_validate(
            {"secs": None, "values": None, "activity_id": None, "watts_per_kg": None}
        )
        assert curve.secs == []
        assert curve.values == []
        assert curve.activity_id == []
        assert curve.watts_per_kg == []

    def test_curve_set_handles_null_curves(self):
        from intervals_icu_mcp.models import CurveSet

        curve_set = CurveSet.model_validate({"list": None})
        assert curve_set.curves == []

    def test_fitness_summary_handles_null_interpretation(self):
        from intervals_icu_mcp.models import FitnessSummary

        summary = FitnessSummary.model_validate({"interpretation": None})
        assert summary.interpretation == {}

    def test_intervals_dto_handles_null_icu_intervals(self):
        from intervals_icu_mcp.models import IntervalsDTO

        dto = IntervalsDTO.model_validate({"icu_intervals": None})
        assert dto.icu_intervals == []

    def test_best_efforts_handles_null_efforts(self):
        from intervals_icu_mcp.models import BestEfforts

        efforts = BestEfforts.model_validate({"efforts": None})
        assert efforts.efforts == []

    def test_gear_handles_null_reminders(self):
        from intervals_icu_mcp.models import Gear

        gear = Gear.model_validate({"id": "b123", "reminders": None})
        assert gear.reminders == []


class TestPydanticAliases:
    """Test that icu_average_watts / icu_weighted_avg_watts map correctly."""

    async def test_activity_watts_aliases(self, mock_config, respx_mock):
        """API returns icu_average_watts; model should populate average_watts."""
        activity_data = [
            {
                "id": "a1",
                "start_date_local": "2026-03-17T08:00:00",
                "name": "Power Ride",
                "type": "Ride",
                "icu_average_watts": 220,
                "distance": 50000.0,
                "moving_time": 3600,
            }
        ]
        respx_mock.get("/athlete/i123456/activities").mock(
            return_value=Response(200, json=activity_data)
        )

        result = await get_recent_activities(limit=1, days_back=7, ctx=make_ctx(mock_config))
        response = json.loads(result)

        activities = response["data"]["activities"]
        assert len(activities) == 1
        assert activities[0]["average_watts"] == 220


# ==================== Date Handling ====================


class TestDateHandling:
    """Test ISO-8601 date parsing and T00:00:00 suffix."""

    async def test_calendar_events_parses_full_iso_dates(self, mock_config, respx_mock):
        """get_calendar_events handles full ISO-8601 datetime strings from API."""
        events = [
            {
                "id": 3001,
                "start_date_local": "2026-03-18T00:00:00",
                "category": "WORKOUT",
                "name": "Morning Run",
                "type": "Run",
            }
        ]
        respx_mock.get("/athlete/i123456/events").mock(return_value=Response(200, json=events))

        result = await get_calendar_events(days_ahead=7, ctx=make_ctx(mock_config))
        response = json.loads(result)
        assert response["data"]["summary"]["total_events"] == 1

    async def test_create_event_adds_time_suffix(self, mock_config, respx_mock, mock_event_data):
        """create_event adds T00:00:00 suffix to date-only strings."""
        respx_mock.post("/athlete/i123456/events").mock(
            return_value=Response(200, json=mock_event_data)
        )

        await create_event(
            start_date="2026-03-20",
            name="Test",
            category="WORKOUT",
            ctx=make_ctx(mock_config),
        )

        request_body = json.loads(respx_mock.calls.last.request.content)
        assert request_body["start_date_local"] == "2026-03-20T00:00:00"

    async def test_duplicate_events_sends_correct_body(
        self, mock_config, respx_mock, mock_event_data
    ):
        """duplicate_events sends eventIds, numCopies, weeksBetween to the correct endpoint."""
        dup_data = [{**mock_event_data, "id": 1002}]
        respx_mock.post("/athlete/i123456/duplicate-events").mock(
            return_value=Response(200, json=dup_data)
        )

        await duplicate_events(
            event_ids="[1001]", num_copies=2, weeks_between=3, ctx=make_ctx(mock_config)
        )

        request_body = json.loads(respx_mock.calls.last.request.content)
        assert request_body["eventIds"] == [1001]
        assert request_body["numCopies"] == 2
        assert request_body["weeksBetween"] == 3
