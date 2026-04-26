# Tool, Resource, and Prompt Reference

Complete inventory of everything the Intervals.icu MCP server exposes: 58 tools across 11 categories, 2 MCP Resources, and 7 MCP Prompts.

## Tools

### Activities (12 tools)

| Tool                     | Description                                       |
| ------------------------ | ------------------------------------------------- |
| `icu_get_recent_activities`  | List recent activities with summary metrics       |
| `icu_get_activity_details`   | Get comprehensive details for a specific activity |
| `icu_search_activities`      | Search activities by name or tag                  |
| `icu_search_activities_full` | Search activities with full details               |
| `icu_get_activities_around`  | Get activities before and after a specific one    |
| `icu_update_activity`        | Update activity name, description, or metadata    |
| `icu_delete_activity`        | Delete an activity                                |
| `icu_download_activity_file` | Download original activity file                   |
| `icu_download_fit_file`      | Download activity as FIT file                     |
| `icu_download_gpx_file`      | Download activity as GPX file                     |
| `icu_bulk_create_manual_activities` | Create multiple manual activities with upsert on external_id |
| `icu_update_activity_streams` | Update raw timeseries streams for an activity (JSON or CSV) |

### Activity Analysis (8 tools)

| Tool                     | Description                                                   |
| ------------------------ | ------------------------------------------------------------- |
| `icu_get_activity_streams`   | Get time-series data (power, HR, cadence, altitude, GPS)      |
| `icu_get_activity_intervals` | Get structured workout intervals with targets and performance |
| `icu_get_best_efforts`       | Find peak performances across all durations in an activity    |
| `icu_search_intervals`       | Find similar intervals across activity history                |
| `icu_get_power_histogram`    | Get power distribution histogram for an activity              |
| `icu_get_hr_histogram`       | Get heart rate distribution histogram for an activity         |
| `icu_get_pace_histogram`     | Get pace distribution histogram for an activity               |
| `icu_get_gap_histogram`      | Get grade-adjusted pace histogram for an activity             |

### Activity Messages (2 tools)

The threaded notes/comments shown under an activity — the user's own training notes, comments from followers, or coach feedback.

| Tool                       | Description                                                |
| -------------------------- | ---------------------------------------------------------- |
| `icu_get_activity_messages`    | Read notes/comments/coach feedback on a specific activity  |
| `icu_add_activity_message`     | Post a note or comment on a specific activity              |

### Athlete (2 tools)

| Tool                  | Description                                                     |
| --------------------- | --------------------------------------------------------------- |
| `icu_get_athlete_profile` | Get athlete profile with fitness metrics and sport settings     |
| `icu_get_fitness_summary` | Get detailed CTL/ATL/TSB analysis with training recommendations |

### Wellness (3 tools)

| Tool                    | Description                                                         |
| ----------------------- | ------------------------------------------------------------------- |
| `icu_get_wellness_data`     | Get recent wellness metrics with trends (HRV, sleep, mood, fatigue) |
| `icu_get_wellness_for_date` | Get complete wellness data for a specific date                      |
| `icu_update_wellness`       | Update or create wellness data for a date                           |

### Events / Calendar (10 tools)

| Tool                    | Description                                                |
| ----------------------- | ---------------------------------------------------------- |
| `icu_get_calendar_events`   | Get planned events and workouts from calendar              |
| `icu_get_upcoming_workouts` | Get upcoming planned workouts only                         |
| `icu_get_event`             | Get details for a specific event                           |
| `icu_create_event`          | Create new calendar events (workouts, races, notes, goals) |
| `icu_update_event`          | Modify existing calendar events                            |
| `icu_delete_event`          | Remove events from calendar                                |
| `icu_bulk_create_events`    | Create multiple events in a single operation               |
| `icu_bulk_delete_events`    | Delete multiple events in a single operation               |
| `icu_duplicate_events`      | Duplicate one or more events with configurable copies and spacing |
| `icu_apply_training_plan` | Apply an entire training plan (workout folder) onto the calendar |

### Performance / Curves (3 tools)

| Tool               | Description                                              |
| ------------------ | -------------------------------------------------------- |
| `icu_get_power_curves` | Analyze power curves with FTP estimation and power zones |
| `icu_get_hr_curves`    | Analyze heart rate curves with HR zones                  |
| `icu_get_pace_curves`  | Analyze running/swimming pace curves with optional GAP   |

### Workout Library (2 tools)

| Tool                     | Description                               |
| ------------------------ | ----------------------------------------- |
| `icu_get_workout_library`    | Browse workout folders and training plans |
| `icu_get_workouts_in_folder` | View all workouts in a specific folder    |

### Gear Management (6 tools)

| Tool                   | Description                                |
| ---------------------- | ------------------------------------------ |
| `icu_get_gear_list`        | Get all gear items with usage and status   |
| `icu_create_gear`          | Add new gear to tracking                   |
| `icu_update_gear`          | Update gear details, mileage, or status    |
| `icu_delete_gear`          | Remove gear from tracking                  |
| `icu_create_gear_reminder` | Create maintenance reminders for gear      |
| `icu_update_gear_reminder` | Update existing gear maintenance reminders |

### Sport Settings (5 tools)

| Tool                    | Description                                             |
| ----------------------- | ------------------------------------------------------- |
| `icu_get_sport_settings`    | Get sport-specific settings and thresholds              |
| `icu_update_sport_settings` | Update FTP, FTHR, pace threshold, or zone configuration |
| `icu_apply_sport_settings`  | Apply updated settings to historical activities         |
| `icu_create_sport_settings` | Create new sport-specific settings                      |
| `icu_delete_sport_settings` | Delete sport-specific settings                          |

### Custom Items (5 tools)

The user's personal additions to their account: custom charts on dashboards, custom data fields on wellness/activities/intervals, custom power/HR/pace zone configurations, custom activity panels, and custom computed streams. The Intervals.icu API umbrella name is "custom items".

| Tool                    | Description                                                                |
| ----------------------- | -------------------------------------------------------------------------- |
| `icu_get_custom_items`      | List the user's custom additions (charts, fields, zones, panels, etc.)     |
| `icu_get_custom_item`       | Fetch the full configuration of one custom addition by ID                  |
| `icu_create_custom_item`    | Add a new custom chart, field, zones config, or dashboard panel            |
| `icu_update_custom_item`    | Modify an existing custom addition (rename, reconfigure, change visibility)|
| `icu_delete_custom_item`    | Permanently remove a custom addition                                       |

## MCP Resources

Resources provide ongoing context to the LLM without requiring explicit tool calls.

| Resource                          | Description                                                              |
| --------------------------------- | ------------------------------------------------------------------------ |
| `intervals-icu://athlete/profile` | Complete athlete profile with current fitness metrics and sport settings |
| `intervals-icu://workout-syntax`  | Structured workout syntax reference for generating valid Intervals.icu workouts (cycling, running, swimming) |

## MCP Prompts

Prompt templates for common queries, accessible via prompt suggestions in Claude.

| Prompt                    | Description                                                              |
| ------------------------- | ------------------------------------------------------------------------ |
| `icu_analyze_recent_training` | Comprehensive training analysis over a specified period                  |
| `icu_performance_analysis`    | Detailed power/HR/pace curve analysis with zones                         |
| `icu_activity_deep_dive`      | Deep dive into a specific activity with streams, intervals, best efforts |
| `icu_recovery_check`          | Recovery assessment with wellness trends and training load               |
| `icu_training_plan_review`    | Weekly training plan evaluation with workout library                     |
| `icu_plan_training_week`      | AI-assisted weekly training plan creation based on current fitness       |
| `generate_workout`            | Generate a structured workout with sport, type, and duration parameters  |
