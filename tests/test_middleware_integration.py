"""Integration tests for ConfigMiddleware → Context → Tool pipeline.

These tests use FastMCP's in-process Client to exercise the real middleware
stack, catching issues like state serialization that unit tests with mocked
ctx.get_state() would miss.
"""

import json

import pytest
from fastmcp import Client, Context, FastMCP

from intervals_icu_mcp.middleware import ConfigMiddleware


@pytest.fixture
def _env_credentials(monkeypatch):
    """Set fake Intervals.icu credentials in the environment."""
    monkeypatch.setenv("INTERVALS_ICU_API_KEY", "test_api_key_integration")
    monkeypatch.setenv("INTERVALS_ICU_ATHLETE_ID", "i999999")
    # Prevent pydantic-settings from reading a real .env file
    monkeypatch.setenv("ENV_FILE", "/dev/null")


@pytest.fixture
def integration_server(_env_credentials):
    """Create a minimal FastMCP server with the real ConfigMiddleware."""
    server = FastMCP("integration-test")
    server.add_middleware(ConfigMiddleware())

    @server.tool()
    async def inspect_config(ctx: Context) -> str:
        """Test tool that inspects the config object from middleware."""
        config = await ctx.get_state("config")
        return json.dumps(
            {
                "type": type(config).__name__,
                "has_api_key_attr": hasattr(config, "intervals_icu_api_key"),
                "has_athlete_id_attr": hasattr(config, "intervals_icu_athlete_id"),
                "api_key": config.intervals_icu_api_key
                if hasattr(config, "intervals_icu_api_key")
                else None,
                "athlete_id": config.intervals_icu_athlete_id
                if hasattr(config, "intervals_icu_athlete_id")
                else None,
            }
        )

    return server


class TestMiddlewareIntegration:
    """Test that ConfigMiddleware correctly injects ICUConfig through the real FastMCP pipeline."""

    async def test_config_is_icu_config_object(self, integration_server):
        """Config stored by middleware must be an ICUConfig instance, not a dict."""
        async with Client(integration_server) as client:
            result = await client.call_tool("inspect_config")
            data = json.loads(result.data)

            assert data["type"] == "ICUConfig", (
                f"Expected ICUConfig object, got {data['type']}. "
                "Middleware must use serializable=False in set_state()."
            )

    async def test_config_has_attribute_access(self, integration_server):
        """Config must support attribute access (not dict key access)."""
        async with Client(integration_server) as client:
            result = await client.call_tool("inspect_config")
            data = json.loads(result.data)

            assert data["has_api_key_attr"] is True
            assert data["has_athlete_id_attr"] is True

    async def test_config_values_from_env(self, integration_server):
        """Config values must match the environment variables."""
        async with Client(integration_server) as client:
            result = await client.call_tool("inspect_config")
            data = json.loads(result.data)

            assert data["api_key"] == "test_api_key_integration"
            assert data["athlete_id"] == "i999999"

    async def test_middleware_rejects_missing_credentials(self, monkeypatch):
        """Middleware must raise ToolError when credentials are not configured."""
        monkeypatch.setenv("INTERVALS_ICU_API_KEY", "")
        monkeypatch.setenv("INTERVALS_ICU_ATHLETE_ID", "")
        monkeypatch.setenv("ENV_FILE", "/dev/null")

        server = FastMCP("test-no-creds")
        server.add_middleware(ConfigMiddleware())

        @server.tool()
        async def dummy_tool(ctx: Context) -> str:
            return "should not reach here"

        from fastmcp.exceptions import ToolError

        async with Client(server) as client:
            with pytest.raises(ToolError, match="credentials"):
                await client.call_tool("dummy_tool")
