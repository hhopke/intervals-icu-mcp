# Architecture

Detailed component documentation for the Intervals.icu MCP server.

## FastMCP Server (`server.py`)

- Entry point that initializes the FastMCP server
- Registers all tools, resources, and prompts
- Tools are imported from `tools/` modules but registered in server.py
- Middleware is added before tools are registered

## Middleware (`middleware.py`)

- `ConfigMiddleware` runs before every tool call
- Loads Intervals.icu configuration from environment, then applies per-request
  HTTP header overrides (see [Multi-tenant credentials](#multi-tenant-credentials))
- Validates the resolved configuration
- Injects `ICUConfig` into context state via `ctx.set_state("config", config)`
- Tools access config via `ctx.get_state("config")`

## API Client (`client.py`)

- `ICUClient` is an async HTTP client using httpx
- Uses Basic Auth with username "API_KEY" and the API key as password
- All API methods are async and must be used with async context manager
- Handles error responses with `ICUAPIError` exceptions
- Default timeout is 30 seconds

## Authentication (`auth.py`)

- `ICUConfig` loads credentials from `.env` file using pydantic-settings
- `load_config()` loads configuration from environment
- `validate_credentials()` checks if credentials are properly set
- Interactive setup script at `scripts/setup_auth.py`

### Authentication Flow

1. User runs `uv run intervals-icu-mcp-auth` to set up credentials
2. Credentials stored in `.env` file (API key + athlete ID)
3. `ConfigMiddleware` resolves and validates credentials on every tool call
4. `ICUClient` uses Basic Auth with username "API_KEY"

### Multi-tenant credentials

Credentials are resolved **per request**, so a single HTTP deployment can serve
multiple athletes. `apply_header_credentials()` (in `auth.py`) layers per-request
HTTP headers on top of the env-var-derived `ICUConfig`:

| Header (case-insensitive) | Overrides config field |
|---|---|
| `X-Intervals-Api-Key` | `intervals_icu_api_key` |
| `X-Intervals-Athlete-Id` | `intervals_icu_athlete_id` |

Resolution priority is **header → env var fallback**. A present, non-empty header
wins; absent or empty headers leave the env value in place. `intervals_icu_delete_mode`
is a startup/env concern and is never affected by headers.

Headers are read via FastMCP's `get_http_headers()`, which returns `{}` for
non-HTTP transports (e.g. stdio) and never raises — so stdio and single-tenant
env-only setups behave exactly as before. The resolution happens in
`ConfigMiddleware` for tool calls, and inline in the
`intervals-icu://athlete/profile` resource (resources bypass middleware).

The per-tool `athlete_id` parameter still composes on top of this: the header sets
the request's *default* athlete, while an explicit `athlete_id` argument can still
target another athlete (coach access). Treat these headers as secrets and only
expose the HTTP transport behind TLS + authentication (see the README security note).

## Response Builder (`response_builder.py`)

All tools return JSON with consistent structure:

```json
{
  "data": {},           // Main data payload
  "analysis": {},       // Optional insights and computed metrics
  "metadata": {}        // Query metadata, timestamps
}
```

- `ResponseBuilder.build_response()` creates success responses
- `ResponseBuilder.build_error_response()` creates error responses
- Automatically converts datetime objects to ISO strings

### Response Rules

- Never return raw API responses
- Always use `ResponseBuilder.build_response()` for consistency
- Include `analysis` section for insights when relevant
- Use `metadata` for query context (date ranges, limits, etc.)

## Models (`models.py`)

Pydantic models for all API responses. Models include: Activity, Athlete, Wellness, Event, PowerCurve, etc.

## MCP Resources

Resources expose reference content the LLM can pull on demand. They are paid only when fetched, unlike tool descriptions (paid every session). We use this to keep tool descriptions lean — long enum lists, schema definitions, and DSL specs live in resources.

| URI | Source module | Purpose |
|---|---|---|
| `intervals-icu://athlete/profile` | inline in `server.py` | Live athlete profile + fitness metrics; loads via `ICUClient` |
| `intervals-icu://workout-syntax` | `workout_syntax.py` | Intervals.icu structured workout DSL reference (cycling/running/swimming) |
| `intervals-icu://event-categories` | `event_categories.py` | Calendar event category enum + use-case mapping + training_availability values, referenced from `create_event` / `update_event` / `bulk_create_events` |
| `intervals-icu://custom-item-schemas` | `custom_item_schemas.py` | Per-`item_type` `content` schema for `create_custom_item` / `update_custom_item` (INPUT_FIELD / ACTIVITY_FIELD / INTERVAL_FIELD constraints + worked examples) |

When adding a new tool whose description repeats >~200 chars of reference content (enums, schemas, DSL), prefer extracting that content into a new module and registering it as a resource. The pattern: a single `*_SPEC = """..."""` constant per module, imported lazily inside the resource function.

## Tool Organization

Tools are organized into 11 categories in `src/intervals_icu_mcp/tools/`:

1. **activities.py** — Query and manage activities
2. **activity_analysis.py** — Streams, intervals, best efforts
3. **athlete.py** — Profile and fitness metrics (CTL/ATL/TSB)
4. **wellness.py** — HRV, sleep, recovery metrics
5. **events.py** — Calendar queries
6. **event_management.py** — Create/update/delete events
7. **performance.py** — Power/HR/pace curves
8. **curves.py** — HR and pace curve analysis
9. **workout_library.py** — Browse workout folders and plans
10. **gear.py** — Manage gear and reminders
11. **sport_settings.py** — FTP, FTHR, pace thresholds

### Tool Pattern

All tools follow the same async pattern:

```python
async def tool_name(
    param: str,
    ctx: Context | None = None,
) -> str:
    """Tool description."""
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            # Make API calls
            result = await client.method()

            # Build response
            return ResponseBuilder.build_response(
                data={"key": "value"},
                analysis={"insights": "..."},
            )
    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
```

By default, the `metadata` block only contains fields a tool explicitly attaches.
Set `INTERVALS_ICU_DEBUG_METADATA=true` to additionally inject `fetched_at` and
(if passed) `query_type` — useful for tracing but otherwise noise the LLM
doesn't read.

## Error Handling

- `ICUAPIError` for API errors (401, 404, 429, etc.)
- Middleware raises `ToolError` if credentials not configured
- All tools return error JSON instead of raising exceptions
- Include helpful error messages and suggestions

## Date Handling

- API uses ISO-8601 format (YYYY-MM-DD or full datetime)
- `ResponseBuilder.format_date_with_day()` adds day-of-week info
- All datetimes automatically converted to ISO strings in responses

## API Specification

The `openapi-spec.json` (210KB) contains the full Intervals.icu API specification. Use it as a reference when adding new tools to understand available endpoints, parameters, and response schemas.
