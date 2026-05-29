"""OpenAI catalogue rows (LiteLLM-routed) and their cost constants.

Split out of ``_catalog_entries.py`` so each module fits the repo's
500-line file budget. ``catalog.py`` is the only consumer — see the
module docstring there for the composition story.

Tool use is intentionally text-only for v1 (provider rejects non-empty
``tools=`` with a debug log); revisit once the OpenAI function-calling
bridge lands.

NOTE: xAI catalog entries via LiteLLM were intentionally dropped in
favour of the native ``Host.xai`` provider (PRs #314/#324) which has
full reasoning + Live Search support. If Grok 3 needs to be available
again, add it under ``Host.xai`` in the xAI entries module.

OpenAI's ``reasoning_effort`` enum is
``none | minimal | low | medium | high | xhigh`` (sourced from
openai-python ``src/openai/types/shared/reasoning_effort.py``). Per
the SDK's ``Reasoning`` type docstring, ``xhigh`` is supported on
models *after* gpt-5.1-codex-max — so the 5.2 series and everything
later (5.3-chat, 5.3-codex, 5.4-*, 5.5) get the full four-level
surface. ``gpt-5`` / ``-mini`` / ``-nano`` and the o-series predate
the cutoff so they cap at ``high``; the resolver maps ``extra-high``
→ ``high`` for them.
"""

from __future__ import annotations

from app.providers.model_id import Host, Vendor

from .entries import ModelEntry

# OpenAI cost rates routed via LiteLLM. Sourced from the LiteLLM
# pricing JSON
# (https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json)
# which mirrors OpenAI's published pricing. Update on each price
# change. Values are USD per 1M tokens.
_OPENAI_GPT_5_5_IN_USD = 5.00
_OPENAI_GPT_5_5_OUT_USD = 30.00
_OPENAI_GPT_5_4_IN_USD = 2.50
_OPENAI_GPT_5_4_OUT_USD = 15.00
_OPENAI_GPT_5_4_MINI_IN_USD = 0.75
_OPENAI_GPT_5_4_MINI_OUT_USD = 4.50
_OPENAI_GPT_5_4_NANO_IN_USD = 0.20
_OPENAI_GPT_5_4_NANO_OUT_USD = 1.25
_OPENAI_GPT_5_3_CHAT_IN_USD = 1.75
_OPENAI_GPT_5_3_CHAT_OUT_USD = 14.00
_OPENAI_GPT_5_3_CODEX_IN_USD = 1.75
_OPENAI_GPT_5_3_CODEX_OUT_USD = 14.00
_OPENAI_GPT_5_1_CODEX_MAX_IN_USD = 1.25
_OPENAI_GPT_5_1_CODEX_MAX_OUT_USD = 10.00
_OPENAI_GPT_5_IN_USD = 1.25
_OPENAI_GPT_5_OUT_USD = 10.00
_OPENAI_GPT_5_MINI_IN_USD = 0.25
_OPENAI_GPT_5_MINI_OUT_USD = 2.00
_OPENAI_GPT_5_NANO_IN_USD = 0.05
_OPENAI_GPT_5_NANO_OUT_USD = 0.40
_OPENAI_GPT_4_1_IN_USD = 2.00
_OPENAI_GPT_4_1_OUT_USD = 8.00
_OPENAI_GPT_4_1_MINI_IN_USD = 0.40
_OPENAI_GPT_4_1_MINI_OUT_USD = 1.60
_OPENAI_GPT_4O_IN_USD = 2.50
_OPENAI_GPT_4O_OUT_USD = 10.00
_OPENAI_GPT_4O_MINI_IN_USD = 0.15
_OPENAI_GPT_4O_MINI_OUT_USD = 0.60
_OPENAI_O1_IN_USD = 15.00
_OPENAI_O1_OUT_USD = 60.00
_OPENAI_O1_MINI_IN_USD = 3.00
_OPENAI_O1_MINI_OUT_USD = 12.00
_OPENAI_O3_IN_USD = 2.00
_OPENAI_O3_OUT_USD = 8.00
_OPENAI_O3_MINI_IN_USD = 1.10
_OPENAI_O3_MINI_OUT_USD = 4.40
_OPENAI_O4_MINI_IN_USD = 1.10
_OPENAI_O4_MINI_OUT_USD = 4.40


OPENAI_ENTRIES: tuple[ModelEntry, ...] = (
    # Native Codex SDK models (first-class provider via openai_codex host).
    # These only appear for users/workspaces that have Codex auth (see
    # host_authenticated in factory.py). Distinct from the litellm-routed
    # equivalents so users can choose the native thread/agent experience.
    ModelEntry(
        host=Host.openai_codex,
        vendor=Vendor.openai,
        model="gpt-5.5",
        display_name="GPT-5.5 (Codex SDK)",
        short_name="GPT-5.5 Codex",
        description="OpenAI GPT-5.5 via the official Codex Python SDK (native threads, local app-server, full agentic capabilities)",
        is_default=False,
        cost_per_mtok_in_usd=5.00,
        cost_per_mtok_out_usd=30.00,
        supports_reasoning=("minimal", "low", "medium", "high", "extra-high"),
    ),
    ModelEntry(
        host=Host.litellm,
        vendor=Vendor.openai,
        model="gpt-5.5",
        display_name="GPT-5.5",
        short_name="GPT-5.5",
        description="OpenAI's current frontier reasoning model",
        is_default=False,
        cost_per_mtok_in_usd=_OPENAI_GPT_5_5_IN_USD,
        cost_per_mtok_out_usd=_OPENAI_GPT_5_5_OUT_USD,
        supports_reasoning=("minimal", "low", "medium", "high", "extra-high"),
    ),
    ModelEntry(
        host=Host.litellm,
        vendor=Vendor.openai,
        model="gpt-5.4",
        display_name="GPT-5.4",
        short_name="GPT-5.4",
        description="GPT-5.4 mainline reasoning",
        is_default=False,
        cost_per_mtok_in_usd=_OPENAI_GPT_5_4_IN_USD,
        cost_per_mtok_out_usd=_OPENAI_GPT_5_4_OUT_USD,
        supports_reasoning=("minimal", "low", "medium", "high", "extra-high"),
    ),
    ModelEntry(
        host=Host.litellm,
        vendor=Vendor.openai,
        model="gpt-5.4-mini",
        display_name="GPT-5.4 mini",
        short_name="GPT-5.4 mini",
        description="Cheaper GPT-5.4 reasoning",
        is_default=False,
        cost_per_mtok_in_usd=_OPENAI_GPT_5_4_MINI_IN_USD,
        cost_per_mtok_out_usd=_OPENAI_GPT_5_4_MINI_OUT_USD,
        supports_reasoning=("minimal", "low", "medium", "high", "extra-high"),
    ),
    ModelEntry(
        host=Host.litellm,
        vendor=Vendor.openai,
        model="gpt-5.4-nano",
        display_name="GPT-5.4 nano",
        short_name="GPT-5.4 nano",
        description="Smallest GPT-5.4 tier",
        is_default=False,
        cost_per_mtok_in_usd=_OPENAI_GPT_5_4_NANO_IN_USD,
        cost_per_mtok_out_usd=_OPENAI_GPT_5_4_NANO_OUT_USD,
        supports_reasoning=("minimal", "low", "medium", "high", "extra-high"),
    ),
    ModelEntry(
        host=Host.litellm,
        vendor=Vendor.openai,
        model="gpt-5.3-chat-latest",
        display_name="GPT-5.3 (chat latest)",
        short_name="GPT-5.3 chat",
        description="GPT-5.3 chat alias (Codex Spark family)",
        is_default=False,
        cost_per_mtok_in_usd=_OPENAI_GPT_5_3_CHAT_IN_USD,
        cost_per_mtok_out_usd=_OPENAI_GPT_5_3_CHAT_OUT_USD,
        supports_reasoning=("minimal", "low", "medium", "high", "extra-high"),
    ),
    ModelEntry(
        host=Host.litellm,
        vendor=Vendor.openai,
        model="gpt-5.3-codex",
        display_name="GPT-5.3 Codex",
        short_name="GPT-5.3 Codex",
        description="Code-tuned GPT-5.3",
        is_default=False,
        cost_per_mtok_in_usd=_OPENAI_GPT_5_3_CODEX_IN_USD,
        cost_per_mtok_out_usd=_OPENAI_GPT_5_3_CODEX_OUT_USD,
        supports_reasoning=("minimal", "low", "medium", "high", "extra-high"),
    ),
    ModelEntry(
        host=Host.litellm,
        vendor=Vendor.openai,
        model="gpt-5.1-codex-max",
        display_name="GPT-5.1 Codex Max",
        short_name="GPT-5.1 Codex Max",
        description="Code-tuned GPT-5.1 (xhigh cutoff)",
        is_default=False,
        cost_per_mtok_in_usd=_OPENAI_GPT_5_1_CODEX_MAX_IN_USD,
        cost_per_mtok_out_usd=_OPENAI_GPT_5_1_CODEX_MAX_OUT_USD,
        # gpt-5.1-codex-max is the cutoff *for* xhigh — the docstring
        # says "after gpt-5.1-codex-max", so this row itself caps at
        # ``high``.
        supports_reasoning=("minimal", "low", "medium", "high"),
    ),
    ModelEntry(
        host=Host.litellm,
        vendor=Vendor.openai,
        model="gpt-5",
        display_name="GPT-5",
        short_name="GPT-5",
        description="Original GPT-5 (pre-xhigh)",
        is_default=False,
        cost_per_mtok_in_usd=_OPENAI_GPT_5_IN_USD,
        cost_per_mtok_out_usd=_OPENAI_GPT_5_OUT_USD,
        supports_reasoning=("minimal", "low", "medium", "high"),
    ),
    ModelEntry(
        host=Host.litellm,
        vendor=Vendor.openai,
        model="gpt-5-mini",
        display_name="GPT-5 mini",
        short_name="GPT-5 mini",
        description="Cheaper GPT-5 with reasoning",
        is_default=False,
        cost_per_mtok_in_usd=_OPENAI_GPT_5_MINI_IN_USD,
        cost_per_mtok_out_usd=_OPENAI_GPT_5_MINI_OUT_USD,
        supports_reasoning=("minimal", "low", "medium", "high"),
    ),
    ModelEntry(
        host=Host.litellm,
        vendor=Vendor.openai,
        model="gpt-5-nano",
        display_name="GPT-5 nano",
        short_name="GPT-5 nano",
        description="Smallest GPT-5 tier",
        is_default=False,
        cost_per_mtok_in_usd=_OPENAI_GPT_5_NANO_IN_USD,
        cost_per_mtok_out_usd=_OPENAI_GPT_5_NANO_OUT_USD,
        supports_reasoning=("minimal", "low", "medium", "high"),
    ),
    ModelEntry(
        host=Host.litellm,
        vendor=Vendor.openai,
        model="gpt-4.1",
        display_name="GPT-4.1",
        short_name="GPT-4.1",
        description="GPT-4 successor, no reasoning knob",
        is_default=False,
        cost_per_mtok_in_usd=_OPENAI_GPT_4_1_IN_USD,
        cost_per_mtok_out_usd=_OPENAI_GPT_4_1_OUT_USD,
    ),
    ModelEntry(
        host=Host.litellm,
        vendor=Vendor.openai,
        model="gpt-4.1-mini",
        display_name="GPT-4.1 mini",
        short_name="GPT-4.1 mini",
        description="Cheaper GPT-4.1",
        is_default=False,
        cost_per_mtok_in_usd=_OPENAI_GPT_4_1_MINI_IN_USD,
        cost_per_mtok_out_usd=_OPENAI_GPT_4_1_MINI_OUT_USD,
    ),
    ModelEntry(
        host=Host.litellm,
        vendor=Vendor.openai,
        model="gpt-4o",
        display_name="GPT-4o",
        short_name="GPT-4o",
        description="Multimodal GPT-4, no reasoning knob",
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
        description="Cheap and fast GPT-4o",
        is_default=False,
        cost_per_mtok_in_usd=_OPENAI_GPT_4O_MINI_IN_USD,
        cost_per_mtok_out_usd=_OPENAI_GPT_4O_MINI_OUT_USD,
    ),
    ModelEntry(
        host=Host.litellm,
        vendor=Vendor.openai,
        model="o3",
        display_name="OpenAI o3",
        short_name="o3",
        description="o-series reasoning, full size",
        is_default=False,
        cost_per_mtok_in_usd=_OPENAI_O3_IN_USD,
        cost_per_mtok_out_usd=_OPENAI_O3_OUT_USD,
        supports_reasoning=("minimal", "low", "medium", "high"),
    ),
    ModelEntry(
        host=Host.litellm,
        vendor=Vendor.openai,
        model="o3-mini",
        display_name="OpenAI o3 mini",
        short_name="o3 mini",
        description="Smaller o-series reasoning",
        is_default=False,
        cost_per_mtok_in_usd=_OPENAI_O3_MINI_IN_USD,
        cost_per_mtok_out_usd=_OPENAI_O3_MINI_OUT_USD,
        supports_reasoning=("minimal", "low", "medium", "high"),
    ),
    ModelEntry(
        host=Host.litellm,
        vendor=Vendor.openai,
        model="o4-mini",
        display_name="OpenAI o4 mini",
        short_name="o4 mini",
        description="Newest small reasoning model",
        is_default=False,
        cost_per_mtok_in_usd=_OPENAI_O4_MINI_IN_USD,
        cost_per_mtok_out_usd=_OPENAI_O4_MINI_OUT_USD,
        supports_reasoning=("minimal", "low", "medium", "high"),
    ),
    ModelEntry(
        host=Host.litellm,
        vendor=Vendor.openai,
        model="o1",
        display_name="OpenAI o1",
        short_name="o1",
        description="Legacy deep reasoning",
        is_default=False,
        cost_per_mtok_in_usd=_OPENAI_O1_IN_USD,
        cost_per_mtok_out_usd=_OPENAI_O1_OUT_USD,
        supports_reasoning=("minimal", "low", "medium", "high"),
    ),
    ModelEntry(
        host=Host.litellm,
        vendor=Vendor.openai,
        model="o1-mini",
        display_name="OpenAI o1 mini",
        short_name="o1 mini",
        description="Legacy lightweight reasoning",
        is_default=False,
        cost_per_mtok_in_usd=_OPENAI_O1_MINI_IN_USD,
        cost_per_mtok_out_usd=_OPENAI_O1_MINI_OUT_USD,
        supports_reasoning=("minimal", "low", "medium", "high"),
    ),
)
