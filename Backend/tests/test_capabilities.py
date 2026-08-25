from __future__ import annotations

import unittest
from unittest.mock import patch

from Backend.Capabilities import capability_prompt, capability_snapshot


class CapabilityStateTests(unittest.TestCase):
    def test_snapshot_reports_drive_as_read_only(self) -> None:
        with patch("Backend.Capabilities.google_mcp_connected", return_value=True):
            snapshot = capability_snapshot({"servers": [], "runtime": {}})
        drive = next(item for item in snapshot["google"] if item["id"] == "google_drive")
        self.assertTrue(drive["connected"])
        self.assertTrue(drive["available"])
        self.assertTrue(drive["read_only"])

    def test_capability_prompt_reports_only_currently_exposed_tools(self) -> None:
        with patch("Backend.Capabilities.google_mcp_connected", return_value=True):
            prompt = capability_prompt(
                {"servers": [], "runtime": {}},
                ["research_web", "gmail_search_messages"],
            )

        self.assertIn("research_web", prompt)
        self.assertIn("gmail_search_messages", prompt)


if __name__ == "__main__":
    unittest.main()
