"""LiteLLM provider — text-only StreamFn adapter for the agent loop.

LiteLLM (https://docs.litellm.ai/) is a Python SDK that exposes a
single OpenAI-compatible call surface (``litellm.acompletion``) over
every major LLM provider.  We use the in-process SDK rather than the
separate LiteLLM proxy server so this provider drops cleanly into the
existing ``AILLM`` seam without standing up a sidecar service.  The
proxy can be added later by swapping ``api_base`` to point at a
``litellm --config`` deployment; the call shape is identical.

This v1 is intentionally **text-only**: ``tools=`` is accepted for
``AILLM`` protocol parity but ignored with a debug log.  The
function-calling bridge (AgentTool → OpenAI ``tools`` schema → tool
result roundtrip) will land in a follow-up alongside the OpenAI tool-
flow tests.  Until then, LiteLLM-routed models cannot run workspace
tools — pick Claude or Gemini for tool-driven flows.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import litellm
import openai
from litellm.exceptions import (
    APIError as LiteLLMAPIError,
)
from litellm.exceptions import (
    AuthenticationError as LiteLLMAuthenticationError,
)
from litellm.exceptions import (
    RateLimitError as LiteLLMRateLimitError,
)
from litellm.exceptions import (
    Timeout as LiteLLMTimeout,
)
from litellm.exceptions import (
    UnsupportedParamsError as LiteLLMUnsupportedParamsError,
)

from app.agents import (
    DEFAULT_AGENT_SYSTEM_PROMPT as _FALLBACK_SYSTEM_PROMPT,
)
from app.agents import (
    AgentContext,
    AgentLoopConfig,
    AgentMessage,
    AgentTool,
    AssistantMessage,
    LLMDoneEvent,
    LLMEvent,
    LLMTextDeltaEvent,
    StreamFn,
    UserMessage,
    agent_loop,
)
from app.agents.safety_factory import safety_from_settings
from app.agents.types import PermissionCheckFn, TextContent
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
from ._stream_logging import log_provider_stream_event
from .base import ReasoningEffort, StreamEvent
from .gemini.events import agent_event_to_stream_event, identity_convert
from .model_id import Vendor

if TYPE_CHECKING:
    from app.agents.types import ToolCallContent

logger = logging.getLogger(__name__)


# Workspace-facing env-var name per vendor.  ``resolve_api_key`` reads
# the encrypted per-workspace ``.env`` first and falls back to the
# matching ``Settings`` attribute (see ``app/core/keys.py``).
_VENDOR_API_KEY_NAME: dict[Vendor, str] = {
    Vendor.openai: "OPENAI_API_KEY",
    Vendor.xai: "XAI_API_KEY",
}


def _litellm_model_string(vendor: Vendor, model: str) -> str:
    """Format ``vendor`` + ``model`` for ``litellm.acompletion(model=...)``.

    LiteLLM dispatches by the ``<provider>/<model>`` prefix; the
    provider strings happen to match our ``Vendor`` enum values for
    every vendor we support today.  When a future vendor diverges
    (e.g. ``mistral`` → ``mistral_chat``) add a per-vendor override
    table rather than reaching for ``str.replace``.
    """
    return f"{vendor.value}/{model}"


def _resolve_litellm_api_key(vendor: Vendor, workspace_root: Path | None) -> str | None:
    """Resolve the API key for ``vendor`` honouring workspace overrides."""
    key_name = _VENDOR_API_KEY_NAME.get(vendor)
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


def _build_litellm_messages(
    messages: list[AgentMessage],
    system_prompt: str,
    images: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Convert agent-loop messages to LiteLLM's OpenAI-shaped messages.

    PR 09: when ``images`` is supplied, the last user message becomes a
    multimodal content list (images first, then the text question)
    matching OpenAI's shape.
    """
    out: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    last_user_idx = -1
    for idx, msg in enumerate(messages):
        if msg["role"] == "user":
            last_user_idx = idx

    for idx, msg in enumerate(messages):
        if msg["role"] == "user":
            text = msg["content"]
            if idx == last_user_idx and images:
                content_list: list[dict[str, Any]] = [{"type": "text", "text": text}]
                for img in images:
                    if "data" in img:
                        media_type = img.get("media_type", "image/png")
                        data_uri = f"data:{media_type};base64,{img['data']}"
                        content_list.append({"type": "image_url", "image_url": {"url": data_uri}})
                out.append({"role": "user", "content": content_list})
            elif text.strip():
                out.append({"role": "user", "content": text})
            continue
        if msg["role"] == "assistant":
            text_parts = [b["text"] for b in msg["content"] if b["type"] == "text"]
            joined = "".join(text_parts)
            if joined.strip():
                out.append({"role": "assistant", "content": joined})
            continue
        # ``toolResult`` messages are dropped silently in v1 — no
        # roundtrip is possible without the tool-call message that
        # produced them.  Once tools land, emit the matching
        # ``{"role": "tool", "tool_call_id": ..., "content": ...}``
        # shape here.
    return out


def _delta_text(chunk: Any) -> str:
    """Extract the streamed text fragment from one LiteLLM chunk.

    LiteLLM normalises every provider's chunk into the OpenAI shape:
    ``chunk.choices[0].delta.content`` is the new text (or ``None``
    on chunks that only carry tool calls / finish_reason / usage).
    """
    choices = getattr(chunk, "choices", None) or []
    if not choices:
        return ""
    delta = getattr(choices[0], "delta", None)
    if delta is None:
        return ""
    content = getattr(delta, "content", None)
    return content or ""


# Map Pawrrtal's five-level ``ReasoningEffort`` literal onto OpenAI's
# six-level ``reasoning_effort`` enum (``none | minimal | low | medium |
# high | xhigh``).  ``minimal`` is OpenAI's lightest tier (low-latency
# chat / high throughput) and ``extra-high`` lifts to OpenAI's
# ``xhigh`` so a user who picked the heaviest level on a Claude turn
# keeps getting the heaviest available level after switching to a
# GPT-5-class model. Sourced from
# ``openai/types/shared/reasoning_effort.py`` in the official Python
# SDK — see https://github.com/openai/openai-python.
_LITELLM_REASONING_EFFORT: dict[str, str] = {
    "minimal": "minimal",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "extra-high": "xhigh",
}


# ---------------------------------------------------------------------------
# Provider seam.
#
# ``open_litellm_stream`` exposes the *connection* phase of a LiteLLM
# completion. It returns the raw chunk async-iterator when LiteLLM
# accepts the request, or raises one of the closed-set ``ProviderError``
# variants (auth / rate-limit / unsupported-param / timeout / unknown)
# when the connection / setup phase fails. Errors raised *inside* the
# iterator after a successful open continue to surface as the SDK
# raises them — the chat router classifies those into
# ``StreamEvent(type="error")`` frames.
#
# This is *additive*. Production today routes through
# :class:`LiteLLMLLM` → :func:`make_litellm_stream_fn` and is
# unchanged; no production caller invokes ``open_litellm_stream`` yet,
# but the test suite (``tests/test_litellm_provider.py``) pins the
# closed-set classifier behaviour so a future migration has the seam
# already covered.
# ---------------------------------------------------------------------------


def _extract_retry_after(exc: BaseException) -> float | None:
    """Pull a ``Retry-After`` hint off a LiteLLM exception's HTTP response.

    LiteLLM does not promote the header onto the exception itself —
    callers have to read ``exc.response.headers`` (see
    ``vendor/litellm/.../exceptions.py``). The header may be missing,
    non-numeric (HTTP date), or absent entirely; in any of those
    cases we return ``None`` so the caller can apply its own backoff.
    """
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


def _classify_litellm_exception(exc: BaseException, *, model: str) -> ProviderError:
    """Map a LiteLLM SDK exception onto our closed ``ProviderError`` set.

    The mapping order matters — ``UnsupportedParamsError`` is a
    subclass of ``BadRequestError`` which is itself a subclass of the
    generic ``APIError``, so the narrowest variants are matched first.
    Unrecognised exceptions fall into :class:`ProviderUnknownError`
    carrying the original message verbatim so on-call still has
    something to grep for.
    """
    if isinstance(exc, LiteLLMAuthenticationError):
        return ProviderAuthError(message=str(exc))
    if isinstance(exc, LiteLLMRateLimitError):
        # LiteLLM's ``RateLimitError.__init__`` does not set a
        # ``retry_after`` attribute; the actual hint is on the upstream
        # HTTP response's ``Retry-After`` header (see
        # ``litellm/exceptions.py``). Parse from there, falling back
        # gracefully when the response / header is missing or the
        # value is malformed.
        retry_after = _extract_retry_after(exc)
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


async def open_litellm_stream(
    vendor: Vendor,
    model: str,
    workspace_root: Path | None = None,
    *,
    messages: list[dict[str, Any]],
    reasoning_effort: ReasoningEffort | None = None,
) -> AsyncIterator[Any]:
    """Open a LiteLLM streaming completion.

    Returns the raw chunk async-iterator when LiteLLM accepts the
    request. Raises one of the closed-set ``ProviderError`` variants
    (auth / rate-limit / unsupported-param / timeout / unknown) when
    the connection / setup phase fails. Mid-stream errors after a
    successful open continue to surface as the SDK raises them.

    Args:
        vendor: The model's vendor enum.
        model: Bare model name (no provider prefix).
        workspace_root: Optional workspace path for per-workspace key
            overrides; mirrors the rest of the LiteLLM seam.
        messages: Pre-assembled OpenAI-shape message list. The caller
            (or :func:`_build_litellm_messages`) is responsible for
            multimodal flattening.
        reasoning_effort: Optional reasoning knob mapped through
            :data:`_LITELLM_REASONING_EFFORT`.

    Raises:
        ProviderError: One of the closed-set variants on connection /
            setup failure (see ``_classify_litellm_exception``).

    Returns:
        ``AsyncIterator[Any]`` yielding raw LiteLLM chunks. Use
        :func:`_delta_text` to extract text fragments.
    """
    model_string = _litellm_model_string(vendor, model)

    async def _open() -> AsyncIterator[Any]:
        """Resolve the API key, build kwargs, and call ``acompletion``."""
        api_key = _resolve_litellm_api_key(vendor, workspace_root)
        if not api_key:
            # Translate "missing key" into an auth error so the caller
            # can match a single ProviderAuthError variant regardless
            # of whether the upstream or our key resolution rejected.
            # Vendors that aren't in ``_VENDOR_API_KEY_NAME`` still need
            # a readable hint — fall back to the vendor's enum value
            # so we never blow up with a raw ``KeyError`` here.
            key_label = _VENDOR_API_KEY_NAME.get(vendor, vendor.value)
            raise LiteLLMAuthenticationError(
                message=(
                    f"missing {key_label} — set it in the workspace env or as a gateway env var."
                ),
                llm_provider=vendor.value,
                model=model_string,
            )

        completion_kwargs: dict[str, object] = {
            "model": model_string,
            "messages": messages,
            "api_key": api_key,
            "stream": True,
        }
        if reasoning_effort is not None:
            mapped = _LITELLM_REASONING_EFFORT.get(reasoning_effort)
            if mapped is not None:
                completion_kwargs["reasoning_effort"] = mapped

        response = await litellm.acompletion(**completion_kwargs)
        # ``litellm.acompletion(stream=True)`` returns an
        # ``AsyncIterator`` over chunks. Cast away the SDK's loose typing
        # at the seam — this is the documented streaming contract.
        return response  # type: ignore[no-any-return]

    try:
        return await _open()
    except (
        LiteLLMAuthenticationError,
        LiteLLMRateLimitError,
        LiteLLMUnsupportedParamsError,
        LiteLLMTimeout,
        LiteLLMAPIError,
        # LiteLLM's HTTP-error subclasses (``BadRequestError``,
        # ``APIConnectionError``, ``InternalServerError``,
        # ``ServiceUnavailableError``, ``NotFoundError``,
        # ``PermissionDeniedError``, ``ContextWindowExceededError``)
        # inherit from ``openai.APIError`` — NOT
        # ``litellm.exceptions.APIError`` — so without this branch
        # they would escape the classifier and propagate raw out
        # of the function. ``openai.APIError`` is the upstream common
        # base.
        openai.APIError,
        # Defensive: a missing entry in ``_VENDOR_API_KEY_NAME`` or
        # any other dict-keyed lookup inside ``_open`` should never
        # crash out unclassified — collapse to ``ProviderUnknownError``.
        KeyError,
    ) as exc:
        raise _classify_litellm_exception(exc, model=model_string) from exc


def make_litellm_stream_fn(
    vendor: Vendor,
    model: str,
    workspace_root: Path | None = None,
    *,
    system_prompt: str,
    reasoning_effort: ReasoningEffort | None = None,
    images: list[dict[str, str]] | None = None,
) -> StreamFn:
    """Build a StreamFn backed by ``litellm.acompletion``.

    Args:
        vendor: The model's vendor enum (used to pick the API-key
            workspace name and to format LiteLLM's ``provider/model``
            string).
        model: Bare model name (no provider prefix), e.g. ``"gpt-4o"``.
        workspace_root: Absolute path from the ``workspaces.path`` DB
            column for per-workspace key overrides.  Optional, matching
            the other providers.
            overrides.  ``None`` falls back to gateway-global settings.
        system_prompt: The system prompt captured into the returned
            closure.  Mirrors :func:`make_gemini_stream_fn`'s contract
            so the chat router can assemble the workspace prompt and
            bind it per request.

        reasoning_effort: Per-turn reasoning knob (already resolved
            against the model's catalog support tuple). ``None`` lets
            the model use its default; otherwise the mapped OpenAI
            ``reasoning_effort`` value (per
            :data:`_LITELLM_REASONING_EFFORT`) rides on the
            ``litellm.acompletion`` kwargs.
        images: Optional list of base64 multimodal image inputs.

    Returns:
        An async generator factory the agent loop can call.  When a
        non-empty ``tools`` list is passed, the call still runs but
        tools are logged-and-ignored — see the v1 scope note in the
        module docstring.
    """
    model_string = _litellm_model_string(vendor, model)

    async def stream_fn(
        messages: list[AgentMessage],
        tools: list[AgentTool],
    ) -> AsyncIterator[LLMEvent]:
        if tools:
            logger.debug(
                "LITELLM_TOOLS_IGNORED model=%s count=%d (text-only v1)",
                model_string,
                len(tools),
            )

        api_key = _resolve_litellm_api_key(vendor, workspace_root)
        if not api_key:
            # ``_VENDOR_API_KEY_NAME`` is keyed by the providers we
            # actively support — fall back to the vendor enum value so
            # the user-facing error never trips on a ``KeyError`` for
            # a not-yet-mapped vendor.
            key_label = _VENDOR_API_KEY_NAME.get(vendor, vendor.value)
            error_text = (
                f"LiteLLM error: missing {key_label} — "
                "set it in the workspace env or as a gateway env var."
            )
            yield LLMTextDeltaEvent(type="text_delta", text=error_text)
            yield LLMDoneEvent(
                type="done",
                stop_reason="error",
                content=[TextContent(type="text", text=error_text)],
            )
            return

        litellm_messages = _build_litellm_messages(messages, system_prompt, images=images)

        # Forward Pawrrtal's reasoning knob to OpenAI's
        # ``reasoning_effort`` parameter via LiteLLM. Set only when the
        # caller supplied a value AND the mapping exists — so non-
        # reasoning models that LiteLLM routes (gpt-4o, gpt-4.1) keep
        # their behaviour unchanged even if a stale stored value
        # lingers (the chat-router resolver should have cleared it
        # already, but this is a defensive belt-and-braces).
        completion_kwargs: dict[str, object] = {
            "model": model_string,
            "messages": litellm_messages,
            "api_key": api_key,
            "stream": True,
        }
        if reasoning_effort is not None:
            mapped = _LITELLM_REASONING_EFFORT.get(reasoning_effort)
            if mapped is not None:
                completion_kwargs["reasoning_effort"] = mapped

        full_text = ""
        try:
            response = await litellm.acompletion(**completion_kwargs)
            async for chunk in response:
                text = _delta_text(chunk)
                if text:
                    yield LLMTextDeltaEvent(type="text_delta", text=text)
                    full_text += text

        except LiteLLMAPIError as exc:
            logger.error(
                "LiteLLM streaming error model=%s: %s",
                model_string,
                exc,
                exc_info=True,
            )
            error_text = f"LiteLLM error: {exc}"
            yield LLMTextDeltaEvent(type="text_delta", text=error_text)
            yield LLMDoneEvent(
                type="done",
                stop_reason="error",
                content=[TextContent(type="text", text=error_text)],
            )
            return

        content: list[TextContent | ToolCallContent] = []
        if full_text:
            content.append(TextContent(type="text", text=full_text))
        yield LLMDoneEvent(type="done", stop_reason="stop", content=content)

    return stream_fn


class LiteLLMLLM:
    """AILLM backed by the agent_loop + a LiteLLM StreamFn.

    Text-only v1: ``tools`` is accepted for protocol parity but the
    underlying StreamFn ignores them.  See module docstring.
    """

    def __init__(
        self,
        model: str,
        vendor: Vendor,
        *,
        workspace_root: Path | None = None,
    ) -> None:
        """Construct a LiteLLM provider.

        Args:
            model: Bare model name (no provider prefix), e.g. ``"gpt-4o"``.
            vendor: The model's vendor enum — picks the API-key
                workspace name and the LiteLLM provider prefix.
            workspace_root: Absolute path from the ``workspaces.path`` DB
                column for per-workspace key overrides.  Optional, matching
                the other providers.
        """
        self._model = model
        self._vendor = vendor
        self._workspace_root = workspace_root
        # Tests monkeypatch this attribute to inject a
        # ``ScriptedStreamFn``; production sets it per-request inside
        # ``stream()`` so the captured system prompt matches the
        # request the chat router assembled.  Mirrors GeminiLLM —
        # see ``.claude/rules/testing/agent-loop-testing-philosophy.md``.
        self._stream_fn: StreamFn | None = None

    async def stream(
        self,
        question: str,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        history: list[dict[str, str]] | None = None,
        tools: list[AgentTool] | None = None,
        system_prompt: str | None = None,
        reasoning_effort: ReasoningEffort | None = None,
        permission_check: PermissionCheckFn | None = None,
        images: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Run the agent loop and translate AgentEvents → StreamEvents.

        Args:
            question: Current user message.
            conversation_id: Used for logging; not persisted here.
            user_id: Authenticated user UUID (used for logging).
            history: Prior messages oldest-first as ``{role, content}``
                dicts.
            tools: Accepted for ``AILLM`` parity; ignored in v1 (the
                StreamFn logs a debug line and drops them).
            system_prompt: System prompt for this turn.  Falls back
                to ``_FALLBACK_SYSTEM_PROMPT`` for bare unit-test
                callers.
            reasoning_effort: Per-turn reasoning knob. Forwarded as
                ``reasoning_effort`` on the ``litellm.acompletion`` call
                via :data:`_LITELLM_REASONING_EFFORT` (Pawrrtal's four
                levels mapped onto OpenAI's six-level enum, with
                ``extra-high`` → ``xhigh``).  Non-reasoning models
                ignore the kwarg.
            permission_check: Forwarded to the loop's
                ``AgentLoopConfig``.  Inert in v1 because no tools fire.
            images: Multimodal inputs.  Accepted for protocol parity
                and ignored; the LiteLLM image flow lands with the tool
                bridge.
        """
        prior: list[AgentMessage] = []
        for m in history or []:
            role = m.get("role")
            content = m.get("content", "")
            if role == "user":
                prior.append(UserMessage(role="user", content=content))
            elif role == "assistant":
                prior.append(
                    AssistantMessage(
                        role="assistant",
                        content=[TextContent(type="text", text=content)],
                        stop_reason="stop",
                    )
                )

        context = AgentContext(
            system_prompt=system_prompt or _FALLBACK_SYSTEM_PROMPT,
            messages=prior,
            tools=list(tools or []),
        )
        prompt = UserMessage(role="user", content=question)
        config = AgentLoopConfig(
            convert_to_llm=identity_convert,
            safety=safety_from_settings(settings),
            permission_check=permission_check,
        )

        stream_fn = self._stream_fn or make_litellm_stream_fn(
            self._vendor,
            self._model,
            self._workspace_root,
            system_prompt=context.system_prompt,
            reasoning_effort=reasoning_effort,
            images=images,
        )

        try:
            async for event in agent_loop([prompt], context, config, stream_fn):
                stream_event = agent_event_to_stream_event(event)
                if stream_event is not None:
                    log_provider_stream_event(
                        logger,
                        provider="LITELLM",
                        model=f"{self._vendor.value}/{self._model}",
                        conversation_id=conversation_id,
                        event=stream_event,
                    )
                    yield stream_event

        except Exception as exc:
            logger.error(
                "LiteLLM agent-loop error model=%s/%s: %s",
                self._vendor.value,
                self._model,
                exc,
                exc_info=True,
            )
            stream_event = StreamEvent(type="error", content=f"LiteLLM provider error: {exc}")
            log_provider_stream_event(
                logger,
                provider="LITELLM",
                model=f"{self._vendor.value}/{self._model}",
                conversation_id=conversation_id,
                event=stream_event,
            )
            yield stream_event
