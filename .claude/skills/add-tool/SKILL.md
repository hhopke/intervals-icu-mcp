---
name: add-tool
description: |
  Step-by-step guide for adding a new MCP tool to this Intervals.icu server.
  Use when the user wants to add a new tool, endpoint, or API integration.
  Ensures the established async pattern, response format, naming discipline,
  and LLM-facing token budgets are followed consistently.
---

## What you're producing

An MCP tool is an **LLM-consumed artifact**. The tool's name and description are
read by every Claude/GPT/etc. model that connects to this server, on every
session, before the user has typed anything. Be ruthless about clarity and
length. Write for the model, not for human readers (humans read `docs/tools.md`
and the README).

## Prerequisites

Before starting:

- Verify the Intervals.icu API endpoint exists in [`openapi-spec.json`](../../../openapi-spec.json) — check the request/response schema, enum values, and required fields.
- Decide the **tier** the tool belongs to: `core` (daily-use, exposed by default) or `full` (specialty/coach, opt-in via `INTERVALS_ICU_TOOLSET=full`). When tier work lands per [issue #27](../../../docs/tools.md), tag accordingly.
- Check for **confusable names** in the existing tool surface. If your tool name shares a prefix or noun with another tool (e.g. `get_activity_*`, `*_event`, `create_*`), the opening sentence of the description MUST lead with the distinguishing access pattern, not the shared concept.
- Decide whether a new API client method is needed in `client.py`.

## Steps

### 1. Add the API client method (if needed)

File: [`src/intervals_icu_mcp/client.py`](../../../src/intervals_icu_mcp/client.py)

Add an async method to `ICUClient` following the existing pattern. Type the local variable so pyright doesn't widen `Any`:

```python
async def get_something(self, athlete_id: str | None = None) -> list[dict[str, Any]]:
    """Fetch something from the API."""
    athlete_id = athlete_id or self.config.intervals_icu_athlete_id
    response = await self._request("GET", f"/athlete/{athlete_id}/something")
    result: list[dict[str, Any]] = response.json()
    return result
```

Trust the API contract — don't add `if isinstance(data, list) else []` defensive ternaries unless there's a real reason. Pydantic models are preferred when the response shape is stable; raw dicts are fine for variable-shape endpoints (e.g. `custom_items.content`).

### 2. Create the tool function

File: `src/intervals_icu_mcp/tools/<category>.py` (existing file or new category)

```python
from typing import Annotated, Any
from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..response_builder import ResponseBuilder


async def tool_name(
    activity_id: Annotated[str, "The Intervals.icu activity ID (use icu_search_activities to find one if you only have a description)"],
    athlete_id: Annotated[
        str | None, "Athlete ID (only for coaches; uses configured default otherwise)"
    ] = None,
    ctx: Context | None = None,
) -> str:
    """Single-line summary that distinguishes this tool from siblings.

    Use when the user says things like: "<concrete user prompt>", "<another
    one>". Match the user's intent to the tool's specific access pattern.

    Args:
        activity_id: The Intervals.icu activity ID
        athlete_id: Athlete ID (uses configured default if not provided)

    Returns:
        JSON string with the data
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            result = await client.method(activity_id, athlete_id=athlete_id)

            return ResponseBuilder.build_response(
                data={"key": "value"},
                metadata={"count": len(result)},
                query_type="tool_type",
            )
    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )
```

Notes:
- **`await ctx.get_state("config")`** — the `await` is required.
- Wrap in `try` for both `ICUAPIError` (HTTP-level) and `Exception` (unexpected).
- Validate enum-style parameters at the boundary with `validation_error` responses **before** the API call. Don't let the API tell the user their input was wrong if we can catch it cheaper upstream.
- Use a small `_to_dict(item)` helper if the response payload needs field selection. Pattern: only include keys when the value is not None — see [`tools/custom_items.py:_custom_item_to_dict`](../../../src/intervals_icu_mcp/tools/custom_items.py).

### 3. Register the tool in server.py

File: [`src/intervals_icu_mcp/server.py`](../../../src/intervals_icu_mcp/server.py)

Import the function with the others in its category, then register with appropriate annotations:

```python
mcp.tool(
    name="icu_<verb>_<noun>",
    annotations={
        "readOnlyHint": True,    # False for writes
        "destructiveHint": False, # True for destructive ops
        "idempotentHint": True,
        "openWorldHint": True,
    },
)(tool_name)
```

Naming convention: `icu_<verb>_<noun>` for reads; verb-prefixed for writes (`create_`, `update_`, `delete_`, `add_`, `bulk_*`). Plural noun for list-returning tools (`get_activity_messages`); singular for single-record tools (`get_activity_message_by_id` if it existed).

### 4. Write tests

File: `tests/test_<category>_tools.py`

We use `pytest-asyncio` configured globally (no `@pytest.mark.asyncio` decorator needed) and `respx` for HTTP mocking:

```python
import json
from unittest.mock import AsyncMock, MagicMock

from httpx import Response

from intervals_icu_mcp.tools.<category> import tool_name


class TestToolName:
    async def test_tool_name_success(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/endpoint").mock(
            return_value=Response(200, json={"id": 1, "name": "Test"})
        )

        result = await tool_name(arg="x", ctx=mock_ctx)
        response = json.loads(result)

        assert response["data"]["id"] == 1

    async def test_tool_name_validation_error(self, mock_config):
        # Test that invalid input is rejected without an HTTP call
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        result = await tool_name(arg="invalid", ctx=mock_ctx)
        response = json.loads(result)

        assert response["error"]["type"] == "validation_error"

    async def test_tool_name_api_error(self, mock_config, respx_mock):
        # Test that API errors surface cleanly
        mock_ctx = MagicMock()
        mock_ctx.get_state = AsyncMock(return_value=mock_config)

        respx_mock.get("/athlete/i123456/endpoint").mock(return_value=Response(404))

        result = await tool_name(arg="x", ctx=mock_ctx)
        response = json.loads(result)

        assert response["error"]["type"] == "api_error"
```

Cover at minimum: happy path, validation rejection (if applicable), API error surfacing, athlete_id override (if applicable).

Fixtures `mock_config` and `respx_mock` come from [`tests/conftest.py`](../../../tests/conftest.py).

### 5. Verify

```bash
make can-release
```

Confirms ruff (formatting + lint), pyright (strict on `src/`), all tests pass, and pyroma scores 10/10.

### 6. Update inventories

- [`CLAUDE.md`](../../../CLAUDE.md) — tool count in Project Overview, plus tool category list if a new category was added.
- [`README.md`](../../../README.md) — tool count line and the Available Tools table.
- [`docs/tools.md`](../../../docs/tools.md) — per-category table.
- [`tests/test_transport_integration.py`](../../../tests/test_transport_integration.py) — the `assert len(tools) == N` assertion needs bumping.

## Quality checklist (LLM-facing)

Before marking the work done, run through these. They matter more than people expect.

### Token budgets

These are *targets*, not hard caps. Going over with good reason is fine — but justify it in the PR.

- **Tool description** (combining docstring + all `Annotated` params): aim for ≤200 tokens. Top-end tools with many parameters can go higher; review them especially carefully.
- **Per-`Annotated` parameter**: aim for ≤80 tokens. If you need more (e.g. enum lists, schema docs), move the long content into an MCP Resource and reference it. See [`intervals-icu://workout-syntax`](../../../src/intervals_icu_mcp/workout_syntax.py) as the canonical example.
- **Response payload**: keep median responses under ~1500 tokens. Anthropic recommends a 25K-token cap for tool responses; we should be far below that.

### Description quality

- **First sentence is critical** — Anthropic's research shows it dominates LLM tool selection. Lead with the distinguishing access pattern, not the shared concept. Bad: *"Get details about an activity."* Good: *"Fetch the headline summary of one activity (name, date, distance, time, training load, sport)."*
- **Use concrete user prompts** in `Annotated` descriptions where it helps disambiguation: *"Use when the user says: 'show me my last ride', 'what's my recent activity?'"*
- **Match the user's natural language**, not the API's. Example: API calls them "messages"; users call them "comments" or "notes". Mention both.
- **No marketing prose**, no "elegant", no "powerful". Every word costs tokens forever.

### Confusable-name discipline

If your tool name shares a prefix, suffix, or noun with another tool, the opening sentence MUST disambiguate. Existing confusable clusters to watch:

- `icu_get_activity_*` family (details / intervals / streams)
- `icu_search_activities` vs `icu_search_activities_full`
- `icu_create_event` / `icu_bulk_create_events` / `icu_duplicate_events`
- `icu_get_*_curves` / `icu_get_*_histogram` (per metric)
- `icu_*_message` vs `icu_*_messages` (singular = write, plural = read)

If adding to one of these clusters, study how the existing siblings differentiate and follow that pattern.

### Input examples for complex tools

If the tool has any of:
- A free-form structured field (workout description, JSON content schema, dict payload)
- Multiple optional params that interact non-obviously
- An enum-driven inner schema (different content shapes per item_type)

…ship 1-2 `input_examples` with the tool definition. Anthropic reports 72% → 90% accuracy on complex parameter handling when examples are included. Token cost is small (~50-200 tokens per example) vs. the round-trip cost of a model getting it wrong. See [issue #29](../../../docs/tools.md) for the project-wide rollout plan.

### Cache discipline

Tool descriptions are at the top of Anthropic's prompt-caching hierarchy: `tools → system → messages`. Any change to a tool description **invalidates the cache for everything below it**, costing 1.25× (5-min cache) or 2× (1-hour cache) the base input tokens for the next session that hits this server.

Practical rule: **batch description changes into one PR**. Don't drip them across multiple commits — each commit cascades. If you're touching descriptions, touch them all at once.

## Anti-patterns (don't do these)

- **Auto-metadata bloat.** Don't add `fetched_at`, `query_type`, or other debug fields to the response metadata — `ResponseBuilder` handles metadata; if you have a meaningful per-tool addition (`count`, `message`, etc.), pass it via the `metadata=` param. ([Issue #25](../../../docs/tools.md) is removing the auto-debug fields entirely.)
- **Raw Pydantic dumps.** Don't return `model.model_dump()` or `model.dict()` directly. Use a `_to_dict` helper that selects fields. Lets you skip null-valued fields, control output shape, and keep the response token-lean.
- **Pass-through API descriptions.** Don't copy-paste the OpenAPI summary into the tool description. The API docs are written for HTTP clients; tool descriptions are written for LLMs choosing between tools.
- **Generic opening sentences.** *"Get a thing."* / *"Manage things."* — these tell the LLM nothing. Lead with the distinguishing access pattern.
- **Renaming an existing tool.** Tool names are part of the public contract. Users have prompts mentioning them by name; renaming breaks those silently. Description rewrites are safe; renames are not.
- **Pre-mature defensive coding** in client methods (`if isinstance(data, list) else []`). Trust the API contract; if a response really is unstable, model that explicitly with Pydantic + `extra="allow"`.

## Response format reminder

All tools return JSON via `ResponseBuilder.build_response()`:

```json
{
  "data": {...},
  "analysis": {...},  // optional - computed insights
  "metadata": {...}   // optional - count, message, etc.
}
```

Errors via `ResponseBuilder.build_error_response()`:

```json
{
  "error": {
    "message": "...",
    "type": "api_error" | "validation_error" | "internal_error",
    "timestamp": "...",
    "suggestions": [...]   // optional
  }
}
```

Never return raw API responses or unstructured strings.
