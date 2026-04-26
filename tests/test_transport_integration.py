"""End-to-end transport tests.

These are the reproducible equivalent of the manual MCP-Inspector smoke test:
confirm that the server, with all its tools / resources / prompts registered,
actually serves MCP requests correctly over both the in-memory transport and
the HTTP (streamable-http) transport exposed by `--transport http`.
"""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from asgi_lifespan import LifespanManager
from fastmcp import Client

from intervals_icu_mcp.server import mcp


class TestInMemoryTransport:
    """Fast in-process checks that validate registration wiring.

    Uses FastMCP's in-memory Client transport. This exercises the full MCP
    protocol (initialize, list_*, call_tool) without an HTTP layer, so any
    breakage here indicates a problem in server.py's tool/resource/prompt
    registration code — exactly the code path that has 0% unit coverage.
    """

    async def test_client_connects(self):
        async with Client(mcp) as client:
            assert client.is_connected()

    async def test_all_default_mode_tools_registered(self):
        """Default delete_mode=safe registers 55 tools (3 destructive tools gated)."""
        async with Client(mcp) as client:
            tools = await client.list_tools()
            assert len(tools) == 55
            names = {t.name for t in tools}
            # Spot-check tools from different modules / tiers
            assert "icu_get_recent_activities" in names
            assert "icu_get_athlete_profile" in names
            assert "icu_bulk_create_events" in names  # Tier 2 coverage addition
            assert "icu_duplicate_events" in names
            assert "icu_get_activity_messages" in names  # Activity messages
            assert "icu_get_custom_items" in names  # Custom items
            assert "icu_update_sport_settings" in names

    async def test_tools_use_icu_prefix(self):
        """Every tool follows the naming convention documented in the README."""
        async with Client(mcp) as client:
            tools = await client.list_tools()
            non_prefixed = [t.name for t in tools if not t.name.startswith("icu_")]
            assert non_prefixed == []

    async def test_destructive_tools_carry_destructive_hint(self):
        """MCP tool annotations communicate risk to the LLM."""
        async with Client(mcp) as client:
            tools = await client.list_tools()
            destructive_names = {"icu_delete_activity", "icu_delete_event", "icu_delete_gear"}
            for tool in tools:
                if tool.name in destructive_names:
                    assert tool.annotations is not None
                    assert tool.annotations.destructiveHint is True, (
                        f"{tool.name} should carry destructiveHint=True"
                    )

    async def test_both_resources_registered(self):
        async with Client(mcp) as client:
            resources = await client.list_resources()
            uris = {str(r.uri) for r in resources}
            assert "intervals-icu://athlete/profile" in uris
            assert "intervals-icu://workout-syntax" in uris

    async def test_prompts_registered(self):
        async with Client(mcp) as client:
            prompts = await client.list_prompts()
            names = {p.name for p in prompts}
            # Spot-check a representative sample. Note: prompts do NOT carry
            # the `icu_` prefix that the tools convention uses.
            assert "analyze_recent_training" in names
            assert "generate_workout" in names
            assert "recovery_check" in names


class TestHTTPTransport:
    """Validate the actual HTTP transport wiring used by `--transport http`.

    Uses httpx with an ASGI transport against `mcp.http_app()` — the same
    Starlette app that uvicorn would serve. Catches regressions specific to
    HTTP serving: missing Accept-header handling, wrong mount path, the
    streamable-http protocol handshake, etc.
    """

    @asynccontextmanager
    async def _http_client(self) -> AsyncIterator[httpx.AsyncClient]:
        """AsyncClient bound to the MCP ASGI app with lifespan managed.

        FastMCP's streamable-http transport initializes its session manager in
        the ASGI lifespan hook. httpx's ASGITransport doesn't run lifespan
        events on its own, so we wrap the app in asgi_lifespan.LifespanManager
        to start / stop it around each test.
        """
        app = mcp.http_app()
        async with LifespanManager(app) as manager:
            transport = httpx.ASGITransport(app=manager.app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                yield client

    @staticmethod
    def _parse_sse_response(body: str) -> dict:
        """Streamable-HTTP returns an SSE stream; pull the JSON out of the first data: line."""
        for line in body.splitlines():
            if line.startswith("data: "):
                return json.loads(line.removeprefix("data: "))
        raise AssertionError(f"No SSE data frame in body: {body!r}")

    async def test_rejects_request_without_sse_accept_header(self):
        """Browsers hitting the URL get a useful JSON-RPC error, not a crash.

        This is the exact failure we saw during manual smoke-testing when the
        browser or MCP Inspector was configured for plain HTTP instead of
        streamable-HTTP — it should stay a predictable error, never 500.
        """
        async with self._http_client() as client:
            resp = await client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
                headers={"Accept": "application/json"},
            )
            payload = resp.json()
            assert payload["error"]["code"] == -32600
            assert "text/event-stream" in payload["error"]["message"]

    async def test_initialize_and_list_tools_over_http(self):
        """Full MCP handshake + tools/list over the HTTP transport.

        Mirrors what MCP Inspector does when it connects: send initialize,
        then tools/list, and confirm the server responds with the tool
        catalog. This is the automated replacement for the manual Inspector
        smoke test.
        """
        async with self._http_client() as client:
            # Step 1 — initialize and capture the session id the server issues
            init_body = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "pytest-integration", "version": "0.1"},
                },
            }
            async with client.stream(
                "POST",
                "/mcp",
                json=init_body,
                headers={"Accept": "application/json, text/event-stream"},
            ) as init_resp:
                assert init_resp.status_code == 200
                init_body_text = (await init_resp.aread()).decode()
                init_payload = self._parse_sse_response(init_body_text)
                assert init_payload["result"]["serverInfo"]["name"] == "intervals_icu_mcp"
                session_id = init_resp.headers.get("mcp-session-id")
                assert session_id, "Server did not issue a session id"

            # Step 2 — send the required initialized notification
            await client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                headers={
                    "Accept": "application/json, text/event-stream",
                    "mcp-session-id": session_id,
                },
            )

            # Step 3 — tools/list on the established session
            async with client.stream(
                "POST",
                "/mcp",
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                headers={
                    "Accept": "application/json, text/event-stream",
                    "mcp-session-id": session_id,
                },
            ) as tools_resp:
                assert tools_resp.status_code == 200
                tools_body = (await tools_resp.aread()).decode()
                tools_payload = self._parse_sse_response(tools_body)
                tool_names = {t["name"] for t in tools_payload["result"]["tools"]}
                assert len(tool_names) == 55  # safe mode default
                assert "icu_get_recent_activities" in tool_names
