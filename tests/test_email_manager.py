from __future__ import annotations

import base64
import tempfile
import unittest
from email import message_from_bytes
from pathlib import Path
from unittest.mock import patch

import Backend.EmailManager as email_manager
from Backend.GoogleOAuth import google_session_context


class ConnectedGmailTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(
            email_manager,
            "EMAIL_RECORDS_PATH",
            Path(self.temp_dir.name) / "PendingEmails.json",
        )
        self.path_patch.start()

    def tearDown(self) -> None:
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def create_pending(self) -> dict[str, object]:
        with (
            patch.object(email_manager, "google_mcp_connected", return_value=True),
            patch.object(
                email_manager,
                "google_connected_email",
                return_value="connected@example.com",
            ),
        ):
            return email_manager.create_pending_email(
                recipient="recipient@example.com",
                subject="Project update",
                body="The project is on track.",
                request_text="Send the project update",
            )

    def test_pending_email_is_scoped_to_browser_session(self) -> None:
        with google_session_context("browser-a"):
            pending = self.create_pending()
            self.assertEqual(
                email_manager.get_latest_pending_email()["id"],
                pending["id"],
            )
        with google_session_context("browser-b"):
            self.assertIsNone(email_manager.get_latest_pending_email())
            with self.assertRaises(email_manager.EmailDeliveryError):
                email_manager.confirm_pending_email(str(pending["id"]))

    def test_confirmation_sends_once_from_connected_account(self) -> None:
        with google_session_context("browser-a"):
            pending = self.create_pending()
            with patch.object(
                email_manager,
                "send_gmail_email",
                return_value={
                    "sender": "connected@example.com",
                    "to": ["recipient@example.com"],
                    "cc": [],
                    "bcc_count": 0,
                    "subject": "Project update",
                    "message_id": "gmail-message-id",
                    "thread_id": "gmail-thread-id",
                },
            ) as send:
                result = email_manager.confirm_pending_email(str(pending["id"]))
            send.assert_called_once()
            self.assertEqual(result["sender"], "connected@example.com")
            with self.assertRaises(email_manager.EmailDeliveryError):
                email_manager.confirm_pending_email(str(pending["id"]))

    def test_local_draft_does_not_require_gmail_connection(self) -> None:
        with google_session_context("browser-a"):
            with patch.object(email_manager, "google_connected_email", return_value=""):
                draft = email_manager.save_email_draft(
                    recipient="recipient@example.com",
                    subject="Draft only",
                    body="Nothing should be sent.",
                )
        self.assertEqual(draft["status"], "draft")

    def test_delivery_uses_gmail_api_oauth_and_connected_sender(self) -> None:
        class GmailResponse:
            ok = True
            status_code = 200

            @staticmethod
            def json() -> dict[str, str]:
                return {"id": "message-id", "threadId": "thread-id"}

        with (
            google_session_context("browser-a"),
            patch.object(email_manager, "google_mcp_connected", return_value=True),
            patch.object(
                email_manager,
                "google_connected_email",
                return_value="connected@example.com",
            ),
            patch.object(email_manager, "google_access_token", return_value="oauth-token"),
            patch.object(
                email_manager.requests,
                "post",
                return_value=GmailResponse(),
            ) as post,
        ):
            result = email_manager.send_gmail_email(
                recipient="recipient@example.com",
                subject="OAuth delivery",
                body="Sent through the Gmail API.",
            )

        self.assertEqual(result["sender"], "connected@example.com")
        call = post.call_args
        self.assertEqual(call.args[0], email_manager.GMAIL_SEND_URL)
        self.assertEqual(
            call.kwargs["headers"]["Authorization"],
            "Bearer oauth-token",
        )
        raw = call.kwargs["json"]["raw"]
        decoded = base64.urlsafe_b64decode(raw.encode("ascii"))
        message = message_from_bytes(decoded)
        self.assertEqual(message["From"], "connected@example.com")
        self.assertEqual(message["To"], "recipient@example.com")


if __name__ == "__main__":
    unittest.main()
