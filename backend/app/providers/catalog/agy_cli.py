"""Antigravity catalogue rows for the direct API provider."""

from __future__ import annotations

from app.providers.base import ReasoningEffort
from app.providers.model_id import Host, Vendor

from .entries import ModelEntry

_AGY_IN_USD = 0.0
_AGY_OUT_USD = 0.0


def _agy_api_entry(
    *,
    vendor: Vendor,
    model: str,
    display_name: str,
    short_name: str,
    description: str,
    supports_reasoning: tuple[ReasoningEffort, ...] = (),
) -> ModelEntry:
    """Build an Antigravity API catalog row backed by local agy auth."""
    return ModelEntry(
        host=Host.agy_api,
        vendor=vendor,
        model=model,
        display_name=display_name,
        short_name=short_name,
        description=description,
        cost_per_mtok_in_usd=_AGY_IN_USD,
        cost_per_mtok_out_usd=_AGY_OUT_USD,
        supports_reasoning=supports_reasoning,
    )


AGY_API_ENTRIES: tuple[ModelEntry, ...] = (
    _agy_api_entry(
        vendor=Vendor.google,
        model="gemini-2.5-flash-thinking",
        display_name="Gemini 3.1 Flash Lite",
        short_name="Gemini 3.1 Flash Lite",
        description="Antigravity legacy Gemini Flash Thinking model",
    ),
    _agy_api_entry(
        vendor=Vendor.google,
        model="gemini-3.5-flash-extra-low",
        display_name="Gemini 3.5 Flash (Low)",
        short_name="Gemini 3.5 Flash Low",
        description="Antigravity Gemini 3.5 Flash low-thinking-budget model",
        supports_reasoning=("low",),
    ),
    _agy_api_entry(
        vendor=Vendor.google,
        model="gemini-3.5-flash-low",
        display_name="Gemini 3.5 Flash (Medium)",
        short_name="Gemini 3.5 Flash Medium",
        description="Antigravity Gemini 3.5 Flash medium-thinking-budget model",
        supports_reasoning=("medium",),
    ),
    _agy_api_entry(
        vendor=Vendor.google,
        model="gemini-2.5-pro",
        display_name="Gemini 2.5 Pro",
        short_name="Gemini 2.5 Pro",
        description="Antigravity Gemini 2.5 Pro model",
        supports_reasoning=("medium",),
    ),
    _agy_api_entry(
        vendor=Vendor.google,
        model="gemini-3.1-pro-low",
        display_name="Gemini 3.1 Pro (Low)",
        short_name="Gemini 3.1 Pro Low",
        description="Antigravity Gemini 3.1 Pro low-thinking-budget model",
        supports_reasoning=("low",),
    ),
    _agy_api_entry(
        vendor=Vendor.openai,
        model="gpt-oss-120b-medium",
        display_name="GPT-OSS 120B (Medium)",
        short_name="GPT-OSS 120B Medium",
        description="Antigravity-hosted GPT-OSS model",
        supports_reasoning=("medium",),
    ),
    _agy_api_entry(
        vendor=Vendor.anthropic,
        model="claude-sonnet-4-6",
        display_name="Claude Sonnet 4.6 (Thinking)",
        short_name="Sonnet 4.6 Thinking",
        description="Antigravity-hosted Claude Sonnet thinking model",
        supports_reasoning=("medium",),
    ),
    _agy_api_entry(
        vendor=Vendor.anthropic,
        model="claude-opus-4-6-thinking",
        display_name="Claude Opus 4.6 (Thinking)",
        short_name="Opus 4.6 Thinking",
        description="Antigravity-hosted Claude Opus thinking model",
        supports_reasoning=("medium",),
    ),
    _agy_api_entry(
        vendor=Vendor.google,
        model="gemini-pro-agent",
        display_name="Gemini 3.1 Pro (High)",
        short_name="Gemini 3.1 Pro High",
        description="Antigravity Gemini 3.1 Pro high-thinking-budget agent model",
        supports_reasoning=("high",),
    ),
    _agy_api_entry(
        vendor=Vendor.google,
        model="gemini-3-flash-agent",
        display_name="Gemini 3.5 Flash (High)",
        short_name="Gemini 3.5 Flash High",
        description="Antigravity Gemini 3.5 Flash high-thinking-budget agent model",
        supports_reasoning=("high",),
    ),
    _agy_api_entry(
        vendor=Vendor.google,
        model="gemini-3.1-flash-image",
        display_name="Gemini 3.1 Flash Image",
        short_name="Gemini 3.1 Flash Image",
        description="Image-capable Gemini 3.1 Flash model returned by Antigravity",
    ),
    _agy_api_entry(
        vendor=Vendor.google,
        model="gemini-3-flash",
        display_name="Gemini 3 Flash",
        short_name="Gemini 3 Flash",
        description="Antigravity Gemini 3 Flash dynamic-thinking model",
        supports_reasoning=("low", "medium", "high"),
    ),
    _agy_api_entry(
        vendor=Vendor.google,
        model="gemini-3.1-pro-high",
        display_name="Gemini 3.1 Pro (High)",
        short_name="Gemini 3.1 Pro High",
        description="Antigravity Gemini 3.1 Pro high-thinking-budget model",
        supports_reasoning=("high",),
    ),
    _agy_api_entry(
        vendor=Vendor.google,
        model="gemini-2.5-flash",
        display_name="Gemini 2.5 Flash",
        short_name="Gemini 2.5 Flash",
        description="Legacy Gemini Flash model returned by Antigravity",
    ),
    _agy_api_entry(
        vendor=Vendor.google,
        model="gemini-2.5-flash-lite",
        display_name="Gemini 2.5 Flash Lite",
        short_name="Gemini 2.5 Flash Lite",
        description="Legacy Gemini Flash Lite model returned by Antigravity",
    ),
    _agy_api_entry(
        vendor=Vendor.google,
        model="tab_jump_flash_lite_preview",
        display_name="Tab Jump Flash Lite Preview",
        short_name="Tab Jump Flash Lite",
        description="Antigravity tab-jump preview model returned by fetchAvailableModels",
    ),
    _agy_api_entry(
        vendor=Vendor.google,
        model="tab_flash_lite_preview",
        display_name="Tab Flash Lite Preview",
        short_name="Tab Flash Lite",
        description="Antigravity tab-completion preview model returned by fetchAvailableModels",
    ),
    _agy_api_entry(
        vendor=Vendor.google,
        model="gemini-3.1-flash-lite",
        display_name="Gemini 3.1 Flash Lite",
        short_name="Gemini 3.1 Flash Lite",
        description="Lightweight Gemini 3.1 Flash model returned by Antigravity",
    ),
)
