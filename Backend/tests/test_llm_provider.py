from __future__ import annotations

from unittest import TestCase
from unittest.mock import MagicMock, patch

import Backend.LLMProvider as provider


class LLMProviderOutputBudgetTests(TestCase):
    def test_lmstudio_uses_the_callers_research_budget(self) -> None:
        response = MagicMock()
        response.json.return_value = {"output": [{"type": "message", "content": "Report"}]}

        with patch("Backend.LLMProvider.requests.post", return_value=response) as post:
            provider.lmstudio_generate("Research prompt", max_output_tokens=2200)

        self.assertEqual(post.call_args.kwargs["json"]["max_output_tokens"], 2200)

    def test_openrouter_uses_the_current_completion_budget_field(self) -> None:
        response = MagicMock()
        response.json.return_value = {"choices": [{"message": {"content": "Report"}}]}

        with patch("Backend.LLMProvider.requests.post", return_value=response) as post:
            provider.openrouter_generate("Research prompt", max_output_tokens=2200)

        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["max_completion_tokens"], 2200)
        self.assertNotIn("max_tokens", payload)

    def test_openai_persona_provider_uses_gpt_5_4_mini_and_bounded_output(self) -> None:
        response = MagicMock()
        response.json.return_value = {"choices": [{"message": {"content": "Persona"}}]}

        with patch("Backend.LLMProvider.get_config", side_effect=lambda name, default="": "test-key" if name == "OPENAI_API_KEY" else default), patch("Backend.LLMProvider.requests.post", return_value=response) as post:
            result = provider.openai_generate("Persona prompt", model="gpt-5.4-mini", max_output_tokens=1200, reasoning="off")

        self.assertEqual(result, "Persona")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "gpt-5.4-mini")
        self.assertEqual(payload["max_completion_tokens"], 1200)
        self.assertNotIn("reasoning_effort", payload)

    def test_persona_routing_prefers_dedicated_openai_key(self) -> None:
        with patch("Backend.LLMProvider.get_config", side_effect=lambda name, default="": "test-key" if name == "OPENAI_API_KEY" else default), patch("Backend.LLMProvider.openai_generate", return_value="AI persona") as generate:
            result = provider.generate_persona_text("Persona prompt")

        self.assertEqual(result, "AI persona")
        self.assertEqual(generate.call_args.args[2], "gpt-5.4-mini")
