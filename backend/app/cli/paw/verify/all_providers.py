"""All-provider verification scenario."""

from __future__ import annotations

import re
from typing import Any

from app.cli.paw.config import PersonaState
from app.cli.paw.http import PawClient
from app.cli.paw.verify import helpers
from app.cli.paw.verify.chat_roundtrip import run_chat_roundtrip_scenario
from app.cli.paw.verify.scenarios import ScenarioResult

DEFAULT_PROVIDER_ALLOWLIST = {
    "agy-api",
    "openai-codex",
    "opencode-go",
}


async def run_all_providers_scenario(
    state: PersonaState,
    client: PawClient,
    *,
    include_hosts: set[str] | None = None,
    include_paid: bool = False,
) -> ScenarioResult:
    """Run the chat-roundtrip scenario for one model per selected provider host."""
    r = ScenarioResult(name="all-providers")
    catalog = (await client.request("GET", "/api/v1/models")).json()
    selected = _select_provider_models(
        helpers.extract_models(catalog),
        include_hosts=include_hosts or set(),
        include_paid=include_paid,
    )
    r.artifacts["selected_models"] = selected
    r.add(
        "provider_models_selected",
        bool(selected),
        detail="no catalog model matched the allowed provider hosts",
    )
    if not selected:
        return r

    provider_results: list[dict[str, Any]] = []
    for row in selected:
        model_id = str(row.get("model_id") or row.get("id"))
        child = await run_chat_roundtrip_scenario(state, client, model_override=model_id)
        child_dict = child.to_dict()
        child_dict["host"] = row.get("host")
        child_dict["model_id"] = model_id
        provider_results.append(child_dict)
        r.add(
            f"provider_{_check_slug(str(row.get('host') or 'unknown'))}_passed",
            child.passed,
            detail=f"model={model_id}",
        )
    r.artifacts["provider_results"] = provider_results
    return r


def _select_provider_models(
    models: list[dict[str, Any]],
    *,
    include_hosts: set[str],
    include_paid: bool,
) -> list[dict[str, Any]]:
    """Pick one catalog row per selected host in catalog order."""
    allowed = set(include_hosts) or set(DEFAULT_PROVIDER_ALLOWLIST)
    if include_paid:
        allowed = {str(row.get("host")) for row in models if row.get("host")}
    selected: dict[str, dict[str, Any]] = {}
    for row in models:
        host = str(row.get("host") or "")
        model_id = row.get("model_id") or row.get("id")
        if not host or not model_id or host not in allowed or host in selected:
            continue
        selected[host] = row
    return list(selected.values())


def _check_slug(value: str) -> str:
    """Convert a provider host string to a check-name-safe suffix."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return slug or "unknown"
