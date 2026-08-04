from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import Backend.Chatbot as chatbot
import Backend.EmailManager as email_manager
import Backend.MCPManager as mcp_manager
import Backend.TodoManager as todo_manager
from Backend.WebApp import app


class BrowserSessionAPITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.patches = [
            patch.object(chatbot, "SESSION_DATA_DIR", root / "sessions"),
            patch.object(todo_manager, "SESSION_DATA_DIR", root / "sessions"),
            patch.object(
                email_manager,
                "EMAIL_RECORDS_PATH",
                root / "PendingEmails.json",
            ),
            patch.object(
                mcp_manager,
                "PENDING_ACTIONS_PATH",
                root / "PendingMCPActions.json",
            ),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def test_todos_are_isolated_between_browser_sessions(self) -> None:
        with TestClient(app) as browser_a, TestClient(app) as browser_b:
            created = browser_a.post(
                "/api/todos",
                json={"task": "Private task", "due": "tomorrow"},
            )
            self.assertEqual(created.status_code, 200)
            self.assertEqual(len(browser_a.get("/api/todos").json()["tasks"]), 1)
            self.assertEqual(browser_b.get("/api/todos").json()["tasks"], [])

    def test_public_capabilities_do_not_expose_server_credentials(self) -> None:
        with TestClient(app) as browser:
            response = browser.get("/api/mcp/servers")
        self.assertEqual(response.status_code, 200)
        serialized = response.text.lower()
        self.assertNotIn("authorization", serialized)
        self.assertNotIn("client_secret", serialized)
        self.assertNotIn('"headers"', serialized)
        self.assertNotIn('"env"', serialized)


if __name__ == "__main__":
    unittest.main()
