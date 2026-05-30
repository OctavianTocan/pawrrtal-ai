"""Helper functions for the LiteLLM provider."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from litellm.exceptions import AuthenticationError as LiteLLMAuthenticationError
from litellm.exceptions import RateLimitError as LiteLLMRateLimitError
from litellm.exceptions import Timeout as LiteLLMTimeout
from litellm.exceptions import UnsupportedParamsError as LiteLLMUnsupportedParamsError

from app.agents import AgentMessage, AssistantMessage
from app.agents.types import TextContent, ToolCallContent
from app.infrastructure.config import settings
from app.infrastructure.keys import resolve_api_key

from ._errors import (
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnknownError,
    ProviderUnsupportedParamError,
)
from .model_id import Vendor

VENDOR_API_KEY_NAME: dict[Vendor, str] = {
    Vendor.openai: "OPENAI_API_KEY",
    Vendor.xai: "XAI_API_KEY",
}


def litellm_model_string(vendor: Vendor, model: str) -> str:
    """Format ``vendor`` + ``model`` for ``litellm.acompletion(model=...)``."""
    return f"{vendor.value}/{model}"


def resolve_litellm_api_key(vendor: Vendor, workspace_root: Path | None) -> str | None:
    """Resolve the API key for ``vendor`` honouring workspace overrides."""
    key_name = VENDOR_API_KEY_NAME.get(vendor)
    if key_name is None:
        return None
    if workspace_root is not None:
        return resolve_api_key(workspace_root, key_name) or None
    settings_attr = {
        Vendor.openai: "openai_api_key",
        Vendor.xai: "xai_api_key",
    }[vendor]
    value = getattr(settings, settings_attr, "") or ""
    return value or None


def _last_user_message_index(messages: list[AgentMessage]) -> int:
    return max((idx for idx, msg in enumerate(messages) if msg["role"] == "user"), default=-1)


def _image_content(text: str, images: list[dict[str, str]]) -> list[dict[str, Any]]:
    content_list: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for img in images:
        if "data" not in img:
            continue
        media_type = img.get("media_type", "image/png")
        data_uri = f"data:{media_type};base64,{img['data']}"
        content_list.append({"type": "image_url", "image_url": {"url": data_uri}})
    return content_list


def _user_message_content(
    *,
    text: str,
    idx: int,
    last_user_idx: int,
    images: list[dict[str, str]] | None,
) -> str | list[dict[str, Any]] | None:
    if idx == last_user_idx and images:
        return _image_content(text, images)
    if text.strip():
        return text
    return None


def _assistant_message_content(message: AssistantMessage) -> str | None:
    text_parts = [b["text"] for b in _assistant_text_blocks(message["content"])]
    joined = "".join(text_parts)
    return joined if joined.strip() else None


def _assistant_text_blocks(
    content: list[TextContent | ToolCallContent],
) -> list[TextContent]:
    return [block for block in content if block["type"] == "text"]


def build_litellm_messages(
    messages: list[AgentMessage],
    system_prompt: str,
    images: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Convert agent-loop messages to LiteLLM's OpenAI-shaped messages."""
    out: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    last_user_idx = _last_user_message_index(messages)

    for idx, msg in enumerate(messages):
        if msg["role"] == "user":
            content = _user_message_content(
                text=msg["content"],
                idx=idx,
                last_user_idx=last_user_idx,
                images=images,
            )
            if content is not None:
                out.append({"role": "user", "content": content})
            continue
        if msg["role"] == "assistant":
            content = _assistant_message_content(msg)
            if content is not None:
                out.append({"role": "assistant", "content": content})
            continue
    return out


def delta_text(chunk: Any) -> str:
    """Extract the streamed text fragment from one LiteLLM chunk."""
    choices = getattr(chunk, "choices", None) or []
    if not choices:
        return ""
    delta = getattr(choices[0], "delta", None)
    if delta is None:
        return ""
    content = getattr(delta, "content", None)
    return content or ""


def extract_retry_after(exc: BaseException) -> float | None:
    """Pull a ``Retry-After`` hint off a LiteLLM exception's HTTP response."""
    response = getattr(exc, "response", None)
    if response is None:
        return None
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    raw = headers.get("Retry-After") or headers.get("retry-after")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def classify_litellm_exception(exc: BaseException, *, model: str) -> ProviderError:
    """Map a LiteLLM SDK exception onto our closed ``ProviderError`` set."""
    if isinstance(exc, LiteLLMAuthenticationError):
        return ProviderAuthError(message=str(exc))
    if isinstance(exc, LiteLLMRateLimitError):
        retry_after = extract_retry_after(exc)
        return ProviderRateLimitError(message=str(exc), retry_after=retry_after)
    if isinstance(exc, LiteLLMUnsupportedParamsError):
        param = str(getattr(exc, "param", "") or "")
        return ProviderUnsupportedParamError(
            message=str(exc),
            param=param,
            model=model,
        )
    if isinstance(exc, LiteLLMTimeout):
        return ProviderTimeoutError(message=str(exc))
    return ProviderUnknownError(message=str(exc))
