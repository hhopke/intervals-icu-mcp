# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

MCP (Model Context Protocol) server for Intervals.icu — provides up to 61 tools, 4 resources, and 9 prompts for accessing training data, wellness metrics, and performance analysis through Claude and other LLMs. The default `INTERVALS_ICU_DELETE_MODE=safe` registers 58 tools; `full` registers all 61, `none` registers 55.

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
| `/release-write` | Draft GitHub Release notes from CHANGELOG, tag, and publish |

## Verification

**Always run `make can-release` before finishing any feature work.** This runs the full test and lint suite, matching what CI checks on every push.

## Merging PRs

PRs are **squash-merged only** (repo setting: commit title from `PR_TITLE`, body `BLANK`). The PR title becomes the single `main` commit subject with ` (#N)` appended — write PR titles as single-line conventional commits (≤ ~70 chars), and edit non-conforming community PR titles before merging.

## Releases

CHANGELOG.md is **manual** — there is no automated changelog generation. Entries are the **maintainer's responsibility**: community PRs deliberately do not include them (CONTRIBUTING.md and the PR template say so, to avoid `[Unreleased]` merge conflicts and keep SemVer classification in one place). Add the `[Unreleased]` bullet at merge time, while the PR context is fresh; `/release-check` verifies every user-facing commit since the last tag has an entry before a release is cut. The only release-related automation:
- Package version comes from the git tag via `hatch-vcs` (no `pyproject.toml` bump needed)
- `publish.yml` syncs `server.json` version from the tag and publishes to PyPI + MCP Registry
- `release.yml` builds and pushes the Docker image

To cut a release:
1. Rename `## [Unreleased]` → `## [X.Y.Z] — YYYY-MM-DD` in CHANGELOG.md
2. Commit (e.g., `chore(release): X.Y.Z`)
3. Tag and push: `git tag vX.Y.Z && git push origin main vX.Y.Z`

Follow SemVer with the narrowed contract defined in the CHANGELOG header. **Major** (breaking): removing or renaming a tool or tool parameter, changing config env var semantics, changing which tools register by default, or removing information from a response. **Minor**: response-shape changes that preserve the information (key renames, restructuring, added fields) — MCP responses are read dynamically by LLMs, not parsed by typed clients. Releases ≤ 4.0.0 predate this policy and treated any response-shape change as breaking.

### Deferred breaking changes (batch into the next major)

**Prefer non-breaking fixes and ship them continuously** — add fields, or accept aliases (e.g. `icu_bulk_create_events` accepts `event_type` as an alias for the API's `type`). Most interface inconsistencies can be fixed this way; don't defer a fix that can be non-breaking. Only when a change *must* break the contract (renaming/removing a tool or parameter with no alias path, dropping an accepted alias, changing env-var semantics or default registration) do we **defer it and batch all such changes into one planned major** — so consumers migrate once and the cleaned-up interface is designed holistically, not dribbled out across majors.

Running list of deferred breaking cleanups (do together in the next major; keep this list current as more are found):

- **Unify create vs. bulk field names.** `icu_create_event` exposes friendly params (`event_type`, `duration_seconds`, `distance_meters`, `training_load`); `icu_bulk_create_events` takes the raw API names in its JSON (`type`, `moving_time`, `distance`, `icu_training_load`). Bulk now accepts `event_type` as a non-breaking alias, but the others still silently drop when a model reuses the singular interface. Non-breaking interim: add the remaining aliases to bulk. Breaking cleanup to batch: settle on one naming scheme across both tools and drop the aliases.

## Important Files

- `.env` — Local credentials (not in git)
- `.env.example` — Template for credentials
- `openapi-spec.json` — Intervals.icu API specification. Kept up to date automatically via `.github/workflows/update-openapi.yml` (or run `curl -s https://intervals.icu/api/v1/docs > openapi-spec.json` to update locally).
- `uv.lock` — Locked dependencies (commit this)
- `.github/workflows/test.yml` — CI tests
- `.github/workflows/release.yml` — Docker release automation
