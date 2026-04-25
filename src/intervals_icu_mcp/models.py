"""Pydantic models for Intervals.icu API responses."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Type aliases for common enums
ActivityType = Literal["Ride", "Run", "Swim", "Walk", "Hike", "VirtualRide", "VirtualRun", "Other"]
EventCategory = Literal[
    "WORKOUT",
    "NOTE",
    "RACE_A",
    "RACE_B",
    "RACE_C",
    "TARGET",
    "PLAN",
    "HOLIDAY",
    "SICK",
    "INJURED",
    "SET_EFTP",
    "FITNESS_DAYS",
    "SEASON_START",
    "SET_FITNESS",
    "RACE",
    "GOAL",
]
TrainingAvailability = Literal["NORMAL", "LIMITED", "UNAVAILABLE"]


# ==================== Athlete Models ====================


class SportSettings(BaseModel):
    """Sport-specific settings for an athlete."""

    id: int
    type: str | None = None
    ftp: int | None = None
    fthr: int | None = None
    pace_threshold: float | None = None
    swim_threshold: float | None = None


class Athlete(BaseModel):
    """Full athlete profile information."""

    id: str
    name: str
    email: str | None = None
    weight: float | None = None
    dob: str | None = None
    sex: str | None = None
    created: datetime | None = None
    ctl: float | None = None
    atl: float | None = None
    tsb: float | None = None
    ramp_rate: float | None = None
    sport_settings: list[SportSettings] = Field(default_factory=list[SportSettings])


class AthleteProfile(BaseModel):
    """Simplified athlete profile."""

    id: str
    name: str
    email: str | None = None
    weight: float | None = None
    ctl: float | None = None
    atl: float | None = None
    tsb: float | None = None


# ==================== Activity Models ====================


class ActivitySummary(BaseModel):
    """Summary representation of an activity (for lists)."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    start_date_local: datetime
    name: str | None = None
    type: str | None = None
    distance: float | None = None
    moving_time: int | None = None
    elapsed_time: int | None = None
    total_elevation_gain: float | None = None
    average_speed: float | None = None
    average_heartrate: int | None = None
    average_watts: int | None = Field(default=None, alias="icu_average_watts")
    normalized_power: int | None = None
    average_cadence: float | None = None
    icu_training_load: int | None = None
    icu_intensity: float | None = None


class Activity(ActivitySummary):
    """Detailed activity with full information."""

    athlete_id: str | None = None
    description: str | None = None
    calories: int | None = None
    carbs_ingested: int | None = None
    device_name: str | None = None
    max_heartrate: int | None = None
    max_speed: float | None = None
    max_watts: int | None = None
    max_cadence: float | None = None
    weighted_average_watts: int | None = Field(default=None, alias="icu_weighted_avg_watts")
    variability_index: float | None = None
    efficiency_factor: float | None = None
    tss: float | None = None
    hrss: float | None = None
    trimp: float | None = None
    feel: int | None = None
    perceived_exertion: int | None = None
    compliance: float | None = None
    avg_lr_balance: float | None = None
    commute: bool | None = None
    trainer: bool | None = None
    indoor: bool | None = None
    analyzed: str | None = None


class ActivitySearchResult(BaseModel):
    """Search result for activities."""

    id: str
    name: str | None = None
    start_date_local: datetime
    type: str | None = None
    distance: float | None = None
    moving_time: int | None = None


# ==================== Wellness Models ====================


class Wellness(BaseModel):
    """Wellness record with health metrics."""

    id: str  # ISO-8601 date
    weight: float | None = None
    resting_hr: int | None = Field(None, alias="restingHR")
    hrv: float | None = None
    hrv_sdnn: float | None = Field(None, alias="hrvSDNN")
    sleep_secs: int | None = Field(None, alias="sleepSecs")
    sleep_quality: int | None = Field(None, alias="sleepQuality")
    sleep_score: float | None = Field(None, alias="sleepScore")
    avg_sleeping_hr: float | None = Field(None, alias="avgSleepingHR")
    fatigue: int | None = None
    soreness: int | None = None
    stress: int | None = None
    mood: int | None = None
    motivation: int | None = None
    injury: int | None = None
    spo2: float | None = None
    respiration: float | None = None
    hydration: int | None = None
    hydration_volume: float | None = Field(None, alias="hydrationVolume")
    kcal_consumed: int | None = Field(None, alias="kcalConsumed")
    menstrual_phase: str | None = Field(None, alias="menstrualPhase")
    systolic: int | None = None
    diastolic: int | None = None
    blood_glucose: float | None = Field(None, alias="bloodGlucose")
    lactate: float | None = None
    body_fat: float | None = Field(None, alias="bodyFat")
    readiness: float | None = None
    baevsky_si: float | None = Field(None, alias="baevskySI")
    steps: int | None = None
    comments: str | None = None
    ctl: float | None = None
    atl: float | None = None
    tsb: float | None = None  # Training Stress Balance
    ctl_load: float | None = Field(None, alias="ctlLoad")
    atl_load: float | None = Field(None, alias="atlLoad")
    ramp_rate: float | None = Field(None, alias="rampRate")
    updated: datetime | None = None

    model_config = ConfigDict(populate_by_name=True)


# ==================== Event/Calendar Models ====================


class Event(BaseModel):
    """Calendar event (planned workout, note, race, etc.)."""

    id: int
    start_date_local: str  # ISO-8601 date
    end_date_local: str | None = None
    category: str | None = None  # See EventCategory for valid values
    name: str | None = None
    description: str | None = None
    type: str | None = None
    distance: float | None = None
    distance_target: float | None = None
    moving_time: int | None = None
    icu_training_load: int | None = Field(None, alias="icu_training_load")
    icu_intensity: float | None = Field(None, alias="icu_intensity")
    icu_atl: float | None = Field(None, alias="icu_atl")
    icu_ctl: float | None = Field(None, alias="icu_ctl")
    joules: int | None = None
    joules_above_ftp: int | None = Field(None, alias="joules_above_ftp")
    color: str | None = None
    training_availability: str | None = None
    show_as_note: bool | None = None
    not_on_fitness_chart: bool | None = None
    show_on_ctl_line: bool | None = None
    hide_from_athlete: bool | None = Field(None, alias="hide_from_athlete")
    athlete_cannot_edit: bool | None = Field(None, alias="athlete_cannot_edit")
    external_id: str | None = Field(None, alias="external_id")
    created_by_id: str | None = Field(None, alias="created_by_id")

    model_config = ConfigDict(populate_by_name=True)


# ==================== Workout Library Models ====================


class Workout(BaseModel):
    """Workout from library."""

    id: int
    athlete_id: str | None = Field(None, alias="athlete_id")
    name: str | None = None
    description: str | None = None
    folder_id: int | None = Field(None, alias="folder_id")
    moving_time: int | None = Field(None, alias="moving_time")
    distance: float | None = None
    icu_training_load: int | None = Field(None, alias="icu_training_load")
    icu_intensity: float | None = Field(None, alias="icu_intensity")
    joules: int | None = None
    joules_above_ftp: int | None = Field(None, alias="joules_above_ftp")
    indoor: bool | None = None
    color: str | None = None
    type: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class Folder(BaseModel):
    """Workout folder or training plan."""

    id: int
    athlete_id: str | None = Field(None, alias="athlete_id")
    name: str | None = None
    description: str | None = None
    num_workouts: int | None = Field(None, alias="num_workouts")
    start_date_local: str | None = Field(None, alias="start_date_local")
    duration_weeks: int | None = Field(None, alias="duration_weeks")
    hours_per_week_min: int | None = Field(None, alias="hours_per_week_min")
    hours_per_week_max: int | None = Field(None, alias="hours_per_week_max")

    model_config = ConfigDict(populate_by_name=True)


# ==================== Power Curve Models ====================


class CurveData(BaseModel):
    """A single curve from the API (one time range)."""

    model_config = ConfigDict(populate_by_name=True)

    secs: list[int] = Field(default_factory=lambda: list[int]())
    values: list[int] = Field(default_factory=lambda: list[int]())
    activity_id: list[str] = Field(default_factory=lambda: list[str]())
    watts_per_kg: list[float] = Field(default_factory=lambda: list[float]())
    start_date_local: str | None = None
    end_date_local: str | None = None
    days: int | None = None
    weight: float | None = None


class CurveSet(BaseModel):
    """Wrapper returned by all curve API endpoints (power, HR, pace)."""

    model_config = ConfigDict(populate_by_name=True)

    curves: list[CurveData] = Field(default_factory=lambda: list[CurveData](), alias="list")


# ==================== Training Plan Models ====================


class AthleteTrainingPlan(BaseModel):
    """Athlete's current training plan."""

    athlete_id: str | None = Field(None, alias="athlete_id")
    folder_id: int | None = Field(None, alias="folder_id")
    plan_name: str | None = Field(None, alias="plan_name")
    start_date_local: str | None = Field(None, alias="start_date_local")
    end_date_local: str | None = Field(None, alias="end_date_local")
    weeks_remaining: int | None = Field(None, alias="weeks_remaining")

    model_config = ConfigDict(populate_by_name=True)


# ==================== Generic Response Models ====================


class APIError(BaseModel):
    """Error response from API."""

    message: str
    status_code: int | None = None


# ==================== Supporting Models ====================


class FitnessSummary(BaseModel):
    """Custom model for aggregated fitness metrics."""

    ctl: float | None = None  # Chronic Training Load (Fitness)
    atl: float | None = None  # Acute Training Load (Fatigue)
    tsb: float | None = None  # Training Stress Balance (Form)
    ramp_rate: float | None = None  # Rate of fitness change
    date: str | None = None
    interpretation: dict[str, Any] = Field(default_factory=dict)


# ==================== Activity Interval Models ====================


class Interval(BaseModel):
    """Activity interval data."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: int | None = None
    type: str | None = None  # e.g., "WORK", "REST", "WARM_UP", "COOL_DOWN"
    start: int | None = None  # Start time in seconds
    end: int | None = None  # End time in seconds
    duration: int | None = None  # Duration in seconds
    distance: float | None = None
    average_watts: int | None = None
    normalized_power: int | None = None
    average_heartrate: int | None = None
    max_heartrate: int | None = None
    average_cadence: float | None = None
    average_speed: float | None = None
    target: str | None = None  # Target description
    target_min: float | None = None
    target_max: float | None = None


class IntervalsDTO(BaseModel):
    """Response from the intervals endpoint — wraps the interval list."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str | None = None
    icu_intervals: list[Interval] = Field(default_factory=lambda: list[Interval]())


# ==================== Activity Streams Models ====================


class ActivityStream(BaseModel):
    """A single stream returned by the API."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    name: str | None = None
    data: Any = None


# ==================== Best Efforts Models ====================


class Effort(BaseModel):
    """Single best effort entry from the API."""

    start_index: int | None = None
    end_index: int | None = None
    average: float | None = None
    duration: int | None = None
    distance: float | None = None


class BestEfforts(BaseModel):
    """Response from the best-efforts endpoint."""

    efforts: list[Effort] = Field(default_factory=lambda: list[Effort]())


# ==================== Gear Models ====================


class GearReminder(BaseModel):
    """Gear maintenance reminder."""

    id: int
    text: str | None = None
    distance_alert: float | None = Field(None, alias="distance_alert")
    time_alert: int | None = Field(None, alias="time_alert")
    due_distance: float | None = Field(None, alias="due_distance")
    due_time: int | None = Field(None, alias="due_time")
    is_due: bool | None = Field(None, alias="is_due")
    snoozed_until: str | None = Field(None, alias="snoozed_until")

    model_config = ConfigDict(populate_by_name=True)


class Gear(BaseModel):
    """Gear/equipment item."""

    id: str
    athlete_id: str | None = Field(None, alias="athlete_id")
    name: str | None = None
    brand: str | None = None
    model: str | None = None
    gear_type: str | None = Field(None, alias="gear_type")  # e.g., "BIKE", "SHOE"
    active: bool | None = None
    primary: bool | None = None
    distance: float | None = None  # Total distance in meters
    moving_time: int | None = Field(None, alias="moving_time")  # Total time in seconds
    activity_count: int | None = Field(None, alias="activity_count")
    reminders: list[GearReminder] = Field(default_factory=list[GearReminder])

    model_config = ConfigDict(populate_by_name=True)


# ==================== Histogram Models ====================


class HistogramBin(BaseModel):
    """Single bin in a histogram."""

    min: float  # Minimum value for this bin
    max: float  # Maximum value for this bin
    count: int  # Number of data points in this bin
    secs: int | None = None  # Time spent in this bin (seconds)


class Histogram(BaseModel):
    """Histogram data for activity metrics."""

    bins: list[HistogramBin] = Field(default_factory=list[HistogramBin])
    total_count: int | None = None
    total_secs: int | None = None
