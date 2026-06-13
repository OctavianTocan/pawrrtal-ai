"""Tests for provider selection fallbacks."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

from app.providers.base import AILLM, StreamEvent
from app.providers.catalog import ModelEntry
from app.providers.model_id import Host, Vendor
from app.providers.selection import provider_or_default


class DummyLLM:
    """Tiny provider used to verify which model ID selection resolved."""

    async def stream(
        self,
        question: str,
        conversation_id: UUID,
        user_id: UUID,
        history: list[dict[str, str]] | None = None,
        tools: object | None = None,
        system_prompt: str | None = None,
        reasoning_effort: str | None = None,
        images: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        if False:
            yield {"type": "delta", "content": question}


def _entry(model_id: str, host: Host) -> ModelEntry:
    """Build the minimal catalog row selection needs for these tests."""
    _, raw_model = model_id.split(":", maxsplit=1)
    vendor, model = raw_model.split("/", maxsplit=1)
    return ModelEntry(
        host=host,
        vendor=Vendor(vendor),
        model=model,
        display_name=model,
        short_name=model,
        description=model,
    )


def test_provider_or_default_falls_back_when_host_is_unauthenticated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A saved AGY API model should not construct AGY when auth is missing."""
    requested_id = "agy-api:google/gemini-3.5-flash-low"
    fallback_id = "claude-code-pty:anthropic/claude-opus-4-7"
    resolved_ids: list[str] = []

    def fake_host_authenticated(host: Host, *, workspace_root: Path | None = None) -> bool:
        return host is not Host.agy_api

    def fake_resolve_llm(model_id: str, *, workspace_root: Path | None = None) -> AILLM:
        resolved_ids.append(model_id)
        return cast(AILLM, DummyLLM())

    monkeypatch.setattr(
        "app.providers.selection.host_authenticated",
        fake_host_authenticated,
    )
    monkeypatch.setattr(
        "app.providers.selection.first_authenticated_catalog_model",
        lambda workspace_root=None: _entry(fallback_id, Host.claude_code_pty),
    )
    monkeypatch.setattr("app.providers.selection.resolve_llm", fake_resolve_llm)

    selection = provider_or_default(requested_id, workspace_root=tmp_path)

    assert selection.effective_model_id == fallback_id
    assert selection.bad_model_id == requested_id
    assert selection.warning == "host not authenticated: agy-api"
    assert resolved_ids == [fallback_id]


def test_provider_or_default_bad_model_uses_authenticated_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Invalid IDs should use the same authenticated default path."""
    fallback_id = "claude-code-pty:anthropic/claude-opus-4-7"
    resolved_ids: list[str] = []

    def fake_resolve_llm(model_id: str, *, workspace_root: Path | None = None) -> AILLM:
        resolved_ids.append(model_id)
        return cast(AILLM, DummyLLM())

    monkeypatch.setattr(
        "app.providers.selection.first_authenticated_catalog_model",
        lambda workspace_root=None: _entry(fallback_id, Host.claude_code_pty),
    )
    monkeypatch.setattr("app.providers.selection.resolve_llm", fake_resolve_llm)

    selection = provider_or_default("not-a-model", workspace_root=tmp_path)

    assert selection.effective_model_id == fallback_id
    assert selection.bad_model_id == "not-a-model"
    assert "not a valid model ID" in str(selection.warning)
    assert resolved_ids == [fallback_id]
