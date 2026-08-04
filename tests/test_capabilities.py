from __future__ import annotations

import unittest
from dataclasses import dataclass
from unittest.mock import patch

from Backend.Capabilities import capability_snapshot, select_tools_for_query


@dataclass
class FakeTool:
    name: str


class CapabilityRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        names = [
            "get_capabilities",
            "search_web",
            "read_webpage",
            "open_website",
            "open_application",
            "close_application",
            "control_volume",
            "control_brightness",
            "get_system_specs",
            "get_power_and_wifi_status",
            "draft_email",
            "send_email",
            "add_task",
            "get_tasks",
            "complete_task",
            "remove_task",
            "google_drive_search_files",
            "google_drive_read_file_content",
            "google_calendar_list_events",
            "google_calendar_create_event",
            "gmail_search_messages",
            "gmail_read_message",
            "maps_search_places",
            "maps_geocode",
            "maps_get_directions",
        ]
        self.tools = [FakeTool(name) for name in names]

    def selected(self, query: str) -> set[str]:
        return {tool.name for tool in select_tools_for_query(query, self.tools)}

    def test_normal_question_keeps_bounded_research_tools(self) -> None:
        self.assertEqual(
            self.selected("Explain recursion simply"),
            {
                "get_capabilities",
                "search_web",
                "read_webpage",
                "gmail_search_messages",
                "gmail_read_message",
            },
        )

    def test_email_address_routes_connected_gmail_send_tools(self) -> None:
        selected = self.selected("Send this to person@example.com")
        self.assertIn("draft_email", selected)
        self.assertIn("send_email", selected)
        self.assertIn("gmail_search_messages", selected)

    def test_plural_email_read_request_routes_gmail_tools(self) -> None:
        selected = self.selected("Read my latest 3 emails and summarize them")
        self.assertIn("gmail_search_messages", selected)
        self.assertIn("gmail_read_message", selected)

    def test_mixed_drive_and_calendar_request_routes_both_domains(self) -> None:
        selected = self.selected(
            "Read the project plan from Google Drive and schedule a meeting tomorrow"
        )
        self.assertIn("google_drive_read_file_content", selected)
        self.assertIn("google_calendar_create_event", selected)

    def test_natural_task_phrase_routes_todo_tools(self) -> None:
        selected = self.selected("I need to submit the report tomorrow")
        self.assertIn("add_task", selected)

    def test_opening_youtube_does_not_expose_desktop_mutations(self) -> None:
        selected = self.selected("Open YouTube")
        self.assertIn("open_website", selected)
        self.assertNotIn("open_application", selected)

    def test_nearby_restaurant_request_routes_maps_tools(self) -> None:
        selected = self.selected("Find the best restaurants near me")
        self.assertIn("maps_search_places", selected)
        self.assertIn("maps_geocode", selected)
        self.assertIn("maps_get_directions", selected)

    def test_snapshot_reports_drive_as_read_only(self) -> None:
        with patch("Backend.Capabilities.google_mcp_connected", return_value=True):
            snapshot = capability_snapshot({"servers": [], "runtime": {}})
        drive = next(item for item in snapshot["google"] if item["id"] == "google_drive")
        self.assertTrue(drive["connected"])
        self.assertTrue(drive["available"])
        self.assertTrue(drive["read_only"])


if __name__ == "__main__":
    unittest.main()
