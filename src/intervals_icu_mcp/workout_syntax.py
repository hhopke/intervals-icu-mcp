"""Intervals.icu workout syntax reference for LLM consumption.

This module provides the structured workout syntax specification that
Intervals.icu uses. When the 'description' field of a WORKOUT event
contains this syntax, the Intervals.icu server automatically parses it
into a structured workout_doc with training load, zone distribution,
and device sync support.

Workout syntax specification adapted from intervals-icu-workout-parser
by Marvin Nazari (MIT License).

Source: https://github.com/MarvinNazari/intervals-icu-workout-parser
Spec:   https://marvinnazari.github.io/intervals-icu-workout-parser/llms-spec.txt
Forum:  https://forum.intervals.icu/t/using-ia-chatgpt-to-write-intervals-icu-workouts/85094

Copyright (c) 2025 Marvin Nazari - MIT License
See https://github.com/MarvinNazari/intervals-icu-workout-parser/blob/main/LICENSE
"""

WORKOUT_SYNTAX_SPEC = """# Intervals.icu Workout Syntax Reference

Complete specification for the Intervals.icu workout text format. This format is
used to define structured workouts with sections, repeats, duration, and intensity
targets for cycling, running, and swimming. Place this text in the 'description'
field when creating WORKOUT events via the API.

## Structure Overview
A workout consists of:
1. **Title** (first non-empty line, optional when using API - use the 'name' field instead)
2. **Sections** (Warmup, Main Set, Cooldown, or custom names)
3. **Steps** within sections (duration + optional target)

```
Section Name [repeat]
- duration target
- duration target

Another Section
- duration target
```

## Sections
Sections group related steps. Common names: `Warmup`, `Warm Up`, `Main Set`, `Main`, `Cooldown`, `Cool Down`.

Add repeat count after section name:

```
Main Set 3x
- 5m 90%
- 2m 50%
```

Or standalone repeat:

```
Intervals 5x
- 400m 110% pace
- 400m Z1
```

**Important**: Leave a blank line before and after repeat blocks.

## Duration Formats

### Time-Based
| Format | Example | Description |
|--------|---------|-------------|
| `Xm` | `10m` | Minutes |
| `Xs` | `30s` | Seconds |
| `Xh` | `1h` | Hours |
| `XhYm` | `1h30m` | Hours and minutes |
| `XmYs` | `5m30s` | Minutes and seconds |
| `X:YY` | `5:00` | Minutes:seconds |
| `X:YY:ZZ` | `1:30:00` | Hours:minutes:seconds |

### Distance-Based
| Format | Example | Description |
|--------|---------|-------------|
| `Xm` | `400m` | Meters (context-dependent, >200 = meters) |
| `Xkm` | `5km` | Kilometers |
| `Xmi` | `3mi` | Miles |
| `Xyd` | `100yd` | Yards (swimming) |

### Lap Press
```
- lap press Z2
```
Step ends when user presses lap button on device.

## Target Formats

### Power (Cycling)
| Format | Example | Description |
|--------|---------|-------------|
| `X%` | `90%` | Percentage of FTP |
| `X% power` | `90% power` | Explicit power target |
| `X-Y%` | `88-94%` | Power range |
| `Xw` | `250w` | Absolute watts |
| `X-Yw` | `240-260w` | Watts range |
| `ZX` | `Z4` | Power zone (Z1-Z7) |

### Heart Rate
| Format | Example | Description |
|--------|---------|-------------|
| `X% HR` | `75% HR` | Percentage of max HR or LTHR |
| `X-Y% HR` | `70-80% HR` | HR range |
| `Xbpm` | `145bpm` | Absolute BPM |
| `X-Ybpm` | `140-150bpm` | BPM range |
| `ZX HR` | `Z2 HR` | HR zone |

### Pace (Running/Swimming)
| Format | Example | Description |
|--------|---------|-------------|
| `X% pace` | `90% pace` | Percentage of threshold pace |
| `X-Y% pace` | `85-90% pace` | Pace range |
| `X:XX/km` | `5:00/km` | Minutes per kilometer |
| `X:XX/mi` | `8:00/mi` | Minutes per mile |
| `X:XX/100m` | `1:45/100m` | Per 100m (swimming) |
| `ZX pace` | `Z3 pace` | Pace zone |

### Cadence
| Format | Example | Description |
|--------|---------|-------------|
| `Xrpm` | `90rpm` | Target cadence |
| `X-Yrpm` | `85-95rpm` | Cadence range |

### Ramps
Use `ramp` for gradual intensity changes over a step's duration:
```
- 10m ramp 50%-75%
- 10m ramp 60-80% pace
```

### Combined Targets
Multiple targets can be combined on one line:
```
- 10m 88-94% 90rpm
- 5km Z2 HR 170spm
```

### Free Ride / No Target
```
- 20m free
```
ERG mode off, no target.

### Text Prompts / Instructions
Text before the duration becomes a device prompt or instruction:
```
- Spin easy 5m 50%
- High cadence 3m 80% 100rpm
```

## Rest Intervals
Rest can be specified after the main target:
```
- 200m 95% pace 30s rest
- 100m Z4 20s rest
```

## Complete Examples

### Cycling - Sweet Spot
```
Warmup
- 10m 55%
- 5m 70%

Main Set 3x
- 10m 88-94%
- 5m 55%

Cooldown
- 10m 50%
```

### Cycling - VO2max Intervals
```
Warmup
- 15m 55%
- 3x 1m 80%

Main Set 5x
- 3m 106-120%
- 3m 50%

Cooldown
- 10m 50%
```

### Running - Tempo Run
```
Warmup
- 15m Z2 HR

Main Set
- 20m 85-90% pace

Cooldown
- 10m Z1 HR
```

### Running - 800m Repeats
```
Warmup
- 15m Z2 HR
- 4x 100m strides

Main Set 5x
- 800m 105-110% pace
- 400m Z1 HR

Cooldown
- 10m Z1 HR
```

### Swimming - CSS Training
```
Warmup
- 400m Z2 pace
- 4x 50m 85% pace

Main Set 5x
- 200m 95% pace 30s rest

Cooldown
- 200m Z1 pace
```

## Zone Reference

### Power Zones (Z1-Z7)
| Zone | Name | % FTP |
|------|------|-------|
| Z1 | Active Recovery | <55% |
| Z2 | Endurance | 55-75% |
| Z3 | Tempo | 76-87% |
| Z4 | Threshold | 88-94% |
| Z5 | VO2max | 95-105% |
| Z6 | Anaerobic | 106-120% |
| Z7 | Neuromuscular | >120% |

### HR Zones (Z1-Z5)
| Zone | Name | % Max HR |
|------|------|----------|
| Z1 | Recovery | 50-60% |
| Z2 | Aerobic | 60-70% |
| Z3 | Tempo | 70-80% |
| Z4 | Threshold | 80-90% |
| Z5 | VO2max | 90-100% |

### Pace Zones
Based on threshold/CSS pace. Zone numbers vary by sport and methodology.
"""
