"""Unit tests for per-request header credential resolution.

These cover the pure resolution helper that lets a single deploy serve multiple
athletes: ``X-Intervals-Api-Key`` / ``X-Intervals-Athlete-Id`` headers override
the env-var-derived config, with env values as fallback.
"""

from intervals_icu_mcp.auth import ICUConfig, apply_header_credentials


def _base_config() -> ICUConfig:
    return ICUConfig(
        intervals_icu_api_key="env_key",
        intervals_icu_athlete_id="i_env",
        intervals_icu_delete_mode="full",
    )


class TestApplyHeaderCredentials:
    def test_headers_override_env(self):
        result = apply_header_credentials(
            _base_config(),
            {"x-intervals-api-key": "hdr_key", "x-intervals-athlete-id": "i_hdr"},
        )
        assert result.intervals_icu_api_key == "hdr_key"
        assert result.intervals_icu_athlete_id == "i_hdr"

    def test_no_headers_falls_back_to_env(self):
        result = apply_header_credentials(_base_config(), {})
        assert result.intervals_icu_api_key == "env_key"
        assert result.intervals_icu_athlete_id == "i_env"

    def test_only_api_key_header(self):
        result = apply_header_credentials(
            _base_config(), {"x-intervals-api-key": "hdr_key"}
        )
        assert result.intervals_icu_api_key == "hdr_key"
        assert result.intervals_icu_athlete_id == "i_env"  # env fallback

    def test_only_athlete_id_header(self):
        result = apply_header_credentials(
            _base_config(), {"x-intervals-athlete-id": "i_hdr"}
        )
        assert result.intervals_icu_api_key == "env_key"  # env fallback
        assert result.intervals_icu_athlete_id == "i_hdr"

    def test_empty_header_values_are_ignored(self):
        result = apply_header_credentials(
            _base_config(),
            {"x-intervals-api-key": "", "x-intervals-athlete-id": ""},
        )
        assert result.intervals_icu_api_key == "env_key"
        assert result.intervals_icu_athlete_id == "i_env"

    def test_header_lookup_is_case_insensitive(self):
        result = apply_header_credentials(
            _base_config(),
            {"X-Intervals-Api-Key": "hdr_key", "X-INTERVALS-ATHLETE-ID": "i_hdr"},
        )
        assert result.intervals_icu_api_key == "hdr_key"
        assert result.intervals_icu_athlete_id == "i_hdr"

    def test_returns_icu_config_and_preserves_delete_mode(self):
        result = apply_header_credentials(
            _base_config(), {"x-intervals-api-key": "hdr_key"}
        )
        assert isinstance(result, ICUConfig)
        # delete_mode is a startup/env concern and must not be touched by headers
        assert result.intervals_icu_delete_mode == "full"

    def test_does_not_mutate_input_config(self):
        config = _base_config()
        apply_header_credentials(
            config, {"x-intervals-api-key": "hdr_key", "x-intervals-athlete-id": "i_hdr"}
        )
        assert config.intervals_icu_api_key == "env_key"
        assert config.intervals_icu_athlete_id == "i_env"
