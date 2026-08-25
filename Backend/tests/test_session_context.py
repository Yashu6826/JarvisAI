from __future__ import annotations

import unittest
from unittest.mock import patch

from Backend.AgentArchitecture import build_context
from Backend.SessionContext import derive_context, prompt_block


class SessionContextTests(unittest.TestCase):
    def test_shared_speakers_are_preserved_in_context(self) -> None:
        context = derive_context(
            [
                {"id": "1", "role": "user", "sender_name": "Alice", "content": "Find cafes in Indiranagar.", "visibility": "shared"},
                {"id": "2", "role": "assistant", "content": "Cafe A and Cafe B are good options.", "visibility": "shared"},
                {"id": "3", "role": "user", "sender_name": "Bob", "content": "Which one has Wi-Fi?", "visibility": "shared"},
            ],
            user_id="bob",
        )
        block = prompt_block(context)
        self.assertIn("Alice: Find cafes", block)
        self.assertIn("Bob: Which one has Wi-Fi?", block)
        self.assertIn("Nexa: Cafe A", block)

    def test_private_visible_message_does_not_enter_shared_context_for_other_user(self) -> None:
        context = derive_context(
            [
                {"id": "1", "role": "user", "sender_name": "Alice", "content": "Shared plan", "visibility": "shared"},
                {"id": "2", "role": "assistant", "content": "Alice private result", "visibility": "private", "visible_to_user_id": "alice"},
                {"id": "3", "role": "assistant", "content": "Shared result", "visibility": "shared"},
            ],
            user_id="bob",
        )
        block = prompt_block(context)
        self.assertNotIn("Alice private result", block)
        self.assertIn("Shared result", block)

    def test_context_contains_conversation_not_tool_routing_instructions(self) -> None:
        context = derive_context(
            [
                {"id": "1", "role": "user", "sender_name": "Alice", "content": "Summarize my Gmail.", "visibility": "shared"},
                {"id": "2", "role": "assistant", "content": "Here is the summary.", "visibility": "shared"},
            ],
            user_id="alice",
            last_workflow="personal_app",
            last_domains=["gmail"],
        )

        block = prompt_block(context)
        self.assertIn("Summarize my Gmail", block)
        self.assertNotIn("workflow=personal_app", block)
        self.assertNotIn("domains=gmail", block)

    def test_agent_context_uses_session_context_when_available(self) -> None:
        with patch(
            "Backend.AgentArchitecture.load_for_agent",
            return_value={
                "recent": "Alice: We chose Cafe B.",
                "summary": "Earlier visible session excerpts",
                "entities": [],
                "active_task": "Check Cafe B tomorrow",
            },
        ):
            context = build_context()
        self.assertIn("Cafe B", context.conversation)
        self.assertEqual(context.session_context["active_task"], "Check Cafe B tomorrow")


if __name__ == "__main__":
    unittest.main()
