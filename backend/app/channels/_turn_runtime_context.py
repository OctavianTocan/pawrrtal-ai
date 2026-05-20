"""Compose the per-turn system prompt: workspace + runtime metadata.

Tiny helper that keeps :mod:`app.channels.turn_runner` below the
fan-out budget the architecture gate (sentrux ``no_god_files``)
enforces.  Without this seam the runner would pull
:mod:`app.core.providers.catalog`, :mod:`app.core.providers.model_id`,
:mod:`app.core.agent_loop.safety_factory`, and
:mod:`app.core.runtime_context` directly — four imports that all live
together purely for the system-prompt assembly path.

Closes the runtime-context plumbing for issues #289, #291, #294, #309.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from app.channels._turn_workspace import workspace_system_prompt
from app.core.agent_loop.safety_factory import safety_from_settings
from app.core.config import settings
from app.core.providers.catalog import find as find_catalog_entry
from app.core.providers.model_id import InvalidModelId, parse_model_id
from app.core.runtime_context import ProviderIdentity, append_runtime_context

if TYPE_CHECKING:
    from app.core.agent_loop.types import AgentTool


def system_prompt_for_turn(
    workspace_root: Path | None,
    *,
    model_id: str | None,
    tools: list[AgentTool] | None,
    extra_context: str | None = None,
) -> str | None:
    """Return the workspace prompt with runtime metadata appended.

    Args:
        workspace_root: User's default workspace directory; forwarded to
            :func:`workspace_system_prompt` so AGENTS.md / SOUL.md /
            skills are loaded.
        model_id: Canonical ``host:vendor/model`` id resolved by the
            chat router. ``None`` skips the active-model block.
        tools: AgentTool list bound for this turn. ``None`` skips the
            tool-inventory block entirely; the empty list still renders
            an explicit "no tools" notice so the model doesn't fall
            back to filesystem discovery.
        extra_context: Extra context to add to the system prompt.

    Returns:
        Composed system prompt, or ``None`` when the workspace prompt
        loader returned nothing (providers fall back to their bundled
        default in that case — we never synthesise a prompt just to
        wear the runtime metadata).
    """
    base_prompt = workspace_system_prompt(workspace_root)
    return append_runtime_context(
        base_prompt,
        identity=_provider_identity_for(model_id),
        safety=safety_from_settings(settings),
        tools=tools,
        extra_context=extra_context,
    )


def _provider_identity_for(model_id: str | None) -> ProviderIdentity | None:
    """Look up trusted provider + model metadata for ``model_id``.

    Returns ``None`` when the channel didn't supply a model id (rare —
    typically only legacy tests). When the id is well-formed we always
    return a :class:`ProviderIdentity` so the system-prompt block can
    answer "which model are you?" with trusted runtime metadata. The
    catalog lookup is best-effort: an unknown but well-formed id (e.g.
    an operator pinning a preview that hasn't been added to the
    catalog yet) still produces a usable identity built from the
    parsed host / vendor / model fields.
    """
    if not model_id:
        return None
    try:
        parsed = parse_model_id(model_id)
    except InvalidModelId:
        # Channel sent us something we can't decode — surface the raw
        # id rather than silently drop the section.
        return ProviderIdentity(provider="unknown", model_id=model_id)
    entry = find_catalog_entry(parsed)
    display_name = entry.display_name if entry is not None else None
    return ProviderIdentity(
        provider=parsed.host.value,
        model_id=model_id,
        display_name=display_name,
    )
