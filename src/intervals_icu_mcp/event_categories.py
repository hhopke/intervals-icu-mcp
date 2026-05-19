"""Intervals.icu calendar event categories reference for LLM consumption.

Exposed as the `intervals-icu://event-categories` MCP Resource. The
`category` parameter on event-management tools (create_event, update_event,
bulk_create_events) points the LLM here instead of inlining the full enum +
use-case mapping in every Annotated description.
"""

EVENT_CATEGORIES_SPEC = """# Intervals.icu Calendar Event Categories

Use this reference when picking a `category` value for create_event /
update_event / bulk_create_events. Match the user's intent to the closest
category. The API enforces the enum strictly — unknown values are rejected.

## Categories by use case

### Planned training
- `WORKOUT` — a planned workout. For structured workouts, put
  Intervals.icu workout syntax in the `description` field (see the
  `intervals-icu://workout-syntax` resource). The server parses the text
  into a structured workout with training load and zone distribution.
- `PLAN` — a training plan day marker (used by training-plan automation).

### Races
- `RACE_A` — top-priority "A" race
- `RACE_B` — secondary race
- `RACE_C` — minor race / tune-up event

Race events **require** an `event_type` (activity discipline). The API
rejects races without a discipline. Valid disciplines: `Ride`, `Run`,
`Swim`, `Walk`, `Hike`, `VirtualRide`, `VirtualRun`, `Other`.

### Performance goals
- `TARGET` — a performance goal or milestone (e.g. "FTP 300W by June").

### Life events (typically use start_date + end_date + training_availability)
- `HOLIDAY` — vacation / time off (German UI: Urlaub)
- `SICK` — illness (German UI: Krank)
- `INJURED` — injury (German UI: Verletzt)

For these ranged categories, set `training_availability` so the planner
knows how to handle scheduled workouts in the window:
- `NORMAL` — train as planned (German UI: Verfügbar)
- `LIMITED` — partial training capacity (German UI: Begrenzt)
- `UNAVAILABLE` — no training (German UI: Nicht verfügbar)

### Fitness chart adjustments
- `SET_EFTP` — manually set eFTP (estimated FTP) on this date
- `FITNESS_DAYS` — adjust fitness-days count (German UI: Fitnesstage)
- `SEASON_START` — season start marker (German UI: Saison)
- `SET_FITNESS` — manually set fitness (CTL) value

### Notes
- `NOTE` — generic calendar note. Use when the user wants to record
  something on a date that isn't a workout, race, or life event.

## Legacy aliases (accepted on input, normalized internally)
- `RACE` → `RACE_A`
- `GOAL` → `TARGET`

The server normalizes these before sending to the API. Users can pass
either form; new code should prefer the canonical names.

## Picking the right category

When the user's request is ambiguous, ask them. Common ambiguities:

- "Add a race" → ask which tier (A, B, C) so it weights the fitness
  chart correctly. Default to `RACE_A` only if the user makes it clear
  this is their main goal.
- "Block off some days" → ranged HOLIDAY/SICK/INJURED. Pick by reason;
  if the user just says "I'm not training next week," ask why.
- "Add a workout" → `WORKOUT`. If the user describes structure
  (intervals, targets), include it in `description` using workout syntax.
"""
