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
- `icu_bulk_create_events` now accepts `event_type` as an alias for the API's `type` field on each event object, matching the parameter name `icu_create_event` / `icu_update_event` already expose. Previously the singular tools took `event_type` while the bulk tool only read raw `type`, so a model reusing the singular interface in a bulk payload silently created events with no sport discipline (and RACE events failed validation). `event_type` is now the documented field for all three tools; raw `type` is still accepted and wins if both are supplied.

### Added
- WORKOUT event responses from `icu_create_event`, `icu_update_event`, and `icu_bulk_create_events` now echo whether the `description` actually parsed into a structured workout: `workout_parsed` (bool), plus `workout_steps` (step count with repeats expanded) when it did, or a `workout_parse_hint` pointing at the correct syntax when it didn't. Previously these tools returned a silent success even when a description was stored as unparsed prose — producing no steps, no zones, and no training load — leaving the caller no signal that the workout was not structured. Backed by the `workout_doc` field now retained on the `Event` model. For `Swim` workouts that parse but compute no training load, an extra `workout_load_hint` explains why — swim load needs a pace target with a swim CSS/threshold set (commonly unset), or an HR target (which loads off swim FTHR without a CSS) — so the caller can fix it instead of shipping a silent zero-load swim.

### Changed
- The `description` parameter of `icu_create_event` / `icu_update_event` and the `events` parameter of `icu_bulk_create_events` now carry a compact inline Intervals.icu workout-syntax cheat-sheet instead of only pointing at the `intervals-icu://workout-syntax` resource. Many MCP hosts (e.g. Claude Desktop) never surface resources to the model, so a model on those hosts could not read the spec and fell back to inventing non-native formats that silently fail to parse; the in-context cheat-sheet targets the specific failure modes observed in testing (bracket DSLs, nested bullets, target-before-duration, bare run zones with no load, dropped cadence targets, missing rest-interval syntax, `m`-vs-`mtr` distance-unit confusion, and missing blank lines around repeat blocks — which silently collapse a repeat to a single rep). The resource is retained for hosts that can read it.

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
