"""Tests for the server CLI entry point."""

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
