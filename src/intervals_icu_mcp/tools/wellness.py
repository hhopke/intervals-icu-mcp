"""Wellness and health tracking tools for Intervals.icu MCP server."""

from datetime import datetime, timedelta
from typing import Annotated, Any

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..response_builder import ResponseBuilder


async def get_wellness_data(
    days_back: Annotated[int, "Number of days to look back"] = 7,
    ctx: Context | None = None,
) -> str:
    """Get wellness data for recent days.

    Returns wellness metrics including HRV, sleep, resting heart rate,
    mood, fatigue, soreness, and other health markers.

    Args:
        days_back: Number of days to retrieve (default 7)

    Returns:
        JSON string with wellness data
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        # Calculate date range
        oldest_date = datetime.now() - timedelta(days=days_back)
        oldest = oldest_date.strftime("%Y-%m-%d")
        newest = datetime.now().strftime("%Y-%m-%d")

        async with ICUClient(config) as client:
            wellness_records = await client.get_wellness(
                oldest=oldest,
                newest=newest,
            )

            if not wellness_records:
                return ResponseBuilder.build_response(
                    data={"wellness_data": [], "count": 0},
                    metadata={"message": f"No wellness data found for the last {days_back} days"},
                )

            # Sort by date (most recent first)
            wellness_records.sort(key=lambda x: x.id, reverse=True)

            wellness_data: list[dict[str, Any]] = []
            for record in wellness_records:
                day_data: dict[str, Any] = {"date": record.id}

                # Sleep metrics
                sleep: dict[str, Any] = {}
                if record.sleep_secs:
                    sleep["duration_seconds"] = record.sleep_secs
                if record.sleep_quality:
                    sleep["quality"] = record.sleep_quality
                if record.sleep_score:
                    sleep["score"] = round(record.sleep_score, 0)
                if record.avg_sleeping_hr:
                    sleep["avg_sleeping_hr"] = round(record.avg_sleeping_hr, 0)
                if sleep:
                    day_data["sleep"] = sleep

                # HRV and resting HR
                heart: dict[str, Any] = {}
                if record.hrv:
                    heart["hrv_rmssd"] = round(record.hrv, 1)
                if record.hrv_sdnn:
                    heart["hrv_sdnn"] = round(record.hrv_sdnn, 1)
                if record.resting_hr:
                    heart["resting_hr"] = record.resting_hr
                if heart:
                    day_data["heart"] = heart

                # Subjective metrics
                subjective: dict[str, Any] = {}
                if record.fatigue:
                    subjective["fatigue"] = record.fatigue
                if record.soreness:
                    subjective["soreness"] = record.soreness
                if record.stress:
                    subjective["stress"] = record.stress
                if record.mood:
                    subjective["mood"] = record.mood
                if record.motivation:
                    subjective["motivation"] = record.motivation
                if subjective:
                    day_data["subjective"] = subjective

                # Body metrics
                body: dict[str, Any] = {}
                if record.weight:
                    body["weight_kg"] = record.weight
                if record.body_fat:
                    body["body_fat_percent"] = round(record.body_fat, 1)
                if body:
                    day_data["body"] = body

                # Training load
                training: dict[str, Any] = {}
                if record.ctl:
                    training["ctl"] = round(record.ctl, 1)
                if record.atl:
                    training["atl"] = round(record.atl, 1)
                if record.tsb:
                    training["tsb"] = round(record.tsb, 1)
                if training:
                    day_data["training"] = training

                # Other metrics
                other: dict[str, Any] = {}
                if record.steps:
                    other["steps"] = record.steps
                if record.kcal_consumed:
                    other["calories_consumed"] = record.kcal_consumed
                if record.hydration_volume:
                    other["hydration_liters"] = round(record.hydration_volume, 1)
                if record.readiness:
                    other["readiness"] = round(record.readiness, 0)
                if other:
                    day_data["other"] = other

                # Comments
                if record.comments:
                    day_data["comments"] = record.comments

                wellness_data.append(day_data)

            # Calculate trends if we have multiple days
            trends: dict[str, Any] = {}
            if len(wellness_records) > 1:
                # HRV trend
                hrv_values = [r.hrv for r in wellness_records if r.hrv is not None]
                if len(hrv_values) >= 2:
                    trends["hrv"] = {
                        "current": round(hrv_values[0], 1),
                        "change": round(hrv_values[0] - hrv_values[-1], 1),
                    }

                # Resting HR trend
                rhr_values = [r.resting_hr for r in wellness_records if r.resting_hr is not None]
                if len(rhr_values) >= 2:
                    trends["resting_hr"] = {
                        "current": rhr_values[0],
                        "change": rhr_values[0] - rhr_values[-1],
                    }

                # Sleep quality trend
                sleep_values = [
                    r.sleep_quality for r in wellness_records if r.sleep_quality is not None
                ]
                if len(sleep_values) >= 2:
                    trends["avg_sleep_quality"] = round(sum(sleep_values) / len(sleep_values), 1)

                # Weight trend
                weight_values = [r.weight for r in wellness_records if r.weight is not None]
                if len(weight_values) >= 2:
                    trends["weight"] = {
                        "current": weight_values[0],
                        "change": round(weight_values[0] - weight_values[-1], 1),
                    }

            result_data: dict[str, Any] = {
                "wellness_data": wellness_data,
                "count": len(wellness_data),
            }
            if trends:
                result_data["trends"] = trends

            return ResponseBuilder.build_response(
                data=result_data,
                query_type="wellness_data",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def get_wellness_for_date(
    date: Annotated[str, "Date in YYYY-MM-DD format"],
    ctx: Context | None = None,
) -> str:
    """Get wellness data for a specific date.

    Returns all wellness metrics for the specified date including sleep,
    HRV, heart rate, mood, fatigue, and other health markers.

    Args:
        date: Date in ISO-8601 format (YYYY-MM-DD)

    Returns:
        JSON string with wellness data for the date
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    # Validate date format
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return ResponseBuilder.build_error_response(
            "Invalid date format. Please use YYYY-MM-DD format.",
            error_type="validation_error",
        )

    try:
        async with ICUClient(config) as client:
            wellness = await client.get_wellness_for_date(date=date)

            wellness_data: dict[str, Any] = {"date": date}

            # Sleep
            sleep: dict[str, Any] = {}
            if wellness.sleep_secs:
                sleep["duration_seconds"] = wellness.sleep_secs
            if wellness.sleep_quality:
                sleep["quality"] = wellness.sleep_quality
            if wellness.sleep_score:
                sleep["score"] = round(wellness.sleep_score, 0)
            if wellness.avg_sleeping_hr:
                sleep["avg_sleeping_hr"] = round(wellness.avg_sleeping_hr, 0)
            if sleep:
                wellness_data["sleep"] = sleep

            # Heart metrics
            heart: dict[str, Any] = {}
            if wellness.hrv:
                heart["hrv_rmssd"] = round(wellness.hrv, 1)
            if wellness.hrv_sdnn:
                heart["hrv_sdnn"] = round(wellness.hrv_sdnn, 1)
            if wellness.resting_hr:
                heart["resting_hr"] = wellness.resting_hr
            if wellness.baevsky_si:
                heart["baevsky_si"] = round(wellness.baevsky_si, 1)
            if heart:
                wellness_data["heart"] = heart

            # Subjective feelings
            subjective: dict[str, Any] = {}
            if wellness.fatigue:
                subjective["fatigue"] = wellness.fatigue
            if wellness.soreness:
                subjective["soreness"] = wellness.soreness
            if wellness.stress:
                subjective["stress"] = wellness.stress
            if wellness.mood:
                subjective["mood"] = wellness.mood
            if wellness.motivation:
                subjective["motivation"] = wellness.motivation
            if wellness.readiness:
                subjective["readiness"] = round(wellness.readiness, 0)
            if wellness.injury:
                subjective["injury"] = wellness.injury
            if subjective:
                wellness_data["subjective"] = subjective

            # Body metrics
            body: dict[str, Any] = {}
            if wellness.weight:
                body["weight_kg"] = wellness.weight
            if wellness.body_fat:
                body["body_fat_percent"] = round(wellness.body_fat, 1)
            if body:
                wellness_data["body"] = body

            # Vital signs
            vitals: dict[str, Any] = {}
            if wellness.systolic:
                vitals["systolic_mmhg"] = wellness.systolic
            if wellness.diastolic:
                vitals["diastolic_mmhg"] = wellness.diastolic
            if wellness.spo2:
                vitals["spo2_percent"] = round(wellness.spo2, 1)
            if wellness.respiration:
                vitals["respiration_rate"] = round(wellness.respiration, 1)
            if vitals:
                wellness_data["vitals"] = vitals

            # Activity & Nutrition
            activity_nutrition: dict[str, Any] = {}
            if wellness.steps:
                activity_nutrition["steps"] = wellness.steps
            if wellness.kcal_consumed:
                activity_nutrition["calories_consumed"] = wellness.kcal_consumed
            if wellness.hydration_volume:
                activity_nutrition["hydration_liters"] = round(wellness.hydration_volume, 1)
            if activity_nutrition:
                wellness_data["activity_nutrition"] = activity_nutrition

            # Training load
            training: dict[str, Any] = {}
            if wellness.ctl:
                training["ctl"] = round(wellness.ctl, 1)
            if wellness.atl:
                training["atl"] = round(wellness.atl, 1)
            if wellness.tsb:
                training["tsb"] = round(wellness.tsb, 1)
            if wellness.ramp_rate:
                training["ramp_rate"] = round(wellness.ramp_rate, 1)
            if training:
                wellness_data["training"] = training

            # Other metrics
            other: dict[str, Any] = {}
            if wellness.blood_glucose:
                other["blood_glucose_mmol_per_l"] = round(wellness.blood_glucose, 1)
            if wellness.lactate:
                other["lactate_mmol_per_l"] = round(wellness.lactate, 1)
            if wellness.menstrual_phase:
                other["menstrual_phase"] = wellness.menstrual_phase
            if other:
                wellness_data["other"] = other

            # Comments
            if wellness.comments:
                wellness_data["comments"] = wellness.comments

            return ResponseBuilder.build_response(
                data=wellness_data,
                query_type="wellness_for_date",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def update_wellness(
    date: Annotated[str, "Date in YYYY-MM-DD format"],
    weight: Annotated[float | None, "Weight in kg"] = None,
    resting_hr: Annotated[int | None, "Resting heart rate in bpm"] = None,
    hrv: Annotated[float | None, "HRV (rMSSD) value"] = None,
    sleep_secs: Annotated[int | None, "Sleep duration in seconds"] = None,
    sleep_quality: Annotated[int | None, "Sleep quality (1-5 scale)"] = None,
    fatigue: Annotated[int | None, "Fatigue level (1-5 scale)"] = None,
    soreness: Annotated[int | None, "Soreness level (1-5 scale)"] = None,
    stress: Annotated[int | None, "Stress level (1-5 scale)"] = None,
    mood: Annotated[int | None, "Mood level (1-5 scale)"] = None,
    motivation: Annotated[int | None, "Motivation level (1-5 scale)"] = None,
    readiness: Annotated[float | None, "Readiness score (0-100)"] = None,
    comments: Annotated[str | None, "Comments or notes"] = None,
    ctx: Context | None = None,
) -> str:
    """Update wellness data for a specific date.

    Updates wellness metrics for the specified date. If a record doesn't exist for
    that date, it will be created. Only provide the fields you want to update.

    All subjective metrics (fatigue, soreness, stress, mood, motivation) use a 1-5 scale:
    1 = Very low/poor, 3 = Normal/moderate, 5 = Very high/excellent

    Args:
        date: Date in ISO-8601 format (YYYY-MM-DD)
        weight: Weight in kilograms
        resting_hr: Resting heart rate in beats per minute
        hrv: Heart rate variability (rMSSD) in milliseconds
        sleep_secs: Sleep duration in seconds
        sleep_quality: Sleep quality rating (1-5)
        fatigue: Fatigue level (1-5)
        soreness: Muscle soreness level (1-5)
        stress: Stress level (1-5)
        mood: Mood rating (1-5)
        motivation: Motivation level (1-5)
        readiness: Overall readiness score (0-100)
        comments: Any notes or comments about the day

    Returns:
        JSON string with updated wellness data
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    # Validate date format
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return ResponseBuilder.build_error_response(
            "Invalid date format. Please use YYYY-MM-DD format.",
            error_type="validation_error",
        )

    try:
        # Build wellness data (only include provided fields)
        wellness_data: dict[str, Any] = {"id": date}

        if weight is not None:
            wellness_data["weight"] = weight
        if resting_hr is not None:
            wellness_data["restingHR"] = resting_hr
        if hrv is not None:
            wellness_data["hrv"] = hrv
        if sleep_secs is not None:
            wellness_data["sleepSecs"] = sleep_secs
        if sleep_quality is not None:
            wellness_data["sleepQuality"] = sleep_quality
        if fatigue is not None:
            wellness_data["fatigue"] = fatigue
        if soreness is not None:
            wellness_data["soreness"] = soreness
        if stress is not None:
            wellness_data["stress"] = stress
        if mood is not None:
            wellness_data["mood"] = mood
        if motivation is not None:
            wellness_data["motivation"] = motivation
        if readiness is not None:
            wellness_data["readiness"] = readiness
        if comments is not None:
            wellness_data["comments"] = comments

        if len(wellness_data) == 1:  # Only has 'id'
            return ResponseBuilder.build_error_response(
                "No wellness data provided. Please specify at least one metric to update.",
                error_type="validation_error",
            )

        async with ICUClient(config) as client:
            wellness = await client.update_wellness(wellness_data)

            result_data: dict[str, Any] = {"date": date}

            if wellness.weight:
                result_data["weight_kg"] = wellness.weight
            if wellness.resting_hr:
                result_data["resting_hr"] = wellness.resting_hr
            if wellness.hrv:
                result_data["hrv_rmssd"] = round(wellness.hrv, 1)
            if wellness.sleep_secs:
                result_data["sleep_duration_seconds"] = wellness.sleep_secs
            if wellness.sleep_quality:
                result_data["sleep_quality"] = wellness.sleep_quality
            if wellness.fatigue:
                result_data["fatigue"] = wellness.fatigue
            if wellness.soreness:
                result_data["soreness"] = wellness.soreness
            if wellness.stress:
                result_data["stress"] = wellness.stress
            if wellness.mood:
                result_data["mood"] = wellness.mood
            if wellness.motivation:
                result_data["motivation"] = wellness.motivation
            if wellness.readiness:
                result_data["readiness"] = round(wellness.readiness, 0)
            if wellness.comments:
                result_data["comments"] = wellness.comments

            return ResponseBuilder.build_response(
                data=result_data,
                query_type="update_wellness",
                metadata={"message": f"Successfully updated wellness for {date}"},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )
