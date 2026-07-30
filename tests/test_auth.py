"""Tests for credential validation."""

from intervals_icu_mcp.auth import ICUConfig, validate_credentials


class TestValidateCredentials:
    def test_accepts_athlete_id_i123456(self):
        """i123456 is a real athlete id, not a reserved value — it must not be
        rejected just because .env.example uses it (regression for #104)."""
        config = ICUConfig(
            intervals_icu_api_key="a_real_key",
            intervals_icu_athlete_id="i123456",
        )
        assert validate_credentials(config) is True

    def test_accepts_normal_credentials(self):
        config = ICUConfig(
            intervals_icu_api_key="a_real_key",
            intervals_icu_athlete_id="i368404",
        )
        assert validate_credentials(config) is True

    def test_rejects_missing_api_key(self):
        config = ICUConfig(intervals_icu_api_key="", intervals_icu_athlete_id="i368404")
        assert validate_credentials(config) is False

    def test_rejects_placeholder_api_key(self):
        config = ICUConfig(
            intervals_icu_api_key="your_api_key_here",
            intervals_icu_athlete_id="i368404",
        )
        assert validate_credentials(config) is False

    def test_rejects_missing_athlete_id(self):
        config = ICUConfig(intervals_icu_api_key="a_real_key", intervals_icu_athlete_id="")
        assert validate_credentials(config) is False
