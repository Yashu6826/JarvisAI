from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from Backend.AgentArchitecture import (
    AgentRunStore,
    RouteDecision,
    Workflow,
    build_context,
    route_from_plan,
)


class AgentArchitectureTests(TestCase):
    def test_gmail_route_is_derived_from_selected_tool_not_request_words(self) -> None:
        decision = route_from_plan({"tool_names": ["gmail_search_messages"]})
        self.assertEqual(decision.workflow, Workflow.PERSONAL_APP)
        self.assertEqual(decision.domains, ["gmail"])

    def test_send_email_plan_is_an_action_requiring_confirmation(self) -> None:
        decision = route_from_plan({"tool_names": ["draft_email", "send_email"]})
        self.assertEqual(decision.workflow, Workflow.ACTION)
        self.assertEqual(decision.domains, ["gmail"])
        self.assertTrue(decision.requires_confirmation)

    def test_mixed_drive_calendar_plan_preserves_both_domains(self) -> None:
        decision = route_from_plan({
            "tool_names": [
                "google_drive_search_files",
                "google_calendar_list_events",
            ]
        })
        self.assertEqual(decision.workflow, Workflow.PERSONAL_APP)
        self.assertEqual(decision.domains, ["drive", "calendar"])

    def test_owner_profile_route_is_derived_from_owner_tool(self) -> None:
        decision = route_from_plan({"tool_names": ["answer_owner_profile"]})
        self.assertEqual(decision.workflow, Workflow.KNOWLEDGE)
        self.assertEqual(decision.domains, ["owner_profile"])

    def test_web_route_is_derived_from_research_tool(self) -> None:
        decision = route_from_plan({"tool_names": ["research_web"]})
        self.assertEqual(decision.workflow, Workflow.RESEARCH)
        self.assertEqual(decision.domains, ["web"])

    def test_dynamic_connected_app_mutation_requires_confirmation(self) -> None:
        decision = route_from_plan({"tool_names": ["notion_update_page"]})
        self.assertEqual(decision.workflow, Workflow.ACTION)
        self.assertEqual(decision.domains, ["notion"])
        self.assertTrue(decision.requires_confirmation)

    def test_no_tool_plan_is_direct(self) -> None:
        decision = route_from_plan({"tool_names": []})
        self.assertEqual(decision.workflow, Workflow.DIRECT)
        self.assertEqual(decision.domains, [])

    def test_context_is_bounded_and_uses_user_scoped_history(self) -> None:
        with patch(
            "Backend.AgentArchitecture.LoadHistory",
            return_value=[
                {"role": "user", "content": "first question"},
                {"role": "assistant", "content": "first answer"},
                {"role": "system", "content": "not included"},
            ],
        ):
            context = build_context(max_chars=100)
        self.assertIn("User: first question", context.conversation)
        self.assertIn("Assistant: first answer", context.conversation)
        self.assertNotIn("not included", context.conversation)

    def test_run_store_records_no_request_or_tool_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AgentRunStore(Path(temp_dir) / "runs.json")
            decision = RouteDecision(
                workflow=Workflow.RESEARCH,
                reason="test",
                confidence=1,
            )
            run = store.start(decision, "secret user request", ["research_web"])
            store.finish(run.id, tool_calls=["research_web"])
            payload = json.loads(
                (Path(temp_dir) / "runs.json").read_text(encoding="utf-8")
            )
        self.assertEqual(payload[0]["status"], "completed")
        self.assertEqual(payload[0]["request_chars"], len("secret user request"))
        self.assertNotIn("secret user request", json.dumps(payload))
