# Usage Examples

Ask Claude to interact with your Intervals.icu data using natural language. This page collects example prompts organized by tool category. For the full tool reference, see [tools.md](tools.md).

## MCP Prompts

Built-in prompt templates for common queries, available via prompt suggestions in Claude:

- `analyze-recent-training` — comprehensive training analysis over a specified period
- `performance-analysis` — analyze power/HR/pace curves and zones
- `activity-deep-dive` — deep dive into a specific activity with streams, intervals, and best efforts
- `recovery-check` — recovery assessment with wellness trends and training load
- `training-plan-review` — weekly training plan evaluation with workout library
- `plan-training-week` — AI-assisted weekly training plan creation based on current fitness
- `generate-workout` — generate a structured workout for any sport (cycling, running, swimming) with proper Intervals.icu syntax

## Activities

```
"Show me my activities from the last 30 days"
"Get details for my last long run"
"Find all my threshold workouts"
"Update the name of my last activity"
"Delete that duplicate activity"
"Download the FIT file for my race"
```

## Activity Analysis

```
"Show me the power data from yesterday's ride"
"What were my best efforts in my last race?"
"Find similar interval workouts to my last session"
"Show me the intervals from my workout on Tuesday"
"Get the power histogram for my last ride"
"Show me the heart rate distribution for that workout"
```

## Athlete Profile & Fitness

```
"Show my current fitness metrics and training load"
"Am I overtraining? Check my CTL, ATL, and TSB"
```

_Note: The athlete profile resource (`intervals-icu://athlete/profile`) automatically provides ongoing context._

## Wellness & Recovery

```
"How's my recovery this week? Show HRV and sleep trends"
"What was my wellness data for yesterday?"
"Update my wellness data for today - I slept 8 hours and feel great"
```

## Calendar & Planning

```
"What workouts do I have planned this week?"
"Create a sweet spot cycling workout for tomorrow"
"Create a tempo run with 800m repeats for Wednesday"
"Generate a CSS swim training session for Friday"
"Update my workout on Friday"
"Delete the workout on Saturday"
"Duplicate this week's plan for next week"
"Create 5 workouts for my build phase"
```

> **Structured Workouts**: The server includes a complete workout syntax reference (`intervals-icu://workout-syntax`) that enables LLMs to generate valid structured workouts with proper power/HR/pace targets, zones, ramps, repeats, and cadence for cycling, running, and swimming.

## Performance Analysis

```
"What's my 20-minute power and FTP?"
"Show me my heart rate zones"
"Analyze my running pace curve"
```

## Workout Library

```
"Show me my workout library"
"What workouts are in my threshold folder?"
```

## Gear Management

```
"Show me my gear list"
"Add my new running shoes to gear tracking"
"Create a reminder to replace my bike chain at 3000km"
"Update the mileage on my road bike"
```

## Sport Settings

```
"Update my FTP to 275 watts"
"Show my current zone settings for cycling"
"Set my running threshold pace to 4:30 per kilometer"
"Apply my new threshold settings to historical activities"
```
