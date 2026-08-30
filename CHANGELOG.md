# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**The versioned contract covers what breaks integrations:** removing or renaming a
tool, removing or renaming a tool parameter, changing the meaning of a config env
var, changing which tools register by default, or removing information from a
response. Any of these requires a **major** bump. Response payload *shape* changes
that preserve the information (key renames, restructuring, added fields) ship in
**minor** releases — MCP responses are read dynamically by LLMs, not parsed by typed
clients. (Releases up to and including 4.0.0 treated any response-shape change as
breaking; this narrower contract applies from the next release onward.)

## [Unreleased]

### Fixed
- `icu_get_sport_settings` silently dropped the athlete's configured training zones. The API returns `hr_zones`, `power_zones`, and `pace_zones` (with their names) on every sport-settings record, but the `SportSettings` model never declared the fields, so they were discarded before the response was built — the same bug class as the #98 custom-wellness-fields and #109 hydration drops. This left the tool description's long-standing "and zones" claim untrue, and left models reasoning about zones from `icu_get_power_curves` / `icu_get_hr_curves`, which synthesize *generic* zones from a hardcoded formula (5 HR bands at 50-100% of max HR; 6 power bands off an FTP estimated as 20-min power × 0.95) rather than reading the athlete's configuration. The two disagree materially — on a live account the real Ride Z1 tops at 138 bpm across 7 named zones where the synthesized Z1 is 102-122 across 5 unnamed ones. `icu_get_sport_settings`, `icu_update_sport_settings`, and `icu_create_sport_settings` now return the configured zone sets: HR zones as absolute bpm ranges, power zones as %FTP, pace zones as % of threshold pace, each with its Intervals.icu name, alongside `max_hr_bpm`, `hr_load_type`, `hrrc_min_percent`, sweet-spot bounds, and default warmup/cooldown durations. Semantics were established against the live API, which documents none of them: the top power and pace zone carry `999` as an open-ended sentinel (rendered as `unbounded`, not a 999% ceiling), and unused zone sets arrive as `null` rather than `[]`. The update response carries zones too, so the effect of `recalc_hr_zones` is finally visible to the caller. `icu_get_athlete_profile` and the athlete-profile resource deliberately keep their existing lean output — zones add roughly 1k tokens per call. Reported by @jorge-huxley; implementation approach from @nitobosch's #116.

## [4.4.0] — 2026-07-31

### Fixed
- The fitness/fatigue/form tools ignored the requested athlete and always returned the configured default profile's CTL/ATL/TSB. `icu_get_fitness_summary` and `icu_get_athlete_profile` exposed **no parameters at all**, so a coach asking for a specific athlete's numbers got their own back with no error — the response looked normal and the substitution was only detectable by cross-checking the Intervals.icu web UI. Both now accept an optional `athlete_id`, as do `icu_get_wellness_data` and `icu_get_wellness_for_date` (wellness records carry CTL/ATL). The API client already supported per-athlete routing on all four; only the tool signatures were missing it. `icu_get_fitness_chart` already accepted `athlete_id` and was unaffected — verified against the live API, where an unauthorized ID correctly returns HTTP 403 rather than silently falling back. Reported by @alexxsirko (#99).
- `icu_update_wellness` also gained `athlete_id`, so a coach reading a managed athlete's wellness can write back to that athlete instead of silently updating their own record.
- `icu_get_fitness_summary` and `icu_get_fitness_chart` now echo the resolved `athlete_id` in the response. The #99 failure was undetectable because the payload never stated whose numbers it carried; naming the athlete makes a wrong-athlete answer visible without a trip to the web UI. (`icu_get_athlete_profile` already returned the id under `profile.id`.)
- `icu_get_fitness_summary`'s no-data message told the caller to "complete some activities to build your fitness history" — nonsense advice when a coach queries an athlete with no data. It now names the athlete and the date instead.
- All 9 MCP prompts told the model to call tools that do not exist — they referenced bare names (`get_fitness_summary`, `create_event`, `get_recent_activities`) while every tool registers as `icu_*`. Some prompts mixed both conventions in a single body. Hosts that surface prompts would hand the model a checklist of unresolvable tool names, leaving it to guess. All references now use the registered names, with a test asserting every tool a prompt names is actually registered so a future rename cannot silently stale them.
- `icu_get_wellness_data` / `icu_get_wellness_for_date` silently dropped athlete-defined custom wellness fields (e.g. REMSleep, ActiveEnergy): the `Wellness` model preserves unknown API keys via `extra="allow"`, but the response formatter only read enumerated fields, so custom values never reached the response. They now appear under a `custom_fields` key with their original Intervals.icu names; valid falsy values like `0` are kept, only `null` is omitted. Verified against the live API with a throwaway custom field (created, written, read back, cleaned up). Contributed by @1781412-cpu (#98).
- `validate_credentials()` treated the athlete id `i123456` as an unconfigured placeholder and rejected it — but it is a real Intervals.icu id that simply happens to be the example in `.env.example`. Because the check runs in `ConfigMiddleware` on every call, the (real) owner of that id could not use a single tool, and the error told them to re-run auth, which writes the same id back. The special-case is dropped; the API is the authority on whether credentials work (an invalid id already returns a clear HTTP 403/404). The `your_api_key_here` placeholder check on the key is kept — unlike the athlete id, it cannot collide with a real credential (#104).
- `icu_search_intervals` returned HTTP 422 on every call and had never worked: the client sent `minDuration`/`maxDuration` instead of the API's required `minSecs`/`maxSecs` and never sent the equally-required `minIntensity`/`maxIntensity` at all. All four bounds are now always sent, with unset bounds defaulting to the widest accepted range (0–86400 s, 0–999 %) so a bare call works, and `limit` is passed to the server instead of over-fetching. Two more defects surfaced during the live-verified fix: `type` is not a free-form label but the enum `AUTO`/`POWER`/`HR`/`PACE` (the interval's *target* type — values like `WORK` or a sport name 422), which the tool now documents, case-normalizes, and validates with a clear error before calling the API; and the endpoint returns full ~180-field Activity objects (~4.6 KB each — ~140 KB for the default 30 results), which are now projected down to the 8 interval-relevant fields under a `data.activities` key, keeping the `interval_summary` strings like `2x 8m 162w`. New optional `min_intensity`/`max_intensity` parameters round out the filters (#102).
- `icu_create_gear_reminder` and `icu_update_gear_reminder` never worked, and reminder data shown by `icu_get_gear_list` was silently reduced to an id — three stacked defects, all live-verified: the client called plural `.../reminders` paths that do not exist (HTTP 404; the API only serves singular `/reminder`, `/reminder/{id}`); the write payload used invented field names (`text`, `distance_alert`, `time_alert`) that the API rejects in favour of `name`, `distance` (m), `time` (s); and the `GearReminder` model declared those same invented fields, so parsing a real reminder dropped everything but the id. Tool parameters are unchanged (still `text`, `distance_alert` in km, `time_alert` in hours) and now map to the real fields; the model mirrors the actual schema; and since the API responds with the full gear object rather than the reminder, the client types it accordingly and the tools extract the affected reminder. The gear list now shows real reminder content including `percent_used` and usage-since-reset. Partial updates verified live: updating only the text preserves the distance threshold (#107).
- The wellness formatter silently dropped the subjective `hydration` rating (1-4) — the same bug class as the #98 custom-fields drop, one layer deeper: because `hydration` *is* enumerated on the `Wellness` model, it never reached the `custom_fields` fallback either. It now surfaces in the `subjective` block with its scale (`1-4, 1=well hydrated, 4=very dehydrated` — range live-verified: the API accepts exactly 1–4) in `metadata.scales`, and `icu_update_wellness` gained a `hydration` parameter so the metric is round-trippable end-to-end. The liters-drunk `hydrationVolume` is unaffected and stays a separate `nutrition.hydration_liters` field (#109).
- The `Gear` model itself used invented field names, discovered while live-testing the #107 fix: it read `gear_type`, `active`, `moving_time`, and `activity_count`, but the API's fields are `type` (a CamelCase enum: `Bike`, `Shoes`, `Trainer`, plus ~40 component types like `Chain` and `Cassette`), `retired` (a date string, null = in use), `time`, and `activities` — and the API has **no** `brand`, `model`, `active`, or `primary` fields at all. Consequences before the fix: `icu_get_gear_list` showed `type: null, active: null` and omitted total time and activity count for every gear item, and `icu_create_gear` silently created untyped gear while dropping `brand`/`model`/`primary`. The model now mirrors the real schema; the gear list additionally surfaces `purchased_on`, `notes`, and `retired_on`; `gear_type` still works on the tools (case-insensitive, mapped to the enum, validated with a clear error, `SHOE` alias kept) and `active` maps to `retired` (False retires the gear dated today, True un-retires it). `brand`/`model`/`primary` are accepted but reported as ignored in a response warning — the API cannot store them; dropping the params is deferred to the next major (#110).

### Added
- New `icu_list_athletes` tool — lists every athlete the API key can reach (the caller plus anyone they follow or coach), with each one's access level and a `can_write` flag. Until now there was **no way to discover a valid `athlete_id`**: 45 tools accept the parameter and nothing enumerated legal values, so coaches had to copy ids out of the web UI by hand. Backed by the documented `GET /api/v1/athletes` endpoint, projected down from ~160 fields per athlete to the four that matter (a 2-athlete roster drops from ~9.5 KB to ~0.6 KB). Access is derived from the API's `icu_permission` (`NONE`/`READ`/`WRITE`) and `icu_coach` fields, so a model can tell before calling whether a write will be permitted rather than discovering it via HTTP 403. Safe-mode tool count goes 58 → 59 (61 → 62 in full mode).
- `athlete_id` on the remaining 19 athlete-scoped tools, completing multi-athlete support: `icu_get_power_curves`, `icu_get_hr_curves`, `icu_get_pace_curves`, `icu_get_sport_settings`, `icu_update_sport_settings`, `icu_apply_sport_settings`, `icu_create_sport_settings`, `icu_delete_sport_settings`, `icu_get_gear_list`, `icu_create_gear`, `icu_update_gear`, `icu_delete_gear`, `icu_create_gear_reminder`, `icu_update_gear_reminder`, `icu_get_workout_library`, `icu_get_workouts_in_folder`, `icu_search_activities_full`, `icu_get_activities_around`, and `icu_search_intervals`. Previously multi-athlete support was half-shipped — activity and event tools honoured `athlete_id` while these silently answered for the configured default, which is the inconsistency behind #99. All 45 athlete-scoped tools now route consistently; the 16 tools scoped by a globally-unique `activity_id` correctly take no `athlete_id`. Verified against the live API (an inaccessible ID returns HTTP 403 rather than falling back).
- `docs/tools.md` now documents the coaching/following model, which had never been described: access is a per-relationship role (any account can coach), following grants read-only and coaching grants write, and the coach authenticates with their own API key.

## [4.3.2] — 2026-07-23

### Fixed
- `icu_get_workouts_in_folder` failed with HTTP 405 for every folder and training plan — broken since the initial release. It called `GET /athlete/{id}/folders/{folderId}/workouts`, but that Intervals.icu path is PUT-only (a bulk-update operation); the API has no per-folder listing endpoint at all. The client now fetches the athlete's full workout library (`GET /athlete/{id}/workouts`) and filters by `folder_id`. Verified against the live API. Reported by @gadelain (#95).

## [4.3.1] — 2026-07-21

### Fixed
- Every `icu_update_wellness` call crashed with a validation error (`sportInfo: Input should be a valid list`): the Intervals.icu API returns explicit `null` (not a missing key) for list/dict fields with no computed data — e.g. `sportInfo` on any wellness day without eFTP/W'/Pmax metrics, the common case — and Pydantic's `default_factory` only applies when the key is absent. All eight fields with this pattern now coerce `null` to an empty list/dict before validation: `Wellness.sport_info`, `Athlete.sport_settings`, `CurveData.secs`/`values`/`activity_id`/`watts_per_kg`, `CurveSet.curves`, `FitnessSummary.interpretation`, `IntervalsDTO.icu_intervals`, `BestEfforts.efforts`, and `Gear.reminders`. Verified against the live API. Contributed by @Jozwiaczek (#94).

## [4.3.0] — 2026-07-14

### Added
- New `icu_get_fitness_chart` tool — a read-only CTL/ATL/TSB time-series (Performance Management Chart) over a configurable window via required `days_back` / `days_ahead` (365-day cap each). Future points sourced from planned calendar workouts are tagged `is_projected: true`, and the response includes a summary block. Backed by a new optional `fields` param on the client's wellness fetch so only the fitness columns are pulled. Safe-mode tool count goes 57 → 58 (60 → 61 in full mode). Contributed by @jorge-huxley (#87).
- WORKOUT event responses from `icu_create_event`, `icu_update_event`, and `icu_bulk_create_events` now echo whether the `description` actually parsed into a structured workout: `workout_parsed` (bool), plus `workout_steps` (step count with repeats expanded) when it did, or a `workout_parse_hint` pointing at the correct syntax when it didn't. Previously these tools returned a silent success even when a description was stored as unparsed prose — producing no steps, no zones, and no training load — leaving the caller no signal that the workout was not structured. Backed by the `workout_doc` field now retained on the `Event` model. For `Swim` workouts whose work steps carry no pace or HR target (so they get no usable training load), an extra `workout_load_hint` explains why — swim load needs a pace target with a swim CSS/threshold set (commonly unset), or an HR target (which loads off swim FTHR without a CSS) — so the caller can fix it instead of shipping a silent zero-load swim.

### Fixed
- `icu_update_sport_settings` / `icu_create_sport_settings` could not set a swim CSS/threshold pace: the write path multiplied the pace by 60 and sent seconds (e.g. `240` for 4:00/100m), which the API rejects with HTTP 422 "Invalid threshold pace". Intervals.icu stores the swim threshold as **speed in m/s** (unlike run, which is min/km) — confirmed against the live API and UI, where a stored `4.0` renders as `0:25/100m` (= 4 m/s). The swim path now converts min/100m ↔ m/s on both write and read (`100 / (min × 60)`). Verified live end-to-end: setting 4:00/100m stores `0.4167` and renders as `4:00/100m` in Intervals.icu (#88).
- Pace-target syntax was mis-documented and silently failing: absolute pace requires a trailing `pace` keyword — the bare forms previously taught by the resource and the cheat-sheet (`5:00/km`, `8:00/mi`, `1:45/100m`) are dropped by the parser, and absolute swim pace denominators are `/100m`/`/100y` (not the `mtr`/`yrd` spellings that step distances use). All live-verified against the parser; the resource, the inline cheat-sheet, and the swim `workout_load_hint` now teach the working forms (`- 5m 4:45/km pace`, `- 200mtr 1:45/100m pace`) plus the relative threshold form (`100% pace` = run threshold / swim CSS), and warn that the words `CSS`/`threshold`/`5K pace` are not parsed as targets — the exact failures observed from two models in community testing. The hint also now tells the model to check `icu_get_sport_settings` before reporting the athlete's CSS unset (the old wording led a model to claim an already-set CSS was missing).
- `icu_bulk_create_events` now accepts `event_type` as an alias for the API's `type` field on each event object, matching the parameter name `icu_create_event` / `icu_update_event` already expose. Previously the singular tools took `event_type` while the bulk tool only read raw `type`, so a model reusing the singular interface in a bulk payload silently created events with no sport discipline (and RACE events failed validation). `event_type` is now the documented field for all three tools; raw `type` is still accepted and wins if both are supplied.

### Changed
- The `description` parameter of `icu_create_event` / `icu_update_event` and the `events` parameter of `icu_bulk_create_events` now carry a compact inline Intervals.icu workout-syntax cheat-sheet instead of only pointing at the `intervals-icu://workout-syntax` resource. Many MCP hosts (e.g. Claude Desktop) never surface resources to the model, so a model on those hosts could not read the spec and fell back to inventing non-native formats that silently fail to parse; the in-context cheat-sheet targets the specific failure modes observed in testing (bracket DSLs, nested bullets, target-before-duration, bare run zones with no load, dropped cadence targets, missing rest-interval syntax, `m`-vs-`mtr` distance-unit confusion, and missing blank lines around repeat blocks — which silently collapse a repeat to a single rep). The resource is retained for hosts that can read it.
- Documented the previously-undocumented `intensity=warmup|active|rest|cooldown` step attribute in the `intervals-icu://workout-syntax` resource — it sets the structured-workout step *type* (used when syncing to a device) and has no effect on duration, distance, zones, or training load. Live FIT/ZWO export probes established the device semantics, now reflected in the resource and in the cheat-sheet's rest clause: section headers already export to FIT as warmup/cooldown steps, `intensity=rest` is the only form that exports a true device rest step (an appended `Ns rest` folds into the step's planned duration without exporting a rest step), and Zwift `.zwo` export ignores step types entirely.

## [4.2.0] — 2026-07-10

### Added
- `indoor_ftp` is now exposed end-to-end: new field on the `SportSettings` model, surfaced in `icu_get_sport_settings`, writable via `icu_update_sport_settings` / `icu_create_sport_settings`, and included in `icu_get_athlete_profile` and the `intervals-icu://athlete/profile` resource. Contributed by @jorge-huxley (#85).
- New `recalc_hr_zones` parameter (default `true`) on `icu_update_sport_settings` — the API's update endpoint requires the `recalcHrZones` query param, which the client previously never sent (#85).

### Changed
- Sport settings tool responses now use unified threshold field names from a shared formatter: `ftp_watts`, `indoor_ftp_watts`, `fthr_bpm`, and human-readable running/swim pace strings — the same shape across `icu_get_sport_settings`, update/create, the athlete profile tool, and the profile resource. Response-shape change that preserves the information (minor under the versioning contract) (#85).
- Docs: removed the misleading "zone configuration" claim from the sport settings tool descriptions and clarified what `icu_apply_sport_settings` vs `icu_update_sport_settings` actually do (#85).

### Fixed
- Sport settings data was silently dropped when parsing live API responses: the model expected legacy field names, but the API returns `sportSettings` (embedded in the athlete), `lthr`, `threshold_pace`, `types[]`, and swim pace as `SECS_100M`. Before the fix, `icu_get_athlete_profile` parsed zero embedded sport settings and threshold fields came back empty. Writes had the mirror-image bug — MCP parameters are now translated to the documented API field names (`types`, `lthr`, `threshold_pace` plus pace-unit metadata). Verified against the live API. Contributed by @jorge-huxley (#85).
- `icu_apply_sport_settings` failed with HTTP 405 on every call: the client sent `POST`, but the live API only accepts `PUT`. The non-functional `oldest_date` parameter was removed — normally a parameter removal is breaking, but the tool never worked, so this ships as a bug fix (#85).
- `icu_update_sport_settings` / `icu_create_sport_settings` now reject `pace_threshold` and `swim_threshold` in the same call with a validation error — the API stores one pace triple per sport settings record, so passing both silently lost one of them (#85).

## [4.1.0] — 2026-07-07

### Added
- New `icu_get_annual_training_plan` tool — reads Annual Training Plan (ATP) periodization from the calendar: weekly load targets (TSS), Base/Build/Peak phase blocks, and per-week notes as structured `week_note` objects (ATP-generated `plan_applied` notes only — overlapping personal calendar notes are excluded), shaped from `PLAN`/`TARGET`/`NOTE` events. Defaults to a 365-day forward window; narrow with `days_ahead`/`days_back`. Safe-mode tool count goes 55 → 56 (58 → 59 in full mode). Contributed by @jorge-huxley (#73, #84).
- New `icu_get_activities_by_date` tool — lists activities in an explicit date window (`oldest`/`newest`, YYYY-MM-DD, both inclusive; `newest` defaults to today), bounded only by `limit` (default 500, newest-first). Reaches arbitrary historical windows that `icu_get_recent_activities` (anchored to today, capped at 100) cannot. Safe-mode tool count goes 56 → 57 (59 → 60 in full mode). Contributed by @rfrancica (#74).
- The `Event` model now retains `load_target`, `time_target`, `tags`, and `plan_applied` from the API (previously dropped during validation).

### Changed
- Versioning policy: the SemVer contract is narrowed to what breaks integrations — tool names, tool parameters, config env var semantics, default tool registration, and removal of information from responses. Response-shape changes that preserve information (key renames, restructuring, added fields) are now **minor**, not major. See the header above. Previously any response-shape change forced a major bump.
- `client.get_activities()` now passes `limit` to the API as a query param instead of fetching the entire date range and truncating client-side. Verified against the live API that server-side `limit` keeps the newest N in descending order — identical results, far less data over the wire for wide date windows (#80).

### Fixed
- Corrected the distance units in the `intervals-icu://workout-syntax` resource: meters are `mtr` (e.g. `400mtr`) and yards are `yrd`, not the ambiguous `m`/`yd`. Intervals.icu parses a bare `m` as **minutes**, so the previous docs led LLMs to write `400m` for a 400 m swim step — parsed as 400 minutes, producing wildly inflated durations and distances (a 2500 m swim came out as ~417 km / ~41 h). All swim/run examples now use `mtr`, and a note spells out the `m`-means-minutes rule (#75).
- `icu_get_activities_around` failed with HTTP 422 on every call: the client sent query params `id`/`count`, but the API requires `activity_id`/`limit`. New regression tests assert the outgoing query params, not just the URL path — the gap that let this slip through (#74).

## [4.0.0] — 2026-06-18

### Added
- `icu_get_activity_details` now surfaces a dedicated `nutrition` section grouping `calories_burned`, `carbs_ingested_g`, and `carbs_used_g`. `carbs_used` is a new field on the `Activity` model (was previously dropped on the floor). The `_g` suffix on carb fields signals grams (matching the wellness-side `carbohydrates_g` convention).
- `icu_get_activity_details` now emits `metadata.subjective_scales` (`{"feel": "1-5", "rpe": "1-10"}`) whenever the corresponding values are present, so downstream LLMs stop interpreting raw ordinals on an assumed 0-10 scale.

### Changed
- **Breaking — response shape:** `icu_get_activity_details` renamed the `calories` output key to `calories_burned` and moved it out of the `other` section into the new `nutrition` section. The API field is energy expenditure; the prior label collided with the wellness-side `calories_consumed`/`kcalConsumed` (intake), confusing intake-vs-expenditure comparisons.

## [3.0.0] — 2026-05-20

This release focuses on **token efficiency** and **tool-selection accuracy**. Combined effect: ~3,300-3,500 fewer tokens per default-mode session (~35% of the pre-release tool-description budget). First-tool-call routing accuracy on Haiku 4.5 improved from 28/35 (80%) on the pre-trim baseline to 30/35 (86%) on the merged set, measured by the new smoke-eval harness (0 regressions).

### Added
- Two new MCP Resources: `intervals-icu://event-categories` (calendar event category enum + use-case mapping + training_availability values) and `intervals-icu://custom-item-schemas` (per-item_type `content` schema for `create_custom_item` / `update_custom_item` with INPUT_FIELD/ACTIVITY_FIELD/INTERVAL_FIELD constraints and worked examples). The tool descriptions now point at these instead of inlining the same prose every session.
- Tool-selection accuracy: rewrote disambiguating first-sentences across 9 confusable tools — `icu_get_activity_details` / `icu_get_activity_intervals` / `icu_get_activity_streams`, `icu_search_activities` / `icu_search_activities_full`, `icu_get_wellness_data` / `icu_get_wellness_for_date`, and `icu_create_event` / `icu_bulk_create_events` / `icu_duplicate_events`. Each first sentence now leads with the distinguishing access pattern (SUMMARY / per-LAP / RAW; LIGHT / FULL; RANGE / ONE; ONE new / MANY new / COPY existing) so the LLM picks the right tool first instead of a wrong-tool round-trip.
- Long-tail tool-description trim across the remaining ~40 tools (activities, activity_analysis, activity_messages, athlete, curves, custom_items, events, event_management, gear, performance, sport_settings, wellness, workout_library). Removed redundant `Args:` blocks (which duplicate Annotated descriptions) and trivial `Returns:` blocks; tightened first sentences to lead with the distinguishing access pattern. Estimated additional ~2,000 tokens saved upfront per session on top of the new Resources and first-sentence rewrites. Net -400 lines across 13 files; no behavior change.
- Smoke-eval harness for first-tool-call routing accuracy: `scripts/smoke_eval.py`, `tests/smoke_eval.json` (35 routing cases), `scripts/smoke_eval_diff.py`, and `make smoke-eval` / `make smoke-eval/save` / `make smoke-eval/diff` targets. Drives the Anthropic API with the MCP server's in-process tool definitions and records which tool the model picks first per case. Never executes any tool (`DRY_RUN = True` guard, asserted at runtime); never touches the intervals.icu API. Used to validate routing impact of this release and as durable infrastructure for any future PR that touches tool descriptions. Costs ~$0.07 per run; not part of `make test`. Requires only `ANTHROPIC_API_KEY` (set in `.env`).

### Fixed
- Histogram tools (`icu_get_hr_histogram`, `icu_get_power_histogram`, `icu_get_pace_histogram`, `icu_get_gap_histogram`) crashed with `argument after ** must be a mapping, not list` on any activity with real data. The endpoints return a bare JSON array of `{min, max, secs}` objects, not a wrapper object; the previous `Histogram`/`HistogramBin` models never matched the actual API (the OpenAPI spec advertises a richer shape that isn't populated by these endpoints). Replaced with a minimal `Bucket` model and added regression tests with real-shape payloads.
- Tool docstring cross-references now consistently use the registered `icu_*` tool names (e.g. `icu_get_activity_intervals`) instead of bare function names (`get_activity_intervals`). Eliminates an inference step the LLM would otherwise have to perform when bridging documentation cross-refs to its tool list — defensive against stricter / smaller models even though Haiku 4.5 bridges internally.
- `ICUConfig` (auth.py) now sets `extra="ignore"` so `.env` can host secrets for unrelated tools (e.g. `ANTHROPIC_API_KEY` for the smoke-eval harness) without breaking validation of the intervals-icu config.

### Changed
- **Breaking — response shape:** Histogram tools now return `buckets` (was `bins`), each shaped `{<metric>_range: {min_*, max_*}, time_seconds}` where boundaries come straight from the API's `min`/`max` fields. The previous `count` field is dropped (the API doesn't return raw sample counts — `secs` is time-in-bucket).
- **Breaking — response shape:** removed `fetched_at` and `query_type` from the auto-generated `metadata` block. The `metadata` key still exists on every response (tools still attach their own fields). Set `INTERVALS_ICU_DEBUG_METADATA=true` to restore the old behavior for debugging.
- Trimmed verbose param descriptions on `icu_create_event`, `icu_update_event`, `icu_bulk_create_events`, `icu_create_custom_item`, and `icu_update_custom_item`. Long enum lists and content schemas moved to the new Resources (measured ~1,200 tokens saved upfront per default-mode session). Pure tool-description change; no behavioral or response-shape change.

## [2.0.0] — 2026-04-29

### Added
- `INTERVALS_ICU_DELETE_MODE` env var (`safe` / `full` / `none`) gating which destructive tools are registered with the server. The gate sits outside the model's reach — unregistered tools cannot be invoked. See the README's *Delete Safety Mode* section.
- Safe-mode partition logic: `delete_event` / `bulk_delete_events` skip past events (today and earlier) and return a uniform `deleted` / `skipped` envelope with reason codes.
- Startup log line: `intervals-icu MCP starting: delete_mode=<mode>, registered_tools=<n>`.
- Strava-restricted activity detection: activity and analysis tools surface an explanation when Strava data is unavailable due to privacy settings.
- `update_wellness` now accepts the full set of writable fields: nutrition macros (`calories`, `carbs`, `fat`, `protein`), body composition (`body_fat`, `abdomen`, `vo2max`), vitals (`systolic`, `diastolic`, `spo2`, `respiration`), lab results (`blood_glucose`, `lactate`), `injury` (1-5 scale), `menstrual_phase`, and `locked` (prevents device sync from overwriting manual entries).

### Fixed
- Wellness tools: surfaced previously dropped API fields and added human-readable labels for subjective scales (sleep quality, readiness, mood, fatigue, etc.).

### Changed
- **Breaking — default behavior:** `delete_activity`, `delete_sport_settings`, `delete_custom_item` are no longer registered out of the box. Set `INTERVALS_ICU_DELETE_MODE=full` to restore them. Sport settings and custom items are gated because their deletion impacts historical chart math and stored activity data, respectively.
- **Breaking — response shape:** `delete_event` returns the `deleted` / `skipped` envelope (was `{event_id, deleted: true}`).
- Bumped FastMCP from 3.1.1 to 3.2.4.

## [1.3.0] — 2026-04-26

### Added
- **Activity messages tools** — read and write notes/comments on activities via `icu_get_activity_messages` and `icu_add_activity_message`.
- **Custom items tools** — full CRUD for custom charts, fields, zones, and dashboard items via `icu_get_custom_items`, `icu_get_custom_item`, `icu_create_custom_item`, `icu_update_custom_item`, `icu_delete_custom_item`. Includes documented content schema and conditional-required fields for field-type items.
- ChatGPT connector setup documented in the README (HTTP transport + tunnel walkthrough).
- Automated OpenAPI spec refresh via `.github/workflows/update-openapi.yml`; bot commits are GPG-signed to satisfy the verified-signature branch rule.

### Fixed
- Docker release build: package version is now derived from a pre-built wheel so `hatch-vcs` resolves correctly inside the build context.
- MCP Registry publish: `mcp-publisher` asset glob updated to the current upstream artifact name.

## [1.2.0] — 2026-04-25

### Added
- **Full calendar category support** — `create_event` / `update_event` / `bulk_create_events` accept the complete Intervals.icu category enum (RACE_A/B/C, TARGET, PLAN, HOLIDAY, SICK, INJURED, SET_EFTP, FITNESS_DAYS, SEASON_START, SET_FITNESS) plus range fields (`end_date_local`) and `training_availability` (NORMAL/LIMITED/UNAVAILABLE) for life-event blocks. Legacy `RACE`→`RACE_A` and `GOAL`→`TARGET` aliases accepted.
- Automated MCP Registry publishing on release via GitHub OIDC — `server.json` version is synced from the release tag, no manual bump required.
- PyPI package quality gates in CI: `twine check`, `pyroma --min=10`, and link verification.
- Dynamic versioning via `hatch-vcs` — package version flows from the git tag, no manual edits in `pyproject.toml`.

### Changed
- README trimmed; reference content extracted to [docs/examples.md](docs/examples.md) and [docs/tools.md](docs/tools.md) for clearer onboarding and discoverability.

## [1.1.0] — 2026-04-24

### Added
- HTTP and SSE transports via a `--transport` flag, enabling remote deployment behind a reverse proxy, tunnel, or container. See the Remote Deployment section of the README.
- CI coverage gate to prevent regressions in test coverage.
- Automated transport smoke test that replaces the previously manual MCP Inspector check.

### Changed
- Expanded the HTTP transport security warning in the README with concrete deployment guidance (Tailscale, Cloudflare Tunnel, reverse-proxy-with-auth, SSH tunnel).

## [1.0.2] — 2026-04-24

### Fixed
- LICENSE file now packaged with the PyPI distribution and links resolve correctly from the PyPI page.
- `server.json` description shortened to meet the MCP Registry 100-char limit.

## [1.0.1] — 2026-04-24

### Added
- PyPI publish workflow via Trusted Publishers.
- MCP Registry submission metadata (`server.json`).

### Changed
- Documentation leads with the `uvx` install flow now that the package is on PyPI.

## [1.0.0] — 2026-04-23

Initial release of this independent continuation of [eddmann/intervals-icu-mcp](https://github.com/eddmann/intervals-icu-mcp) (MIT).

### Fixed
- **Power/HR/pace curves** — rewrote curve models to match actual API response format, added required `type` parameter, fixed query parameter format.
- **Fitness summary** — CTL/ATL/TSB now fetched from wellness endpoint (was returning empty from athlete endpoint).
- **Duplicate events** — fixed to correct API endpoint and batch body format.
- **Bulk delete events** — fixed HTTP method and endpoint.
- **Activity intervals** — API returns wrapped `IntervalsDTO` object, not a flat list; fixed model to extract `icu_intervals`.
- **Best efforts** — added required `stream` parameter (watts, heartrate, pace); fixed response model to match API `BestEfforts` format.
- **Activity streams** — API returns array of stream objects, not a dict; fixed endpoint to use `.json` extension and correct model.
- **Date parsing** — event tools now handle ISO-8601 datetime formats correctly.
- **Missing event IDs** — calendar and workout responses include event IDs, enabling update/delete operations.

### Added
- **Structured Workout Generation** — LLM-ready workout syntax resource (`intervals-icu://workout-syntax`) and `generate_workout` prompt for creating valid structured workouts across cycling, running, and swimming. Syntax spec attributed to [MarvinNazari/intervals-icu-workout-parser](https://github.com/MarvinNazari/intervals-icu-workout-parser) (MIT).
- **New Bulk/Streams APIs** — full support for `icu_apply_training_plan`, `icu_bulk_create_manual_activities`, and `icu_update_activity_streams`.
- **MCP Builder Standards** — universal `icu_` naming prefix and `destructiveHint` safeguards for all modification tools.
- **Multi-athlete support** — optional `athlete_id` parameter on activity, event, and calendar tools.
- **MCP verification prompts** — `verify-setup` and `verify-multi-athlete` for live validation.

### Changed
- Upgraded to FastMCP 3.x.
- Added middleware integration tests.
- Added tests for multi-athlete routing, model aliases, and date handling.
