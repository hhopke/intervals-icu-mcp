---
name: release-write
description: |
  Write release notes for a new version and cut the release.
  Use when the user wants to ship a tagged release after merging
  the release CHANGELOG commit. Produces a clean GitHub Release
  body sourced from CHANGELOG.md, then tags + publishes.
allowed-tools: Bash(git tag:*), Bash(git push:*), Bash(git log:*), Bash(gh release create:*), Bash(gh release view:*), Bash(sed:*), Bash(awk:*), Bash(cat:*), Read, Write
---

## Context

This repo's release path is half-manual:

| Step | Trigger | Workflow |
|---|---|---|
| Push `chore(release): X.Y.Z` to main | `push.branches: main` | `release.yml` → Docker build/push |
| Push tag `vX.Y.Z` | (none) | nothing |
| Create GitHub Release on the tag | `release.types: [published]` | `publish.yml` → PyPI + MCP Registry |

**Creating the GitHub Release is what actually triggers PyPI publish.** It is not optional. CHANGELOG.md is manual (per CLAUDE.md). This skill writes the GitHub Release body so users opening the Releases tab or the PyPI project page see polished notes, not raw commit history.

## Prerequisites

- The release commit (`chore(release): X.Y.Z`) is already on `origin/main` — i.e. CHANGELOG.md has been renamed from `[Unreleased]` to `[X.Y.Z] — YYYY-MM-DD`, committed, and pushed.
- `make can-release` is green.
- You are on `main`, up to date with `origin/main`.
- **`server.json` `description` is ≤ 100 chars.** The MCP Registry rejects longer descriptions with HTTP 422 (`expected length <= 100`), failing the `mcp-registry` job *after* PyPI has already published — a partial release that's annoying to recover. Pre-flight check: `jq -r '.description | length' server.json`. If it's over 100, stop and get it trimmed on `main` first.

If any prereq is missing, stop and tell the user what to do first.

## Instructions

### 1. Extract the CHANGELOG section for this version

Find the start line of `## [X.Y.Z]` and the start line of the *next* version section below it. Read everything in between, dropping the leading `## [...] — date` heading line (GitHub uses the release title instead).

```bash
# Example for v3.0.0:
awk '/^## \[3\.0\.0\]/{flag=1; next} /^## \[/{flag=0} flag' CHANGELOG.md
```

Save the extracted body to a temp file (e.g. `/tmp/release-notes-X.Y.Z.md`).

### 2. Reshape into the project's narrative style

**Critical:** the release notes are NOT a copy of the CHANGELOG section. The CHANGELOG is the exhaustive source-of-truth; the release body is a curated headline version. Past releases in this repo (v2.0.0, v1.3.0, v1.2.0) follow a narrative style — read 1-2 of them before drafting to anchor on the existing voice:

```bash
gh release view vPREVIOUS --json body --jq .body
```

Adopt these conventions:

- **Title has a tagline:** `vX.Y.Z – Headline Theme One & Headline Theme Two` (not plain `vX.Y.Z`). Same theme(s) you'd put in a tweet.
- **Body uses narrative section headers**, not CHANGELOG-style category buckets. Examples from past releases: `## New features`, `## Improvements`, `## Notes`, or headline-named sections like `## Delete Safety Mode`. **DO NOT use `### Added / ### Fixed / ### Changed`** — that's CHANGELOG style; the release notes are different.
- **Body is shorter than the CHANGELOG section.** Aim for ~50-70% of the CHANGELOG content, focused on what's user-visible and headline-worthy.
- **Top callout (`> [!NOTE]`) only when there's a measured headline number** — token savings, accuracy gain, perf improvement. Skip for routine releases.
- **Inline upgrade prose** for breaking changes — one or two sentences, no diff blocks. Pattern from v2.0.0: *"Upgrading from 1.x: \<thing> no longer \<behavior>. Set \<env var> to restore."* For multiple breaking changes, a `## Upgrading from vX.Y` heading with prose paragraphs (NOT diff snippets unless the consumer audience is parsing-heavy — see below).
- **Single Full-Changelog comparison link at the bottom**, single line:
  ```markdown
  **Full Changelog:** https://github.com/<owner>/<repo>/compare/v<PREVIOUS>...v<CURRENT>
  ```
  This replaces a hand-curated PR list. Don't list PRs unless the user explicitly asks for it.

**MCP-specific framing for response-shape changes:**

Per the narrowed SemVer contract (CHANGELOG header, adopted after 4.0.0), information-preserving response-shape changes (key renames, restructuring, added fields) are **minor**, not breaking. Only tool/parameter removals or renames, config env var semantic changes, default-registration changes, and removal of information from responses force a major. The reasoning:
- MCP responses are consumed by LLMs that rephrase into natural language.
- Programmatic parsers (`response["data"]["field"]`) are rare in MCP usage.
- A field rename usually doesn't break user-visible behavior; the LLM adapts.

When a release does include a breaking change — or a notable shape change worth flagging — keep the release-notes treatment proportional to the actual user impact: **one paragraph of inline upgrade prose, not an SDK-style Migration section with before/after diff blocks**. Diff blocks are for projects where consumers write typed parsing code; they're overkill here.

Don't:
- Rewrite the CHANGELOG verbatim. The CHANGELOG is comprehensive; the release notes are curated.
- Use CHANGELOG section headings (`### Added`, etc.) — that's the wrong genre.
- Add diff-snippet Migration sections for MCP response-shape changes — overkill for the audience.
- Add emojis unless the user explicitly asks for them (per project convention).
- Include co-author lines or AI attribution (per [feedback_commits.md] memory).

### 3. Show the polished notes to the user for review

Print the contents of the temp file. The user may want to tweak before publishing. Wait for explicit go-ahead before step 4.

### 4. Cut the release (only after user confirms)

```bash
# Create the tag (no automation; just a marker)
git tag vX.Y.Z
git push origin vX.Y.Z

# Create the GitHub Release using the polished notes file
# This is what triggers publish.yml → PyPI + MCP Registry
gh release create vX.Y.Z --title "vX.Y.Z – <tagline>" --notes-file /tmp/release-notes-X.Y.Z.md
```

Do NOT use `--generate-notes` — that uses GitHub's auto-generated PR/commit list, which is noisier than what we just polished.

Do NOT use `--draft`. The release needs to be published to trigger `publish.yml`.

### 5. Verify the release published correctly

```bash
gh release view vX.Y.Z --json url,tagName,publishedAt
```

Report the URL to the user. Then watch the publish workflow to completion:

```bash
gh run watch "$(gh run list --workflow=publish.yml --limit=1 --json databaseId --jq '.[0].databaseId')" --exit-status
```

`publish.yml` has **two jobs**: `pypi` then `mcp-registry` (`needs: pypi`). Watch **both** — the registry job can fail *after* PyPI has published, leaving a partial release (PyPI live, registry missing). Don't report success off the PyPI job alone.

If it fails, surface the failure (`gh run view <id> --log-failed`) and stop — do not retry without user confirmation. Recovery notes:
- **Registry-only failure (PyPI already up):** re-running the CI run won't help — it's pinned to the original tag commit. Either (a) fix the cause on `main`, force-move the tag, and delete+recreate the Release to re-fire the workflow (the `pypi` job has `skip-existing: true`, so it no-ops on the already-published version), or (b) publish to the registry manually: download `mcp-publisher` from `modelcontextprotocol/registry`, `jq` the release version into `server.json`, `./mcp-publisher login github` (interactive device flow), `./mcp-publisher publish`.
- Confirm the registry entry landed: `curl -s "https://registry.modelcontextprotocol.io/v0/servers?search=<pkg>" | jq '.servers[]?.version'`.

## Anti-patterns (don't do these)

- **Don't edit CHANGELOG.md from this skill.** The release commit is already on main; further edits create drift between the canonical changelog and the release body.
- **Don't tag without pushing the release commit first.** Tagging an older commit means the published artifact references stale CHANGELOG.
- **Don't auto-publish without showing the user the polished notes.** Even if the CHANGELOG looks fine, the polish step (TL;DR, PR list, migration guide) is judgment-based and the user should approve.
- **Don't use `--draft` then forget to publish.** `publish.yml` only fires on `release.types: [published]`, not on draft creation.
- **Don't generate "what's changed" via `--generate-notes` for a polished release.** That's GitHub's auto-listing; it's noisier and less narrative than the CHANGELOG section.

## Quality bar

The release body should answer three questions for a reader scanning the Releases tab:
1. **What changed at a glance?** — the TL;DR callout.
2. **What do I need to know to upgrade?** — the Changed (breaking) bullets + Migration section.
3. **Where did this come from?** — the Full Changelog comparison link.

If a reader can answer those without clicking into the CHANGELOG, the polish is sufficient. Avoid duplicating the CHANGELOG into a verbose PR list at the bottom — the comparison link is enough.
