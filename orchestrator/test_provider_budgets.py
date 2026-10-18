"""Offline regressions for bounded per-role provider generation options."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from orchestrator import providers, run


class ProviderBudgetTests(unittest.TestCase):
    def test_checked_in_role_identities_and_planner_budget(self):
        agents = run.load_agents()
        self.assertEqual({role: (agent["provider"], agent["model"]) for role, agent in agents.items()}, {
            "planner": ("openrouter", "deepseek/deepseek-v4.1-flash"),
            "frontend": ("openrouter", "anthropic/claude-sonnet-5.5"),
            "backend": ("openrouter", "anthropic/claude-sonnet-5.5"),
            "tester": ("openrouter", "deepseek/deepseek-v4.1-flash"),
            "reviewer": ("anthropic", "claude-sonnet-5"),
        })
        self.assertEqual(agents["planner"].get("max_tokens"), 16384)
        self.assertEqual(agents["planner"].get("reasoning"), {"effort": "low"})
        for agent in agents.values():
            options = {key: agent[key] for key in ("max_tokens", "reasoning") if key in agent}
            providers.validate_provider_options(agent["provider"], agent["model"], **options)

    def test_role_options_reach_openrouter_without_changing_identity(self):
        agent = {"provider": "openrouter", "model": "deepseek/deepseek-v4.1-flash",
                 "instructions": "planner/instructions.md", "max_tokens": 16384,
                 "reasoning": {"effort": "low"}}
        with patch.object(run, "load_agents", return_value={"planner": agent}), \
             patch.object(run, "load_instructions", return_value="system"), \
             patch.object(providers, "OpenAI") as client, \
             patch.dict("os.environ", {"OPENROUTER_API_KEY": "offline-test-placeholder"}):
            client.return_value.chat.completions.create.return_value = SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="plan"), finish_reason="stop")])
            self.assertEqual(run.run_agent("planner", "task", timeout=12), "plan")
            request = client.return_value.chat.completions.create.call_args.kwargs
            self.assertEqual(request["model"], agent["model"])
            self.assertEqual(request["max_tokens"], 16384)
            self.assertEqual(request.get("extra_body"), {"reasoning": {"effort": "low"}})
            self.assertEqual(request["timeout"], 12)
            client.return_value.chat.completions.create.assert_called_once()

    def test_invalid_budgets_fail_before_client_or_request(self):
        invalid = [
            {"max_tokens": value} for value in (0, -1, True, 1.5, "16384", None, 32769)
        ] + [
            {"reasoning": value} for value in (
                {}, [], "low", {"effort": "secret-invalid"}, {"effort": True},
                {"max_tokens": 0}, {"max_tokens": True}, {"max_tokens": 1.5},
                {"max_tokens": 16385}, {"max_tokens": 15361},
                {"effort": "low", "max_tokens": 2048}, {"enabled": True},
                {"effort": "low", "unknown": "secret-invalid"},
            )
        ]
        with patch.object(providers, "OpenAI") as client:
            for options in invalid:
                with self.subTest(options=options):
                    with self.assertRaises(providers.ProviderError) as caught:
                        providers.call_openrouter("model", "system", "task", **options)
                    self.assertEqual(caught.exception.error_type, "PROVIDER_CONFIG_ERROR")
                    self.assertNotIn("secret-invalid", str(caught.exception))
            client.assert_not_called()

    def test_reasoning_reserves_at_least_1024_visible_tokens(self):
        with patch.object(providers, "OpenAI") as client:
            with self.assertRaises(providers.ProviderError) as caught:
                providers.call_openrouter("model", "s", "u", max_tokens=2048,
                                          reasoning={"max_tokens": 1025})
            self.assertEqual(caught.exception.error_type, "PROVIDER_CONFIG_ERROR")
            client.assert_not_called()

    def test_numeric_reasoning_and_total_budget_reach_request(self):
        with patch.object(providers, "OpenAI") as client, \
             patch.dict("os.environ", {"OPENROUTER_API_KEY": "offline-test-placeholder"}):
            client.return_value.chat.completions.create.return_value = SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])
            self.assertEqual(providers.call_provider("openrouter", "model", "s", "u",
                             max_tokens=4096, reasoning={"max_tokens": 2048}), "ok")
            request = client.return_value.chat.completions.create.call_args.kwargs
            self.assertEqual(request["max_tokens"], 4096)
            self.assertEqual(request["extra_body"], {"reasoning": {"max_tokens": 2048}})

    def test_anthropic_total_budget_and_unsupported_reasoning(self):
        with patch.object(providers, "Anthropic") as client, \
             patch.dict("os.environ", {"ANTHROPIC_API_KEY": "offline-test-placeholder"}):
            client.return_value.messages.create.return_value = SimpleNamespace(
                content=[SimpleNamespace(type="text", text="ok")])
            self.assertEqual(providers.call_provider("anthropic", "model", "s", "u", max_tokens=2048), "ok")
            request = client.return_value.messages.create.call_args.kwargs
            self.assertEqual(request["max_tokens"], 2048)
            self.assertNotIn("extra_body", request)
            client.reset_mock()
            for options in ({"reasoning": {"effort": "low"}}, {"max_tokens": True}):
                with self.assertRaises(providers.ProviderError) as caught:
                    providers.call_provider("anthropic", "model", "s", "u", **options)
                self.assertEqual(caught.exception.error_type, "PROVIDER_CONFIG_ERROR")
                client.assert_not_called()

    def test_legacy_role_does_not_add_optional_call_arguments(self):
        agent = {"provider": "openrouter", "model": "legacy-model", "instructions": "x"}
        with patch.object(run, "load_agents", return_value={"planner": agent}), \
             patch.object(run, "load_instructions", return_value="system"), \
             patch.object(run, "call_provider", return_value="ok") as call:
            self.assertEqual(run.run_agent("planner", "task"), "ok")
            call.assert_called_once_with(provider="openrouter", model="legacy-model",
                                         system_prompt="system", user_prompt="task", timeout=None)

    def test_legacy_provider_uses_default_without_reasoning(self):
        with patch.object(providers, "OpenAI") as client, \
             patch.dict("os.environ", {"OPENROUTER_API_KEY": "offline-test-placeholder"}):
            client.return_value.chat.completions.create.return_value = SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])
            self.assertEqual(providers.call_provider("openrouter", "model", "s", "u", 10), "ok")
            request = client.return_value.chat.completions.create.call_args.kwargs
            self.assertEqual(request["max_tokens"], 16384)
            self.assertNotIn("extra_body", request)

    def test_bad_role_config_fails_before_instruction_read(self):
        for options in ({"max_tokens": 0}, {"reasoning": None}, {"reasoning": {"effort": "bad"}}):
            agent = {"provider": "openrouter", "model": "model", "instructions": "x", **options}
            with self.subTest(options=options), \
                 patch.object(run, "load_agents", return_value={"planner": agent}), \
                 patch.object(run, "load_instructions") as read, \
                 patch.object(run, "call_provider") as call:
                with self.assertRaises(providers.ProviderError) as caught:
                    run.run_agent("planner", "task")
                self.assertEqual(caught.exception.error_type, "PROVIDER_CONFIG_ERROR")
                read.assert_not_called()
                call.assert_not_called()

    def test_empty_length_has_numeric_usage_not_reasoning_or_response_content(self):
        response = SimpleNamespace(
            choices=[SimpleNamespace(finish_reason="length", message=SimpleNamespace(
                content="", reasoning="secret-reasoning"))],
            usage=SimpleNamespace(prompt_tokens=300, completion_tokens=4096, total_tokens=4396,
                completion_tokens_details=SimpleNamespace(reasoning_tokens=4096)))
        with patch.object(providers, "OpenAI") as client, \
             patch.dict("os.environ", {"OPENROUTER_API_KEY": "offline-test-placeholder"}):
            client.return_value.chat.completions.create.return_value = response
            with self.assertRaises(providers.ProviderError) as caught:
                providers.call_openrouter("model", "s", "u", max_tokens=4096,
                                          reasoning={"effort": "low"})
            error = caught.exception
            self.assertEqual(error.error_type, "PROVIDER_EMPTY_RESPONSE")
            self.assertEqual(error.diagnostics, {"max_tokens": 4096, "finish_reason": "length",
                "prompt_tokens": 300, "completion_tokens": 4096, "total_tokens": 4396,
                "reasoning_tokens": 4096})
            self.assertIn("4096", str(error))
            self.assertNotIn("secret-reasoning", str(error))
            client.return_value.chat.completions.create.assert_called_once()

    def test_untrusted_metadata_is_not_echoed(self):
        response = SimpleNamespace(
            choices=[SimpleNamespace(finish_reason="secret-finish", message=SimpleNamespace(content=""))],
            usage=SimpleNamespace(prompt_tokens="secret-usage", completion_tokens=True,
                total_tokens=10**100, completion_tokens_details={"reasoning_tokens": -1}))
        with patch.object(providers, "OpenAI") as client, \
             patch.dict("os.environ", {"OPENROUTER_API_KEY": "offline-test-placeholder"}):
            client.return_value.chat.completions.create.return_value = response
            with self.assertRaises(providers.ProviderError) as caught:
                providers.call_openrouter("model", "s", "u")
            self.assertEqual(caught.exception.diagnostics,
                             {"max_tokens": 16384, "finish_reason": "unknown"})
            self.assertNotIn("secret-", str(caught.exception))

    def test_no_choices_is_classified_empty(self):
        with patch.object(providers, "OpenAI") as client, \
             patch.dict("os.environ", {"OPENROUTER_API_KEY": "offline-test-placeholder"}):
            client.return_value.chat.completions.create.return_value = SimpleNamespace(choices=[])
            with self.assertRaises(providers.ProviderError) as caught:
                providers.call_openrouter("model", "s", "u")
            self.assertEqual(caught.exception.error_type, "PROVIDER_EMPTY_RESPONSE")

    def test_raw_exceptions_and_tracebacks_are_redacted_for_both_providers(self):
        import traceback
        from openai import AuthenticationError, RateLimitError, BadRequestError, APITimeoutError
        from anthropic import (AuthenticationError as AAuth, RateLimitError as ARate,
                               BadRequestError as ABad, APITimeoutError as ATimeout)
        cases = [
            ("openrouter", "OpenAI", AuthenticationError, RateLimitError, BadRequestError, APITimeoutError),
            ("anthropic", "Anthropic", AAuth, ARate, ABad, ATimeout),
        ]
        for provider, constructor, auth, rate, bad, timeout in cases:
            exceptions = [(RuntimeError("secret-body"), "PROVIDER_REQUEST_FAILED"),
                (auth("secret-body", response=MagicMock(status_code=401), body=None), "PROVIDER_AUTH_ERROR"),
                (rate("secret-body", response=MagicMock(status_code=429), body=None), "PROVIDER_RATE_LIMIT"),
                (bad("credit secret-body", response=MagicMock(status_code=400), body=None), "PROVIDER_CREDIT_ERROR"),
                (timeout(request=MagicMock()), "PROVIDER_TIMEOUT")]
            for exc, error_type in exceptions:
                with self.subTest(provider=provider, error_type=error_type), \
                     patch.object(providers, constructor) as client, \
                     patch.dict("os.environ", {"OPENROUTER_API_KEY": "offline-test-placeholder",
                                               "ANTHROPIC_API_KEY": "offline-test-placeholder"}):
                    create = (client.return_value.chat.completions.create if provider == "openrouter"
                              else client.return_value.messages.create)
                    create.side_effect = exc
                    with self.assertRaises(providers.ProviderError) as caught:
                        providers.call_provider(provider, "model", "s", "u")
                    self.assertEqual(caught.exception.error_type, error_type)
                    self.assertNotIn("secret-body", "".join(traceback.format_exception(caught.exception)))
                    create.assert_called_once()

    def test_constructor_failure_is_also_redacted(self):
        for provider, constructor in (("openrouter", "OpenAI"), ("anthropic", "Anthropic")):
            with self.subTest(provider=provider), \
                 patch.object(providers, constructor, side_effect=RuntimeError("secret-constructor")), \
                 patch.dict("os.environ", {"OPENROUTER_API_KEY": "offline-test-placeholder",
                                           "ANTHROPIC_API_KEY": "offline-test-placeholder"}):
                with self.assertRaises(providers.ProviderError) as caught:
                    providers.call_provider(provider, "model", "s", "u")
                self.assertNotIn("secret-constructor", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
