# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- HTTP and SSE transports via a `--transport` flag, enabling remote deployment behind a reverse proxy, tunnel, or container. See the Remote Deployment section of the README.
- CI coverage gate to prevent regressions in test coverage.
- Automated transport smoke test that replaces the previously manual MCP Inspector check.

### Changed
- Expanded the HTTP transport security warning in the README with concrete deployment guidance (Tailscale, Cloudflare Tunnel, reverse-proxy-with-auth, SSH tunnel).

## [1.0.1] — 2026-04-24

### Added
- PyPI publish workflow via Trusted Publishers.
- MCP Registry submission metadata (`server.json`).

### Fixed
- LICENSE file now packaged with the PyPI distribution and links resolve correctly from the PyPI page.
- `server.json` description shortened to meet the MCP Registry 100-char limit.

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
