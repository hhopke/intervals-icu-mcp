"""Intensity factor conversion.

The Intervals.icu API returns ``icu_intensity`` as a percentage of threshold
(NP 99 W at FTP 185 W comes back as ``53.51``). Tools expose it as
``intensity_factor``, which readers expect as the conventional ratio (``0.535``),
so every tool converts through this helper.
"""


def intensity_factor(icu_intensity: float | None) -> float | None:
    """Convert the API's ``icu_intensity`` percentage to an intensity factor ratio.

    Returns None when the value is missing or zero, so callers can omit the field.
    """
    if not icu_intensity:
        return None
    return round(icu_intensity / 100, 3)
