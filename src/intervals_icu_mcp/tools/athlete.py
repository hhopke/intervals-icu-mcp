"""Athlete profile and fitness tools for Intervals.icu MCP server."""

from typing import Any

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..response_builder import ResponseBuilder


async def get_athlete_profile(
    ctx: Context | None = None,
) -> str:
    """Get the authenticated athlete's profile information.

    Returns athlete profile including personal details, sport settings,
    and current fitness metrics (CTL, ATL, TSB).

    Returns:
        JSON string with athlete profile data
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            athlete = await client.get_athlete()

            # Build profile data
            profile: dict[str, Any] = {
                "id": athlete.id,
                "name": athlete.name,
            }

            if athlete.email:
                profile["email"] = athlete.email
            if athlete.sex:
                profile["sex"] = athlete.sex
            if athlete.dob:
                profile["dob"] = athlete.dob
            if athlete.weight:
                profile["weight_kg"] = athlete.weight

            # Fitness metrics
            fitness: dict[str, Any] = {}
            if athlete.ctl is not None:
                fitness["ctl"] = round(athlete.ctl, 1)
            if athlete.atl is not None:
                fitness["atl"] = round(athlete.atl, 1)
            if athlete.tsb is not None:
                fitness["tsb"] = round(athlete.tsb, 1)
            if athlete.ramp_rate is not None:
                fitness["ramp_rate"] = round(athlete.ramp_rate, 1)

            # Sport settings
            sports: list[dict[str, Any]] = []
            if athlete.sport_settings:
                for sport in athlete.sport_settings:
                    sport_data: dict[str, Any] = {}
                    if sport.type:
                        sport_data["type"] = sport.type
                    if sport.ftp:
                        sport_data["ftp"] = sport.ftp
                    if sport.fthr:
                        sport_data["fthr"] = sport.fthr
                    if sport.pace_threshold:
                        sport_data["pace_threshold_seconds"] = sport.pace_threshold
                        minutes = int(sport.pace_threshold // 60)
                        seconds = int(sport.pace_threshold % 60)
                        sport_data["pace_threshold_formatted"] = f"{minutes}:{seconds:02d} /km"
                    if sport.swim_threshold:
                        sport_data["swim_threshold"] = sport.swim_threshold
                    sports.append(sport_data)

            data: dict[str, Any] = {
                "profile": profile,
                "fitness": fitness,
            }
            if sports:
                data["sports"] = sports

            # Analysis
            analysis: dict[str, Any] = {}
            if athlete.tsb is not None:
                if athlete.tsb > 20:
                    analysis["form_status"] = "very_fresh"
                    analysis["form_description"] = "Very fresh - good for racing"
                elif athlete.tsb > 5:
                    analysis["form_status"] = "recovered"
                    analysis["form_description"] = "Recovered and ready for hard training"
                elif athlete.tsb > -10:
                    analysis["form_status"] = "optimal"
                    analysis["form_description"] = "Optimal zone - productive training possible"
                elif athlete.tsb > -30:
                    analysis["form_status"] = "fatigued"
                    analysis["form_description"] = "Accumulating fatigue - recovery may be needed"
                else:
                    analysis["form_status"] = "very_fatigued"
                    analysis["form_description"] = "High fatigue - prioritize recovery"

            if athlete.ramp_rate is not None:
                if athlete.ramp_rate > 8:
                    analysis["ramp_rate_status"] = "high_risk"
                    analysis["ramp_rate_warning"] = (
                        "Fitness increasing too fast - reduce training load"
                    )
                elif athlete.ramp_rate > 5:
                    analysis["ramp_rate_status"] = "caution"
                    analysis["ramp_rate_warning"] = (
                        "Fitness increasing rapidly - monitor fatigue closely"
                    )
                elif athlete.ramp_rate > 0:
                    analysis["ramp_rate_status"] = "good"
                    analysis["ramp_rate_description"] = "Sustainable fitness gain"
                elif athlete.ramp_rate > -5:
                    analysis["ramp_rate_status"] = "declining"
                    analysis["ramp_rate_description"] = (
                        "Fitness slightly declining (taper/recovery)"
                    )
                else:
                    analysis["ramp_rate_status"] = "declining_significantly"
                    analysis["ramp_rate_description"] = "Fitness declining significantly"

            return ResponseBuilder.build_response(
                data,
                analysis=analysis if analysis else None,
                query_type="athlete_profile",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(
            e.message,
            error_type="api_error",
            suggestions=["Check your API key and athlete ID configuration"],
        )
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}",
            error_type="internal_error",
        )


async def get_fitness_summary(
    ctx: Context | None = None,
) -> str:
    """Get the athlete's current fitness, fatigue, and form metrics.

    Returns a comprehensive summary of training load metrics including:
    - CTL (Chronic Training Load / Fitness)
    - ATL (Acute Training Load / Fatigue)
    - TSB (Training Stress Balance / Form)
    - Ramp Rate (rate of fitness change)

    Includes interpretations to help understand training status.

    Returns:
        JSON string with fitness summary and recommendations
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            athlete = await client.get_athlete()

            if athlete.ctl is None and athlete.atl is None:
                return ResponseBuilder.build_error_response(
                    "No fitness data available. Complete some activities to build your fitness history.",
                    error_type="no_data",
                )

            # Core metrics
            fitness: dict[str, Any] = {}
            if athlete.ctl is not None:
                fitness["ctl"] = {
                    "value": round(athlete.ctl, 1),
                    "description": "Chronic Training Load (Fitness)",
                    "explanation": "Long-term training load (42-day weighted average)",
                }
            if athlete.atl is not None:
                fitness["atl"] = {
                    "value": round(athlete.atl, 1),
                    "description": "Acute Training Load (Fatigue)",
                    "explanation": "Short-term training load (7-day weighted average)",
                }
            if athlete.tsb is not None:
                fitness["tsb"] = {
                    "value": round(athlete.tsb, 1),
                    "description": "Training Stress Balance (Form)",
                    "explanation": "Fitness - Fatigue",
                }
            if athlete.ramp_rate is not None:
                fitness["ramp_rate"] = {
                    "value": round(athlete.ramp_rate, 1),
                    "description": "Rate of fitness change (CTL increase per week)",
                }

            # Analysis and recommendations
            analysis: dict[str, Any] = {}

            # TSB interpretation
            if athlete.tsb is not None:
                if athlete.tsb > 20:
                    analysis["form_status"] = "very_fresh"
                    analysis["form_interpretation"] = "You're very fresh - good for racing!"
                elif athlete.tsb > 5:
                    analysis["form_status"] = "recovered"
                    analysis["form_interpretation"] = "You're recovered and ready for hard training"
                elif athlete.tsb > -10:
                    analysis["form_status"] = "optimal"
                    analysis["form_interpretation"] = "Optimal zone - productive training possible"
                elif athlete.tsb > -30:
                    analysis["form_status"] = "fatigued"
                    analysis["form_interpretation"] = (
                        "You're accumulating fatigue - recovery may be needed"
                    )
                else:
                    analysis["form_status"] = "very_fatigued"
                    analysis["form_interpretation"] = "High fatigue - prioritize recovery"

            # Ramp rate interpretation
            if athlete.ramp_rate is not None:
                if athlete.ramp_rate > 8:
                    analysis["ramp_rate_status"] = "high_risk"
                    analysis["ramp_rate_interpretation"] = "Fitness increasing too fast"
                    analysis["ramp_rate_warning"] = "Reduce training load to avoid overtraining"
                elif athlete.ramp_rate > 5:
                    analysis["ramp_rate_status"] = "caution"
                    analysis["ramp_rate_interpretation"] = "Fitness increasing rapidly"
                    analysis["ramp_rate_warning"] = "Monitor fatigue and recovery closely"
                elif athlete.ramp_rate > 0:
                    analysis["ramp_rate_status"] = "good"
                    analysis["ramp_rate_interpretation"] = "Sustainable fitness gain"
                elif athlete.ramp_rate > -5:
                    analysis["ramp_rate_status"] = "declining"
                    analysis["ramp_rate_interpretation"] = (
                        "Fitness slightly declining (taper/recovery)"
                    )
                else:
                    analysis["ramp_rate_status"] = "declining_significantly"
                    analysis["ramp_rate_interpretation"] = "Fitness declining significantly"

            # Training recommendations
            recommendations: list[str] = []
            if athlete.tsb is not None and athlete.ramp_rate is not None:
                if athlete.tsb < -30:
                    recommendations.append("Take an easy week or rest days")
                    recommendations.append("Focus on recovery and low-intensity activities")
                elif athlete.tsb < -10 and athlete.ramp_rate > 5:
                    recommendations.append("Balance hard training with recovery")
                    recommendations.append("Consider a recovery week soon")
                elif athlete.tsb > 5:
                    if athlete.ramp_rate < 0:
                        recommendations.append("Good time to increase training load")
                        recommendations.append("Consider adding volume or intensity")
                    else:
                        recommendations.append("You're fresh and can handle hard workouts")
                        recommendations.append("Good time for races or breakthrough sessions")
                else:
                    recommendations.append("Continue current training approach")
                    recommendations.append("Mix hard sessions with recovery days")

            if recommendations:
                analysis["recommendations"] = recommendations

            data = {
                "athlete_name": athlete.name,
                "fitness_metrics": fitness,
            }

            return ResponseBuilder.build_response(
                data,
                analysis=analysis,
                query_type="fitness_summary",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(
            e.message,
            error_type="api_error",
        )
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}",
            error_type="internal_error",
        )
