"""Branch-coverage tests for athlete tools — TSB/ramp-rate buckets, sport-setting
detail, fitness-summary recommendations and error paths.

Complements `test_athlete_tools.py`, which covers happy-path basics.
"""

import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import Response

from intervals_icu_mcp.tools.athlete import get_athlete_profile, get_fitness_summary


def _ctx(mock_config):
    ctx = MagicMock()
    ctx.get_state = AsyncMock(return_value=mock_config)
    return ctx


class TestAthleteProfileFormBuckets:
    @pytest.mark.parametrize(
        ("tsb", "expected_status"),
        [
            (25.0, "very_fresh"),
            (10.0, "recovered"),
            (0.0, "optimal"),
            (-20.0, "fatigued"),
            (-40.0, "very_fatigued"),
        ],
    )
    async def test_form_status_buckets(self, tsb, expected_status, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456").mock(
            return_value=Response(
                200,
                json={
                    "id": "i123456",
                    "name": "Test",
                    "tsb": tsb,
                },
            )
        )

        result = await get_athlete_profile(ctx=_ctx(mock_config))
        response = json.loads(result)
        assert response["analysis"]["form_status"] == expected_status

    @pytest.mark.parametrize(
        ("ramp_rate", "expected_status"),
        [
            (10.0, "high_risk"),
            (6.0, "caution"),
            (2.0, "good"),
            (-3.0, "declining"),
            (-10.0, "declining_significantly"),
        ],
    )
    async def test_ramp_rate_buckets(self, ramp_rate, expected_status, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456").mock(
            return_value=Response(
                200,
                json={
                    "id": "i123456",
                    "name": "Test",
                    "ramp_rate": ramp_rate,
                },
            )
        )

        result = await get_athlete_profile(ctx=_ctx(mock_config))
        response = json.loads(result)
        assert response["analysis"]["ramp_rate_status"] == expected_status


class TestAthleteProfileSportSettings:
    async def test_pace_threshold_formatted(self, mock_config, respx_mock):
        """Run threshold_pace is rendered with the same unit suffixes as sport settings tools."""
        respx_mock.get("/athlete/i123456").mock(
            return_value=Response(
                200,
                json={
                    "id": "i123456",
                    "name": "Test",
                    "sportSettings": [
                        {
                            "id": 1,
                            "types": ["Run"],
                            "lthr": 170,
                            "threshold_pace": 4.0,
                            "pace_units": "MINS_KM",
                            "pace_load_type": "RUN",
                        },
                        {
                            "id": 2,
                            "types": ["Ride"],
                            "ftp": 260,
                            "indoor_ftp": 250,
                            "lthr": 165,
                        },
                        {
                            "id": 3,
                            "types": ["Swim"],
                            "threshold_pace": 100 / 120,  # m/s for 2:00/100m
                            "pace_units": "SECS_100M",
                            "pace_load_type": "SWIM",
                        },
                    ],
                },
            )
        )

        result = await get_athlete_profile(ctx=_ctx(mock_config))
        response = json.loads(result)
        sports = response["data"]["sports"]
        run = next(s for s in sports if s["type"] == "Run")
        assert run["fthr_bpm"] == 170
        assert run["pace_threshold"] == "4:00 /km"
        ride = next(s for s in sports if s["type"] == "Ride")
        assert ride["ftp_watts"] == 260
        assert ride["indoor_ftp_watts"] == 250
        swim = next(s for s in sports if s["type"] == "Swim")
        assert swim["swim_threshold"] == "2:00 /100m"


class TestAthleteProfileErrors:
    async def test_api_error_includes_suggestion(self, mock_config, respx_mock):
        respx_mock.get("/athlete/i123456").mock(return_value=Response(401, json={}))

        result = await get_athlete_profile(ctx=_ctx(mock_config))
        response = json.loads(result)
        assert response["error"]["type"] == "api_error"
        # API-error path adds a suggestions hint
        assert any("API key" in s for s in response["error"].get("suggestions", []))


class TestFitnessSummaryNoData:
    @patch("intervals_icu_mcp.tools.athlete.date")
    async def test_no_data_when_ctl_and_atl_missing(self, mock_date, mock_config, respx_mock):
        mock_date.today.return_value = date(2026, 3, 17)
        respx_mock.get("/athlete/i123456/wellness/2026-03-17").mock(
            return_value=Response(200, json={"id": "2026-03-17"})
        )

        result = await get_fitness_summary(ctx=_ctx(mock_config))
        response = json.loads(result)
        assert response["error"]["type"] == "no_data"


class TestFitnessSummaryRecommendations:
    @patch("intervals_icu_mcp.tools.athlete.date")
    async def test_overtrained_recommends_rest(self, mock_date, mock_config, respx_mock):
        mock_date.today.return_value = date(2026, 3, 17)
        respx_mock.get("/athlete/i123456/wellness/2026-03-17").mock(
            return_value=Response(
                200,
                json={
                    "id": "2026-03-17",
                    "ctl": 60.0,
                    "atl": 100.0,
                    "tsb": -40.0,  # < -30 → rest recommendation
                    "rampRate": 2.0,
                },
            )
        )

        result = await get_fitness_summary(ctx=_ctx(mock_config))
        response = json.loads(result)
        recs = response["analysis"]["recommendations"]
        assert any("rest" in r.lower() for r in recs)

    @patch("intervals_icu_mcp.tools.athlete.date")
    async def test_fresh_with_declining_recommends_load_increase(
        self, mock_date, mock_config, respx_mock
    ):
        """TSB > 5 and ramp_rate < 0 → recommendations to add training load."""
        mock_date.today.return_value = date(2026, 3, 17)
        respx_mock.get("/athlete/i123456/wellness/2026-03-17").mock(
            return_value=Response(
                200,
                json={
                    "id": "2026-03-17",
                    "ctl": 50.0,
                    "atl": 30.0,
                    "tsb": 20.0,
                    "rampRate": -2.0,
                },
            )
        )

        result = await get_fitness_summary(ctx=_ctx(mock_config))
        response = json.loads(result)
        recs = response["analysis"]["recommendations"]
        assert any("increase" in r.lower() or "add" in r.lower() for r in recs)

    @patch("intervals_icu_mcp.tools.athlete.date")
    async def test_fresh_with_climbing_recommends_breakthrough(
        self, mock_date, mock_config, respx_mock
    ):
        """TSB > 5 and ramp_rate >= 0 → recommendations for hard workouts."""
        mock_date.today.return_value = date(2026, 3, 17)
        respx_mock.get("/athlete/i123456/wellness/2026-03-17").mock(
            return_value=Response(
                200,
                json={
                    "id": "2026-03-17",
                    "ctl": 50.0,
                    "atl": 30.0,
                    "tsb": 20.0,
                    "rampRate": 3.0,
                },
            )
        )

        result = await get_fitness_summary(ctx=_ctx(mock_config))
        response = json.loads(result)
        recs = response["analysis"]["recommendations"]
        # "hard workouts" or "breakthrough" or "races"
        text = " ".join(recs).lower()
        assert "hard" in text or "race" in text or "breakthrough" in text

    @patch("intervals_icu_mcp.tools.athlete.date")
    async def test_intermediate_with_high_ramp_recommends_balance(
        self, mock_date, mock_config, respx_mock
    ):
        """TSB in [-30,-10) and ramp_rate > 5 → balance-with-recovery recommendation."""
        mock_date.today.return_value = date(2026, 3, 17)
        respx_mock.get("/athlete/i123456/wellness/2026-03-17").mock(
            return_value=Response(
                200,
                json={
                    "id": "2026-03-17",
                    "ctl": 50.0,
                    "atl": 70.0,
                    "tsb": -20.0,
                    "rampRate": 7.0,
                },
            )
        )

        result = await get_fitness_summary(ctx=_ctx(mock_config))
        response = json.loads(result)
        recs = response["analysis"]["recommendations"]
        text = " ".join(recs).lower()
        assert "balance" in text or "recovery" in text


class TestFitnessSummaryErrors:
    @patch("intervals_icu_mcp.tools.athlete.date")
    async def test_api_error(self, mock_date, mock_config, respx_mock):
        mock_date.today.return_value = date(2026, 3, 17)
        respx_mock.get("/athlete/i123456/wellness/2026-03-17").mock(
            return_value=Response(500, json={})
        )

        result = await get_fitness_summary(ctx=_ctx(mock_config))
        response = json.loads(result)
        assert response["error"]["type"] == "api_error"
