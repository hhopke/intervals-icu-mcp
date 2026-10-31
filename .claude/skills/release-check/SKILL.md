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

2. Check the release-note inputs. Release notes are generated from merged PR titles and
   the conventional-commit type sets the version bump. CHANGELOG.md is frozen at 5.8.0,
   so don't check or edit it. PRs are squash-merged, so each `main` commit subject is a
   PR title. Preview the next release:
   ```bash
   python3 .github/scripts/next_version.py
   ```
   It lists every commit since the last tag with the bump it asks for, warns about
   non-conventional subjects, and prints the computed version. Report:
   - any non-conventional subject (it lands in the notes as-is and counts as a patch);
   - any commit whose type looks wrong for what it did: a user-facing addition or a
     response-shape change titled `fix`/`chore` (should be `feat`), or a breaking change
     per CLAUDE.md with no `!` (would ship as minor/patch instead of major). Check the PR
     (`gh pr view N`, N from the ` (#N)` suffix) when the subject alone is ambiguous.

   Titles can't be changed after merge. Fix a wrong bump by passing `-f version=X.Y.Z`
   when dispatching the release, and a misleading line by editing the notes after publishing.

3. Parse the output and report a clear summary:

   **If everything passes:**
   > ✅ Release check passed. All tests, linting (ruff + pyright), and formatting checks are green, and every commit since the last tag has a conventional title. Next release: vX.Y.Z (<bump>).

   **If something fails:**
   > ❌ Release check failed.
   
   List each failing check with:
   - What failed (test name, lint rule, file, or a mistyped or non-conventional commit title)
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
