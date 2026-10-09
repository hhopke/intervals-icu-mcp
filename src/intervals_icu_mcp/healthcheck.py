"""Small stdlib-only liveness check for stdio and HTTP server transports."""

import argparse
import http.client
import json
import math
import os
import socket
import time
from collections.abc import Sequence
from typing import NoReturn

_SERVER_MODULE = "intervals_icu_mcp.server"
_MAX_BODY = 4096
_TRANSPORTS = ("stdio", "http", "streamable-http", "sse")


class ProbeError(Exception):
    """The local server did not demonstrate liveness."""


class _QuietArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise ValueError("invalid arguments")


def _read_proc_cmdline() -> bytes:
    with open("/proc/1/cmdline", "rb") as process:
        return process.read()


def _is_python_executable(value: str) -> bool:
    name = os.path.basename(value)
    if name in {"python", "python3"}:
        return True
    if name.startswith("python3."):
        return name[8:].isdigit()
    return False


def _validate_entrypoint(argv: Sequence[str]) -> None:
    if (
        len(argv) < 3
        or not _is_python_executable(argv[0])
        or argv[1] != "-m"
        or argv[2] != _SERVER_MODULE
    ):
        raise ValueError("unknown server process")


def _read_server_argv() -> list[str]:
    """Read and validate PID 1's exact Python module entrypoint."""
    try:
        raw = _read_proc_cmdline()
        if not raw or not raw.endswith(b"\0"):
            raise ValueError("malformed process command line")
        argv = [part.decode("utf-8") for part in raw[:-1].split(b"\0")]
        _validate_entrypoint(argv)
        return argv
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError("unknown server process") from exc


def _server_argument_parser() -> _QuietArgumentParser:
    parser = _QuietArgumentParser(add_help=False, allow_abbrev=True)
    parser.add_argument("--transport", choices=_TRANSPORTS, default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    # This option is recognized so abbreviations such as --p stay ambiguous
    # in the same way as the server's parser. The health route is always root.
    parser.add_argument("--path", default=None)
    return parser


def _local_target(host: str | None, port: int | None) -> tuple[str, int]:
    host = "127.0.0.1" if host is None else host
    port = 8000 if port is None else port
    if not host:
        raise ValueError("invalid server host")
    if isinstance(port, bool) or type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("invalid server port")

    if host == "0.0.0.0":
        host = "127.0.0.1"
    elif host == "::":
        if not socket.has_ipv6:
            raise ValueError("IPv6 is unavailable")
        host = "::1"
    return host, port


def _target_from_argv(argv: list[str]) -> tuple[str, int] | None:
    """Return the local HTTP target, or ``None`` for a known stdio server."""
    _validate_entrypoint(argv)
    parser = _server_argument_parser()
    try:
        options, _unknown = parser.parse_known_args(argv[3:])
    except (argparse.ArgumentError, ValueError) as exc:
        raise ValueError("invalid server options") from exc

    if options.transport == "stdio":
        return None
    return _local_target(options.host, options.port)


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ProbeError("healthcheck timed out")
    return remaining


def _valid_timeout(timeout: float) -> float:
    if (
        isinstance(timeout, bool)
        or type(timeout) not in (int, float)
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise ValueError("invalid timeout")
    return float(timeout)


def _read_health_response(
    response: http.client.HTTPResponse, sock: socket.socket, deadline: float
) -> bytes:
    body = bytearray()
    while len(body) <= _MAX_BODY:
        if response.isclosed():
            break
        sock.settimeout(_remaining(deadline))
        chunk = response.read1(_MAX_BODY + 1 - len(body))
        if not chunk:
            break
        body.extend(chunk)
        if len(body) > _MAX_BODY:
            raise ProbeError("health response too large")
    return bytes(body)


def check(timeout: float = 2.0, host: str | None = None, port: int | None = None) -> None:
    """Check HTTP liveness, falling back to import-only for unknown PID 1."""
    duration = _valid_timeout(timeout)
    if host is None and port is None:
        try:
            server_argv = _read_server_argv()
        except ValueError:
            return
        target = _target_from_argv(server_argv)
        if target is None:
            return
    else:
        target = _local_target(host, port)

    host, port = target
    deadline = time.monotonic() + duration
    connection = http.client.HTTPConnection(host, port, timeout=_remaining(deadline))
    try:
        connection.connect()
        if connection.sock is None:
            raise ProbeError("health connection unavailable")
        sock = connection.sock
        sock.settimeout(_remaining(deadline))
        connection.request("GET", "/health")
        sock.settimeout(_remaining(deadline))
        response = connection.getresponse()
        with response:
            if response.status != 200:
                raise ProbeError("health route returned an error")
            body = _read_health_response(response, sock, deadline)
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, ValueError) as exc:
            raise ProbeError("health response was invalid") from exc
        if payload != {"status": "ok"}:
            raise ProbeError("health response was invalid")
    finally:
        connection.close()


def _cli_parser() -> _QuietArgumentParser:
    parser = _QuietArgumentParser(
        prog="python -m intervals_icu_mcp.healthcheck",
        description="Check the local Intervals.icu MCP server liveness.",
    )
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    return parser


def main() -> int:
    try:
        args = _cli_parser().parse_args()
        check(timeout=args.timeout, host=args.host, port=args.port)
    except Exception:
        print("healthcheck failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
