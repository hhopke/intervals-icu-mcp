# Contributing

Thanks for your interest in improving the Intervals.icu MCP server. **Contributions are heavily welcomed** — this project exists because people kept wanting their own training workflow to work, and most of what's here grew out of exactly that.

No contribution is too small. A typo, a clearer parameter description, one extra test case, a bug report with a good reproduction — those are genuinely valuable, not a lesser form of helping. You don't need to be a Python expert or know anything about MCP going in, and an unfinished PR opened as a draft is a perfectly good way to ask for help.

## Ways to help

- **Tell us how you're using it.** [Show and tell](https://github.com/hhopke/intervals-icu-mcp/discussions/categories/show-and-tell) is the most useful thing you can contribute without writing any code — which tools you lean on, what your prompts look like, where the server gets in your way.
- **Ask and answer questions.** [Q&A](https://github.com/hhopke/intervals-icu-mcp/discussions/categories/q-a) — and answering someone else's question is a real contribution.
- **Float an idea.** [Ideas](https://github.com/hhopke/intervals-icu-mcp/discussions/categories/ideas) for a tool or analysis you wish existed, even half-formed.
- **Report a bug or request a feature.** [Open an issue](https://github.com/hhopke/intervals-icu-mcp/issues/new/choose) when you have a reproduction or a concrete proposal.
- **Send a pull request.** [Good first issues](https://github.com/hhopke/intervals-icu-mcp/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) are scoped to be a gentle landing.

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

Open an issue using the templates at [github.com/hhopke/intervals-icu-mcp/issues/new/choose](https://github.com/hhopke/intervals-icu-mcp/issues/new/choose). For bugs, please include the MCP client you're using (Claude Desktop, Claude Code, Cursor, etc.), the tool name, and the full error response if you have one. If you're not sure whether what you're seeing is a bug, [ask in Q&A](https://github.com/hhopke/intervals-icu-mcp/discussions/categories/q-a) first — that's what it's for, and it's never a waste of anyone's time.

## Code style

- Python 3.11+, 100-char lines, double quotes — enforced by ruff (`make format` auto-fixes).
- Public tools use `Annotated[..., "description"]` on every parameter so LLMs can reason about arguments.
- Every tool returns a JSON string built via `ResponseBuilder` for consistency.

## License

By contributing, you agree that your contributions will be licensed under the project's [MIT License](LICENSE).
