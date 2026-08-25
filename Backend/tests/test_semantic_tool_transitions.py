from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from unittest import TestCase
from unittest.mock import patch

from Backend.AgentArchitecture import Workflow, route_from_plan
from Backend.JarvisAgent import _perceive_request_impl


@dataclass
class FakeTool:
    name: str
    description: str


TOOLS = [
    FakeTool("research_web", "Research current public internet sources and return evidence."),
    FakeTool("gmail_search_messages", "Search and summarize the connected Gmail inbox."),
    FakeTool("google_drive_search_files", "Find files in the connected Google Drive."),
    FakeTool("google_calendar_list_events", "Read events from the connected Google Calendar."),
    FakeTool("get_system_specs", "Inspect this computer's hardware and operating system."),
]

CURRENT_CASES = {
    "gmail": (
        "What landed in my electronic postbox since lunch?",
        "gmail_search_messages",
        Workflow.PERSONAL_APP,
    ),
    "drive": (
        "Pull up the cloud document where I wrote the launch budget.",
        "google_drive_search_files",
        Workflow.PERSONAL_APP,
    ),
    "calendar": (
        "How packed is tomorrow afternoon?",
        "google_calendar_list_events",
        Workflow.PERSONAL_APP,
    ),
    "web": (
        "Which entertainment subscriptions are worth it in India right now?",
        "research_web",
        Workflow.RESEARCH,
    ),
    "device": (
        "What hardware is this machine running?",
        "get_system_specs",
        Workflow.DIRECT,
    ),
}


class SemanticToolTransitionTests(TestCase):
    def test_every_current_intent_can_override_every_prior_domain(self) -> None:
        prior_domains = ["gmail", "drive", "calendar", "web", "device"]
        all_names = {tool.name for tool in TOOLS}

        for prior in prior_domains:
            session = {
                "recent": f"User: Previous {prior} task.\nNexa: Previous result.",
                "last_workflow": "personal_app" if prior in {"gmail", "drive", "calendar"} else "research",
                "last_domains": [prior],
            }
            for current, (query, expected_tool, expected_workflow) in CURRENT_CASES.items():
                response = json.dumps({
                    "intent": f"semantic {current} task",
                    "needs_tools": True,
                    "tool_names": [expected_tool],
                    "workflow": [f"Use {expected_tool} for the current request."],
                    "max_tool_calls": 1,
                })
                with self.subTest(prior=prior, current=current), patch(
                    "Backend.JarvisAgent.generate_text",
                    return_value=response,
                ) as planner:
                    plan = asyncio.run(_perceive_request_impl(query, TOOLS, session))

                    self.assertEqual(plan["tool_names"], [expected_tool])
                    self.assertEqual(route_from_plan(plan).workflow, expected_workflow)
                    prompt = planner.call_args.args[0]
                    self.assertTrue(all(name in prompt for name in all_names))

    def test_one_request_can_semantically_select_multiple_domains(self) -> None:
        response = json.dumps({
            "intent": "prepare from Drive and inspect calendar",
            "needs_tools": True,
            "tool_names": [
                "google_drive_search_files",
                "google_calendar_list_events",
            ],
            "workflow": [
                "Find the launch plan in Drive.",
                "Check the calendar for a suitable review slot.",
            ],
            "max_tool_calls": 2,
        })

        with patch("Backend.JarvisAgent.generate_text", return_value=response):
            plan = asyncio.run(_perceive_request_impl(
                "Find our launch plan and tell me when I can review it tomorrow.",
                TOOLS,
                {"recent": "User: We were previously researching streaming services."},
            ))

        decision = route_from_plan(plan)
        self.assertEqual(
            plan["tool_names"],
            ["google_drive_search_files", "google_calendar_list_events"],
        )
        self.assertEqual(decision.domains, ["drive", "calendar"])


if __name__ == "__main__":
    import unittest

    unittest.main()
