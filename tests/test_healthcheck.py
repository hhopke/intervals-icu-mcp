"""Contract tests for the stdlib-only healthcheck entry point."""

import http.client
import os
import socket
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from intervals_icu_mcp import healthcheck


def argv(*args: str) -> list[str]:
    return ["/app/.venv/bin/python", "-m", "intervals_icu_mcp.server", *args]


def test_read_server_argv_accepts_exact_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        healthcheck,
        "_read_proc_cmdline",
        lambda: b"/app/.venv/bin/python\0-m\0intervals_icu_mcp.server\0--port=8123\0",
    )
    assert healthcheck._read_server_argv() == [
        "/app/.venv/bin/python",
        "-m",
        "intervals_icu_mcp.server",
        "--port=8123",
    ]


@pytest.mark.parametrize(
    "raw",
    [b"", b"\0", b"python\0-m\0intervals_icu_mcp.server", b"python\0-m\0\xff\0"],
)
def test_read_server_argv_rejects_unreadable_or_malformed_data(
    monkeypatch: pytest.MonkeyPatch, raw: bytes
) -> None:
    monkeypatch.setattr(healthcheck, "_read_proc_cmdline", lambda: raw)
    with pytest.raises(ValueError):
        healthcheck._read_server_argv()


def test_read_server_argv_rejects_unreadable_proc(monkeypatch: pytest.MonkeyPatch) -> None:
    def unreadable() -> bytes:
        raise PermissionError("private detail")

    monkeypatch.setattr(healthcheck, "_read_proc_cmdline", unreadable)
    with pytest.raises(ValueError):
        healthcheck._read_server_argv()


def test_target_from_argv_defaults_to_stdio() -> None:
    assert healthcheck._target_from_argv(argv()) is None
    assert healthcheck._target_from_argv(["python", "-m", "intervals_icu_mcp.server"]) is None
    assert healthcheck._target_from_argv(["python3", "-m", "intervals_icu_mcp.server"]) is None


def test_target_from_argv_last_split_and_equals_values_win() -> None:
    assert healthcheck._target_from_argv(
        argv(
            "--transport",
            "http",
            "--host=127.0.0.2",
            "--port",
            "8001",
            "--port=8123",
            "--ho",
            "127.0.0.3",
        )
    ) == ("127.0.0.3", 8123)
    assert healthcheck._target_from_argv(argv("--trans=streamable-http", "--po=8124")) == (
        "127.0.0.1",
        8124,
    )
    assert healthcheck._target_from_argv(
        argv("--transport=http", "--verbose", "ignored", "--unrelated=value")
    ) == ("127.0.0.1", 8000)


@pytest.mark.parametrize("transport", ["http", "streamable-http", "sse"])
def test_target_from_argv_http_transports(transport: str) -> None:
    assert healthcheck._target_from_argv(argv("--transport", transport)) == (
        "127.0.0.1",
        8000,
    )


def test_target_from_argv_maps_ipv4_wildcard() -> None:
    assert healthcheck._target_from_argv(argv("--transport=http", "--host", "0.0.0.0")) == (
        "127.0.0.1",
        8000,
    )


@pytest.mark.parametrize(
    ("host", "port", "expected"),
    [
        ("127.0.0.2", None, ("127.0.0.2", 8000)),
        (None, 8123, ("127.0.0.1", 8123)),
        ("127.0.0.3", 8123, ("127.0.0.3", 8123)),
        ("0.0.0.0", None, ("127.0.0.1", 8000)),
        ("::", None, ("::1", 8000)),
    ],
)
def test_explicit_target_uses_defaults_maps_wildcards_and_skips_proc(
    host: str | None,
    port: int | None,
    expected: tuple[str, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    targets: list[tuple[str, int]] = []
    monkeypatch.setattr(healthcheck.socket, "has_ipv6", True)

    class FailedConnection:
        sock = None

        def __init__(self, host: str, port: int, *, timeout: float) -> None:
            targets.append((host, port))

        def connect(self) -> None:
            raise ConnectionRefusedError

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        healthcheck,
        "_read_server_argv",
        lambda: (_ for _ in ()).throw(AssertionError("proc should be skipped")),
    )
    monkeypatch.setattr(healthcheck.http.client, "HTTPConnection", FailedConnection)
    with pytest.raises(ConnectionRefusedError):
        healthcheck.check(host=host, port=port)
    assert targets == [expected]


@pytest.mark.parametrize(
    ("host", "port"),
    [("", 8000), ("127.0.0.1", 0), ("127.0.0.1", 65536)],
)
def test_explicit_target_rejects_invalid_values(
    host: str, port: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        healthcheck,
        "_read_server_argv",
        lambda: (_ for _ in ()).throw(AssertionError("proc should be skipped")),
    )
    with pytest.raises(ValueError):
        healthcheck.check(host=host, port=port)


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["--host", "127.0.0.2"], ("127.0.0.2", None)),
        (["--port=8123"], (None, 8123)),
        (["--host=127.0.0.3", "--port=8123"], ("127.0.0.3", 8123)),
    ],
)
def test_main_passes_explicit_target_flags(
    monkeypatch: pytest.MonkeyPatch, args: list[str], expected: tuple[str | None, int | None]
) -> None:
    observed: list[tuple[str | None, int | None]] = []

    def check(*, timeout: float, host: str | None, port: int | None) -> None:
        observed.append((host, port))

    monkeypatch.setattr(healthcheck, "check", check)
    monkeypatch.setattr(sys, "argv", ["healthcheck", *args])
    assert healthcheck.main() == 0
    assert observed == [expected]


@pytest.mark.parametrize("args", [["--host="], ["--port=0"], ["--port=65536"], ["--port=wat"]])
def test_main_rejects_invalid_explicit_target_flags(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], args: list[str]
) -> None:
    proc_reads: list[bool] = []

    def read_proc() -> bytes:
        proc_reads.append(True)
        raise AssertionError("proc should be skipped")

    monkeypatch.setattr(
        healthcheck,
        "_read_server_argv",
        read_proc,
    )
    monkeypatch.setattr(sys, "argv", ["healthcheck", *args])
    assert healthcheck.main() == 1
    assert capsys.readouterr().out == "healthcheck failed\n"
    assert proc_reads == []


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--transport", "http"],
        ["--trans=streamable-http", "--po=8124"],
        ["--transport", "sse", "--path", "/mcp", "--host", "::", "--port", "8123"],
        [
            "--transport=http",
            "--host=127.0.0.2",
            "--port",
            "8001",
            "--port=8123",
            "--ho",
            "0.0.0.0",
        ],
    ],
)
def test_probe_parser_matches_server_cli_for_valid_arguments(args: list[str]) -> None:
    from intervals_icu_mcp.server import _parse_args

    server_args = _parse_args(args)
    probe_args, _unknown = healthcheck._server_argument_parser().parse_known_args(args)
    assert (probe_args.transport, probe_args.host, probe_args.port, probe_args.path) == (
        server_args.transport,
        server_args.host,
        server_args.port,
        server_args.path,
    )
    target = healthcheck._target_from_argv(argv(*args))
    if server_args.transport == "stdio":
        assert target is None
    else:
        host = {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(server_args.host, server_args.host)
        assert target == (host, server_args.port)


@pytest.mark.parametrize(
    "args",
    [
        ["--transport=ftp"],
        ["--port=not-a-number"],
        ["--p=8000"],
    ],
)
def test_probe_parser_rejects_server_cli_invalid_arguments(args: list[str]) -> None:
    from intervals_icu_mcp.server import _parse_args

    with pytest.raises(SystemExit):
        _parse_args(args)
    with pytest.raises(ValueError):
        healthcheck._target_from_argv(argv(*args))


@pytest.mark.parametrize("ipv6_supported", [True, False])
def test_target_from_argv_maps_ipv6_only_when_supported(
    monkeypatch: pytest.MonkeyPatch, ipv6_supported: bool
) -> None:
    monkeypatch.setattr(socket, "has_ipv6", ipv6_supported)
    if ipv6_supported:
        assert healthcheck._target_from_argv(argv("--transport=http", "--host=::")) == (
            "::1",
            8000,
        )
    else:
        with pytest.raises(ValueError):
            healthcheck._target_from_argv(argv("--transport=http", "--host=::"))


@pytest.mark.parametrize(
    "args",
    [
        ("--transport",),
        ("--transport=ftp",),
        ("--host",),
        ("--host=", "--transport=http"),
        ("--port=wat",),
        ("--port=0",),
        ("--port=65536",),
        ("--p=8000",),
    ],
)
def test_target_from_argv_rejects_malformed_recognized_options(args: tuple[str, ...]) -> None:
    with pytest.raises(ValueError):
        healthcheck._target_from_argv(argv("--transport=http", *args))


@pytest.mark.parametrize(
    "bad_argv",
    [
        ["tini", "--", "python", "-m", "intervals_icu_mcp.server"],
        ["python", "-m", "other.module"],
        ["python", "src/intervals_icu_mcp/server.py"],
        ["/bin/sh", "-c", "python -m intervals_icu_mcp.server"],
    ],
)
def test_unknown_pid1_is_not_an_http_target(bad_argv: list[str]) -> None:
    with pytest.raises(ValueError):
        healthcheck._target_from_argv(bad_argv)


@pytest.mark.parametrize(
    "raw",
    [
        b"tini\0--\0python\0-m\0intervals_icu_mcp.server\0",
        b"intervals-icu-mcp\0--transport=http\0",
        b"/bin/sh\0-c\0python -m intervals_icu_mcp.server\0",
        b"",
        b"python\0-m\0\xff\0",
        None,
    ],
)
def test_unknown_pid1_falls_back_to_import_only(
    monkeypatch: pytest.MonkeyPatch, raw: bytes | None
) -> None:
    def read_proc() -> bytes:
        if raw is None:
            raise PermissionError("unreadable proc")
        return raw

    def fail_if_connected(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("import-only fallback attempted a connection")

    monkeypatch.setattr(healthcheck, "_read_proc_cmdline", read_proc)
    monkeypatch.setattr(http.client, "HTTPConnection", fail_if_connected)
    monkeypatch.setattr(sys, "argv", ["healthcheck"])
    assert healthcheck.main() == 0


@contextmanager
def endpoint(
    *,
    status: int = 200,
    body: bytes = b'{"status":"ok"}',
    headers: dict[str, str] | None = None,
    delay: float = 0,
):
    seen: list[tuple[str, str]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append((self.command, self.path))
            self.send_response(status)
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            if not any(name.lower() == "content-length" for name in (headers or {})):
                self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                if delay:
                    time.sleep(delay)
                self.wfile.write(body)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port, seen
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def use_endpoint(monkeypatch: pytest.MonkeyPatch, port: int) -> None:
    monkeypatch.setattr(
        healthcheck,
        "_read_server_argv",
        lambda: argv("--transport=http", "--host=127.0.0.1", f"--port={port}"),
    )


def test_health_request_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    accepted = b'{"status":"ok"}' + b" " * (4096 - len(b'{"status":"ok"}'))
    with endpoint(body=accepted) as (port, seen):
        use_endpoint(monkeypatch, port)
        healthcheck.check()
        assert seen == [("GET", "/health")]

    with endpoint(body=b" " * 4097) as (port, _):
        use_endpoint(monkeypatch, port)
        with pytest.raises(healthcheck.ProbeError):
            healthcheck.check(timeout=1)


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (404, b'{"status":"ok"}'),
        (503, b'{"status":"ok"}'),
        (200, b"not json"),
        (200, b'{"status":"not ok"}'),
        (200, b'{"status":"ok","extra":true}'),
        (200, b"[]"),
    ],
)
def test_health_request_requires_exact_status_json(
    monkeypatch: pytest.MonkeyPatch, status: int, body: bytes
) -> None:
    with endpoint(status=status, body=body) as (port, _):
        use_endpoint(monkeypatch, port)
        with pytest.raises(healthcheck.ProbeError):
            healthcheck.check(timeout=1)


def test_no_proxy_or_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:3128")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:3128")
    monkeypatch.setenv("ALL_PROXY", "http://proxy.invalid:3128")
    monkeypatch.setenv("NO_PROXY", "")
    with endpoint(status=302, headers={"Location": "http://127.0.0.1/elsewhere"}) as (
        port,
        seen,
    ):
        use_endpoint(monkeypatch, port)
        with pytest.raises(healthcheck.ProbeError):
            healthcheck.check(timeout=1)
        assert seen == [("GET", "/health")]


def test_health_request_times_out_and_redacts_response(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sentinel = "SENSITIVE_SENTINEL_91d4"
    with endpoint(body=sentinel.encode(), headers={"X-Sentinel": sentinel}, delay=0.2) as (port, _):
        use_endpoint(monkeypatch, port)
        monkeypatch.setattr(sys, "argv", ["healthcheck", "--timeout", "0.05"])
        assert healthcheck.main() == 1
        output = capsys.readouterr().out
        assert output == "healthcheck failed\n"
        assert sentinel not in output

    with endpoint(status=500, body=sentinel.encode(), headers={"X-Sentinel": sentinel}) as (
        port,
        _,
    ):
        use_endpoint(monkeypatch, port)
        assert healthcheck.main() == 1
        output = capsys.readouterr().out
        assert output == "healthcheck failed\n"
        assert sentinel not in output


def test_health_request_connection_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.close()
    use_endpoint(monkeypatch, port)
    with pytest.raises(OSError):
        healthcheck.check(timeout=0.5)


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), -float("inf")])
def test_check_rejects_invalid_timeout(timeout: float) -> None:
    with pytest.raises(ValueError):
        healthcheck.check(timeout=timeout)


@pytest.mark.parametrize(("args", "expected"), [([], 2.0), (["--timeout", "10"], 10.0)])
def test_main_timeout_default_and_override(
    monkeypatch: pytest.MonkeyPatch, args: list[str], expected: float
) -> None:
    observed: list[float] = []
    monkeypatch.setattr(
        healthcheck,
        "check",
        lambda *, timeout=2.0, host=None, port=None: observed.append(timeout),
    )
    monkeypatch.setattr(sys, "argv", ["healthcheck", *args])
    assert healthcheck.main() == 0
    assert observed == [expected]


@pytest.mark.parametrize("value", ["nan", "inf", "0", "-1", "bogus"])
def test_main_invalid_timeout_is_generic(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    value: str,
) -> None:
    monkeypatch.setattr(sys, "argv", ["healthcheck", "--timeout", value])
    assert healthcheck.main() == 1
    assert capsys.readouterr().out == "healthcheck failed\n"


def test_main_does_not_echo_unrecognized_argument_values(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sentinel = "CLI_SECRET_SENTINEL_621a"
    monkeypatch.setattr(sys, "argv", ["healthcheck", "--url", sentinel])
    assert healthcheck.main() == 1
    output = capsys.readouterr().out
    assert output == "healthcheck failed\n"
    assert sentinel not in output


def test_stdio_check_does_not_open_a_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(healthcheck, "_read_server_argv", lambda: argv())

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("stdio healthcheck attempted a network connection")

    monkeypatch.setattr(http.client, "HTTPConnection", fail_if_called)
    healthcheck.check()


def test_stdio_package_import_does_not_load_server_or_sdk() -> None:
    source = (
        "import sys; import intervals_icu_mcp.healthcheck; "
        "assert 'intervals_icu_mcp.server' not in sys.modules; "
        "assert not any(name == 'mcp' or name.startswith('mcp.') for name in sys.modules); "
        "assert 'fastmcp' not in sys.modules"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(os.path.dirname(__file__), "..", "src")
    result = subprocess.run(
        [sys.executable, "-S", "-c", source],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 0, result.stderr
