"""Tests for the icu_intensity (percent) -> intensity factor (ratio) conversion."""

import pytest

from intervals_icu_mcp.tools._intensity import intensity_factor


@pytest.mark.parametrize(
    ("icu_intensity", "expected"),
    [
        (53.51, 0.535),  # NP 99 W / FTP 185 W, live-verified
        (100.0, 1.0),
        (105.4, 1.054),
        (55.136196, 0.551),
    ],
)
def test_converts_percent_to_ratio(icu_intensity: float, expected: float) -> None:
    assert intensity_factor(icu_intensity) == expected


@pytest.mark.parametrize("icu_intensity", [None, 0, 0.0])
def test_missing_or_zero_returns_none(icu_intensity: float | None) -> None:
    assert intensity_factor(icu_intensity) is None
