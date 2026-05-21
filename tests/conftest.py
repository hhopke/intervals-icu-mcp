"""Pytest configuration and shared fixtures."""

import os

import dotenv

# Isolate the test suite from any local `.env` file. The developer's `.env`
# can carry overrides like `INTERVALS_ICU_DELETE_MODE=full` that flip the
# safe-mode default and break tests asserting safe-mode behavior. Both
# `server.py` and `load_config()` call `load_dotenv()` at import time, and
# `ICUConfig` reads `env_file=".env"` directly via pydantic-settings — so any
# leak happens before per-test fixtures can intervene. We neutralize at
# conftest module-load time, BEFORE importing any first-party module that
# might do `from dotenv import load_dotenv` and capture the real binding.
for _key in [k for k in os.environ if k.startswith("INTERVALS_ICU_")]:
    del os.environ[_key]


def _noop_load_dotenv(*_args, **_kwargs):
    return False


dotenv.load_dotenv = _noop_load_dotenv  # type: ignore[assignment]

import pytest  # noqa: E402
import respx  # noqa: E402

from intervals_icu_mcp.auth import ICUConfig  # noqa: E402

ICUConfig.model_config["env_file"] = None


@pytest.fixture
def mock_config():
    """Provide a mock ICU configuration for testing."""
    return ICUConfig(
        intervals_icu_api_key="test_api_key_12345",
        intervals_icu_athlete_id="i123456",
    )


@pytest.fixture
def respx_mock():
    """Provide a respx mock router for HTTP requests."""
    with respx.mock(
        base_url="https://intervals.icu/api/v1",
        assert_all_called=False,
    ) as respx_mock:
        yield respx_mock


@pytest.fixture
def mock_athlete_data():
    """Sample athlete data for testing."""
    return {
        "id": "i123456",
        "name": "Test Athlete",
        "email": "test@example.com",
        "weight": 70.0,
        "ctl": 50.0,
        "atl": 35.0,
        "tsb": 15.0,
        "ramp_rate": 3.5,
        "sport_settings": [
            {
                "id": 1,
                "type": "Ride",
                "ftp": 250,
                "fthr": 165,
            }
        ],
    }


@pytest.fixture
def mock_activity_data():
    """Sample activity data for testing."""
    return {
        "id": "12345",
        "start_date_local": "2025-10-13T08:00:00",
        "name": "Morning Ride",
        "type": "Ride",
        "distance": 50000.0,  # meters
        "moving_time": 7200,  # seconds
        "elapsed_time": 7500,
        "total_elevation_gain": 500.0,
        "average_speed": 6.94,  # m/s
        "average_watts": 200,
        "normalized_power": 210,
        "average_heartrate": 145,
        "icu_training_load": 120,
        "icu_intensity": 0.84,
    }


@pytest.fixture
def mock_wellness_data():
    """Sample wellness data for testing."""
    return {
        "id": "2025-10-13",
        "weight": 70.0,
        "restingHR": 48,
        "hrv": 65.5,
        "hrvSDNN": 75.2,
        "sleepSecs": 28800,  # 8 hours
        "sleepQuality": 8,
        "sleepScore": 85.0,
        "fatigue": 3,
        "soreness": 2,
        "stress": 2,
        "mood": 8,
        "motivation": 9,
        "ctl": 50.0,
        "atl": 35.0,
        "tsb": 15.0,
    }


@pytest.fixture
def mock_event_data():
    """Sample event data for testing."""
    return {
        "id": 1001,
        "start_date_local": "2025-10-14",
        "category": "WORKOUT",
        "name": "Threshold Intervals",
        "type": "Ride",
        "description": "5x5min @ FTP",
        "moving_time": 3600,
        "icu_training_load": 100,
        "icu_intensity": 0.90,
    }


@pytest.fixture
def mock_power_curve_data():
    """Sample power curve data for testing."""
    return {
        "name": "Power Curve",
        "type": "power",
        "athlete_id": "i123456",
        "data": [
            {"secs": 5, "watts": 800, "date": "2025-10-01"},
            {"secs": 60, "watts": 400, "date": "2025-10-05"},
            {"secs": 300, "watts": 300, "date": "2025-10-08"},
            {"secs": 1200, "watts": 250, "date": "2025-10-12"},
        ],
    }
