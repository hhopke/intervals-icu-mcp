"""Athlete profile and fitness tools for Intervals.icu MCP server."""

from datetime import date, timedelta
from typing import Annotated, Any

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..models import Wellness
from ..response_builder import ResponseBuilder
from ..sport_settings_format import format_sport_settings_entry

MAX_FITNESS_CHART_DAYS = 365
_FITNESS_CHART_FIELDS = ["id", "ctl", "atl", "rampRate", "ctlLoad", "atlLoad"]


def _fitness_metrics_point(record: Wellness, today: date) -> dict[str, Any] | None:
    """Shape one wellness record into a lean PMC data point, or None if no fitness data."""
    if record.ctl is None and record.atl is None:
        return None

    record_date = date.fromisoformat(record.id)
    point: dict[str, Any] = {
        "date": record.id,
        "is_projected": record_date > today,
    }
    if record.ctl is not None:
        point["ctl"] = round(record.ctl, 1)
    if record.atl is not None:
        point["atl"] = round(record.atl, 1)

    tsb = record.tsb
    if tsb is None and record.ctl is not None and record.atl is not None:
        tsb = record.ctl - record.atl
    if tsb is not None:
        point["tsb"] = round(tsb, 1)
    if record.ramp_rate is not None:
        point["ramp_rate"] = round(record.ramp_rate, 1)
    if record.ctl_load is not None:
        point["ctl_load"] = round(record.ctl_load, 1)
    if record.atl_load is not None:
        point["atl_load"] = round(record.atl_load, 1)

    return point


def _fitness_chart_summary(series: list[dict[str, Any]], today: date) -> dict[str, Any]:
    """Build start/today/end summary from an ascending fitness chart series."""
    summary: dict[str, Any] = {}
    today_str = today.isoformat()

    if series:
        summary["start"] = {k: v for k, v in series[0].items() if k != "date"}
        summary["end"] = {k: v for k, v in series[-1].items() if k != "date"}

    for point in series:
        if point["date"] == today_str:
            summary["today"] = {k: v for k, v in point.items() if k != "date"}
            break

    return summary


def _athlete_access(record: dict[str, Any], is_default: bool) -> tuple[str, bool]:
    """Map the API's relationship fields onto a plain access label.

    `icu_permission` is NONE/READ/WRITE, and is null for the caller's own record.
    """
    if is_default:
        return "self", True
    permission = record.get("icu_permission")
    if record.get("icu_coach") or permission == "WRITE":
        return "coach", True
    if permission == "READ":
        return "follower", False
    if permission == "NONE":
        return "none", False
    # No permission field and not the configured default: the caller's own
    # record under a different id (e.g. a stale INTERVALS_ICU_ATHLETE_ID).
    return "self", True


async def list_athletes(
    ctx: Context | None = None,
) -> str:
    """List the athletes this account can access — the caller plus anyone they follow or coach.

    Call this FIRST whenever a request concerns someone other than the default
    athlete, to resolve a name to the athlete_id that other tools take. Returns
    each athlete's access level, so you know before calling whether a write will
    be permitted.
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            records = await client.list_athletes()

            default_id = config.intervals_icu_athlete_id
            athletes: list[dict[str, Any]] = []
            for record in records:
                athlete_id = record.get("id")
                if not athlete_id:
                    continue
                is_default = athlete_id == default_id
                access, can_write = _athlete_access(record, is_default)
                entry: dict[str, Any] = {
                    "athlete_id": athlete_id,
                    "name": record.get("name"),
                    "access": access,
                    "can_write": can_write,
                }
                if is_default:
                    entry["is_default"] = True
                if record.get("icu_tags"):
                    entry["tags"] = record["icu_tags"]
                athletes.append(entry)

            # Default athlete first, then alphabetical — a coach's own account is
            # the most common target and should not be buried in a long roster.
            athletes.sort(key=lambda a: (not a.get("is_default", False), (a["name"] or "").lower()))

            if not athletes:
                return ResponseBuilder.build_response(
                    data={"athletes": [], "count": 0, "default_athlete_id": default_id},
                    metadata={
                        "message": (
                            "No athletes returned. This account follows or coaches no one, "
                            "so only the default athlete is available."
                        )
                    },
                    query_type="athlete_list",
                )

            return ResponseBuilder.build_response(
                data={
                    "athletes": athletes,
                    "count": len(athletes),
                    "default_athlete_id": default_id,
                },
                metadata={
                    "access_levels": (
                        "self = this account; coach = read and write; "
                        "follower = read only; none = no access"
                    ),
                    "usage": (
                        "Pass athlete_id to any athlete-scoped tool to target that "
                        "athlete. Omit it to use the default."
                    ),
                },
                query_type="athlete_list",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(
            e.message,
            error_type="api_error",
            suggestions=[
                "This endpoint requires an API key (not an OAuth bearer token).",
                "Athletes appear here only after they accept your follow or coaching request.",
                "Omit athlete_id on other tools to use the configured default athlete.",
            ],
        )
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}",
            error_type="internal_error",
        )


async def get_athlete_profile(
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Get an athlete's profile — sport settings (outdoor/indoor FTP, FTHR, pace) and current CTL/ATL/TSB.

    Defaults to the authenticated athlete; coaches can pass athlete_id to read
    one of their managed athletes instead.
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            athlete = await client.get_athlete(athlete_id=athlete_id)

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
                    sports.append(format_sport_settings_entry(sport, include_id=False))

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
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Get an athlete's current fitness / fatigue / form snapshot — CTL, ATL, TSB, ramp rate, with interpretation and training recommendations.

    Use for "how's my form?", "am I overtrained?", training-status checks.
    Defaults to the authenticated athlete; coaches can pass athlete_id to read
    one of their managed athletes instead.
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            today = date.today().isoformat()
            resolved_athlete = athlete_id or config.intervals_icu_athlete_id
            wellness = await client.get_wellness_for_date(today, athlete_id=athlete_id)

            ctl = wellness.ctl
            atl = wellness.atl
            tsb = wellness.tsb
            ramp_rate = getattr(wellness, "ramp_rate", None)

            if ctl is None and atl is None:
                return ResponseBuilder.build_error_response(
                    f"No fitness data available for athlete {resolved_athlete} on {today}.",
                    error_type="no_data",
                    suggestions=[
                        "Fitness metrics need a training history — check that this "
                        "athlete has activities recorded.",
                    ],
                )

            # Core metrics
            fitness: dict[str, Any] = {}
            if ctl is not None:
                fitness["ctl"] = {
                    "value": round(ctl, 1),
                    "description": "Chronic Training Load (Fitness)",
                    "explanation": "Long-term training load (42-day weighted average)",
                }
            if atl is not None:
                fitness["atl"] = {
                    "value": round(atl, 1),
                    "description": "Acute Training Load (Fatigue)",
                    "explanation": "Short-term training load (7-day weighted average)",
                }
            if tsb is not None:
                fitness["tsb"] = {
                    "value": round(tsb, 1),
                    "description": "Training Stress Balance (Form)",
                    "explanation": "Fitness - Fatigue",
                }
            if ramp_rate is not None:
                fitness["ramp_rate"] = {
                    "value": round(ramp_rate, 1),
                    "description": "Rate of fitness change (CTL increase per week)",
                }

            # Analysis and recommendations
            analysis: dict[str, Any] = {}

            # TSB interpretation
            if tsb is not None:
                if tsb > 20:
                    analysis["form_status"] = "very_fresh"
                    analysis["form_interpretation"] = "You're very fresh - good for racing!"
                elif tsb > 5:
                    analysis["form_status"] = "recovered"
                    analysis["form_interpretation"] = "You're recovered and ready for hard training"
                elif tsb > -10:
                    analysis["form_status"] = "optimal"
                    analysis["form_interpretation"] = "Optimal zone - productive training possible"
                elif tsb > -30:
                    analysis["form_status"] = "fatigued"
                    analysis["form_interpretation"] = (
                        "You're accumulating fatigue - recovery may be needed"
                    )
                else:
                    analysis["form_status"] = "very_fatigued"
                    analysis["form_interpretation"] = "High fatigue - prioritize recovery"

            # Ramp rate interpretation
            if ramp_rate is not None:
                if ramp_rate > 8:
                    analysis["ramp_rate_status"] = "high_risk"
                    analysis["ramp_rate_interpretation"] = "Fitness increasing too fast"
                    analysis["ramp_rate_warning"] = "Reduce training load to avoid overtraining"
                elif ramp_rate > 5:
                    analysis["ramp_rate_status"] = "caution"
                    analysis["ramp_rate_interpretation"] = "Fitness increasing rapidly"
                    analysis["ramp_rate_warning"] = "Monitor fatigue and recovery closely"
                elif ramp_rate > 0:
                    analysis["ramp_rate_status"] = "good"
                    analysis["ramp_rate_interpretation"] = "Sustainable fitness gain"
                elif ramp_rate > -5:
                    analysis["ramp_rate_status"] = "declining"
                    analysis["ramp_rate_interpretation"] = (
                        "Fitness slightly declining (taper/recovery)"
                    )
                else:
                    analysis["ramp_rate_status"] = "declining_significantly"
                    analysis["ramp_rate_interpretation"] = "Fitness declining significantly"

            # Training recommendations
            recommendations: list[str] = []
            if tsb is not None and ramp_rate is not None:
                if tsb < -30:
                    recommendations.append("Take an easy week or rest days")
                    recommendations.append("Focus on recovery and low-intensity activities")
                elif tsb < -10 and ramp_rate > 5:
                    recommendations.append("Balance hard training with recovery")
                    recommendations.append("Consider a recovery week soon")
                elif tsb > 5:
                    if ramp_rate < 0:
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

            data: dict[str, Any] = {
                "athlete_id": resolved_athlete,
                "date": today,
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


async def get_fitness_chart(
    days_back: Annotated[int, "Number of days before today to include (inclusive)"],
    days_ahead: Annotated[
        int, "Number of days after today to include (inclusive); use 0 for history only"
    ],
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Fetch the Performance Management Chart time-series — daily CTL, ATL, and TSB.

    Returns past history plus future projections from planned calendar workouts.
    Use for: "show my fitness chart", "CTL trend last 90 days", "projected form
    at end of my block", "what will my TSB be in 3 weeks".
    NOT for: today's training recommendations (icu_get_fitness_summary), HRV/sleep/
    recovery trends (icu_get_wellness_data), or one day's full wellness record
    (icu_get_wellness_for_date).
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    if days_back < 0 or days_ahead < 0:
        return ResponseBuilder.build_error_response(
            "days_back and days_ahead must be zero or positive.",
            error_type="validation_error",
        )

    if days_back + days_ahead > MAX_FITNESS_CHART_DAYS:
        return ResponseBuilder.build_error_response(
            f"Total date window cannot exceed {MAX_FITNESS_CHART_DAYS} days "
            f"(days_back + days_ahead = {days_back + days_ahead}). "
            "Use a smaller range.",
            error_type="validation_error",
        )

    today = date.today()
    oldest = (today - timedelta(days=days_back)).isoformat()
    newest = (today + timedelta(days=days_ahead)).isoformat()

    try:
        async with ICUClient(config) as client:
            records = await client.get_wellness(
                athlete_id=athlete_id,
                oldest=oldest,
                newest=newest,
                fields=_FITNESS_CHART_FIELDS,
            )

            series: list[dict[str, Any]] = []
            for record in records:
                point = _fitness_metrics_point(record, today)
                if point is not None:
                    series.append(point)

            series.sort(key=lambda p: p["date"])

            metadata: dict[str, Any] = {
                "projections_note": (
                    "Future values include planned calendar workouts when the athlete's "
                    "Intervals.icu setting 'Include planned workouts in fitness' is enabled."
                ),
                "sparse_series_note": (
                    "Days without a wellness record are omitted (not zero-filled)."
                ),
            }

            if not series:
                return ResponseBuilder.build_response(
                    data={
                        "athlete_id": athlete_id or config.intervals_icu_athlete_id,
                        "date_range": {"oldest": oldest, "newest": newest},
                        "count": 0,
                        "series": [],
                    },
                    metadata={
                        **metadata,
                        "message": "No fitness chart data found for the specified date range.",
                    },
                    query_type="fitness_chart",
                )

            data: dict[str, Any] = {
                "athlete_id": athlete_id or config.intervals_icu_athlete_id,
                "date_range": {"oldest": oldest, "newest": newest},
                "count": len(series),
                "series": series,
                "summary": _fitness_chart_summary(series, today),
            }

            return ResponseBuilder.build_response(
                data=data,
                metadata=metadata,
                query_type="fitness_chart",
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
