from __future__ import annotations

import base64
import unittest
from unittest.mock import patch

from Backend.GoogleConnectors import gmail_search_messages


class GoogleConnectorTests(unittest.TestCase):
    @patch("Backend.GoogleConnectors._request")
    def test_gmail_search_returns_read_only_message_details(self, request) -> None:
        encoded = base64.urlsafe_b64encode(b"Please review the attached proposal.").decode().rstrip("=")
        request.side_effect = [
            {"messages": [{"id": "message-1"}]},
            {
                "id": "message-1",
                "threadId": "thread-1",
                "snippet": "Please review the attached proposal.",
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "Proposal"},
                        {"name": "From", "value": "sender@example.com"},
                    ],
                    "body": {"data": encoded},
                },
            },
        ]

        result = gmail_search_messages(count=1)

        self.assertTrue(result["ok"])
        self.assertEqual(result["messages"][0]["subject"], "Proposal")
        self.assertIn("review", result["messages"][0]["body"])


if __name__ == "__main__":
    unittest.main()
