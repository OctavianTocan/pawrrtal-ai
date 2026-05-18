"""Single source of truth for which models pawrrtal supports.

Catalog entries carry the canonical ``host:vendor/model`` identity
plus display metadata. Adding a model is a one-file change here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from .model_id import (
    Host,
    InvalidModelId,  # noqa: F401  # re-exported in docstring contract; raised via parse_model_id
    ParsedModelId,
    UnknownModelId,
    Vendor,
    parse_model_id,
)


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
    is_default: bool
    cost_per_mtok_in_usd: float = 0.0
    cost_per_mtok_out_usd: float = 0.0

    @property
    def id(self) -> str:
        """Canonical wire string: ``host:vendor/model``."""
        return f"{self.host.value}:{self.vendor.value}/{self.model}"


# Cost rates published by Anthropic (input / output USD per 1M tokens
# at the time of writing).  Sourced from
# https://docs.anthropic.com/claude/docs/models-overview#model-pricing.
# Update alongside every model release; the chat aggregator uses these
# only as a fallback — Claude's own ``ResultMessage.total_cost_usd``
# wins when available.
_CLAUDE_OPUS_4_7_IN_USD = 15.00
_CLAUDE_OPUS_4_7_OUT_USD = 75.00
_CLAUDE_SONNET_4_6_IN_USD = 3.00
_CLAUDE_SONNET_4_6_OUT_USD = 15.00
_CLAUDE_HAIKU_4_5_IN_USD = 0.80
_CLAUDE_HAIKU_4_5_OUT_USD = 4.00

# Gemini cost rates from
# https://ai.google.dev/gemini-api/docs/pricing.  Used directly by the
# Gemini provider (no SDK-reported total) to fill in the cost ledger.
_GEMINI_3_FLASH_IN_USD = 0.30
_GEMINI_3_FLASH_OUT_USD = 2.50
_GEMINI_3_FLASH_LITE_IN_USD = 0.10
_GEMINI_3_FLASH_LITE_OUT_USD = 0.40

# xAI Grok pricing per https://docs.x.ai/docs/models.  Used by the
# native xAI provider's cost-ledger path (no SDK-reported total).
_GROK_4_3_IN_USD = 1.25
_GROK_4_3_OUT_USD = 2.50

# OpenAI cost rates published at https://openai.com/api/pricing/.
# Routed via LiteLLM so the cost ledger uses these directly (no
# SDK-reported total).  Update on each price change.
_OPENAI_GPT_4O_IN_USD = 2.50
_OPENAI_GPT_4O_OUT_USD = 10.00
_OPENAI_GPT_4O_MINI_IN_USD = 0.15
_OPENAI_GPT_4O_MINI_OUT_USD = 0.60
_OPENAI_O1_IN_USD = 15.00
_OPENAI_O1_OUT_USD = 60.00
_OPENAI_O1_MINI_IN_USD = 3.00
_OPENAI_O1_MINI_OUT_USD = 12.00
_OPENAI_O3_MINI_IN_USD = 1.10
_OPENAI_O3_MINI_OUT_USD = 4.40


MODEL_CATALOG: tuple[ModelEntry, ...] = (
    ModelEntry(
        host=Host.agent_sdk,
        vendor=Vendor.anthropic,
        model="claude-opus-4-7",
        display_name="Claude Opus 4.7",
        short_name="Claude Opus 4.7",
        description="Most capable for ambitious work",
        is_default=False,
        cost_per_mtok_in_usd=_CLAUDE_OPUS_4_7_IN_USD,
        cost_per_mtok_out_usd=_CLAUDE_OPUS_4_7_OUT_USD,
    ),
    ModelEntry(
        host=Host.agent_sdk,
        vendor=Vendor.anthropic,
        model="claude-sonnet-4-6",
        display_name="Claude Sonnet 4.6",
        short_name="Claude Sonnet 4.6",
        description="Balanced for everyday tasks",
        is_default=False,
        cost_per_mtok_in_usd=_CLAUDE_SONNET_4_6_IN_USD,
        cost_per_mtok_out_usd=_CLAUDE_SONNET_4_6_OUT_USD,
    ),
    ModelEntry(
        host=Host.agent_sdk,
        vendor=Vendor.anthropic,
        model="claude-haiku-4-5",
        display_name="Claude Haiku 4.5",
        short_name="Claude Haiku 4.5",
        description="Fastest for quick answers",
        is_default=False,
        cost_per_mtok_in_usd=_CLAUDE_HAIKU_4_5_IN_USD,
        cost_per_mtok_out_usd=_CLAUDE_HAIKU_4_5_OUT_USD,
    ),
    ModelEntry(
        host=Host.google_ai,
        vendor=Vendor.google,
        model="gemini-3-flash-preview",
        display_name="Gemini 3 Flash Preview",
        short_name="Gemini 3 Flash",
        description="Google's frontier multimodal",
        is_default=True,
        cost_per_mtok_in_usd=_GEMINI_3_FLASH_IN_USD,
        cost_per_mtok_out_usd=_GEMINI_3_FLASH_OUT_USD,
    ),
    ModelEntry(
        host=Host.google_ai,
        vendor=Vendor.google,
        model="gemini-3.1-flash-lite-preview",
        display_name="Gemini 3.1 Flash Lite Preview",
        short_name="Gemini Flash Lite",
        description="Light and fast Gemini",
        is_default=False,
        cost_per_mtok_in_usd=_GEMINI_3_FLASH_LITE_IN_USD,
        cost_per_mtok_out_usd=_GEMINI_3_FLASH_LITE_OUT_USD,
    ),
    ModelEntry(
        host=Host.xai,
        vendor=Vendor.xai,
        model="grok-4.3",
        display_name="Grok 4.3",
        short_name="Grok 4.3",
        description="xAI's frontier 1M-context model",
        is_default=False,
        cost_per_mtok_in_usd=_GROK_4_3_IN_USD,
        cost_per_mtok_out_usd=_GROK_4_3_OUT_USD,
    ),
    # OpenAI — routed through LiteLLM in-process SDK gateway.  Tool use
    # is intentionally text-only for v1 (provider rejects non-empty
    # ``tools=`` with a debug log); revisit once the OpenAI function-
    # calling bridge lands.
    #
    # NOTE: xAI catalog entries via LiteLLM were intentionally dropped
    # in favour of the native ``Host.xai`` provider (PRs #314/#324)
    # which has full reasoning + Live Search support.  If Grok 3 needs
    # to be available again, add it under ``Host.xai`` in this catalog.
    ModelEntry(
        host=Host.litellm,
        vendor=Vendor.openai,
        model="gpt-4o",
        display_name="GPT-4o",
        short_name="GPT-4o",
        description="OpenAI's flagship multimodal",
        is_default=False,
        cost_per_mtok_in_usd=_OPENAI_GPT_4O_IN_USD,
        cost_per_mtok_out_usd=_OPENAI_GPT_4O_OUT_USD,
    ),
    ModelEntry(
        host=Host.litellm,
        vendor=Vendor.openai,
        model="gpt-4o-mini",
        display_name="GPT-4o mini",
        short_name="GPT-4o mini",
        description="Cheap and fast OpenAI",
        is_default=False,
        cost_per_mtok_in_usd=_OPENAI_GPT_4O_MINI_IN_USD,
        cost_per_mtok_out_usd=_OPENAI_GPT_4O_MINI_OUT_USD,
    ),
    ModelEntry(
        host=Host.litellm,
        vendor=Vendor.openai,
        model="o1",
        display_name="OpenAI o1",
        short_name="o1",
        description="Deep reasoning, slow",
        is_default=False,
        cost_per_mtok_in_usd=_OPENAI_O1_IN_USD,
        cost_per_mtok_out_usd=_OPENAI_O1_OUT_USD,
    ),
    ModelEntry(
        host=Host.litellm,
        vendor=Vendor.openai,
        model="o1-mini",
        display_name="OpenAI o1 mini",
        short_name="o1 mini",
        description="Lightweight reasoning",
        is_default=False,
        cost_per_mtok_in_usd=_OPENAI_O1_MINI_IN_USD,
        cost_per_mtok_out_usd=_OPENAI_O1_MINI_OUT_USD,
    ),
    ModelEntry(
        host=Host.litellm,
        vendor=Vendor.openai,
        model="o3-mini",
        display_name="OpenAI o3 mini",
        short_name="o3 mini",
        description="Newer reasoning, balanced",
        is_default=False,
        cost_per_mtok_in_usd=_OPENAI_O3_MINI_IN_USD,
        cost_per_mtok_out_usd=_OPENAI_O3_MINI_OUT_USD,
    ),
)


# Module-import-time invariant: exactly one default.
# Explicit raise (not ``assert``) so ``python -O`` cannot strip it.
_default_count = sum(1 for e in MODEL_CATALOG if e.is_default)
if _default_count != 1:
    raise ValueError(f"MODEL_CATALOG must have exactly one default; found {_default_count}")


def _hash_catalog(catalog: tuple[ModelEntry, ...]) -> str:
    """Stable hash of the catalog used as the HTTP ``ETag`` value."""
    payload = json.dumps(
        [asdict(e) for e in catalog],
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


CATALOG_ETAG: str = _hash_catalog(MODEL_CATALOG)
"""Catalog hash, computed once at import. Exposed via the ``ETag``
response header so clients can revalidate cheaply with
``If-None-Match``."""


def default_model() -> ModelEntry:
    """Return the entry marked ``is_default=True``.

    Returns:
        The single default entry. The module-import-time invariant
        guarantees exactly one exists.
    """
    return next(e for e in MODEL_CATALOG if e.is_default)


def find(parsed: ParsedModelId) -> ModelEntry | None:
    """Look up a catalog entry by parsed identifier.

    Args:
        parsed: Pre-parsed identifier (callers go through
            :func:`parse_model_id` first).

    Returns:
        The matching :class:`ModelEntry` or ``None``.
    """
    for entry in MODEL_CATALOG:
        if (
            entry.host is parsed.host
            and entry.vendor is parsed.vendor
            and entry.model == parsed.model
        ):
            return entry
    return None


def is_known(parsed: ParsedModelId) -> bool:
    """Return whether ``parsed`` is in :data:`MODEL_CATALOG`."""
    return find(parsed) is not None


def require_known(model_id: str) -> ModelEntry:
    """Parse ``model_id`` and look it up; raise on either failure.

    Args:
        model_id: Wire-form model identifier (any of the accepted
            input shapes — see :func:`parse_model_id`).

    Returns:
        The catalog entry.

    Raises:
        InvalidModelId: If the string fails to parse.
        UnknownModelId: If the string parses but isn't in the
            catalog.
    """
    parsed = parse_model_id(model_id)
    entry = find(parsed)
    if entry is None:
        raise UnknownModelId(f"model not in catalog: {parsed.id}")
    return entry
