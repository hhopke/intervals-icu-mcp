## Summary

<!-- What does this PR do, and why? If it closes an issue, write "Closes #123". -->

## Changes

<!-- A short bulleted list of the concrete changes. -->

-
-

## Checklist

- [ ] `make can-release` passes locally (tests, ruff, pyright)
- [ ] New tools have a corresponding respx-mocked test file in `tests/`
- [ ] Public-facing behavior changes are reflected in the README or `docs/`
- [ ] New MCP tools follow the `icu_` prefix convention and include `destructiveHint` where appropriate
- [ ] No API keys, athlete IDs, or other credentials are committed

> [!NOTE]
> The PR title becomes your line in the release notes and sets the version bump (`feat` → minor, `!` → major, anything else → patch). Write it as a conventional commit, e.g. `feat(events): add tags`. `CHANGELOG.md` is frozen, so don't edit it. See [CONTRIBUTING.md](https://github.com/hhopke/intervals-icu-mcp/blob/main/CONTRIBUTING.md#versioning-and-release-notes).

## Test plan

<!-- How did you verify the change? e.g. unit tests added, tested live against a Claude Desktop session, etc. -->
