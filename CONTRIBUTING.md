# Contributing

Thanks for your interest in improving the Intervals.icu MCP server. Bug reports, feature requests, and pull requests are all welcome.

## Development setup

```bash
git clone https://github.com/hhopke/intervals-icu-mcp.git
cd intervals-icu-mcp
make install            # uv sync — installs runtime and dev deps
uv run intervals-icu-mcp-auth   # one-time credential setup
```

Most common tasks are exposed as `make` targets — run `make help` to see the full list.

## Before you open a pull request

Run the same gate CI runs:

```bash
make can-release
```

This executes, in order:

- `pytest` — the full test suite (see [docs/testing.md](docs/testing.md))
- `ruff check` — lint
- `pyright` — strict type-check on `src/`
- `make lint/package` — PyPI packaging metadata and README rendering (twine + pyroma)

Everything must be green before a PR can merge. Note that CI additionally enforces 80% test coverage (`pytest --cov-fail-under=80`) — run `make test/coverage` to see where you stand. If you're adding a tool, please also add a respx-mocked test alongside it — the existing tests in `tests/test_activity_tools.py` and `tests/test_event_tools.py` are good templates.

## Changelog

Don't edit `CHANGELOG.md` in your PR. It is maintained by hand, and the maintainer adds entries at merge time — this avoids merge conflicts on the `[Unreleased]` section and keeps the SemVer classification (breaking vs. minor) in one place. Your PR description is the raw material for the entry, so a clear "what & why" summary is the best way to help.

## Adding a new MCP tool

The repo ships a step-by-step guide: [.claude/skills/add-tool/SKILL.md](.claude/skills/add-tool/SKILL.md). It walks through the canonical pattern — client method → tool function → registration in `server.py` → tests — and keeps new tools consistent with the existing ones.

## Reporting bugs / requesting features

Open an issue using the templates at [github.com/hhopke/intervals-icu-mcp/issues/new/choose](https://github.com/hhopke/intervals-icu-mcp/issues/new/choose). For bugs, please include the MCP client you're using (Claude Desktop, Claude Code, Cursor, etc.), the tool name, and the full error response if you have one.

## Code style

- Python 3.11+, 100-char lines, double quotes — enforced by ruff (`make format` auto-fixes).
- Public tools use `Annotated[..., "description"]` on every parameter so LLMs can reason about arguments.
- Every tool returns a JSON string built via `ResponseBuilder` for consistency.

## License

By contributing, you agree that your contributions will be licensed under the project's [MIT License](LICENSE).
