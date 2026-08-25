"""Acceptance tests for the semantic planner's closed tool catalog."""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from unittest.mock import patch

from Backend.AgentTools import AGENT_TOOLS
from Backend.Capabilities import LOCAL_CAPABILITIES
from Backend.JarvisAgent import _planner_available_tools, _planner_tool_catalog


@dataclass
class FakeTool:
    name: str
    description: str = "Test tool purpose"


TOOL_NAMES = {
    "get_capabilities",
    "research_web",
    "search_web",
    "read_webpage",
    "open_website",
    "maps_search_places",
    "maps_geocode",
    "maps_get_directions",
    "get_weather_and_air_quality",
    "check_holiday_schedule",
    "convert_currency",
    "get_system_specs",
    "get_power_and_wifi_status",
    "open_application",
    "close_application",
    "control_volume",
    "control_brightness",
    "create_document",
    "draft_email",
    "send_email",
    "answer_owner_profile",
    "gmail_search_messages",
    "gmail_read_message",
    "google_drive_search_files",
    "google_calendar_list_events",
    "spotify_search_tracks",
}


def fake_tools() -> list[FakeTool]:
    return [FakeTool(name) for name in sorted(TOOL_NAMES)]


class AgentCapabilityMatrixTests(unittest.TestCase):
    def test_all_declared_local_capability_tools_are_registered(self) -> None:
        registered = {str(getattr(tool, "name", "")) for tool in AGENT_TOOLS}
        missing: dict[str, list[str]] = {}
        for capability in LOCAL_CAPABILITIES:
            absent = [name for name in capability["tools"] if name not in registered]
            if absent:
                missing[str(capability["id"])] = absent
        self.assertEqual(missing, {}, f"Declared capabilities missing tools: {missing}")

    def test_connected_catalog_exposes_every_available_tool_to_semantic_planner(self) -> None:
        with patch("Backend.JarvisAgent.google_mcp_connected", return_value=True):
            available = _planner_available_tools(fake_tools())

        self.assertEqual({tool.name for tool in available}, TOOL_NAMES)

    def test_disconnected_integrations_are_filtered_by_availability_not_query(self) -> None:
        def connected(service: str) -> bool:
            return service == "google_drive"

        with patch("Backend.JarvisAgent.google_mcp_connected", side_effect=connected):
            available = {tool.name for tool in _planner_available_tools(fake_tools())}

        self.assertIn("google_drive_search_files", available)
        self.assertNotIn("gmail_search_messages", available)
        self.assertNotIn("send_email", available)
        self.assertNotIn("google_calendar_list_events", available)
        self.assertIn("research_web", available)
        self.assertIn("spotify_search_tracks", available)

    def test_tool_catalog_includes_semantic_purpose_for_every_name(self) -> None:
        catalog = _planner_tool_catalog(fake_tools())

        self.assertEqual({item["name"] for item in catalog}, TOOL_NAMES)
        self.assertTrue(all(item["purpose"] for item in catalog))

    def test_duplicate_tool_names_are_removed_before_planning(self) -> None:
        tools = [FakeTool("research_web"), FakeTool("research_web")]
        with patch("Backend.JarvisAgent.google_mcp_connected", return_value=True):
            available = _planner_available_tools(tools)

        self.assertEqual([tool.name for tool in available], ["research_web"])


if __name__ == "__main__":
    unittest.main()
