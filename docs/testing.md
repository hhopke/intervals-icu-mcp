# Testing

Testing conventions and setup for the Intervals.icu MCP server.

## Stack

- **pytest** with **pytest-asyncio** for async test support
- **respx** for mocking HTTP requests (httpx-compatible)
- `asyncio_mode = "auto"` — no need for `@pytest.mark.asyncio` on every test

## Directory Structure

```
tests/
├── conftest.py          # Shared fixtures (mock client, config, etc.)
├── fixtures/            # API response fixtures (JSON files)
├── stubs/               # Stub implementations
├── test_athlete_tools.py
├── test_middleware_integration.py
└── test_multi_athlete_and_models.py
```

## Running Tests

```bash
# Run all tests
make test

# Run specific test filter
make test/athlete         # matches "athlete"

# Verbose output
make test/verbose

# Run the full pre-release suite (tests + lint)
make can-release
```

## Writing Tests

### Pattern

```python
@pytest.mark.asyncio
async def test_tool_name(mock_client):
    # Arrange: set up respx mock with fixture data
    respx.get("https://intervals.icu/api/v1/...").mock(
        return_value=httpx.Response(200, json=fixture_data)
    )

    # Act: call the tool
    result = await tool_name(param="value", ctx=mock_ctx)

    # Assert: verify response structure
    data = json.loads(result)
    assert "data" in data
    assert "metadata" in data
```

### Fixtures

- Place API response fixtures as JSON files in `tests/fixtures/`
- Name them descriptively: `athlete_profile.json`, `activities_list.json`
- Use realistic data from the Intervals.icu API

### Stubs

- Place stub implementations in `tests/stubs/`
- Use for complex objects that need simplified versions in tests

## Pre-Release Verification

Always run `make can-release` before finishing any feature. This runs:
- `make lint` — ruff check + pyright type checking
- `make test` — full pytest suite
