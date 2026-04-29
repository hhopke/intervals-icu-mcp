"""Tests for wellness tools."""

import json
from unittest.mock import AsyncMock, MagicMock

from httpx import Response

from intervals_icu_mcp.tools.wellness import (
    get_wellness_data,
    get_wellness_for_date,
    update_wellness,
)


class TestWellnessTools:
    """Tests for wellness tools."""

    async def test_update_wellness_success(self, mock_config, respx_mock):
        """Test successful wellness record update."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.put("/athlete/i123456/wellness").mock(
            return_value=Response(
                200,
                json={"id": "2026-03-17", "weight": 71.5, "restingHR": 45},
            )
        )

        result = await update_wellness(
            date="2026-03-17",
            weight=71.5,
            resting_hr=45,
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["date"] == "2026-03-17"
        assert response["data"]["body"]["weight_kg"] == 71.5
        assert response["data"]["heart"]["resting_hr"] == 45
        assert response["metadata"]["message"] == "Successfully updated wellness for 2026-03-17"

    async def test_update_wellness_validation_error(self, mock_config, respx_mock):
        """Test updating wellness with invalid date."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await update_wellness(
            date="invalid-date",
            weight=71.5,
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "error" in response
        assert "Invalid date format" in response["error"]["message"]

    async def test_update_wellness_no_data(self, mock_config, respx_mock):
        """Test updating wellness with no data fields."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await update_wellness(
            date="2026-03-17",
            ctx=mock_ctx,  # No other args provided
        )

        response = json.loads(result)
        assert "error" in response
        assert "No wellness data provided" in response["error"]["message"]

    async def test_get_wellness_for_date_surfaces_new_fields(self, mock_config, respx_mock):
        """Previously-dropped API fields and `spO2` alias must reach the output."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/wellness/2026-04-20").mock(
            return_value=Response(
                200,
                json={
                    "id": "2026-04-20",
                    "weight": 71.0,
                    "spO2": 97.5,
                    "vo2max": 54.2,
                    "abdomen": 82.4,
                    "carbohydrates": 320.5,
                    "protein": 140.2,
                    "fatTotal": 70.1,
                    "menstrualPhase": "FOLLICULAR",
                    "menstrualPhasePredicted": "OVULATING",
                    "locked": True,
                    "tempWeight": False,
                    "tempRestingHR": True,
                    "sportInfo": [
                        {"type": "Ride", "eftp": 252.3, "wPrime": 18000.0, "pMax": 1100.5},
                    ],
                },
            )
        )

        result = await get_wellness_for_date(date="2026-04-20", ctx=mock_ctx)
        response = json.loads(result)
        data = response["data"]

        assert data["body"]["vo2max"] == 54.2
        assert data["body"]["abdomen_cm"] == 82.4
        assert data["vitals"]["spo2_percent"] == 97.5
        assert data["nutrition"]["carbohydrates_g"] == 320.5
        assert data["nutrition"]["protein_g"] == 140.2
        assert data["nutrition"]["fat_total_g"] == 70.1
        assert data["other"]["menstrual_phase"] == "FOLLICULAR"
        assert data["other"]["menstrual_phase_predicted"] == "OVULATING"
        assert data["state_flags"] == {
            "locked": True,
            "temp_weight": False,
            "temp_resting_hr": True,
        }
        assert data["sport_info"] == [
            {"type": "Ride", "eftp": 252.3, "w_prime": 18000.0, "p_max": 1100.5}
        ]

    async def test_get_wellness_for_date_emits_scales(self, mock_config, respx_mock):
        """Scale labels must appear in metadata for subjective metrics in output."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/wellness/2026-04-20").mock(
            return_value=Response(
                200,
                json={
                    "id": "2026-04-20",
                    "fatigue": 4,
                    "mood": 3,
                    "sleepQuality": 2,
                    "sleepScore": 82,
                    "readiness": 75,
                },
            )
        )

        result = await get_wellness_for_date(date="2026-04-20", ctx=mock_ctx)
        response = json.loads(result)

        scales = response["metadata"]["scales"]
        assert "fatigue" in scales and "1-5" in scales["fatigue"]
        assert "mood" in scales
        assert "sleep_quality" in scales and "inverted" in scales["sleep_quality"]
        assert "sleep_score" in scales and "0-100" in scales["sleep_score"]
        assert "readiness" in scales and "0-100" in scales["readiness"]
        # Scales for fields not present should be absent
        assert "soreness" not in scales
        assert "stress" not in scales

    async def test_get_wellness_data_includes_scales_and_extra_fields(
        self, mock_config, respx_mock
    ):
        """List endpoint should also surface new fields and scale labels."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/wellness").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": "2026-04-20",
                        "fatigue": 3,
                        "carbohydrates": 250.0,
                        "vo2max": 53.0,
                    },
                    {
                        "id": "2026-04-19",
                        "fatigue": 2,
                        "protein": 130.0,
                    },
                ],
            )
        )

        result = await get_wellness_data(days_back=2, ctx=mock_ctx)
        response = json.loads(result)

        assert response["data"]["count"] == 2
        days = response["data"]["wellness_data"]
        # Most recent first
        assert days[0]["date"] == "2026-04-20"
        assert days[0]["nutrition"]["carbohydrates_g"] == 250.0
        assert days[0]["body"]["vo2max"] == 53.0
        assert days[1]["nutrition"]["protein_g"] == 130.0
        assert "fatigue" in response["metadata"]["scales"]

    async def test_update_wellness_new_fields(self, mock_config, respx_mock):
        """New fields (injury, body metrics, vitals, lab, menstrual, locked) round-trip correctly."""
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.put("/athlete/i123456/wellness").mock(
            return_value=Response(
                200,
                json={
                    "id": "2026-04-29",
                    "injury": 2,
                    "bodyFat": 18.5,
                    "abdomen": 80.0,
                    "vo2max": 55.0,
                    "systolic": 118,
                    "diastolic": 76,
                    "spO2": 98.0,
                    "respiration": 14.5,
                    "bloodGlucose": 5.2,
                    "lactate": 1.8,
                    "menstrualPhase": "FOLLICULAR",
                    "locked": True,
                },
            )
        )

        result = await update_wellness(
            date="2026-04-29",
            injury=2,
            body_fat=18.5,
            abdomen=80.0,
            vo2max=55.0,
            systolic=118,
            diastolic=76,
            spo2=98.0,
            respiration=14.5,
            blood_glucose=5.2,
            lactate=1.8,
            menstrual_phase="FOLLICULAR",
            locked=True,
            ctx=mock_ctx,
        )

        response = json.loads(result)
        data = response["data"]
        assert data["subjective"]["injury"] == 2
        assert data["body"]["body_fat_percent"] == 18.5
        assert data["body"]["abdomen_cm"] == 80.0
        assert data["body"]["vo2max"] == 55.0
        assert data["vitals"]["systolic_mmhg"] == 118
        assert data["vitals"]["diastolic_mmhg"] == 76
        assert data["vitals"]["spo2_percent"] == 98.0
        assert data["vitals"]["respiration_rate"] == 14.5
        assert data["other"]["blood_glucose_mmol_per_l"] == 5.2
        assert data["other"]["lactate_mmol_per_l"] == 1.8
        assert data["other"]["menstrual_phase"] == "FOLLICULAR"
        assert data["state_flags"]["locked"] is True
        assert "injury" in response["metadata"]["scales"]

    async def test_wellness_model_preserves_unknown_fields(self):
        """`extra=allow` keeps future API additions accessible on the model."""
        from intervals_icu_mcp.models import Wellness

        record = Wellness.model_validate({"id": "2026-04-20", "weight": 70.0, "futureMetric": 42})
        # Unknown field is preserved (not silently dropped)
        assert getattr(record, "futureMetric", None) == 42
