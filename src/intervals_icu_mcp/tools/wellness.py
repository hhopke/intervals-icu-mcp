"""Wellness and health tracking tools for Intervals.icu MCP server."""

from datetime import datetime, timedelta
from typing import Annotated, Any

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..response_builder import ResponseBuilder

# Scale labels for subjective metrics — surfaced in response metadata so LLM
# clients that only see the JSON payload (not the tool docstring) can still
# interpret the values correctly. Direction matters: sleep_quality is inverted
# (1=Great, 5=Poor) while every other 1-5 metric is "higher = more".
WELLNESS_SCALES: dict[str, str] = {
    "fatigue": "1-5 (1=very low, 5=very high)",
    "soreness": "1-5 (1=very low, 5=very high)",
    "stress": "1-5 (1=very low, 5=very high)",
    "mood": "1-5 (1=very poor, 5=very good)",
    "motivation": "1-5 (1=very low, 5=very high)",
    "injury": "1-5 (1=none, 5=severe)",
    "sleep_quality": "1-5 (1=Great, 5=Poor — inverted scale)",
    "sleep_score": "0-100 (device-specific, higher is better)",
    "readiness": "0-100 (higher is better)",
}


def _format_wellness_record(record: Any, date_id: str) -> dict[str, Any]:
    """Format a wellness record object into a structured dictionary."""
    day_data: dict[str, Any] = {"date": date_id}

    # Sleep
    sleep: dict[str, Any] = {}
    if getattr(record, "sleep_secs", None):
        sleep["duration_seconds"] = record.sleep_secs
    if getattr(record, "sleep_quality", None):
        sleep["quality"] = record.sleep_quality
    if getattr(record, "sleep_score", None):
        sleep["score"] = round(record.sleep_score, 0)
    if getattr(record, "avg_sleeping_hr", None):
        sleep["avg_sleeping_hr"] = round(record.avg_sleeping_hr, 0)
    if sleep:
        day_data["sleep"] = sleep

    # Heart metrics
    heart: dict[str, Any] = {}
    if getattr(record, "hrv", None):
        heart["hrv_rmssd"] = round(record.hrv, 1)
    if getattr(record, "hrv_sdnn", None):
        heart["hrv_sdnn"] = round(record.hrv_sdnn, 1)
    if getattr(record, "resting_hr", None):
        heart["resting_hr"] = record.resting_hr
    if getattr(record, "baevsky_si", None):
        heart["baevsky_si"] = round(record.baevsky_si, 1)
    if heart:
        day_data["heart"] = heart

    # Subjective feelings
    subjective: dict[str, Any] = {}
    for field in ["fatigue", "soreness", "stress", "mood", "motivation", "injury"]:
        if getattr(record, field, None):
            subjective[field] = getattr(record, field)
    if getattr(record, "readiness", None):
        subjective["readiness"] = round(record.readiness, 0)
    if subjective:
        day_data["subjective"] = subjective

    # Body metrics
    body: dict[str, Any] = {}
    if getattr(record, "weight", None):
        body["weight_kg"] = record.weight
    if getattr(record, "body_fat", None):
        body["body_fat_percent"] = round(record.body_fat, 1)
    if getattr(record, "abdomen", None):
        body["abdomen_cm"] = round(record.abdomen, 1)
    if getattr(record, "vo2max", None):
        body["vo2max"] = round(record.vo2max, 1)
    if body:
        day_data["body"] = body

    # Vital signs
    vitals: dict[str, Any] = {}
    if getattr(record, "systolic", None):
        vitals["systolic_mmhg"] = record.systolic
    if getattr(record, "diastolic", None):
        vitals["diastolic_mmhg"] = record.diastolic
    if getattr(record, "spo2", None):
        vitals["spo2_percent"] = round(record.spo2, 1)
    if getattr(record, "respiration", None):
        vitals["respiration_rate"] = round(record.respiration, 1)
    if vitals:
        day_data["vitals"] = vitals

    # Activity
    activity: dict[str, Any] = {}
    if getattr(record, "steps", None):
        activity["steps"] = record.steps
    if activity:
        day_data["activity"] = activity

    # Nutrition
    nutrition: dict[str, Any] = {}
    if getattr(record, "kcal_consumed", None):
        nutrition["calories_consumed"] = record.kcal_consumed
    if getattr(record, "carbohydrates", None):
        nutrition["carbohydrates_g"] = round(record.carbohydrates, 1)
    if getattr(record, "protein", None):
        nutrition["protein_g"] = round(record.protein, 1)
    if getattr(record, "fat_total", None):
        nutrition["fat_total_g"] = round(record.fat_total, 1)
    if getattr(record, "hydration_volume", None):
        nutrition["hydration_liters"] = round(record.hydration_volume, 1)
    if nutrition:
        day_data["nutrition"] = nutrition

    # Training load
    training: dict[str, Any] = {}
    for field in ["ctl", "atl", "tsb", "ramp_rate"]:
        if getattr(record, field, None):
            training[field] = round(getattr(record, field), 1)
    if training:
        day_data["training"] = training

    # Per-sport context (eFTP, W', Pmax per sport type)
    sport_info_raw: list[Any] = getattr(record, "sport_info", None) or []
    sport_info_list: list[dict[str, Any]] = []
    for sport in sport_info_raw:
        entry: dict[str, Any] = {}
        if getattr(sport, "type", None):
            entry["type"] = sport.type
        if getattr(sport, "eftp", None):
            entry["eftp"] = round(sport.eftp, 1)
        if getattr(sport, "w_prime", None):
            entry["w_prime"] = round(sport.w_prime, 1)
        if getattr(sport, "p_max", None):
            entry["p_max"] = round(sport.p_max, 1)
        if entry:
            sport_info_list.append(entry)
    if sport_info_list:
        day_data["sport_info"] = sport_info_list

    # State flags (record locked, fallback values in use)
    state_flags: dict[str, Any] = {}
    for field in ["locked", "temp_weight", "temp_resting_hr"]:
        value = getattr(record, field, None)
        if value is not None:
            state_flags[field] = value
    if state_flags:
        day_data["state_flags"] = state_flags

    # Other metrics
    other: dict[str, Any] = {}
    if getattr(record, "blood_glucose", None):
        other["blood_glucose_mmol_per_l"] = round(record.blood_glucose, 1)
    if getattr(record, "lactate", None):
        other["lactate_mmol_per_l"] = round(record.lactate, 1)
    if getattr(record, "menstrual_phase", None):
        other["menstrual_phase"] = record.menstrual_phase
    if getattr(record, "menstrual_phase_predicted", None):
        other["menstrual_phase_predicted"] = record.menstrual_phase_predicted
    if other:
        day_data["other"] = other

    # Comments
    if getattr(record, "comments", None):
        day_data["comments"] = record.comments

    return day_data


def _scales_for_records(records: list[dict[str, Any]]) -> dict[str, str]:
    """Return scale labels only for subjective metrics actually present in output."""
    present: set[str] = set()
    for record in records:
        sleep = record.get("sleep", {})
        if "quality" in sleep:
            present.add("sleep_quality")
        if "score" in sleep:
            present.add("sleep_score")
        subjective = record.get("subjective", {})
        for key in subjective:
            if key in WELLNESS_SCALES:
                present.add(key)
    return {k: WELLNESS_SCALES[k] for k in present}


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
                wellness_data.append(_format_wellness_record(record, record.id))

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

            metadata: dict[str, Any] = {}
            scales = _scales_for_records(wellness_data)
            if scales:
                metadata["scales"] = scales

            return ResponseBuilder.build_response(
                data=result_data,
                metadata=metadata or None,
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

            wellness_data = _format_wellness_record(wellness, date)

            metadata: dict[str, Any] = {}
            scales = _scales_for_records([wellness_data])
            if scales:
                metadata["scales"] = scales

            return ResponseBuilder.build_response(
                data=wellness_data,
                metadata=metadata or None,
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
    injury: Annotated[int | None, "Injury severity (1-5 scale: 1=none, 5=severe)"] = None,
    readiness: Annotated[float | None, "Readiness score (0-100)"] = None,
    body_fat: Annotated[float | None, "Body fat percentage"] = None,
    abdomen: Annotated[float | None, "Abdominal circumference in cm"] = None,
    vo2max: Annotated[float | None, "VO2max (ml/kg/min) — lab result or device estimate"] = None,
    systolic: Annotated[int | None, "Systolic blood pressure in mmHg"] = None,
    diastolic: Annotated[int | None, "Diastolic blood pressure in mmHg"] = None,
    spo2: Annotated[float | None, "Blood oxygen saturation percentage (SpO2)"] = None,
    respiration: Annotated[float | None, "Respiration rate in breaths per minute"] = None,
    blood_glucose: Annotated[float | None, "Blood glucose in mmol/L"] = None,
    lactate: Annotated[float | None, "Blood lactate in mmol/L — lab result"] = None,
    menstrual_phase: Annotated[str | None, "Menstrual phase (e.g. FOLLICULAR, OVULATING, LUTEAL, MENSTRUAL)"] = None,
    locked: Annotated[bool | None, "Lock record to prevent device sync from overwriting manual entries"] = None,
    calories_consumed: Annotated[int | None, "Calories consumed (kcal)"] = None,
    carbohydrates: Annotated[float | None, "Carbohydrates consumed (grams)"] = None,
    protein: Annotated[float | None, "Protein consumed (grams)"] = None,
    fat_total: Annotated[float | None, "Total fat consumed (grams)"] = None,
    hydration_liters: Annotated[float | None, "Hydration volume (liters)"] = None,
    comments: Annotated[str | None, "Comments or notes"] = None,
    ctx: Context | None = None,
) -> str:
    """Update wellness data for a specific date.

    Updates wellness metrics for the specified date. If a record doesn't exist for
    that date, it will be created. Only provide the fields you want to update.

    All subjective metrics (fatigue, soreness, stress, mood, motivation, injury) use a 1-5 scale.
    Set `locked=True` to prevent device sync from overwriting manual entries.

    Args:
        date: Date in ISO-8601 format (YYYY-MM-DD)
        weight: Weight in kilograms
        resting_hr: Resting heart rate in beats per minute
        hrv: Heart rate variability (rMSSD) in milliseconds
        sleep_secs: Sleep duration in seconds
        sleep_quality: Sleep quality rating (1-5, inverted: 1=Great, 5=Poor)
        fatigue: Fatigue level (1-5)
        soreness: Muscle soreness level (1-5)
        stress: Stress level (1-5)
        mood: Mood rating (1-5)
        motivation: Motivation level (1-5)
        injury: Injury severity (1-5: 1=none, 5=severe)
        readiness: Overall readiness score (0-100)
        body_fat: Body fat percentage
        abdomen: Abdominal circumference in cm
        vo2max: VO2max in ml/kg/min
        systolic: Systolic blood pressure in mmHg
        diastolic: Diastolic blood pressure in mmHg
        spo2: Blood oxygen saturation percentage (SpO2)
        respiration: Respiration rate in breaths per minute
        blood_glucose: Blood glucose in mmol/L
        lactate: Blood lactate in mmol/L
        menstrual_phase: Menstrual phase string
        locked: Prevent device sync from overwriting this record
        calories_consumed: Total calories consumed in kcal
        carbohydrates: Carbohydrates in grams
        protein: Protein in grams
        fat_total: Total fat in grams
        hydration_liters: Hydration volume in liters
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
        if injury is not None:
            wellness_data["injury"] = injury
        if readiness is not None:
            wellness_data["readiness"] = readiness
        if body_fat is not None:
            wellness_data["bodyFat"] = body_fat
        if abdomen is not None:
            wellness_data["abdomen"] = abdomen
        if vo2max is not None:
            wellness_data["vo2max"] = vo2max
        if systolic is not None:
            wellness_data["systolic"] = systolic
        if diastolic is not None:
            wellness_data["diastolic"] = diastolic
        if spo2 is not None:
            wellness_data["spO2"] = spo2
        if respiration is not None:
            wellness_data["respiration"] = respiration
        if blood_glucose is not None:
            wellness_data["bloodGlucose"] = blood_glucose
        if lactate is not None:
            wellness_data["lactate"] = lactate
        if menstrual_phase is not None:
            wellness_data["menstrualPhase"] = menstrual_phase
        if locked is not None:
            wellness_data["locked"] = locked
        if calories_consumed is not None:
            wellness_data["kcalConsumed"] = calories_consumed
        if carbohydrates is not None:
            wellness_data["carbohydrates"] = carbohydrates
        if protein is not None:
            wellness_data["protein"] = protein
        if fat_total is not None:
            wellness_data["fatTotal"] = fat_total
        if hydration_liters is not None:
            wellness_data["hydrationVolume"] = hydration_liters
        if comments is not None:
            wellness_data["comments"] = comments

        if len(wellness_data) == 1:  # Only has 'id'
            return ResponseBuilder.build_error_response(
                "No wellness data provided. Please specify at least one metric to update.",
                error_type="validation_error",
            )

        async with ICUClient(config) as client:
            wellness = await client.update_wellness(wellness_data)

            result_data = _format_wellness_record(wellness, date)

            metadata: dict[str, Any] = {"message": f"Successfully updated wellness for {date}"}
            scales = _scales_for_records([result_data])
            if scales:
                metadata["scales"] = scales

            return ResponseBuilder.build_response(
                data=result_data,
                query_type="update_wellness",
                metadata=metadata,
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )
