---
name: release-check
description: |
  Run the full pre-release verification suite and summarize results.
  Use when the user asks to check if the code is ready for release,
  before any PR/merge, or when finishing a feature.
allowed-tools: Bash(make can-release), Bash(make test:*), Bash(make lint:*)
---

## Instructions

1. Run the full pre-release check:
   ```bash
   make can-release
   ```

2. Check CHANGELOG coverage — CHANGELOG.md is manual, and community PRs deliberately
   don't include entries (the maintainer adds them at merge), so this is the last line
   of defense before a release is cut. List everything merged since the last tag and
   compare against the `[Unreleased]` section:
   ```bash
   git describe --tags --abbrev=0
   git log --oneline --no-merges vX.Y.Z..HEAD
   awk '/^## \[Unreleased\]/{flag=1; next} /^## \[/{flag=0} flag' CHANGELOG.md
   ```
   Every **user-facing** change (feat, fix, breaking change — including merged community
   PRs) must have a bullet under `## [Unreleased]`. Internal-only commits (ci, chore,
   docs about the repo itself, release/publish plumbing) don't need entries. PRs are
   squash-merged, so each `main` commit maps 1:1 to a PR via its ` (#N)` suffix. For each
   user-facing commit with no matching bullet, report it as a failure and draft a
   suggested entry (source it from the PR description via `gh pr view N`, taking N from
   the commit subject's suffix).

3. Parse the output and report a clear summary:

   **If everything passes:**
   > ✅ Release check passed. All tests, linting (ruff + pyright), and formatting checks are green, and every user-facing change since the last tag has a CHANGELOG entry.

   **If something fails:**
   > ❌ Release check failed.
   
   List each failing check with:
   - What failed (test name, lint rule, file, or missing CHANGELOG entry)
   - A brief explanation of the issue
   - A suggested fix

4. If tests fail, offer to run the specific failing test in verbose mode:
   ```bash
   make test/verbose
   ```

5. If lint fails, offer to auto-fix:
   ```bash
   make format
   ```

## What `make can-release` checks

- `make lint` — ruff check + pyright type checking
- `make test` — full pytest suite
- Code formatting compliance
