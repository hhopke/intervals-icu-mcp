---
name: release-write
description: |
  Cut a new release. Use when the user wants to ship a tagged release.
  Previews the version bump from merged PR titles, dispatches the Publish Release
  workflow (tests + draft GitHub Release), writes user-facing release notes into the
  draft, and hands it to the maintainer to publish. Publishing the draft tags it and
  publishes to PyPI + MCP Registry.
allowed-tools: Bash(git fetch:*), Bash(git log:*), Bash(git describe:*), Bash(python3 .github/scripts/next_version.py:*), Bash(gh workflow run publish.yml:*), Bash(gh run list:*), Bash(gh run watch:*), Bash(gh run view:*), Bash(gh pr view:*), Bash(gh release view:*), Bash(gh release list:*), Bash(gh release edit:*), Bash(curl -s https://registry.modelcontextprotocol.io:*), Read, Write
---

## Context

Releases are cut on demand (no schedule), in two steps. `CHANGELOG.md` is frozen at 5.8.0;
release notes live only in GitHub Releases.

**Step 1 — dispatch** (`.github/workflows/publish.yml`, `workflow_dispatch`):

| Job | Does |
|---|---|
| `preflight` | Fails fast: requires `main`, checks the `server.json` description is ≤ 100 chars, computes the version with `.github/scripts/next_version.py` (fails on "nothing to release") |
| `test` | Full test suite (reusable `test.yml`) |
| `draft-release` | Refuses if any draft release already exists, then creates a **draft** Release `vX.Y.Z` pinned to the tested commit, with GitHub's generated notes (PR titles) as a placeholder. No tag yet, nothing published |

**Step 2 — publish** (the maintainer publishes the draft → `release: published`):

| Job | Does |
|---|---|
| `pypi` | Builds at the new tag and publishes to PyPI |
| `mcp-registry` | Syncs `server.json` to the tag version and publishes to the MCP Registry |

Version bump, highest wins across all commits since the last tag: `!` → major, `feat` → minor,
anything else → patch. **Don't tag or create the release by hand**, and don't add a
`chore(release)` commit.

**Publishing is the maintainer's call.** Never publish the draft without the user's explicit
go-ahead for that specific release. If they ask you to, use `gh release edit vX.Y.Z --draft=false`
(it runs under their own login, so it triggers the publish jobs; a `GITHUB_TOKEN` publish would not).

## Instructions

### 1. Preflight

- On `main`, up to date with `origin/main`, tags fetched (`git fetch origin main --tags`).
- `make can-release` is green (or run `/release-check`).
- No draft release is pending: `gh release list --limit 5` (a leftover draft makes the
  dispatch fail in `draft-release`; ask the user whether to publish or delete it).

### 2. Preview the version

```bash
python3 .github/scripts/next_version.py
git log --oneline --no-merges "$(git describe --tags --abbrev=0 --match 'v[0-9]*')"..HEAD
```

Show the user the computed version and the bump each commit asks for. Flag:

- a non-conventional subject (counts as a patch);
- a type that doesn't match the change: a user-facing addition or a response-shape change
  titled `fix`/`chore` (should have been `feat`, so the bump is too small), or a breaking change
  per CLAUDE.md without `!` (should be a major). Check the PR (`gh pr view N`) when the subject
  alone is ambiguous. If the computed version is wrong, propose an explicit override.

If `next_version.py` says there is nothing to release, stop.

### 3. Confirm, then dispatch

Wait for the user's explicit go-ahead with the final version. Then:

```bash
gh workflow run publish.yml --ref main                    # computed version
gh workflow run publish.yml --ref main -f version=X.Y.Z   # explicit override
```

Start the watch in the background and write the notes (step 4) while the tests run:

```bash
gh run watch "$(gh run list --workflow=publish.yml --event=workflow_dispatch --limit=1 --json databaseId --jq '.[0].databaseId')" --exit-status
```

If it fails, surface `gh run view <id> --log-failed` and stop. Nothing was tagged or
published, so the fix is: fix on `main`, delete any draft it left, dispatch again.

### 4. Write the release notes

Gather every PR since the last tag. The ` (#N)` suffix on each `main` commit subject is the PR:

```bash
gh pr view N --json number,title,body,author,files,labels
```

Read the body, and the diff (`gh pr diff N`) when the body doesn't say what changed for a user.
Then write the notes in the style of the last hand-written CHANGELOG entry (`CHANGELOG.md`, 5.8.0):

```markdown
## Breaking changes          ← only for a major; what breaks and how to migrate
## Added
- `icu_tool_name` does X for the user. Caveats/limits worth knowing. Contributed by @handle (#N).
## Fixed
- What was wrong, as the user saw it, and what happens now (#N).
## Changed
- ...

This takes the server from A tools to B — `safe` (the default) from C to D, `none` from E to F.

**Full Changelog**: https://github.com/hhopke/intervals-icu-mcp/compare/vPREV...vX.Y.Z
```

Rules:

- **Describe the release as it ships, not the PR history.** Fold follow-up PRs ("apply review
  feedback", renames, fix-ups of an unreleased feature) into the entry they change, citing all
  PR numbers, and use the final tool/parameter names: check `server.py`, not the PR title.
- **Write for a user of the server**, naming tools and parameters in backticks and saying what
  they can now do or what was wrong. Not how the code changed.
- **Leave out** what users don't notice: dependency bumps, CI, tests, refactors, OpenAPI spec
  syncs. Keep ones that change behavior or support (Docker base image, Python versions,
  a security fix) under Changed or Security.
- **Credit external contributors** with "Contributed by @handle" (the PR `author.login`); not
  the maintainer (`hhopke`) and not bots.
- **Tool counts**: only when tools were added or removed. Count `name="icu_` in `server.py`
  and use the per-mode numbers from CLAUDE.md.
- Omit empty sections. No emojis, no AI attribution.

Write the notes to a file in the scratchpad, show them to the user, and revise until they're
happy. Once the run from step 3 has created the draft, upload them:

```bash
gh release edit vX.Y.Z --notes-file <path>
gh release view vX.Y.Z --json url,isDraft
```

### 5. Hand off

Give the user the draft URL and tell them publishing it tags the commit and publishes to
PyPI and the MCP Registry. Stop here unless they explicitly ask you to publish it (see Context).

### 6. After publishing: watch both publish jobs

```bash
gh run watch "$(gh run list --workflow=publish.yml --event=release --limit=1 --json databaseId --jq '.[0].databaseId')" --exit-status
```

`mcp-registry` runs after `pypi` and can fail after PyPI has published, leaving a partial
release — don't report success off the PyPI job alone. Confirm the registry entry:

```bash
curl -s "https://registry.modelcontextprotocol.io/v0/servers?search=intervals-icu-mcp" | jq '.servers[]?.version'
```

Recovery after publishing: re-run the failed jobs of the same `release` run
(`gh run rerun <id> --failed`). They reuse the tag, and `pypi` has `skip-existing: true`.
Don't dispatch again: with no commits past the new tag it reports "Nothing to release". If the
cause needs a code change, the tag must move: delete the Release and the tag, fix on `main`,
and dispatch again. Don't retry anything without the user.

Notes can still be corrected after publishing with `gh release edit vX.Y.Z --notes-file <path>`.
