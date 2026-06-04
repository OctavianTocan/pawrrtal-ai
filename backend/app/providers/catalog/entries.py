""":class:`ModelEntry` dataclass and the Anthropic/Google/xAI rows.

This module exists to keep ``catalog.py`` under the repo's 500-line
file budget. It owns:

* the public :class:`ModelEntry` dataclass (re-exported from
  ``catalog.py`` for backwards compatibility),
* the cost constants for the vendors it owns, and
* :data:`ANTHROPIC_ENTRIES`, :data:`GOOGLE_ENTRIES`, and
  :data:`XAI_ENTRIES`.

OpenAI and OpenCode Go entries live in sibling modules
``_catalog_openai.py`` and ``_catalog_opencode_go.py`` to keep every
file under the 500-line ceiling. ``catalog.py`` composes them all
into :data:`~app.providers.catalog.MODEL_CATALOG`.

Per the repo's module-privacy rule, every non-public symbol stays
private to the providers package — only ``catalog.py`` imports from
here.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.providers.base import ReasoningEffort
from app.providers.model_id import Host, Vendor


@dataclass(frozen=True, slots=True)
class ModelEntry:
    """One supported model.

    The ``id`` property is the canonical wire form used by the API,
    DB, logs, and frontend.

    Cost-per-mtok rates (PR 04): ``cost_per_mtok_in_usd`` /
    ``cost_per_mtok_out_usd`` drive Gemini's per-turn USD computation
    in the chat aggregator.  Claude reports a precise
    ``total_cost_usd`` on its ``ResultMessage`` so these fields are
    informational for Claude entries and authoritative for everyone
    else.  Values are USD per 1M tokens — ``0.0`` means "unknown,
    skip cost accounting"; the cost ledger still records the token
    counts so a later catalog backfill can recompute the dollar
    column.
    """

    host: Host
    vendor: Vendor
    model: str
    display_name: str
    short_name: str
    description: str
    cost_per_mtok_in_usd: float = 0.0
    cost_per_mtok_out_usd: float = 0.0
    # Reasoning-effort levels the provider actually honours for this
    # model.  Empty tuple = "not supported"; the chat router silently
    # drops a ``reasoning_effort`` override and the Telegram ``/thinking``
    # picker replies "not supported".  Ordering is display order in the
    # inline keyboard.
    supports_reasoning: tuple[ReasoningEffort, ...] = ()

    @property
    def id(self) -> str:
        """Canonical wire string: ``host:vendor/model``."""
        return f"{self.host.value}:{self.vendor.value}/{self.model}"


# Cost rates published by Anthropic (input / output USD per 1M tokens).
# Sourced from https://docs.claude.com/en/docs/about-claude/models/overview.
# Update alongside every model release; the chat aggregator uses these
# only as a fallback — Claude's own ``ResultMessage.total_cost_usd``
# wins when available.
_CLAUDE_OPUS_4_7_IN_USD = 5.00
_CLAUDE_OPUS_4_7_OUT_USD = 25.00
_CLAUDE_SONNET_4_6_IN_USD = 3.00
_CLAUDE_SONNET_4_6_OUT_USD = 15.00
_CLAUDE_HAIKU_4_5_IN_USD = 1.00
_CLAUDE_HAIKU_4_5_OUT_USD = 5.00


# Gemini cost rates from https://ai.google.dev/gemini-api/docs/pricing.
# Used directly by the Gemini provider (no SDK-reported total) to fill
# in the cost ledger. Update on each price change.
_GEMINI_3_5_FLASH_IN_USD = 1.50
_GEMINI_3_5_FLASH_OUT_USD = 9.00
_GEMINI_3_1_PRO_IN_USD = 2.00
_GEMINI_3_1_PRO_OUT_USD = 12.00
_GEMINI_3_FLASH_IN_USD = 0.50
_GEMINI_3_FLASH_OUT_USD = 3.00
_GEMINI_3_1_FLASH_LITE_IN_USD = 0.25
_GEMINI_3_1_FLASH_LITE_OUT_USD = 1.50


# xAI Grok pricing per https://docs.x.ai/docs/models. Used by the
# native xAI provider's cost-ledger path (no SDK-reported total).
_GROK_4_3_IN_USD = 1.25
_GROK_4_3_OUT_USD = 2.50


# Claude's adaptive thinking ``effort`` enum is documented as
# ``low | medium | high`` only (see
# https://docs.claude.com/en/docs/build-with-claude/extended-thinking).
# The chat-router resolver maps Pawrrtal's ``extra-high`` down to
# ``high`` automatically. Haiku 4.5 supports extended thinking via the
# manual ``budget_tokens`` knob only — no adaptive ``effort`` — so we
# don't surface reasoning levels for it through the /thinking picker.
ANTHROPIC_ENTRIES: tuple[ModelEntry, ...] = (
    ModelEntry(
        host=Host.agent_sdk,
        vendor=Vendor.anthropic,
        model="claude-opus-4-7",
        display_name="Claude Opus 4.7",
        short_name="Claude Opus 4.7",
        description="Most capable for ambitious work",
        cost_per_mtok_in_usd=_CLAUDE_OPUS_4_7_IN_USD,
        cost_per_mtok_out_usd=_CLAUDE_OPUS_4_7_OUT_USD,
        supports_reasoning=("low", "medium", "high"),
    ),
    ModelEntry(
        host=Host.agent_sdk,
        vendor=Vendor.anthropic,
        model="claude-sonnet-4-6",
        display_name="Claude Sonnet 4.6",
        short_name="Claude Sonnet 4.6",
        description="Balanced for everyday tasks",
        cost_per_mtok_in_usd=_CLAUDE_SONNET_4_6_IN_USD,
        cost_per_mtok_out_usd=_CLAUDE_SONNET_4_6_OUT_USD,
        supports_reasoning=("low", "medium", "high"),
    ),
    ModelEntry(
        host=Host.agent_sdk,
        vendor=Vendor.anthropic,
        model="claude-haiku-4-5",
        display_name="Claude Haiku 4.5",
        short_name="Claude Haiku 4.5",
        description="Fastest for quick answers",
        cost_per_mtok_in_usd=_CLAUDE_HAIKU_4_5_IN_USD,
        cost_per_mtok_out_usd=_CLAUDE_HAIKU_4_5_OUT_USD,
    ),
)


# Gemini 3 exposes ``thinking_level`` for low/medium/high (plus a
# ``minimal`` level we don't surface). The provider maps Pawrrtal's
# ``extra-high`` to Gemini's ``high`` so the picker can still offer
# all four levels — see ``gemini_provider._GEMINI_THINKING_LEVEL``.
GOOGLE_ENTRIES: tuple[ModelEntry, ...] = (
    ModelEntry(
        host=Host.google_ai,
        vendor=Vendor.google,
        model="gemini-3-flash-preview",
        display_name="Gemini 3 Flash Preview",
        short_name="Gemini 3 Flash",
        description="Google's frontier multimodal",
        cost_per_mtok_in_usd=_GEMINI_3_FLASH_IN_USD,
        cost_per_mtok_out_usd=_GEMINI_3_FLASH_OUT_USD,
        # Gemini 3 Flash accepts all four thinking levels per the
        # Gemini 3 developer guide
        # (https://ai.google.dev/gemini-api/docs/gemini-3).
        supports_reasoning=("minimal", "low", "medium", "high"),
    ),
    ModelEntry(
        host=Host.google_ai,
        vendor=Vendor.google,
        model="gemini-3.5-flash",
        display_name="Gemini 3.5 Flash",
        short_name="Gemini 3.5 Flash",
        description="Stable frontier Gemini Flash",
        cost_per_mtok_in_usd=_GEMINI_3_5_FLASH_IN_USD,
        cost_per_mtok_out_usd=_GEMINI_3_5_FLASH_OUT_USD,
        supports_reasoning=("minimal", "low", "medium", "high"),
    ),
    ModelEntry(
        host=Host.google_ai,
        vendor=Vendor.google,
        model="gemini-3.1-pro-preview",
        display_name="Gemini 3.1 Pro Preview",
        short_name="Gemini 3.1 Pro",
        description="Most capable Gemini for complex tasks",
        cost_per_mtok_in_usd=_GEMINI_3_1_PRO_IN_USD,
        cost_per_mtok_out_usd=_GEMINI_3_1_PRO_OUT_USD,
        # 3.1 Pro doesn't accept ``minimal`` (per the Gemini 3
        # developer guide table) so we drop it from the picker.
        supports_reasoning=("low", "medium", "high"),
    ),
    ModelEntry(
        host=Host.google_ai,
        vendor=Vendor.google,
        model="gemini-3.1-flash-lite",
        display_name="Gemini 3.1 Flash Lite",
        short_name="Gemini Flash Lite",
        description="Stable cost-efficient Gemini",
        cost_per_mtok_in_usd=_GEMINI_3_1_FLASH_LITE_IN_USD,
        cost_per_mtok_out_usd=_GEMINI_3_1_FLASH_LITE_OUT_USD,
        # Flash-Lite defaults to ``minimal`` upstream; surface the full
        # 4-level surface so users can dial it up.
        supports_reasoning=("minimal", "low", "medium", "high"),
    ),
    ModelEntry(
        host=Host.google_ai,
        vendor=Vendor.google,
        model="gemini-3.1-flash-lite-preview",
        display_name="Gemini 3.1 Flash Lite Preview",
        short_name="Gemini Flash Lite (preview)",
        description="Preview build of Flash Lite",
        cost_per_mtok_in_usd=_GEMINI_3_1_FLASH_LITE_IN_USD,
        cost_per_mtok_out_usd=_GEMINI_3_1_FLASH_LITE_OUT_USD,
        supports_reasoning=("minimal", "low", "medium", "high"),
    ),
)


# xAI's SDK exposes three reasoning tiers; ``_map_reasoning_effort`` in
# xai_provider.py collapses pawrrtal's five levels into these three
# before the call, so the picker should match what the model actually
# honours.
XAI_ENTRIES: tuple[ModelEntry, ...] = (
    ModelEntry(
        host=Host.xai,
        vendor=Vendor.xai,
        model="grok-4.3",
        display_name="Grok 4.3",
        short_name="Grok 4.3",
        description="xAI's frontier 1M-context model",
        cost_per_mtok_in_usd=_GROK_4_3_IN_USD,
        cost_per_mtok_out_usd=_GROK_4_3_OUT_USD,
        # xAI added a "no thinking" tier to Grok 4.3 (issue #373).
        # ``"minimal"`` is Pawrrtal's canonical "lightest possible
        # reasoning" sentinel, and for Grok it maps to the new
        # ``EFFORT_NONE`` proto value (see ``_map_reasoning_effort``).
        # ``"low"`` and ``"high"`` are Grok's two actual reasoning
        # tiers; everything in between collapses to ``"low"``.
        supports_reasoning=("minimal", "low", "high"),
    ),
)
