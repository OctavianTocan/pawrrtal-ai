"""Provider model selection helpers for Paw lab commands."""

from __future__ import annotations

from typing import Any

PREFERRED_FAST_MODELS_BY_HOST: dict[str, tuple[str, ...]] = {
    "agy-api": (
        "agy-api:google/gemini-3.5-flash-extra-low",
        "agy-api:google/gemini-3.5-flash-low",
    ),
    "gemini-cli": (
        "gemini-cli:google/gemini-2.5-flash-lite",
        "gemini-cli:google/gemini-2.5-flash",
    ),
    "google-ai": (
        "google-ai:google/gemini-3.5-flash",
        "google-ai:google/gemini-3-flash-preview",
    ),
    "openai-codex": (
        "openai-codex:openai/gpt-5.4-mini",
        "openai-codex:openai/gpt-5.4",
    ),
    "opencode-go": (
        "opencode-go:deepseek/deepseek-v4-flash",
        "opencode-go:zai/glm-5.1",
    ),
}


def extract_models(payload: Any) -> list[dict[str, Any]]:
    """Extract model rows from the models endpoint envelope or legacy array."""
    models = payload.get("models") if isinstance(payload, dict) else payload
    if not isinstance(models, list):
        return []
    return [row for row in models if isinstance(row, dict)]


def select_fast_provider_models(
    models: list[dict[str, Any]],
    *,
    include_hosts: set[str],
) -> list[dict[str, Any]]:
    """Pick one fast representative model per provider host in host order."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in models:
        host = str(row.get("host") or "")
        if not host or not _model_id(row):
            continue
        if include_hosts and host not in include_hosts:
            continue
        grouped.setdefault(host, []).append(row)
    return [_preferred_host_row(host, rows) for host, rows in grouped.items()]


def _preferred_host_row(host: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the preferred model for one host, falling back to catalog order."""
    by_id = {_model_id(row): row for row in rows}
    for model_id in PREFERRED_FAST_MODELS_BY_HOST.get(host, ()):
        if model_id in by_id:
            return by_id[model_id]
    return rows[0]


def _model_id(row: dict[str, Any]) -> str:
    """Return the canonical model id from a catalog row."""
    return str(row.get("model_id") or row.get("id") or "")
