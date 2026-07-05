"""Regression tests for the workout syntax reference (intervals-icu://workout-syntax).

The Intervals.icu parser treats a bare ``m`` suffix as **minutes**, never
meters — so a distance step must use ``mtr`` (meters) or ``yrd`` (yards).
Writing ``400m`` for a 400 m swim is parsed as 400 *minutes*, which is what
produced the ~41-hour / hundreds-of-km garbage reported in issue #75.
"""

import re

from intervals_icu_mcp.workout_syntax import WORKOUT_SYNTAX_SPEC


def test_meters_token_is_mtr_not_bare_m():
    """The distance table documents meters as ``mtr``, not the ambiguous ``m``."""
    assert "400mtr" in WORKOUT_SYNTAX_SPEC
    # The old, incorrect "context-dependent, >200 = meters" heuristic is gone.
    assert "context-dependent" not in WORKOUT_SYNTAX_SPEC


def test_yards_token_is_yrd_not_yd():
    """Yards use ``yrd`` (verified against the API); ``yd`` is not a valid token."""
    assert "yrd" in WORKOUT_SYNTAX_SPEC
    assert "yd" not in WORKOUT_SYNTAX_SPEC.replace("yrd", "")


def test_minutes_vs_meters_warning_present():
    """The spec explicitly warns that bare ``m`` means minutes."""
    assert "never meters" in WORKOUT_SYNTAX_SPEC


def test_no_example_step_uses_bare_m_for_distance():
    """No worked example writes a swim/run distance as a bare ``m`` step.

    Matches only step lines (``- ...``, optionally with an ``Nx`` repeat
    prefix such as ``- 4x 100m strides``) for the distance values we
    converted. Anchoring to the line start skips prose like the
    ``### Running - 800m Repeats`` heading, and the trailing ``\\b`` skips
    the corrected ``400mtr`` tokens. Pure time steps like ``- 20m ... pace``
    (20 minutes) are unaffected — 20 is not a converted distance.
    """
    for meters in (50, 100, 200, 400, 800):
        pattern = rf"^- (?:\d+x )?{meters}m\b"
        assert not re.search(pattern, WORKOUT_SYNTAX_SPEC, re.MULTILINE), (
            f"Found bare-metre distance step '- {meters}m' — use '{meters}mtr' instead"
        )
