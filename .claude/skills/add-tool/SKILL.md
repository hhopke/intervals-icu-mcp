---
name: add-tool
description: |
  Step-by-step guide for adding a new MCP tool to this Intervals.icu server.
  Use when the user wants to add a new tool, endpoint, or API integration.
  Ensures the established async pattern, response format, and test conventions
  are followed consistently.
---

## Prerequisites

Before starting, understand:
- The Intervals.icu API endpoint you're wrapping (check `openapi-spec.json`)
- What data the tool should return and what analysis/insights to include
- Whether a new API client method is needed in `client.py`

## Steps

### 1. Add the API client method (if needed)

File: `src/intervals_icu_mcp/client.py`

Add an async method to `ICUClient` following the existing pattern:

```python
async def get_something(self, athlete_id: str, **params) -> dict:
    """Fetch something from the API."""
    response = await self._request("GET", f"/api/v1/athlete/{athlete_id}/something", params=params)
    return response.json()
```

### 2. Create the tool function

File: `src/intervals_icu_mcp/tools/<category>.py` (existing file or new category)

Follow the established async pattern:

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
            result = await client.method()

            return ResponseBuilder.build_response(
                data={"key": "value"},
                analysis={"insights": "..."},
                query_type="tool_type"
            )
    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
```

### 3. Register the tool in server.py

File: `src/intervals_icu_mcp/server.py`

Import and register the tool function. Tools are imported from `tools/` modules but registered in `server.py`.

### 4. Add test fixtures and stubs

- Add API response fixture in `tests/fixtures/`
- Add any needed stubs in `tests/stubs/`
- Use `respx` to mock the HTTP request

### 5. Write tests

File: `tests/test_<category>_tools.py`

```python
@pytest.mark.asyncio
async def test_tool_name(mock_client):
    # Arrange: set up respx mock
    # Act: call the tool
    # Assert: verify response structure (data, analysis, metadata)
    pass
```

### 6. Verify

Run `make can-release` to confirm:
- Tests pass
- Linting passes (ruff + pyright)
- No regressions

### 7. Update tool count

Update the tool count in `CLAUDE.md` (Project Overview section) and `README.md` if applicable.

## Response Format Reminder

All tools must return JSON via `ResponseBuilder.build_response()`:
```json
{
  "data": {},
  "analysis": {},
  "metadata": {}
}
```

Never return raw API responses.
