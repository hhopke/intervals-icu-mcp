---
name: release-write
description: |
  Cut a new release. Use when the user wants to ship a tagged release.
  Previews the version bump and the release notes that will be generated
  from merged PR titles, then dispatches the Publish Release workflow,
  which tags, creates the GitHub Release, and publishes to PyPI + MCP Registry.
allowed-tools: Bash(git tag:*), Bash(git push:*), Bash(git log:*), Bash(gh release create:*), Bash(gh release view:*), Bash(sed:*), Bash(awk:*), Bash(cat:*), Read, Write
---

## Context

Releases are cut on demand (no schedule). Release notes are GitHub's generated notes, i.e. the
merged PR titles since the last tag, and `CHANGELOG.md` is frozen at 5.8.0. Everything after the
dispatch happens inside `.github/workflows/publish.yml`, in one run:

| Job | Does |
|---|---|
| `preflight` | Fails fast: requires `main`, checks the `server.json` description is ≤ 100 chars, computes the version with `.github/scripts/next_version.py` (fails on "nothing to release") |
| `test` | Full test suite (reusable `test.yml`) |
| `cut-release` | Creates tag `vX.Y.Z` and the GitHub Release (`--generate-notes`) |
| `pypi` | Builds at the tag and publishes to PyPI |
| `mcp-registry` | Syncs `server.json` to the tag version and publishes to the MCP Registry |

Version bump, highest wins across all commits since the last tag: `!` → major, `feat` → minor,
anything else → patch. **Don't tag or create the release by hand**, and don't add a
`chore(release)` commit: the workflow does it, and a release made with the default token does
not trigger other workflows.

## Instructions

### 1. Preflight

- On `main`, up to date with `origin/main`, tags fetched (`git fetch origin main --tags`).
- `make can-release` is green (or run `/release-check`).

### 2. Preview the version and the notes

```bash
python3 .github/scripts/next_version.py
git log --oneline --no-merges "$(git describe --tags --abbrev=0 --match 'v[0-9]*')"..HEAD
```

Show the user the computed version, the bump each commit asks for, and the commit subjects:
those subjects are, nearly verbatim, the lines of the release notes. Flag:

- a non-conventional subject (shows up as-is, counts as a patch);
- a type that doesn't match the change: a user-facing addition or a response-shape change
  titled `fix`/`chore` (should have been `feat`, so the bump is too small), or a breaking change
  per CLAUDE.md without `!` (should be a major). If the computed version is wrong, propose an
  explicit override.

If `next_version.py` says there is nothing to release, stop.

### 3. Confirm, then dispatch

Wait for the user's explicit go-ahead with the final version. Then:

```bash
gh workflow run publish.yml --ref main                    # computed version
gh workflow run publish.yml --ref main -f version=X.Y.Z   # explicit override
```

### 4. Watch both publish jobs

```bash
sleep 5
gh run watch "$(gh run list --workflow=publish.yml --limit=1 --json databaseId --jq '.[0].databaseId')" --exit-status
gh release view vX.Y.Z --json url,tagName,publishedAt
```

Report the release URL. `mcp-registry` runs after `pypi` and can fail after PyPI has
published, leaving a partial release — don't report success off the PyPI job alone. If a job
fails, surface it (`gh run view <id> --log-failed`) and stop; don't retry without the user.

Recovery:
- **Failed in `preflight`, `test` or `cut-release`:** nothing was tagged. Fix on `main` and dispatch again.
- **Failed after the tag/Release exist** (PyPI or registry): re-run the failed jobs of the same
  run (`gh run rerun <id> --failed`). Don't dispatch again: with no commits past the new tag it
  reports "Nothing to release". It reuses the tag, and `pypi` has `skip-existing: true`.
  If the cause needs a code change, the tag must move: delete the Release and the tag, fix on
  `main`, and dispatch again.
- Confirm the registry entry landed:
  `curl -s "https://registry.modelcontextprotocol.io/v0/servers?search=intervals-icu-mcp" | jq '.servers[]?.version'`.

### 5. Optional: touch up the notes

The generated notes list each PR title with its author and link, plus first-time contributors.
If a line is misleading (titles can't change after merge), edit the Release body on GitHub
rather than adding a CHANGELOG entry. Keep edits to corrections. No emojis, no AI attribution.
