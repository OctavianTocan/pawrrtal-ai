"""OpenCode Go catalogue rows.

Split out of ``_catalog_entries.py`` so each module fits the repo's
500-line file budget. ``catalog.py`` is the only consumer.

The OpenCode Go gateway — SST's hosted OpenAI-compatible endpoint at
https://opencode.ai/docs/go/ — uses subscription-based pricing
($12 / 5h, $30 / week, $60 / month) rather than per-token rates, so
individual ``cost_per_mtok_*`` values aren't published. Every entry
leaves ``cost_per_mtok_*`` at its 0.0 default ("unknown — skip cost
accounting"); the cost ledger still records the token counts so a
future catalog backfill can recompute USD if/when the gateway exposes
per-model rates. None of these models documents reasoning-effort
support on the OpenCode Go side, so ``supports_reasoning`` is left at
its empty default.
"""

from __future__ import annotations

from app.providers.model_id import Host, Vendor

from .entries import ModelEntry

OPENCODE_GO_ENTRIES: tuple[ModelEntry, ...] = (
    ModelEntry(
        host=Host.opencode_go,
        vendor=Vendor.zai,
        model="glm-5.1",
        display_name="GLM-5.1",
        short_name="GLM-5.1",
        description="Z.ai's open coding model",
    ),
    ModelEntry(
        host=Host.opencode_go,
        vendor=Vendor.zai,
        model="glm-5",
        display_name="GLM-5",
        short_name="GLM-5",
        description="Previous-generation GLM",
    ),
    ModelEntry(
        host=Host.opencode_go,
        vendor=Vendor.moonshot,
        model="kimi-k2.6",
        display_name="Kimi K2.6",
        short_name="Kimi K2.6",
        description="Long-context coding model",
    ),
    ModelEntry(
        host=Host.opencode_go,
        vendor=Vendor.moonshot,
        model="kimi-k2.5",
        display_name="Kimi K2.5",
        short_name="Kimi K2.5",
        description="Previous-generation Kimi",
    ),
    ModelEntry(
        host=Host.opencode_go,
        vendor=Vendor.xiaomi,
        model="mimo-v2.5-pro",
        display_name="MiMo V2.5 Pro",
        short_name="MiMo V2.5 Pro",
        description="Xiaomi's flagship MiMo coding model",
    ),
    ModelEntry(
        host=Host.opencode_go,
        vendor=Vendor.xiaomi,
        model="mimo-v2.5",
        display_name="MiMo V2.5",
        short_name="MiMo V2.5",
        description="Xiaomi MiMo coding model",
    ),
    ModelEntry(
        host=Host.opencode_go,
        vendor=Vendor.alibaba,
        model="qwen3.6-plus",
        display_name="Qwen3.6 Plus",
        short_name="Qwen3.6 Plus",
        description="Alibaba's frontier Qwen coding model",
    ),
    ModelEntry(
        host=Host.opencode_go,
        vendor=Vendor.alibaba,
        model="qwen3.5-plus",
        display_name="Qwen3.5 Plus",
        short_name="Qwen3.5 Plus",
        description="Previous-generation Qwen Plus",
    ),
    ModelEntry(
        host=Host.opencode_go,
        vendor=Vendor.minimax,
        model="minimax-m2.7",
        display_name="MiniMax M2.7",
        short_name="MiniMax M2.7",
        description="MiniMax's frontier model",
    ),
    ModelEntry(
        host=Host.opencode_go,
        vendor=Vendor.minimax,
        model="minimax-m2.5",
        display_name="MiniMax M2.5",
        short_name="MiniMax M2.5",
        description="Previous-generation MiniMax",
    ),
    ModelEntry(
        host=Host.opencode_go,
        vendor=Vendor.deepseek,
        model="deepseek-v4-pro",
        display_name="DeepSeek V4 Pro",
        short_name="DeepSeek V4 Pro",
        description="DeepSeek's flagship V4",
    ),
    ModelEntry(
        host=Host.opencode_go,
        vendor=Vendor.deepseek,
        model="deepseek-v4-flash",
        display_name="DeepSeek V4 Flash",
        short_name="DeepSeek V4 Flash",
        description="Lightweight DeepSeek V4",
    ),
)
