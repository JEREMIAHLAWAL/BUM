import unittest
from unittest.mock import patch, MagicMock
from openai import APITimeoutError as OATimeoutError, AuthenticationError as OAAuthenticationError
from anthropic import APITimeoutError as AnthropicTimeoutError, AuthenticationError as AnthropicAuthenticationError

from orchestrator.providers import (
    call_provider,
    call_openrouter,
    call_anthropic,
    ProviderTimeoutError,
    ProviderAuthError,
    get_provider_timeout,
    DEFAULT_PROVIDER_TIMEOUT_SECONDS,
    DEFAULT_MAX_TOKENS,
)


class TestProviderTimeoutAndErrors(unittest.TestCase):
    def test_default_timeout_configuration(self):
        self.assertEqual(get_provider_timeout(), DEFAULT_PROVIDER_TIMEOUT_SECONDS)

        with patch.dict("os.environ", {"PROVIDER_TIMEOUT_SECONDS": "45.5"}):
            self.assertEqual(get_provider_timeout(), 45.5)

        # Invalid env string gracefully falls back
        with patch.dict("os.environ", {"PROVIDER_TIMEOUT_SECONDS": "invalid_num"}):
            self.assertEqual(get_provider_timeout(), DEFAULT_PROVIDER_TIMEOUT_SECONDS)

    @patch("orchestrator.providers.OpenAI")
    def test_openrouter_success(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Planner spec response"))]
        mock_client.chat.completions.create.return_value = mock_response

        res = call_openrouter(
            model="google/gemini-2.5-flash",
            system_prompt="sys",
            user_prompt="user",
            timeout=30.0,
        )
        self.assertEqual(res, "Planner spec response")
        mock_client.chat.completions.create.assert_called_once()
        self.assertEqual(mock_client.chat.completions.create.call_args[1]["timeout"], 30.0)
        self.assertEqual(mock_client.chat.completions.create.call_args[1]["max_tokens"], DEFAULT_MAX_TOKENS)

    @patch("orchestrator.providers.OpenAI")
    def test_openrouter_timeout_caught_and_wrapped(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.side_effect = OATimeoutError("Request timed out")

        with self.assertRaises(ProviderTimeoutError) as ctx:
            call_openrouter(
                model="google/gemini-2.5-flash",
                system_prompt="sys",
                user_prompt="user",
                timeout=15.0,
            )
        self.assertEqual(ctx.exception.error_type, "PROVIDER_TIMEOUT")
        self.assertEqual(ctx.exception.timeout_seconds, 15.0)
        self.assertEqual(ctx.exception.provider, "openrouter")

    @patch("orchestrator.providers.Anthropic")
    def test_anthropic_success(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_block = MagicMock(type="text", text="VERDICT: APPROVE")
        mock_response = MagicMock(content=[mock_block])
        mock_client.messages.create.return_value = mock_response

        res = call_anthropic(
            model="claude-sonnet-5",
            system_prompt="sys",
            user_prompt="user",
            timeout=60.0,
        )
        self.assertEqual(res, "VERDICT: APPROVE")
        mock_client.messages.create.assert_called_once()
        self.assertEqual(mock_client.messages.create.call_args[1]["timeout"], 60.0)

    @patch("orchestrator.providers.Anthropic")
    def test_anthropic_timeout_caught_and_wrapped(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.side_effect = AnthropicTimeoutError(request=MagicMock())

        with self.assertRaises(ProviderTimeoutError) as ctx:
            call_anthropic(
                model="claude-sonnet-5",
                system_prompt="sys",
                user_prompt="user",
                timeout=25.0,
            )
        self.assertEqual(ctx.exception.error_type, "PROVIDER_TIMEOUT")
        self.assertEqual(ctx.exception.timeout_seconds, 25.0)
        self.assertEqual(ctx.exception.provider, "anthropic")

    @patch("orchestrator.providers.Anthropic")
    def test_anthropic_auth_and_credit_errors(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.side_effect = AnthropicAuthenticationError(
            message="Invalid API Key",
            response=MagicMock(status_code=401),
            body=None,
        )

        with self.assertRaises(ProviderAuthError) as ctx:
            call_anthropic(
                model="claude-sonnet-5",
                system_prompt="sys",
                user_prompt="user",
            )
        self.assertEqual(ctx.exception.error_type, "PROVIDER_AUTH_ERROR")


if __name__ == "__main__":
    unittest.main()
