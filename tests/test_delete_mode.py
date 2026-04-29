"""Tests for INTERVALS_ICU_DELETE_MODE config and conditional tool registration."""

import asyncio
import importlib
import sys

import pytest
from pydantic import ValidationError

from intervals_icu_mcp.auth import ICUConfig


class TestDeleteModeValidation:
    def test_default_is_safe(self, monkeypatch):
        monkeypatch.delenv("INTERVALS_ICU_DELETE_MODE", raising=False)
        cfg = ICUConfig(intervals_icu_api_key="k", intervals_icu_athlete_id="a")
        assert cfg.intervals_icu_delete_mode == "safe"

    def test_accepts_full(self):
        cfg = ICUConfig(
            intervals_icu_api_key="k",
            intervals_icu_athlete_id="a",
            intervals_icu_delete_mode="full",
        )
        assert cfg.intervals_icu_delete_mode == "full"

    def test_accepts_none(self):
        cfg = ICUConfig(
            intervals_icu_api_key="k",
            intervals_icu_athlete_id="a",
            intervals_icu_delete_mode="none",
        )
        assert cfg.intervals_icu_delete_mode == "none"

    def test_normalizes_case_and_whitespace(self):
        cfg = ICUConfig.model_validate(
            {
                "intervals_icu_api_key": "k",
                "intervals_icu_athlete_id": "a",
                "intervals_icu_delete_mode": "  FULL  ",
            }
        )
        assert cfg.intervals_icu_delete_mode == "full"

    def test_rejects_invalid_value(self):
        with pytest.raises(ValidationError) as exc_info:
            ICUConfig.model_validate(
                {
                    "intervals_icu_api_key": "k",
                    "intervals_icu_athlete_id": "a",
                    "intervals_icu_delete_mode": "banana",
                }
            )
        message = str(exc_info.value)
        assert "INTERVALS_ICU_DELETE_MODE must be one of" in message
        assert "banana" in message


def _reload_server() -> object:
    """Re-import the server module so module-level registration re-runs."""
    sys.modules.pop("intervals_icu_mcp.server", None)
    return importlib.import_module("intervals_icu_mcp.server")


class TestConditionalRegistration:
    """Each mode registers a different set of delete tools."""

    @staticmethod
    def _tool_names(server_module: object) -> set[str]:
        tools = asyncio.run(server_module.mcp.list_tools())  # type: ignore[attr-defined]
        return {t.name for t in tools}

    def test_safe_mode_registers_event_and_gear_only(self, monkeypatch):
        monkeypatch.setenv("INTERVALS_ICU_DELETE_MODE", "safe")
        names = self._tool_names(_reload_server())
        assert "icu_delete_event" in names
        assert "icu_bulk_delete_events" in names
        assert "icu_delete_gear" in names
        assert "icu_delete_activity" not in names
        assert "icu_delete_sport_settings" not in names
        assert "icu_delete_custom_item" not in names

    def test_full_mode_registers_all_delete_tools(self, monkeypatch):
        monkeypatch.setenv("INTERVALS_ICU_DELETE_MODE", "full")
        names = self._tool_names(_reload_server())
        for tool in (
            "icu_delete_event",
            "icu_bulk_delete_events",
            "icu_delete_gear",
            "icu_delete_activity",
            "icu_delete_sport_settings",
            "icu_delete_custom_item",
        ):
            assert tool in names, f"expected {tool} registered in full mode"

    def test_none_mode_registers_no_delete_tools(self, monkeypatch):
        monkeypatch.setenv("INTERVALS_ICU_DELETE_MODE", "none")
        names = self._tool_names(_reload_server())
        for tool in (
            "icu_delete_event",
            "icu_bulk_delete_events",
            "icu_delete_gear",
            "icu_delete_activity",
            "icu_delete_sport_settings",
            "icu_delete_custom_item",
        ):
            assert tool not in names, f"expected {tool} NOT registered in none mode"
