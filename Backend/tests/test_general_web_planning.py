from __future__ import annotations

import asyncio
import json
from unittest import TestCase
from unittest.mock import patch

from Backend.AgentTools import _research_queries
from Backend.JarvisAgent import _perceive_request_impl


class FakeTool:
    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description or name.replace("_", " ")


class GeneralWebPlanningTests(TestCase):
    def test_streaming_request_is_selected_semantically_with_full_catalog(self) -> None:
        tools = [
            FakeTool("research_web", "Research current public internet sources"),
            FakeTool("gmail_search_messages", "Search the connected Gmail inbox"),
            FakeTool("google_drive_search_files", "Search connected Google Drive"),
        ]
        session = {
            "recent": "User: Summarize my latest Gmail messages.\nNexa: Summary.",
            "last_workflow": "personal_app",
            "last_domains": ["gmail"],
        }
        response = json.dumps({
            "intent": "compare current streaming platforms",
            "needs_tools": True,
            "tool_names": ["research_web"],
            "workflow": ["Research current streaming platforms and synthesize sources."],
            "max_tool_calls": 1,
        })

        with patch("Backend.JarvisAgent.generate_text", return_value=response) as planner:
            plan = asyncio.run(_perceive_request_impl(
                "Now compare streaming platforms for movies and web series",
                tools,
                session,
            ))

        self.assertEqual(plan["tool_names"], ["research_web"])
        prompt = planner.call_args.args[0]
        self.assertIn("Current request (authoritative for this turn)", prompt)
        self.assertIn("research_web", prompt)
        self.assertIn("gmail_search_messages", prompt)
        self.assertIn("google_drive_search_files", prompt)
        self.assertIn("Never inherit a tool merely because it", prompt)
        self.assertIn("was used earlier in the session", prompt)

    def test_streaming_research_adds_current_year_query(self) -> None:
        queries = _research_queries("best streaming services in India")

        self.assertEqual(len(queries), 2)
        self.assertRegex(queries[0], r"best streaming services in India \d{4}$")
        self.assertEqual(queries[1], "best streaming services in India")

    def test_greeting_with_browser_metadata_can_semantically_choose_no_tool(self) -> None:
        response = json.dumps({
            "intent": "greeting",
            "needs_tools": False,
            "tool_names": [],
            "workflow": ["Reply conversationally."],
            "max_tool_calls": 1,
        })
        query = (
            "Hi\n[Trusted browser location supplied for this request only: "
            "latitude=13.000000, longitude=77.000000. Use these values only "
            "for a location-related request.]"
        )

        with patch("Backend.JarvisAgent.generate_text", return_value=response):
            plan = asyncio.run(_perceive_request_impl(
                query,
                [FakeTool("research_web")],
            ))

        self.assertFalse(plan["needs_tools"])
        self.assertEqual(plan["tool_names"], [])

    def test_reply_context_is_decided_by_semantic_planner(self) -> None:
        response = json.dumps({
            "intent": "respond to replied message",
            "needs_tools": False,
            "tool_names": [],
            "workflow": ["Answer using the replied-to chat message."],
            "max_tool_calls": 1,
        })
        query = (
            '{"previous_message":{"content":"Nice work"},'
            '"current_request":{"query":"What do you think?"}}'
        )

        with patch("Backend.JarvisAgent.generate_text", return_value=response) as planner:
            plan = asyncio.run(_perceive_request_impl(
                query,
                [FakeTool("research_web")],
            ))

        self.assertEqual(plan["tool_names"], [])
        self.assertIn("Current query: What do you think?", planner.call_args.args[0])


if __name__ == "__main__":
    import unittest

    unittest.main()
