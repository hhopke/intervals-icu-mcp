# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

MCP (Model Context Protocol) server for Intervals.icu — provides up to 58 tools, 2 resources, and 9 prompts for accessing training data, wellness metrics, and performance analysis through Claude and other LLMs. The default `INTERVALS_ICU_DELETE_MODE=safe` registers 55 tools; `full` registers all 58, `none` registers 52.

- **Language**: Python 3.11+
- **Framework**: FastMCP
- **API Client**: httpx (async)
- **Validation**: Pydantic v2
- **Auth**: pydantic-settings + `.env`

## Development Commands

```bash
make install          # Install dependencies
make auth             # Set up Intervals.icu credentials (.env)
make run              # Run the MCP server
make test             # Run tests
make test/athlete     # Run tests matching "athlete"
make test/verbose     # Verbose test output
make lint             # Lint (ruff + pyright)
make format           # Auto-format code
make can-release      # Full pre-release check (same as CI)
make docker/build     # Build Docker image
make docker/run       # Run Docker container
```

## Architecture (Quick Reference)

| Component | File | Role |
|---|---|---|
| Server | `server.py` | Entry point, registers tools/resources/prompts |
| Middleware | `middleware.py` | Validates config, injects `ICUConfig` into context |
| Client | `client.py` | Async HTTP client (Basic Auth, 30s timeout) |
| Auth | `auth.py` | Loads credentials from `.env` |
| Response | `response_builder.py` | Consistent JSON structure (data/analysis/metadata) |
| Models | `models.py` | Pydantic models for API responses |
| Formatters | `formatters.py` | Data display formatting helpers |
| Workout syntax | `workout_syntax.py` | Intervals.icu workout DSL reference for LLMs |
| Tools | `tools/` | 13 tool modules (see below) |

**For detailed architecture**: see `docs/architecture.md`

### Tool Categories

1. `activities.py` — Query/manage activities
2. `activity_analysis.py` — Streams, intervals, best efforts
3. `activity_messages.py` — Notes/comments on activities
4. `athlete.py` — Profile, fitness metrics (CTL/ATL/TSB)
5. `wellness.py` — HRV, sleep, recovery
6. `events.py` — Calendar queries
7. `event_management.py` — Create/update/delete events
8. `performance.py` — Power/HR/pace curves
9. `curves.py` — HR and pace curve analysis
10. `workout_library.py` — Browse workout folders and plans
11. `gear.py` — Manage gear and reminders
12. `sport_settings.py` — FTP, FTHR, pace thresholds
13. `custom_items.py` — Charts, custom fields, zones, etc.

## Code Style

- **Ruff** for linting and formatting
- Line length: 100 characters
- Target: Python 3.11+
- Allow unused imports in `__init__.py` files
- Run `make format` to auto-fix style issues

## Type Checking

- **Pyright** with basic type checking mode
- Strict mode only for `src/` directory
- Run `make lint` or `uv run pyright`

## Testing

Tests use pytest + pytest-asyncio with `respx` for HTTP mocking.

**For testing conventions and examples**: see `docs/testing.md`

## Further Documentation

- `docs/architecture.md` — Detailed architecture and design decisions
- `docs/tools.md` — Reference for all registered tools (and the Delete Safety Mode spec)
- `docs/examples.md` — Usage examples
- `docs/testing.md` — Testing conventions
- `docs/chatgpt-connector.md` — ChatGPT custom-connector setup walkthrough

### README discipline

**Keep README.md under 300 lines.** It is the front door for new users — onboarding, install, basic config, links out. Reference material (full tool inventory, deep architectural notes, exhaustive examples) belongs in `docs/`, not the README. If a new section grows past ~30 lines and isn't core onboarding, extract it to `docs/` and link from the README. The README has been trimmed before (PR #6) — don't let it bloat back.

## Skills

The following skills are available in `.claude/skills/`:

| Skill | Description |
|---|---|
| `/commit` | Analyze changes and create conventional commits |
| `/add-tool` | Step-by-step workflow for adding new MCP tools |
| `/release-check` | Run pre-release verification and summarize results |

## Verification

**Always run `make can-release` before finishing any feature work.** This runs the full test and lint suite, matching what CI checks on every push.

## Releases

CHANGELOG.md is **manual** — there is no automated changelog generation. The only release-related automation:
- Package version comes from the git tag via `hatch-vcs` (no `pyproject.toml` bump needed)
- `publish.yml` syncs `server.json` version from the tag and publishes to PyPI + MCP Registry
- `release.yml` builds and pushes the Docker image

To cut a release:
1. Rename `## [Unreleased]` → `## [X.Y.Z] — YYYY-MM-DD` in CHANGELOG.md
2. Commit (e.g., `chore(release): X.Y.Z`)
3. Tag and push: `git tag vX.Y.Z && git push origin main vX.Y.Z`

Follow strict SemVer — breaking changes (response shape changes, default-behavior changes that remove tools, removed parameters) require a major bump. The CHANGELOG header explicitly commits to SemVer.

## Important Files

- `.env` — Local credentials (not in git)
- `.env.example` — Template for credentials
- `openapi-spec.json` — Intervals.icu API specification. Kept up to date automatically via `.github/workflows/update-openapi.yml` (or run `curl -s https://intervals.icu/api/v1/docs > openapi-spec.json` to update locally).
- `uv.lock` — Locked dependencies (commit this)
- `.github/workflows/test.yml` — CI tests
- `.github/workflows/release.yml` — Docker release automation
