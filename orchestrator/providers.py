import os
from typing import Optional

from anthropic import Anthropic, APIConnectionError, APITimeoutError, RateLimitError, AuthenticationError, BadRequestError
from openai import OpenAI, APIConnectionError as OAConnectionError, APITimeoutError as OATimeoutError, RateLimitError as OARateLimitError, AuthenticationError as OAAuthenticationError, BadRequestError as OABadRequestError
from dotenv import load_dotenv


load_dotenv()

DEFAULT_PROVIDER_TIMEOUT_SECONDS = 120.0
DEFAULT_MAX_TOKENS = 16384
# Application ceilings, not claims about any model's context window.
MAX_OUTPUT_TOKENS = 32768
MAX_REASONING_TOKENS = 16384
MIN_VISIBLE_OUTPUT_TOKENS = 1024
REASONING_EFFORTS = frozenset({"none", "minimal", "low", "medium", "high", "xhigh", "max"})
_UNSET = object()


class ProviderError(Exception):
    """Base exception for provider failures."""
    def __init__(self, message: str, error_type: str = "PROVIDER_REQUEST_FAILED", provider: str = "", model: str = "", diagnostics=None):
        super().__init__(message)
        self.error_type = error_type
        self.provider = provider
        self.model = model
        self.diagnostics = dict(diagnostics or {})


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


def validate_provider_options(provider, model, *, max_tokens=DEFAULT_MAX_TOKENS, reasoning=_UNSET):
    """Fail before client construction; return a defensive reasoning copy.

    OpenRouter accepts either effort or a numeric budget, not both. Numeric
    configuration must leave >=1024 tokens of visible-output headroom. Some
    models map budgets to effort, so neither setting guarantees a reservation.
    Model-specific support remains the provider's responsibility; never
    silently replace a model or option.
    https://openrouter.ai/docs/guides/best-practices/reasoning-tokens
    """
    def invalid(message):
        raise ProviderError(message, error_type="PROVIDER_CONFIG_ERROR", provider=provider, model=model)

    if type(max_tokens) is not int or not 1 <= max_tokens <= MAX_OUTPUT_TOKENS:
        invalid("max_tokens must be an integer between 1 and 32768.")
    if reasoning is _UNSET:
        return None
    if provider != "openrouter":
        invalid("reasoning configuration is supported only for OpenRouter.")
    if not isinstance(reasoning, dict) or set(reasoning) not in ({"effort"}, {"max_tokens"}):
        invalid("reasoning must specify exactly one of effort or max_tokens.")
    if "effort" in reasoning:
        effort = reasoning["effort"]
        if not isinstance(effort, str) or effort not in REASONING_EFFORTS:
            invalid("reasoning.effort must be a supported OpenRouter effort value.")
    else:
        budget = reasoning["max_tokens"]
        if type(budget) is not int or not 1 <= budget <= MAX_REASONING_TOKENS:
            invalid("reasoning.max_tokens must be an integer between 1 and 16384.")
        if max_tokens - budget < MIN_VISIBLE_OUTPUT_TOKENS:
            invalid("reasoning.max_tokens must leave at least 1024 tokens for visible output.")
    return dict(reasoning)


def _field(value, name, default=None):
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def _empty_response(provider, model, response, max_tokens, reason, reason_key):
    # Never stringify provider-controlled content, reasoning, IDs or errors.
    allowed = {"stop", "length", "tool_calls", "content_filter", "function_call",
               "error", "end_turn", "max_tokens", "stop_sequence", "tool_use",
               "pause_turn", "refusal", "model_context_window_exceeded"}
    safe_reason = reason if isinstance(reason, str) and reason in allowed else "unknown"
    diagnostics = {"max_tokens": max_tokens, reason_key: safe_reason}
    usage = _field(response, "usage")
    for key in ("prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens"):
        value = _field(usage, key)
        if type(value) is int and 0 <= value <= 1_000_000_000:
            diagnostics[key] = value
    value = _field(_field(usage, "completion_tokens_details"), "reasoning_tokens")
    if type(value) is int and 0 <= value <= 1_000_000_000:
        diagnostics["reasoning_tokens"] = value
    metadata = ", ".join(f"{key}={value}" for key, value in diagnostics.items())
    hint = (" Reasoning and visible output may share the budget; review this role's "
            "bounded reasoning/output settings. No automatic retry was made."
            if safe_reason in {"length", "max_tokens"} else "")
    return ProviderError(
        f"Provider returned no visible text ({metadata}).{hint}",
        error_type="PROVIDER_EMPTY_RESPONSE", provider=provider, model=model,
        diagnostics=diagnostics,
    )


def call_openrouter(
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout: Optional[float] = None,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    reasoning=_UNSET,
) -> str:
    reasoning_options = validate_provider_options("openrouter", model, max_tokens=max_tokens, reasoning=reasoning)
    extra = {"extra_body": {"reasoning": reasoning_options}} if reasoning_options is not None else {}
    api_key = os.getenv("OPENROUTER_API_KEY")

    if not api_key:
        raise ProviderAuthError("OPENROUTER_API_KEY is missing from .env", provider="openrouter", model=model)

    req_timeout = timeout if timeout is not None else get_provider_timeout()

    try:
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            timeout=req_timeout,
            max_retries=2,
        )
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
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
            **extra,
        )
        choices = _field(response, "choices") or []
        choice = choices[0] if choices else None
        content = _field(_field(choice, "message"), "content")
        if not isinstance(content, str) or not content.strip():
            raise _empty_response("openrouter", model, response, max_tokens,
                                  _field(choice, "finish_reason"), "finish_reason")
        return content
    except OATimeoutError:
        raise ProviderTimeoutError(
            f"OpenRouter request timed out after {req_timeout:.1f}s.",
            timeout_seconds=req_timeout,
            provider="openrouter",
            model=model,
        ) from None
    except OAAuthenticationError:
        raise ProviderAuthError(
            "OpenRouter authentication failed.",
            error_type="PROVIDER_AUTH_ERROR",
            provider="openrouter",
            model=model,
        ) from None
    except OARateLimitError:
        raise ProviderRateLimitError(
            "OpenRouter rate limit exceeded.",
            provider="openrouter",
            model=model,
        ) from None
    except OABadRequestError as exc:
        err_msg = str(exc)
        err_type = "PROVIDER_CREDIT_ERROR" if ("credit" in err_msg.lower() or "balance" in err_msg.lower()) else "PROVIDER_REQUEST_FAILED"
        raise ProviderAuthError("OpenRouter credit/balance error." if err_type == "PROVIDER_CREDIT_ERROR" else "OpenRouter rejected the request.", error_type=err_type, provider="openrouter", model=model) from None
    except ProviderError:
        raise
    except Exception:
        raise ProviderError("OpenRouter request failed.", provider="openrouter", model=model) from None


def call_anthropic(
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout: Optional[float] = None,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    reasoning=_UNSET,
) -> str:
    validate_provider_options("anthropic", model, max_tokens=max_tokens, reasoning=reasoning)
    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        raise ProviderAuthError("ANTHROPIC_API_KEY is missing from .env", provider="anthropic", model=model)

    req_timeout = timeout if timeout is not None else get_provider_timeout()

    try:
        client = Anthropic(
            api_key=api_key,
            timeout=req_timeout,
            max_retries=2,
        )
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": user_prompt,
                }
            ],
            timeout=req_timeout,
        )

        # Only visible text is a result, never stringify thinking/tool-use blocks.
        text_result = next((
            _field(block, "text") for block in (_field(response, "content") or [])
            if _field(block, "type") == "text" and isinstance(_field(block, "text"), str)
        ), "")
        if not text_result.strip():
            raise _empty_response("anthropic", model, response, max_tokens,
                                  _field(response, "stop_reason"), "stop_reason")
        return text_result
    except APITimeoutError:
        raise ProviderTimeoutError(
            f"Anthropic request timed out after {req_timeout:.1f}s.",
            timeout_seconds=req_timeout,
            provider="anthropic",
            model=model,
        ) from None
    except AuthenticationError:
        raise ProviderAuthError(
            "Anthropic authentication failed.",
            error_type="PROVIDER_AUTH_ERROR",
            provider="anthropic",
            model=model,
        ) from None
    except RateLimitError:
        raise ProviderRateLimitError(
            "Anthropic rate limit exceeded.",
            provider="anthropic",
            model=model,
        ) from None
    except BadRequestError as exc:
        err_msg = str(exc)
        err_type = "PROVIDER_CREDIT_ERROR" if ("credit" in err_msg.lower() or "balance" in err_msg.lower()) else "PROVIDER_REQUEST_FAILED"
        raise ProviderAuthError("Anthropic credit/balance error." if err_type == "PROVIDER_CREDIT_ERROR" else "Anthropic rejected the request.", error_type=err_type, provider="anthropic", model=model) from None
    except ProviderError:
        raise
    except Exception:
        raise ProviderError("Anthropic request failed.", provider="anthropic", model=model) from None


def call_provider(
    provider: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout: Optional[float] = None,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    reasoning=_UNSET,
) -> str:
    options = {}
    if type(max_tokens) is not int or max_tokens != DEFAULT_MAX_TOKENS:
        options["max_tokens"] = max_tokens
    if reasoning is not _UNSET:
        options["reasoning"] = reasoning

    if provider == "openrouter":
        return call_openrouter(
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout=timeout,
            **options,
        )

    if provider == "anthropic":
        return call_anthropic(
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout=timeout,
            **options,
        )

    raise ValueError(f"Unsupported provider: {provider}")

