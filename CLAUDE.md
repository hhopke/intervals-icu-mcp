# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

MCP (Model Context Protocol) server for Intervals.icu — provides 58 tools, 2 resources, and 7 prompts for accessing training data, wellness metrics, and performance analysis through Claude and other LLMs.

- **Language**: Python 3.11+
- **Framework**: FastMCP
- **API Client**: httpx (async)
- **Validation**: Pydantic v2
- **Auth**: pydantic-settings + `.env`

## Development Commands

```bash
make install          # Install dependencies
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

## Skills

The following skills are available in `.claude/skills/`:

| Skill | Description |
|---|---|
| `/commit` | Analyze changes and create conventional commits |
| `/add-tool` | Step-by-step workflow for adding new MCP tools |
| `/release-check` | Run pre-release verification and summarize results |
| `/mcp-builder` | Anthropic's official guide for building MCP servers |

## Verification

**Always run `make can-release` before finishing any feature work.** This runs the full test and lint suite, matching what CI checks on every push.

## Important Files

- `.env` — Local credentials (not in git)
- `.env.example` — Template for credentials
- `openapi-spec.json` — Intervals.icu API specification. Kept up to date automatically via `.github/workflows/update-openapi.yml` (or run `curl -s https://intervals.icu/api/v1/docs > openapi-spec.json` to update locally).
- `uv.lock` — Locked dependencies (commit this)
- `.github/workflows/test.yml` — CI tests
- `.github/workflows/release.yml` — Docker release automation
