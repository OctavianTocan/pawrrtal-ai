"""API tests for ``/api/v1/completions/autocomplete``.

Tests exercise the real FastAPI router via ``ASGITransport`` and stub
the provider at the ``resolve_llm`` seam — the same pattern as
``test_chat_api.py``. The endpoint only forwards to the provider and
returns its accumulated text, so a ``FakeProvider`` yielding scripted
``StreamEvent`` dicts gives full coverage without touching Gemini.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient

from app.chat.completions.router import AUTOCOMPLETE_TIMEOUT_SECONDS, MAX_SUGGESTION_CHARS


class FakeProvider:
    """Provider test double that yields configured stream events.

    Mirrors the shape used by ``test_chat_api.FakeProvider`` so both
    suites stay legible at a glance.
    """

    def __init__(self, events: list[dict[str, str]]) -> None:
        self.events = events
        self.last_kwargs: dict[str, object] = {}

    async def stream(
        self,
        question: str,
        conversation_id: object,
        user_id: object,
        history: object = None,
        tools: object = None,
        system_prompt: object = None,
        reasoning_effort: object = None,
        permission_check: object = None,
        images: object = None,
    ) -> AsyncIterator[dict[str, str]]:
        self.last_kwargs = {
            "question": question,
            "conversation_id": conversation_id,
            "user_id": user_id,
            "history": history,
            "tools": tools,
            "system_prompt": system_prompt,
            "reasoning_effort": reasoning_effort,
            "permission_check": permission_check,
            "images": images,
        }
        for event in self.events:
            yield event


def _install_provider(monkeypatch: pytest.MonkeyPatch, provider: FakeProvider) -> None:
    """Patch ``resolve_llm`` so the router resolves to ``provider``."""
    monkeypatch.setattr(
        "app.chat.completions.router.resolve_llm",
        lambda _model_id, **_kwargs: provider,
    )


@pytest.mark.anyio
async def test_autocomplete_returns_concatenated_delta_text(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delta events are accumulated into the ``suggestion`` field."""
    _install_provider(
        monkeypatch,
        FakeProvider(
            [
                {"type": "delta", "content": "the world"},
                {"type": "delta", "content": "?"},
            ]
        ),
    )

    response = await client.post(
        "/api/v1/completions/autocomplete",
        json={"text": "hello "},
    )

    assert response.status_code == 200
    assert response.json() == {"suggestion": "the world?"}


@pytest.mark.anyio
async def test_autocomplete_ignores_non_delta_events(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only ``delta`` events contribute to the assembled suggestion."""
    _install_provider(
        monkeypatch,
        FakeProvider(
            [
                {"type": "usage", "content": "ignored"},
                {"type": "delta", "content": "real"},
                {"type": "thinking", "content": "ignored"},
                {"type": "delta", "content": " words"},
            ]
        ),
    )

    response = await client.post(
        "/api/v1/completions/autocomplete",
        json={"text": "hello"},
    )

    assert response.status_code == 200
    assert response.json() == {"suggestion": "real words"}


@pytest.mark.anyio
async def test_autocomplete_strips_quotes_and_whitespace(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Model-emitted quoting and surrounding whitespace are stripped."""
    _install_provider(
        monkeypatch,
        FakeProvider([{"type": "delta", "content": '  "world!"  '}]),
    )

    response = await client.post(
        "/api/v1/completions/autocomplete",
        json={"text": "hello"},
    )

    assert response.json() == {"suggestion": "world!"}


@pytest.mark.anyio
async def test_autocomplete_truncates_long_suggestions(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Suggestions longer than ``MAX_SUGGESTION_CHARS`` are truncated."""
    long_continuation = "x" * (MAX_SUGGESTION_CHARS * 3)
    _install_provider(
        monkeypatch,
        FakeProvider([{"type": "delta", "content": long_continuation}]),
    )

    response = await client.post(
        "/api/v1/completions/autocomplete",
        json={"text": "hello"},
    )

    assert response.status_code == 200
    assert len(response.json()["suggestion"]) == MAX_SUGGESTION_CHARS


@pytest.mark.anyio
async def test_autocomplete_skips_provider_for_short_prefix(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prefixes below ``MIN_PREFIX_CHARS`` never reach the provider."""
    called = False

    def _explode(*_args: object, **_kwargs: object) -> FakeProvider:
        nonlocal called
        called = True
        return FakeProvider([{"type": "delta", "content": "nope"}])

    monkeypatch.setattr("app.chat.completions.router.resolve_llm", _explode)

    response = await client.post(
        "/api/v1/completions/autocomplete",
        json={"text": "hi"},
    )

    assert response.status_code == 200
    assert response.json() == {"suggestion": ""}
    assert called is False


@pytest.mark.anyio
async def test_autocomplete_forwards_system_prompt_and_reasoning_effort(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The provider receives the autocomplete system prompt and ``minimal`` reasoning."""
    provider = FakeProvider([{"type": "delta", "content": "ok"}])
    _install_provider(monkeypatch, provider)

    await client.post(
        "/api/v1/completions/autocomplete",
        json={"text": "hello there"},
    )

    assert provider.last_kwargs["reasoning_effort"] == "minimal"
    assert provider.last_kwargs["history"] is None
    assert provider.last_kwargs["tools"] is None
    system_prompt = provider.last_kwargs["system_prompt"]
    assert isinstance(system_prompt, str)
    assert "autocomplete" in system_prompt.lower()


@pytest.mark.anyio
async def test_autocomplete_returns_empty_on_timeout(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider that streams too slowly collapses to an empty suggestion."""

    class HangingProvider:
        async def stream(
            self,
            question: str,
            conversation_id: object,
            user_id: object,
            history: object = None,
            tools: object = None,
            system_prompt: object = None,
            reasoning_effort: object = None,
            permission_check: object = None,
            images: object = None,
        ) -> AsyncIterator[dict[str, str]]:
            # Sleep well past the timeout so ``asyncio.wait_for`` fires.
            await asyncio.sleep(AUTOCOMPLETE_TIMEOUT_SECONDS * 2)
            yield {"type": "delta", "content": "too late"}

    monkeypatch.setattr(
        "app.chat.completions.router.resolve_llm",
        lambda _model_id, **_kwargs: HangingProvider(),
    )
    # Shrink the timeout for the test so we don't actually wait 4s.
    monkeypatch.setattr("app.chat.completions.router.AUTOCOMPLETE_TIMEOUT_SECONDS", 0.05)

    response = await client.post(
        "/api/v1/completions/autocomplete",
        json={"text": "hello world"},
    )

    assert response.status_code == 200
    assert response.json() == {"suggestion": ""}


@pytest.mark.anyio
async def test_autocomplete_rejects_oversize_payload(client: AsyncClient) -> None:
    """Pydantic enforces ``MAX_PREFIX_CHARS`` and returns 422."""
    response = await client.post(
        "/api/v1/completions/autocomplete",
        json={"text": "x" * 10_000},
    )

    assert response.status_code == 422
