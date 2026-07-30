"""Tests for the server CLI entry point."""

import re

import pytest

from intervals_icu_mcp.server import _parse_args


class TestParseArgs:
    """Protect the CLI contract for --transport / --host / --port / --path."""

    def test_defaults_to_stdio(self):
        args = _parse_args([])
        assert args.transport == "stdio"
        assert args.host == "127.0.0.1"
        assert args.port == 8000
        assert args.path is None

    def test_http_with_custom_host_and_port(self):
        args = _parse_args(["--transport", "http", "--host", "0.0.0.0", "--port", "9000"])
        assert args.transport == "http"
        assert args.host == "0.0.0.0"
        assert args.port == 9000

    def test_sse_transport(self):
        args = _parse_args(["--transport", "sse"])
        assert args.transport == "sse"

    def test_streamable_http_transport(self):
        args = _parse_args(["--transport", "streamable-http", "--path", "/mcp"])
        assert args.transport == "streamable-http"
        assert args.path == "/mcp"

    def test_rejects_unknown_transport(self):
        with pytest.raises(SystemExit):
            _parse_args(["--transport", "websocket"])

    def test_rejects_non_integer_port(self):
        with pytest.raises(SystemExit):
            _parse_args(["--port", "not-a-number"])


class TestVerifyMultiAthletePrompt:
    """The verify_multi_athlete prompt renders an athlete id into every step.

    Regression guard: Step 0 lets the caller omit athlete_id and discover a
    target via icu_list_athletes, but the later steps originally interpolated
    the raw (empty) parameter, so they silently ran against the default athlete
    and verified nothing.
    """

    async def test_no_step_targets_an_empty_athlete_id(self):
        from intervals_icu_mcp.server import verify_multi_athlete

        rendered = await verify_multi_athlete(athlete_id="")

        assert 'athlete_id=""' not in rendered
        assert "icu_list_athletes" in rendered

    async def test_explicit_athlete_id_reaches_every_step(self):
        from intervals_icu_mcp.server import verify_multi_athlete

        rendered = await verify_multi_athlete(athlete_id="i987654")

        # Every step that names athlete_id must use the requested athlete.
        targets = re.findall(r'athlete_id="([^"]*)"', rendered)
        assert targets, "prompt should reference athlete_id"
        assert set(targets) == {"i987654", "i999999"}, set(targets)

    async def test_placeholder_used_when_id_omitted(self):
        from intervals_icu_mcp.server import verify_multi_athlete

        rendered = await verify_multi_athlete(athlete_id="")
        targets = set(re.findall(r'athlete_id="([^"]*)"', rendered))

        # Only the Step 0 placeholder and the deliberate 403 probe.
        assert targets == {"<the athlete you picked in Step 0>", "i999999"}, targets


class TestPromptToolReferences:
    """Every tool a prompt tells the model to call must actually be registered.

    All 9 prompts previously referenced bare names (`get_fitness_summary`) while
    every tool registers as `icu_*`, so the prompts pointed at tools that do not
    exist. This also guards against a future tool rename silently staling them.
    """

    async def test_all_prompt_tool_references_are_registered(self):
        import inspect

        from fastmcp import Client

        import intervals_icu_mcp.server as server_mod
        from intervals_icu_mcp.server import mcp

        async with Client(mcp) as client:
            registered = {t.name for t in await client.list_tools()}
            prompts = await client.list_prompts()

        assert prompts, "expected the server to expose prompts"

        verb = "get|create|update|delete|search|list|bulk|apply|add|download|duplicate"
        offenders: dict[str, list[str]] = {}
        for prompt in prompts:
            fn = getattr(server_mod, prompt.name, None)
            if fn is None:
                continue
            source = inspect.getsource(fn)
            referenced = set(re.findall(rf"\b((?:icu_)?(?:{verb})_[a-z_]+)\b", source))
            # A bare name is only an error when the icu_-prefixed tool exists.
            missing = sorted(
                n for n in referenced if n not in registered and f"icu_{n}" in registered
            )
            if missing:
                offenders[prompt.name] = missing

        assert not offenders, f"prompts reference unregistered tool names: {offenders}"

    async def test_no_double_prefixed_tool_names(self):
        import inspect

        import intervals_icu_mcp.server as server_mod

        source = inspect.getsource(server_mod)
        assert not re.findall(r"icu_icu_\w+", source)
