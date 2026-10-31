"""Tests for .github/scripts/next_version.py (the release version bump rules)."""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "next_version.py"
_spec = importlib.util.spec_from_file_location("next_version", _SCRIPT)
assert _spec and _spec.loader
next_version = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(next_version)


@pytest.mark.parametrize(
    ("subject", "body", "expected"),
    [
        ("feat(events): add tags (#12)", "", "minor"),
        ("feat: add tags", "", "minor"),
        ("fix(athlete): read icu_weight (#176)", "", "patch"),
        ("chore(deps): bump httpx (#175)", "", "patch"),
        ("docs: fix typo", "", "patch"),
        ("feat(tools)!: rename icu_get_upcoming_workouts (#200)", "", "major"),
        ("fix!: drop alias", "", "major"),
        ("refactor: tidy", "BREAKING CHANGE: removes the event_type alias", "major"),
        ("Update README.md", "", "patch"),
        ("feature: not a real type but conventional shape", "", "patch"),
    ],
)
def test_bump_for(subject: str, body: str, expected: str) -> None:
    assert next_version.bump_for(subject, body) == expected


@pytest.mark.parametrize(
    ("version", "bump", "expected"),
    [
        ("v5.8.0", "patch", "5.8.1"),
        ("v5.8.3", "minor", "5.9.0"),
        ("v5.8.3", "major", "6.0.0"),
        ("5.8.0", "patch", "5.8.1"),
    ],
)
def test_apply_bump(version: str, bump: str, expected: str) -> None:
    assert next_version.apply_bump(version, bump) == expected


def test_highest_bump_wins() -> None:
    commits = [("fix: a", ""), ("feat: b", ""), ("chore: c", "")]
    assert next_version.highest_bump(commits) == "minor"
    assert next_version.highest_bump(commits + [("feat!: d", "")]) == "major"
    assert next_version.highest_bump([("ci: e", "")]) == "patch"


def test_parse_version_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        next_version.parse_version("5.8")
    assert next_version.parse_version("v10.2.3") > next_version.parse_version("v9.20.30")
