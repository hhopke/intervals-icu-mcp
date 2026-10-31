"""Compute the next release version from the commits merged since the last tag.

PRs are squash-merged, so each commit subject on main is a PR title. The
conventional-commit type in that title sets the bump:

- ``!`` after the type/scope (``feat!: ...``) -> major. A ``BREAKING CHANGE:`` footer
  also counts, but squash merges here use a blank body, so in practice ``!`` is the
  only signal.
- ``feat`` -> minor
- anything else (fix, docs, chore, a non-conforming title, ...) -> patch

Usage:
    python .github/scripts/next_version.py [--version X.Y.Z]

Prints a summary to stderr and writes ``version``, ``tag`` and ``previous_tag``
to ``$GITHUB_OUTPUT`` when it is set. Exits non-zero when there is nothing to
release or the override is invalid.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

# Keep in sync with TYPES in .github/workflows/pr-title.yml, which enforces titles on PRs.
ALLOWED_TYPES = "feat|fix|docs|style|refactor|test|chore|ci|build|perf|revert"
TITLE_RE = re.compile(rf"^(?P<type>{ALLOWED_TYPES})(?:\([^)]*\))?(?P<bang>!)?: \S")
REVERT_RE = re.compile(r'^Revert ".+"')
BREAKING_FOOTER_RE = re.compile(r"^BREAKING[ -]CHANGE: ", re.MULTILINE)
VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
BUMPS = ("patch", "minor", "major")


def bump_for(subject: str, body: str = "") -> str:
    """Return the bump ('major', 'minor' or 'patch') one commit asks for."""
    match = TITLE_RE.match(subject)
    if BREAKING_FOOTER_RE.search(body) or (match and match.group("bang")):
        return "major"
    if match and match.group("type") == "feat":
        return "minor"
    return "patch"


def parse_version(text: str) -> tuple[int, int, int]:
    match = VERSION_RE.match(text.removeprefix("v"))
    if not match:
        raise ValueError(f"not a X.Y.Z version: {text!r}")
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


def apply_bump(version: str, bump: str) -> str:
    major, minor, patch = parse_version(version)
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def highest_bump(commits: list[tuple[str, str]]) -> str:
    return max((bump_for(subject, body) for subject, body in commits), key=BUMPS.index)


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def _commits_since(tag: str) -> list[tuple[str, str]]:
    raw = _git("log", "--no-merges", "--format=%s%x1f%b%x1e", f"{tag}..HEAD")
    commits = []
    for record in raw.split("\x1e"):
        if record.strip():
            subject, _, body = record.strip("\n").partition("\x1f")
            commits.append((subject, body))
    return commits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", default="", help="explicit X.Y.Z override")
    args = parser.parse_args()

    previous_tag = _git("describe", "--tags", "--abbrev=0", "--match", "v[0-9]*").strip()
    commits = _commits_since(previous_tag)
    if not commits:
        print(f"Nothing to release: no commits since {previous_tag}.", file=sys.stderr)
        return 1

    for subject, body in commits:
        if not (TITLE_RE.match(subject) or REVERT_RE.match(subject)):
            print(f"warning: not a conventional title, counted as patch: {subject}", file=sys.stderr)
        print(f"  {bump_for(subject, body):5}  {subject}", file=sys.stderr)

    if args.version:
        version = args.version.strip().removeprefix("v")
        try:
            if parse_version(version) <= parse_version(previous_tag):
                print(f"{version} is not newer than {previous_tag}.", file=sys.stderr)
                return 1
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"Override: {previous_tag} -> v{version}", file=sys.stderr)
    else:
        bump = highest_bump(commits)
        version = apply_bump(previous_tag, bump)
        print(f"{bump} bump: {previous_tag} -> v{version}", file=sys.stderr)

    if _git("tag", "--list", f"v{version}").strip():
        print(f"Tag v{version} already exists.", file=sys.stderr)
        return 1

    print(version)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as fh:
            fh.write(f"version={version}\ntag=v{version}\nprevious_tag={previous_tag}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
