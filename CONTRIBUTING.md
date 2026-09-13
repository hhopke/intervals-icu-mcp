# Contributing

Thanks for your interest in improving the Intervals.icu MCP server. **Contributions are heavily welcomed, and none is too small** — a typo, a clearer parameter description, one extra test case, a good bug report. No Python or MCP expertise assumed, and a draft PR is a fine way to ask for help.

## Ways to help

- **Tell us how you're using it** — [Show and tell](https://github.com/hhopke/intervals-icu-mcp/discussions/categories/show-and-tell). The most useful thing you can contribute without writing code.
- **Ask or answer a question** — [Q&A](https://github.com/hhopke/intervals-icu-mcp/discussions/categories/q-a).
- **Float an idea** — [Ideas](https://github.com/hhopke/intervals-icu-mcp/discussions/categories/ideas), even half-formed.
- **Report a bug or request a feature** — [open an issue](https://github.com/hhopke/intervals-icu-mcp/issues/new/choose).
- **Send a pull request** — [good first issues](https://github.com/hhopke/intervals-icu-mcp/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) are a gentle landing.

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

Open an issue using the templates at [github.com/hhopke/intervals-icu-mcp/issues/new/choose](https://github.com/hhopke/intervals-icu-mcp/issues/new/choose). For bugs, please include the MCP client you're using (Claude Desktop, Claude Code, Cursor, etc.), the tool name, and the full error response if you have one. Not sure it's a bug? [Ask in Q&A](https://github.com/hhopke/intervals-icu-mcp/discussions/categories/q-a) first.

## Code style

- Python 3.11+, 100-char lines, double quotes — enforced by ruff (`make format` auto-fixes).
- Public tools use `Annotated[..., "description"]` on every parameter so LLMs can reason about arguments.
- Every tool returns a JSON string built via `ResponseBuilder` for consistency.

## License

By contributing, you agree that your contributions will be licensed under the project's [MIT License](LICENSE).
