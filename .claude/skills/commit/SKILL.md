---
name: commit
description: |
  Analyze staged and unstaged changes, summarize intent, and create a
  conventional commit message. Use when the user asks to commit, save work,
  or says "commit this".
allowed-tools: Bash(git add:*), Bash(git status:*), Bash(git commit:*)
---

## Context

Gather the following before composing the commit message:

- Current branch: `git branch --show-current`
- Working tree status: `git status --short --branch`
- Diff (staged + unstaged): `git diff $(git rev-parse --verify HEAD 2>/dev/null || echo --cached)`
- Recent history (if available): `git log --oneline -10 || echo "No commits yet"`

## Instructions

1. Summarize the **intent** of the changes — what problem they solve or what feature they add.
2. Create a **concise, conventional commit message** following [Conventional Commits](https://www.conventionalcommits.org):
   - Format: `type(scope): description`
   - Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `ci`
   - Scope is optional but encouraged (e.g., `tools`, `client`, `middleware`)
3. Stage all relevant changes with `git add`.
4. Commit with `git commit -m "<generated message>"`.
5. If there are unrelated changes, suggest splitting into separate commits.
