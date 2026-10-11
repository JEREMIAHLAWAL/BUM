import os
from typing import Optional

from anthropic import Anthropic, APIConnectionError, APITimeoutError, RateLimitError, AuthenticationError, BadRequestError
from openai import OpenAI, APIConnectionError as OAConnectionError, APITimeoutError as OATimeoutError, RateLimitError as OARateLimitError, AuthenticationError as OAAuthenticationError, BadRequestError as OABadRequestError
from dotenv import load_dotenv


load_dotenv()

DEFAULT_PROVIDER_TIMEOUT_SECONDS = 120.0
DEFAULT_MAX_TOKENS = 16384


class ProviderError(Exception):
    """Base exception for provider failures."""
    def __init__(self, message: str, error_type: str = "PROVIDER_REQUEST_FAILED", provider: str = "", model: str = ""):
        super().__init__(message)
        self.error_type = error_type
        self.provider = provider
        self.model = model


class ProviderTimeoutError(ProviderError):
    """Raised when an LLM provider call exceeds the bounded timeout."""
    def __init__(self, message: str, timeout_seconds: float, provider: str = "", model: str = ""):
        super().__init__(message, error_type="PROVIDER_TIMEOUT", provider=provider, model=model)
        self.timeout_seconds = timeout_seconds


class ProviderAuthError(ProviderError):
    """Raised on authentication or credit balance errors."""
    def __init__(self, message: str, error_type: str = "PROVIDER_AUTH_ERROR", provider: str = "", model: str = ""):
        super().__init__(message, error_type=error_type, provider=provider, model=model)


class ProviderRateLimitError(ProviderError):
    """Raised on provider rate limit."""
    def __init__(self, message: str, provider: str = "", model: str = ""):
        super().__init__(message, error_type="PROVIDER_RATE_LIMIT", provider=provider, model=model)


def get_provider_timeout() -> float:
    """Retrieve configured provider timeout from environment or default (120s)."""
    raw = os.getenv("PROVIDER_TIMEOUT_SECONDS")
    if raw:
        try:
            val = float(raw)
            if val > 0:
                return val
        except ValueError:
            pass
    return DEFAULT_PROVIDER_TIMEOUT_SECONDS


def call_openrouter(
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout: Optional[float] = None,
) -> str:
    api_key = os.getenv("OPENROUTER_API_KEY")

    if not api_key:
        raise ProviderAuthError("OPENROUTER_API_KEY is missing from .env", provider="openrouter", model=model)

    req_timeout = timeout if timeout is not None else get_provider_timeout()

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        timeout=req_timeout,
        max_retries=2,
    )

    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=DEFAULT_MAX_TOKENS,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            timeout=req_timeout,
        )
        content = response.choices[0].message.content
        if not content or not content.strip():
            finish_reason = getattr(response.choices[0], "finish_reason", "unknown")
            hint = (
                " This means the model hit the max_tokens output limit before producing any "
                "visible text (DEFAULT_MAX_TOKENS may need raising for this role)."
                if finish_reason == "length"
                else ""
            )
            raise ProviderError(
                f"OpenRouter returned empty content (finish_reason={finish_reason}).{hint} "
                "The model may have returned only a tool-call/refusal with no text content.",
                error_type="PROVIDER_EMPTY_RESPONSE",
                provider="openrouter",
                model=model,
            )
        return content
    except OATimeoutError as exc:
        raise ProviderTimeoutError(
            f"OpenRouter request timed out after {req_timeout:.1f}s: {exc}",
            timeout_seconds=req_timeout,
            provider="openrouter",
            model=model,
        ) from exc
    except OAAuthenticationError as exc:
        raise ProviderAuthError(
            f"OpenRouter authentication failed: {exc}",
            error_type="PROVIDER_AUTH_ERROR",
            provider="openrouter",
            model=model,
        ) from exc
    except OARateLimitError as exc:
        raise ProviderRateLimitError(
            f"OpenRouter rate limit exceeded: {exc}",
            provider="openrouter",
            model=model,
        ) from exc
    except OABadRequestError as exc:
        err_msg = str(exc)
        err_type = "PROVIDER_CREDIT_ERROR" if ("credit" in err_msg.lower() or "balance" in err_msg.lower()) else "PROVIDER_REQUEST_FAILED"
        raise ProviderAuthError(err_msg, error_type=err_type, provider="openrouter", model=model) from exc
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderError(f"OpenRouter request failed: {exc}", provider="openrouter", model=model) from exc


def call_anthropic(
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout: Optional[float] = None,
) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        raise ProviderAuthError("ANTHROPIC_API_KEY is missing from .env", provider="anthropic", model=model)

    req_timeout = timeout if timeout is not None else get_provider_timeout()

    client = Anthropic(
        api_key=api_key,
        timeout=req_timeout,
        max_retries=2,
    )

    try:
        response = client.messages.create(
            model=model,
            max_tokens=DEFAULT_MAX_TOKENS,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": user_prompt,
                }
            ],
            timeout=req_timeout,
        )

        text_result = None
        for block in response.content:
            if getattr(block, "type", None) == "text":
                text_result = getattr(block, "text", "")
                break

        if text_result is None:
            for block in response.content:
                if hasattr(block, "text"):
                    text_result = block.text
                    break

        if text_result is None and response.content:
            text_result = str(response.content[0])

        if not text_result or not text_result.strip():
            stop_reason = getattr(response, "stop_reason", "unknown")
            raise ProviderError(
                f"Anthropic returned empty content (stop_reason={stop_reason}). "
                "The model may have returned only a tool-call/refusal with no text content.",
                error_type="PROVIDER_EMPTY_RESPONSE",
                provider="anthropic",
                model=model,
            )
        return text_result
    except APITimeoutError as exc:
        raise ProviderTimeoutError(
            f"Anthropic request timed out after {req_timeout:.1f}s: {exc}",
            timeout_seconds=req_timeout,
            provider="anthropic",
            model=model,
        ) from exc
    except AuthenticationError as exc:
        raise ProviderAuthError(
            f"Anthropic authentication failed: {exc}",
            error_type="PROVIDER_AUTH_ERROR",
            provider="anthropic",
            model=model,
        ) from exc
    except RateLimitError as exc:
        raise ProviderRateLimitError(
            f"Anthropic rate limit exceeded: {exc}",
            provider="anthropic",
            model=model,
        ) from exc
    except BadRequestError as exc:
        err_msg = str(exc)
        err_type = "PROVIDER_CREDIT_ERROR" if ("credit" in err_msg.lower() or "balance" in err_msg.lower()) else "PROVIDER_REQUEST_FAILED"
        raise ProviderAuthError(err_msg, error_type=err_type, provider="anthropic", model=model) from exc
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderError(f"Anthropic request failed: {exc}", provider="anthropic", model=model) from exc


def call_provider(
    provider: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout: Optional[float] = None,
) -> str:

    if provider == "openrouter":
        return call_openrouter(
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout=timeout,
        )

    if provider == "anthropic":
        return call_anthropic(
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout=timeout,
        )

    raise ValueError(f"Unsupported provider: {provider}")

