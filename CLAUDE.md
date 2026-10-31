# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

MCP (Model Context Protocol) server for Intervals.icu — provides up to 72 tools, 4 resources, and 9 prompts for accessing training data, wellness metrics, and performance analysis through Claude and other LLMs. The default `INTERVALS_ICU_DELETE_MODE=safe` registers 69 tools; `full` registers all 72, `none` registers 63.

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
4. `athlete.py` — Profile, athlete notes, fitness metrics (CTL/ATL/TSB)
5. `wellness.py` — HRV, sleep, recovery
6. `events.py` — Calendar queries
7. `event_management.py` — Create/update/delete events
8. `performance.py` — Power/HR/pace curves
9. `curves.py` — HR and pace curve analysis
10. `workout_library.py` — Browse, create, and delete folders and plans; create/update/delete library workouts
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
| `/release-write` | Preview the next version and generated notes, then dispatch the release workflow |

## Verification

**Always run `make can-release` before finishing any feature work.** This runs the full test and lint suite, matching what CI checks on every push.

## Merging PRs

PRs are **squash-merged only** (repo setting: commit title from `PR_TITLE`, body `BLANK`). The PR title becomes the single `main` commit subject with ` (#N)` appended — write PR titles as single-line conventional commits (≤ ~70 chars), and edit non-conforming community PR titles before merging. The title is also the release-note line and sets the version bump (see Releases), so check the type (`feat` vs `fix`) and the `!` marker before merging.

## Releases

Releases are **cut on demand** (no fixed schedule) and their notes are **generated from merged PR titles**. `CHANGELOG.md` is **frozen at 5.8.0** and kept for history — never add entries to it. Because squash merges make each PR title the `main` commit subject, the PR title is the release-note line *and* the version-bump input, so getting titles right at merge time is the maintainer's main release task. `pr-title.yml` fails PRs whose title isn't a conventional commit.

Version bump, highest wins across everything merged since the last tag (`.github/scripts/next_version.py`):
- `type!:` / `type(scope)!:` (or a `BREAKING CHANGE:` footer, which squash merges drop, so use `!`) → **major**
- `feat` → **minor**
- anything else → **patch**

To cut a release: **Actions → Publish Release → Run workflow** on `main` (or `gh workflow run publish.yml --ref main`, optionally `-f version=X.Y.Z` to override the computed version). `publish.yml` then runs the test suite, checks the `server.json` description length, computes the version, creates tag `vX.Y.Z` + the GitHub Release with `--generate-notes`, and publishes to PyPI and the MCP Registry in the same run. `/release-write` previews the bump and notes and dispatches it. Other release automation:
- Package version comes from the git tag via `hatch-vcs` (no `pyproject.toml` bump needed, no release commit)
- `publish.yml` syncs `server.json` version from the tag; a Release created by hand in the GitHub UI still publishes via its `release: published` trigger
- `release.yml` builds and pushes the Docker image on every push to `main`

Follow SemVer with the narrowed contract defined in CONTRIBUTING.md ("Versioning and release notes"). **Major** (breaking — title needs `!`): removing or renaming a tool or tool parameter, changing config env var semantics, changing which tools register by default, or removing information from a response. **Minor** (`feat`): response-shape changes that preserve the information (key renames, restructuring, added fields) — MCP responses are read dynamically by LLMs, not parsed by typed clients; retitle a `fix` that changes response shape to `feat`. Releases ≤ 4.0.0 predate this policy and treated any response-shape change as breaking.

### Deferred breaking changes (batch into the next major)

**Prefer non-breaking fixes and ship them continuously** — add fields, or accept aliases (e.g. `icu_bulk_create_events` accepts `event_type` as an alias for the API's `type`). Most interface inconsistencies can be fixed this way; don't defer a fix that can be non-breaking. Only when a change *must* break the contract (renaming/removing a tool or parameter with no alias path, dropping an accepted alias, changing env-var semantics or default registration) do we **defer it and batch all such changes into one planned major** — so consumers migrate once and the cleaned-up interface is designed holistically, not dribbled out across majors.

Running list of deferred breaking cleanups (do together in the next major; keep this list current as more are found):

- Rename `icu_get_upcoming_workouts` → `icu_get_upcoming_workout_events`, and its response key `workouts` → `events`. The tool returns dated **calendar events** of category `WORKOUT`, but its name reads as workout-library content, and the collision got sharper once the library gained `icu_create_workout` / `icu_update_workout` / `icu_delete_workout` (which take a library `workout_id`, not the event ID this tool returns). The description was sharpened in #132 as the non-breaking stopgap; the rename itself needs a major.

## Important Files

- `.env` — Local credentials (not in git)
- `.env.example` — Template for credentials
- `openapi-spec.json` — Intervals.icu API specification. Kept up to date automatically via `.github/workflows/update-openapi.yml` (or run `curl -s https://intervals.icu/api/v1/docs > openapi-spec.json` to update locally).
- `uv.lock` — Locked dependencies (commit this)
- `.github/workflows/test.yml` — CI tests
- `.github/workflows/release.yml` — Docker release automation
- `.github/workflows/publish.yml` — Cut a release on demand (version + notes from PR titles), publish to PyPI + MCP Registry
- `.github/workflows/pr-title.yml` — Enforces conventional-commit PR titles
