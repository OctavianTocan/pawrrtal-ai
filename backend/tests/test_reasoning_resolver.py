"""Tests for the shared reasoning-effort resolver.

The resolver lives in ``app.core.providers.reasoning`` and is the
single source of truth used by every entry point that touches
``Conversation.reasoning_effort`` — the chat router, the Telegram
``/model`` command, the Telegram turn entry point, and the
``/thinking`` picker (the picker only writes valid levels but the
resolver still applies on read).
"""

from __future__ import annotations

import pytest

from app.core.providers.catalog import MODEL_CATALOG
from app.core.providers.model_id import Host
from app.core.providers.reasoning import (
    ReasoningResolution,
    format_adaptation_notice,
    resolve_reasoning_effort,
)


def _model_id_for(host: Host, model: str) -> str:
    """Canonical wire id (``host:vendor/model``) for ``(host, model)``."""
    entry = next(e for e in MODEL_CATALOG if e.host is host and e.model == model)
    return entry.id


# ---------------------------------------------------------------------------
# Happy path: stored value is supported by the current model.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model_id", "stored"),
    [
        (_model_id_for(Host.agent_sdk, "claude-opus-4-7"), "low"),
        (_model_id_for(Host.agent_sdk, "claude-opus-4-7"), "medium"),
        (_model_id_for(Host.agent_sdk, "claude-opus-4-7"), "high"),
        # ``extra-high`` isn't in any catalog row (Claude caps at high,
        # OpenAI's xhigh is post-codex-max only) — the resolver's
        # ``adapted`` path covers that case, tested separately.
        (_model_id_for(Host.xai, "grok-4.3"), "low"),
        (_model_id_for(Host.xai, "grok-4.3"), "high"),
        (_model_id_for(Host.litellm, "o1"), "medium"),
    ],
)
def test_supported_stored_value_passes_through(model_id: str, stored: str) -> None:
    """When the stored value is in ``supports_reasoning``, return it verbatim."""
    resolution = resolve_reasoning_effort(model_id=model_id, stored_effort=stored)
    assert resolution.action == "use"
    assert resolution.effective == stored
    assert resolution.next_stored == stored


# ---------------------------------------------------------------------------
# Absent: no stored override.
# ---------------------------------------------------------------------------


def test_no_stored_override_on_reasoning_model_is_absent() -> None:
    """No override + model supports reasoning → provider picks default."""
    resolution = resolve_reasoning_effort(
        model_id=_model_id_for(Host.agent_sdk, "claude-opus-4-7"),
        stored_effort=None,
    )
    assert resolution.action == "absent"
    assert resolution.effective is None
    assert resolution.next_stored is None


def test_no_stored_override_on_non_reasoning_model_is_absent() -> None:
    """No override + model doesn't support reasoning → also absent (not cleared)."""
    resolution = resolve_reasoning_effort(
        model_id=_model_id_for(Host.litellm, "gpt-4o"),
        stored_effort=None,
    )
    assert resolution.action == "absent"


# ---------------------------------------------------------------------------
# Cleared: stored value present, model doesn't honour reasoning.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model_id",
    [
        _model_id_for(Host.litellm, "gpt-4o"),
        _model_id_for(Host.litellm, "gpt-4o-mini"),
        _model_id_for(Host.opencode_go, "glm-5.1"),
    ],
)
def test_stored_value_on_non_reasoning_model_is_cleared(model_id: str) -> None:
    """Models with ``supports_reasoning=()`` clear any stored override."""
    resolution = resolve_reasoning_effort(model_id=model_id, stored_effort="high")
    assert resolution.action == "cleared"
    assert resolution.effective is None
    assert resolution.next_stored is None


# ---------------------------------------------------------------------------
# Adapted: stored value not in the new model's tuple, adapt to nearest.
# ---------------------------------------------------------------------------


def test_extra_high_on_grok_adapts_to_high() -> None:
    """Grok only honours (low, high); extra-high adapts down to high."""
    resolution = resolve_reasoning_effort(
        model_id=_model_id_for(Host.xai, "grok-4.3"),
        stored_effort="extra-high",
    )
    assert resolution.action == "adapted"
    assert resolution.effective == "high"
    assert resolution.next_stored == "high"


def test_medium_on_grok_adapts_to_low() -> None:
    """Grok supports (low, high); medium is equidistant — ties break to lower."""
    resolution = resolve_reasoning_effort(
        model_id=_model_id_for(Host.xai, "grok-4.3"),
        stored_effort="medium",
    )
    assert resolution.action == "adapted"
    # medium → low (cheaper / faster on ties)
    assert resolution.effective == "low"


def test_extra_high_on_openai_o1_adapts_to_high() -> None:
    """OpenAI o-series supports (low, medium, high); extra-high → high."""
    resolution = resolve_reasoning_effort(
        model_id=_model_id_for(Host.litellm, "o1"),
        stored_effort="extra-high",
    )
    assert resolution.action == "adapted"
    assert resolution.effective == "high"


def test_garbage_stored_value_is_cleared() -> None:
    """An unrecognised stored value (typo, dropped enum member) clears.

    Treating a stale-string as ``adapted`` would surface a meaningless
    "adapted from ridiculously-high to low" notice. The resolver
    instead clears the column and the notice reads "Reasoning
    override cleared" — honest and idempotent.
    """
    resolution = resolve_reasoning_effort(
        model_id=_model_id_for(Host.agent_sdk, "claude-opus-4-7"),
        stored_effort="ridiculously-high",
    )
    assert resolution.action == "cleared"
    assert resolution.effective is None
    assert resolution.next_stored is None


# ---------------------------------------------------------------------------
# Unknown / malformed model_id: clear the override defensively.
# ---------------------------------------------------------------------------


def test_unknown_model_id_clears_stored_value() -> None:
    """A model_id not in the catalog is treated as unresolvable."""
    resolution = resolve_reasoning_effort(
        model_id="agent-sdk:anthropic/claude-i-just-made-up",
        stored_effort="high",
    )
    assert resolution.action == "cleared"
    assert resolution.effective is None


def test_unparseable_model_id_clears_stored_value() -> None:
    """A malformed model_id string is also unresolvable."""
    resolution = resolve_reasoning_effort(
        model_id="not-a-valid-id",
        stored_effort="medium",
    )
    assert resolution.action == "cleared"


def test_none_model_id_clears_stored_value() -> None:
    """``model_id=None`` is treated as 'no model selected yet'."""
    resolution = resolve_reasoning_effort(model_id=None, stored_effort="low")
    assert resolution.action == "cleared"


# ---------------------------------------------------------------------------
# Notice rendering.
# ---------------------------------------------------------------------------


def test_format_notice_use_returns_none() -> None:
    """Happy path → no notice."""
    resolution = resolve_reasoning_effort(
        model_id=_model_id_for(Host.agent_sdk, "claude-opus-4-7"),
        stored_effort="medium",
    )
    assert format_adaptation_notice(resolution, previous_effort="medium") is None


def test_format_notice_absent_returns_none() -> None:
    """No override → no notice."""
    resolution = resolve_reasoning_effort(
        model_id=_model_id_for(Host.agent_sdk, "claude-opus-4-7"),
        stored_effort=None,
    )
    assert format_adaptation_notice(resolution, previous_effort=None) is None


def test_format_notice_cleared_mentions_previous_and_model() -> None:
    """Clear notice surfaces the previous value and the model name."""
    resolution = resolve_reasoning_effort(
        model_id=_model_id_for(Host.litellm, "gpt-4o"),
        stored_effort="high",
    )
    notice = format_adaptation_notice(resolution, previous_effort="high")
    assert notice is not None
    assert "high" in notice
    assert "GPT-4o" in notice


def test_format_notice_adapted_shows_before_and_after() -> None:
    """Adapt notice surfaces both the unsupported value and the chosen substitute."""
    resolution = resolve_reasoning_effort(
        model_id=_model_id_for(Host.xai, "grok-4.3"),
        stored_effort="extra-high",
    )
    notice = format_adaptation_notice(resolution, previous_effort="extra-high")
    assert notice is not None
    assert "extra-high" in notice
    assert "high" in notice
    assert "Grok" in notice


# ---------------------------------------------------------------------------
# Idempotence: applying the resolver to ``next_stored`` should be a no-op.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model_id", "stored"),
    [
        (_model_id_for(Host.agent_sdk, "claude-opus-4-7"), "high"),
        (_model_id_for(Host.xai, "grok-4.3"), "extra-high"),  # adapts to high
        (_model_id_for(Host.google_ai, "gemini-3-flash-preview"), "extra-high"),  # adapts to high
        (_model_id_for(Host.litellm, "gpt-4o"), "medium"),  # clears to None
    ],
)
def test_resolution_is_idempotent(model_id: str, stored: str) -> None:
    """Applying the resolver to its own output should be a no-op."""
    first: ReasoningResolution = resolve_reasoning_effort(model_id=model_id, stored_effort=stored)
    second: ReasoningResolution = resolve_reasoning_effort(
        model_id=model_id, stored_effort=first.next_stored
    )
    # Second pass should never adapt or clear again — the value
    # written back the first time is either valid or absent.
    assert second.action in ("use", "absent")
    assert second.next_stored == first.next_stored
    assert second.effective == first.effective
