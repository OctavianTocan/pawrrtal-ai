"""Antigravity agy CLI catalogue rows (``Host.agy_cli``)."""

from __future__ import annotations

from app.providers.model_id import Host, Vendor

from .entries import ModelEntry

_AGY_CLI_IN_USD = 0.0
_AGY_CLI_OUT_USD = 0.0


AGY_CLI_ENTRIES: tuple[ModelEntry, ...] = (
    ModelEntry(
        host=Host.agy_cli,
        vendor=Vendor.google,
        model="gemini-3.5-flash-high",
        display_name="Gemini 3.5 Flash High (Antigravity)",
        short_name="Gemini 3.5 Flash High AGY",
        description="Local Antigravity CLI agent using the signed-in Google account",
        is_default=False,
        cost_per_mtok_in_usd=_AGY_CLI_IN_USD,
        cost_per_mtok_out_usd=_AGY_CLI_OUT_USD,
    ),
)
