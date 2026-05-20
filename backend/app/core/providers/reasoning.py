"""Per-conversation reasoning-effort resolver.

Single source of truth for how a stored reasoning-effort override is
reconciled with the current model's catalog metadata. Both the
Telegram ``/thinking`` picker, the ``/model`` command path, the chat
router (web), and the Telegram turn entry point go through this
helper so catalog validation lives in exactly one place.

The contract:

* If the model has ``supports_reasoning == ()`` (provider accepts the
  kwarg but silently ignores it — Gemini, GPT-4o, GLM, Kimi), any
  stored override is **cleared** and the provider is called without
  a reasoning knob. Surfacing the change is the caller's job — silent
  clears are a footgun.
* If the stored value is in ``entry.supports_reasoning``, it is
  **used** verbatim — the happy path.
* If the model supports reasoning but the stored value is one the
  current model doesn't honour (e.g. you set ``extra-high`` on
  Claude, then switched to Grok which only honours ``low/high``),
  the resolver **adapts** to the nearest level in the canonical
  ladder ``low → medium → high → extra-high`` so subsequent turns
  send a level the provider actually uses.
* If no override is stored, the action is **absent** and the
  provider picks its own default.

The resolver also returns ``next_stored`` — what should be persisted
on the conversation column. Callers that hold a session typically
write this back so a single normalization happens once instead of
re-firing on every turn.

This module is import-cycle-safe: it only depends on ``base``,
``catalog``, and ``model_id``, which is the bedrock of the providers
tree.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, get_args

from .base import ReasoningEffort
from .catalog import ModelEntry, find
from .model_id import InvalidModelId, parse_model_id

ResolutionAction = Literal["use", "adapted", "cleared", "absent"]
"""What the resolver did with the stored value.

* ``"use"`` — stored value is valid; pass through to the provider.
* ``"adapted"`` — stored value isn't supported by the current model;
  resolver fell back to the nearest level in
  ``entry.supports_reasoning``.
* ``"cleared"`` — model doesn't support reasoning at all; the stored
  override has been zeroed out.
* ``"absent"`` — no stored override; the provider picks its default.
"""


# Canonical reasoning ladder, ordered from lightest to heaviest.
# Used by ``_nearest_supported`` to map an unsupported stored value
# (e.g. ``"extra-high"``) onto whichever level the current model
# actually accepts. The first entry of the ``ReasoningEffort`` literal
# is the canonical ordering source — kept in sync via ``get_args``.
_LEVEL_ORDER: tuple[ReasoningEffort, ...] = get_args(ReasoningEffort)
_LEVEL_INDEX: dict[str, int] = {level: idx for idx, level in enumerate(_LEVEL_ORDER)}


@dataclass(frozen=True, slots=True)
class ReasoningResolution:
    """Outcome of resolving a stored reasoning effort against a model.

    Attributes:
        effective: What the provider should receive on this turn —
            ``None`` to omit the kwarg entirely (provider default).
        next_stored: What should be persisted on the conversation
            column. ``None`` to clear. Callers that hold a session
            should write this back when it differs from the value
            they passed in so the adapt path runs once instead of
            firing on every turn.
        action: What the resolver did, for caller-side messaging.
        model_entry: The resolved catalog entry, or ``None`` when
            ``model_id`` couldn't be parsed / wasn't in the catalog.
            Exposed so callers can render a meaningful notice
            (e.g. ``entry.short_name``) without re-resolving the
            catalog themselves.
    """

    effective: ReasoningEffort | None
    next_stored: ReasoningEffort | None
    action: ResolutionAction
    model_entry: ModelEntry | None


def resolve_reasoning_effort(
    *,
    model_id: str | None,
    stored_effort: str | None,
) -> ReasoningResolution:
    """Reconcile ``stored_effort`` with the current model's catalog entry.

    Pure: makes no DB calls and does not mutate inputs. See the module
    docstring for the full contract.

    Args:
        model_id: Canonical wire form (``"host:vendor/model"``) or
            ``None`` to mean "no model selected yet" (treated as
            unresolvable — the override is cleared).
        stored_effort: The current value of ``Conversation.reasoning_effort``
            or any equivalent override surface. ``None`` means no
            override.

    Returns:
        A :class:`ReasoningResolution` describing what to send to the
        provider and what to persist back to the conversation column.
    """
    entry = _resolve_catalog_entry(model_id)
    if entry is None or not entry.supports_reasoning:
        if stored_effort is None:
            return ReasoningResolution(
                effective=None, next_stored=None, action="absent", model_entry=entry
            )
        return ReasoningResolution(
            effective=None, next_stored=None, action="cleared", model_entry=entry
        )

    if stored_effort is None:
        return ReasoningResolution(
            effective=None, next_stored=None, action="absent", model_entry=entry
        )

    if stored_effort in entry.supports_reasoning:
        # ``stored_effort`` is a plain ``str`` from the DB column; the
        # membership check confirms it's one of the literal values.
        effort: ReasoningEffort = stored_effort
        return ReasoningResolution(
            effective=effort, next_stored=effort, action="use", model_entry=entry
        )

    # Defensive: an unrecognised stored value (typo, dropped enum
    # member, manual SQL) should clear rather than masquerade as an
    # adaptation. ``_nearest_supported`` only knows how to map values
    # that are themselves on the canonical ladder; anything else
    # falls back to ``supported[0]`` which has no semantic justification
    # for the user. Treating it as a clear is honest and idempotent.
    if stored_effort not in _LEVEL_INDEX:
        return ReasoningResolution(
            effective=None, next_stored=None, action="cleared", model_entry=entry
        )

    adapted = _nearest_supported(stored_effort, entry.supports_reasoning)
    return ReasoningResolution(
        effective=adapted, next_stored=adapted, action="adapted", model_entry=entry
    )


def format_adaptation_notice(
    resolution: ReasoningResolution,
    *,
    previous_effort: str | None,
) -> str | None:
    """Render a user-facing one-liner for an ``adapted`` or ``cleared`` outcome.

    Returns ``None`` when no notice is warranted (``use`` / ``absent``)
    so callers can drop the notice block from their reply without an
    extra conditional.

    Args:
        resolution: The :class:`ReasoningResolution` to describe.
        previous_effort: The value that was stored on the conversation
            before the resolver ran. Surfacing this in the message
            (``"high" → "medium"``) gives the operator the context
            they need to understand the change.
    """
    if resolution.action == "cleared":
        return _CLEARED_TEMPLATE.format(
            previous=previous_effort or "(unset)",
            model_name=_model_name(resolution.model_entry),
        )
    if resolution.action == "adapted":
        return _ADAPTED_TEMPLATE.format(
            previous=previous_effort or "(unset)",
            adapted=resolution.next_stored,
            model_name=_model_name(resolution.model_entry),
        )
    return None


_CLEARED_TEMPLATE = (
    "🧠 Reasoning override cleared — {model_name} doesn't honour reasoning levels "
    "(was: {previous})."
)
_ADAPTED_TEMPLATE = (
    "🧠 Reasoning adapted from {previous} to {adapted} — {model_name} doesn't honour {previous}."
)


def _model_name(entry: ModelEntry | None) -> str:
    """Render a model display name, falling back to a placeholder."""
    if entry is None:
        return "this model"
    return entry.short_name


def _resolve_catalog_entry(model_id: str | None) -> ModelEntry | None:
    """Parse + look up a catalog entry, returning ``None`` for bad input."""
    if not model_id:
        return None
    try:
        parsed = parse_model_id(model_id)
    except InvalidModelId:
        return None
    return find(parsed)


def _nearest_supported(target: str, supported: tuple[ReasoningEffort, ...]) -> ReasoningEffort:
    """Return the level in ``supported`` closest to ``target`` on the ladder.

    Ties broken toward the lower (cheaper / faster) level — better to
    under-think than over-bill. ``supported`` is always non-empty when
    this is called (the caller checks ``entry.supports_reasoning``).

    When ``target`` isn't on the canonical ladder at all (would only
    happen if a stale DB row holds a string outside the
    ``ReasoningEffort`` literal — defensive), the resolver falls back
    to the first supported level.
    """
    if target not in _LEVEL_INDEX:
        return supported[0]
    target_idx = _LEVEL_INDEX[target]
    return min(
        supported, key=lambda level: (abs(_LEVEL_INDEX[level] - target_idx), _LEVEL_INDEX[level])
    )
