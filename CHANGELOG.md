# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

This release will be cut as **2.0.0** — destructive-tool defaults change and `delete_event` response shape changes, both breaking per SemVer.

### Added
- `INTERVALS_ICU_DELETE_MODE` env var (`safe` / `full` / `none`) gating which destructive tools are registered with the server. The gate sits outside the model's reach — unregistered tools cannot be invoked. See the README's *Delete Safety Mode* section.
- Safe-mode partition logic: `delete_event` / `bulk_delete_events` skip past events (today and earlier) and return a uniform `deleted` / `skipped` envelope with reason codes.
- Startup log line: `intervals-icu MCP starting: delete_mode=<mode>, registered_tools=<n>`.
- Strava-restricted activity detection: activity and analysis tools surface an explanation when Strava data is unavailable due to privacy settings.
- `update_wellness` now accepts nutrition macro fields (`calories`, `carbs`, `fat`, `protein`, `fiber`).

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
