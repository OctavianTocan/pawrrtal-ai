"""Shared building blocks for ``paw verify`` scenarios.

Extracted from ``codex.py`` (Task 7) when the second and third scenarios
landed and needed the same primitives — model catalog extraction, the
UUID-first conversation create call, and the SSE consumer wrapper.

Keeping this module narrow (no scenario-specific logic) means each
scenario file reads like a sequence of asserted steps rather than a
mix of plumbing and assertions.
"""

from __future__ import annotations

from typing import Any

from app.cli.paw import ids
from app.cli.paw.http import PawClient
from app.cli.paw.verify.scenarios import ScenarioResult


def extract_models(payload: Any) -> list[dict[str, Any]]:
    """Return the model list regardless of whether the API wraps it.

    The catalog endpoint has shipped both shapes (``{"models": [...]}``
    and a bare list) at various points; accept either so scenarios
    don't fail on an envelope change.
    """
    if isinstance(payload, dict):
        models = payload.get("models", [])
        return models if isinstance(models, list) else []
    if isinstance(payload, list):
        return payload
    return []


def first_model(models: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the first catalog entry (positional; the API is ordered)."""
    for m in models:
        if isinstance(m, dict):
            return m
    return None


def find_model(models: list[dict[str, Any]], model_id: str) -> dict[str, Any] | None:
    """Locate a catalog entry by ``model_id`` or legacy ``id``."""
    for m in models:
        if not isinstance(m, dict):
            continue
        if m.get("model_id") == model_id or m.get("id") == model_id:
            return m
    return None


async def resolve_model(
    client: PawClient,
    r: ScenarioResult,
    override: str | None,
    *,
    check_name: str = "model_resolved",
) -> str | None:
    """Resolve a model id from ``--model`` override or the first catalog model.

    Returns ``None`` and adds a failing ``check_name`` row when the catalog
    is empty so the caller can short-circuit cleanly.
    """
    if override is not None:
        r.add(check_name, True, detail=f"override={override}")
        return override
    catalog = (await client.request("GET", "/api/v1/models")).json()
    models = extract_models(catalog)
    first = first_model(models)
    if first is None:
        r.add(
            check_name,
            False,
            detail="catalog is empty; pass --model to override",
        )
        return None
    model_id = first.get("model_id") or first.get("id")
    r.add(check_name, bool(model_id), detail=f"default={model_id}")
    return model_id if isinstance(model_id, str) else None


async def create_conversation(
    client: PawClient,
    r: ScenarioResult,
    *,
    title: str,
    check_name: str = "conversation_created",
) -> str:
    """POST a new conversation with a client-generated UUID. Returns the id."""
    conv_id = ids.new_conversation_id()
    create_resp = await client.request(
        "POST",
        f"/api/v1/conversations/{conv_id}",
        json_body={"id": conv_id, "title": title},
        expect=(200, 201),
    )
    r.add(
        check_name,
        create_resp.status_code in (200, 201),
        detail=f"status={create_resp.status_code}",
    )
    return conv_id


async def stream_turn(
    client: PawClient,
    conv_id: str,
    text: str,
    *,
    model_id: str,
    reasoning_effort: str | None = None,
) -> list[dict[str, Any]]:
    """Drive one chat turn end-to-end; return the full event list.

    The optional ``reasoning_effort`` argument is omitted from the body
    when ``None`` so the backend falls back to the conversation row's
    stored value (matching the frontend's behaviour).
    """
    body: dict[str, Any] = {
        "question": text,
        "model_id": model_id,
        "conversation_id": conv_id,
    }
    if reasoning_effort is not None:
        body["reasoning_effort"] = reasoning_effort
    return [
        ev
        async for ev in client.stream_events(
            method="POST",
            url="/api/v1/chat/",
            json_body=body,
        )
    ]


async def cleanup_conversation(client: PawClient, r: ScenarioResult, conv_id: str) -> None:
    """Delete a conversation and record a ``conversation_cleanup`` check."""
    await client.request(
        "DELETE",
        f"/api/v1/conversations/{conv_id}",
        expect=(200, 204),
    )
    r.add("conversation_cleanup", True)
