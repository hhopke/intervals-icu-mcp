---
name: commit
description: |
  Analyze changes, write a conventional commit, and (when shipping) open a
  PR with closing keywords so referenced issues auto-close on merge. Use
  when the user asks to commit, push, or open a PR.
allowed-tools: Bash(git add:*), Bash(git status:*), Bash(git diff:*), Bash(git log:*), Bash(git branch:*), Bash(git switch:*), Bash(git checkout:*), Bash(git commit:*), Bash(git push:*), Bash(gh pr create:*), Bash(gh pr view:*), Bash(gh pr edit:*), Bash(gh issue view:*), Bash(make can-release:*), Bash(make lint:*), Bash(make test:*), Bash(make format:*)
---

## Context

Gather the following before composing the commit message:

- Current branch: `git branch --show-current`
- Working tree status: `git status --short --branch`
- Diff (staged + unstaged): `git diff $(git rev-parse --verify HEAD 2>/dev/null || echo --cached)`
- Recent history: `git log --oneline -10`

## Branch guard — MANDATORY first step

**Never commit on `main`.** Before staging or committing:

1. Run `git branch --show-current`.
2. If the result is `main`:
   - Propose a branch name derived from the commit type/scope (e.g. `fix/hr-histogram-list-shape`, `feat/event-tags`).
   - Confirm the name with the user, then `git switch -c <branch>`.
   - Only then proceed to stage + commit.
3. If on any other branch, commit there as-is — do not create a new branch.

No exceptions: trivial fixes, doc tweaks, one-liners — all go through a non-main branch.

## Commit message rules

- **Single line. No body. No `Co-Authored-By` / Claude attribution.** This applies to every commit in this repo, regardless of size.
- Format: `type(scope): description` — [Conventional Commits](https://www.conventionalcommits.org).
- Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `ci`, `build`, `perf`.
- Scope is optional but encouraged. Conventional scopes here: `tools`, `client`, `middleware`, `models`, `wellness`, `events`, `ci`, `release`, or a specific tool module name.
- Do not put issue refs (`Closes #N`) in the commit message — those live in the PR body so GitHub auto-closes correctly on merge (and squash merges use a blank commit body, so commit-message refs would be dropped anyway).

## Doc + count sync

For `feat`, `fix`, or anything user-visible, check whether docs need updating in the same commit:

- **`CHANGELOG.md`** — **don't touch it.** It is frozen at 5.8.0. Release notes are generated from merged PR titles, so the PR title is the changelog entry (see the PR title rules below).
- **Tool / resource / prompt counts** — if tools were added or removed, update the counts that appear in:
  - `README.md` (header/intro line and any tool tables)
  - `CLAUDE.md` (project overview line stating tool counts)
  - `docs/tools.md` if the registered set changed
- **README discipline** — keep `README.md` under 300 lines. If a new section would push past ~30 lines and isn't core onboarding, extract it to `docs/` and link from the README.
- **SemVer flag** — if the change removes or renames a tool/parameter, changes config env var semantics, changes default tool registration (e.g. `INTERVALS_ICU_DELETE_MODE`), or removes information from a response, mark the PR title with `!` (`feat(tools)!: ...`) and call it out in the PR body — `!` is what triggers the major bump, per CLAUDE.md. Response-shape changes that preserve the information (key renames, restructuring, added fields) are minor, not breaking: title them `feat`, even when they come from a fix.
- **Do not reference upstream/comparison repos** in commit messages, PR bodies, CHANGELOG, or README.

## Pre-PR gate — MANDATORY before opening a PR

Before any `gh pr create`, run the full release check:

```bash
make can-release
```

This runs `ruff` (lint + format check), `pyright` (type check), the pytest suite, and the coverage gate from `.github/workflows/test.yml`. CI runs the same thing on push — failing it locally means failing CI.

If it fails:
- Lint: `make format` auto-fixes most issues.
- Tests: `make test/verbose` for full output; `make test/<keyword>` to narrow.
- Fix, re-run `make can-release`, do not proceed to PR until it's green.

**Tool-behavior changes** (anything in `src/intervals_icu_mcp/tools/` that changes inputs, outputs, or side-effects): `make can-release` proves the unit tests pass against mocked HTTP — it does **not** prove the tool behaves correctly against the real Intervals.icu API. For non-trivial tool changes, flag this in the PR body and note whether manual verification (via Claude Desktop / MCP Inspector against `make run`) was performed. Don't claim end-to-end verification you didn't do.

## Pull request — closing keywords

When opening a PR (`gh pr create` or user asks for one), put a closing keyword in the **PR body** for every issue this PR resolves. The PR body is the only place GitHub auto-closes from on merge.

- **Auto-closes:** `Closes #N` / `Fixes #N` / `Resolves #N` (one per line, in the body)
- **Does NOT auto-close:** `Implements`, `Addresses`, `Refs`, `Related to` — use these for issues the PR touches but doesn't fully resolve (e.g. ratchet/running-log issues like #4 that should stay open across multiple PRs)

Find the issue # in the user's prompt, branch name, or recent conversation. If unclear, ask — don't guess. After creating, verify with `gh pr view <n> --json closingIssuesReferences`; if empty, fix with `gh pr edit <n> --body-file -`.

**The PR title becomes the `main` commit.** The repo is squash-only (settings: commit title from `PR_TITLE`, body `BLANK`): on merge, `main` gets exactly one commit whose subject is the PR title plus an appended ` (#N)`, and the branch's individual commits fold away. So write the PR title as you would a commit subject — single line, conventional format, ideally ≤ 70 chars to leave room for the ` (#N)` suffix — and edit non-conforming community PR titles *before* merging. The title is also the line users read in the generated release notes and it sets the version bump (`feat` → minor, `!` → major, anything else → patch): describe the user-visible change, not the code change. `pr-title.yml` rejects non-conventional titles. Body uses the existing `.github/PULL_REQUEST_TEMPLATE.md` structure (Summary / Changes / Checklist / Test plan).

## Instructions

1. Summarize the **intent** of the changes — what problem they solve or what they add.
2. Check the branch guard. If on `main`, propose a branch and switch.
3. Decide whether the doc + count sync applies and update those files in the same staging set.
4. Stage with `git add` (specific paths, not `-A`).
5. Commit with `git commit -m "type(scope): description"` — single line.
6. If shipping: run the pre-PR gate, then `gh pr create` with closing keywords in the body, then verify `closingIssuesReferences`.
7. If there are unrelated changes in the working tree, suggest splitting into separate commits.
