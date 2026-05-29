"""Gemini CLI catalogue rows (``Host.gemini_cli``).

Split out of the inline catalog so each module fits the project's
500-line file budget. ``catalog.py`` composes these rows into the
public :data:`~app.providers.catalog.MODEL_CATALOG` tuple.

The locally-installed ``gemini`` binary authenticates via the user's
Google account by default (free tier with daily quota), or via an
API key / Gemini Code Assist license they've configured outside
Pawrrtal. Either way, billing is the user's concern — we do not see
the per-token bill and shouldn't pretend to. Tokens still flow
through ``StreamEvent(type="usage")`` for telemetry; the cost column
is 0.0 so the ledger stays honest.

Models exposed match Gemini CLI's ``--model`` accept list.
"""

from __future__ import annotations

from app.providers.model_id import Host, Vendor

from .entries import ModelEntry

_GEMINI_CLI_IN_USD = 0.0
_GEMINI_CLI_OUT_USD = 0.0


GEMINI_CLI_ENTRIES: tuple[ModelEntry, ...] = (
    ModelEntry(
        host=Host.gemini_cli,
        vendor=Vendor.google,
        model="gemini-2.5-pro",
        display_name="Gemini 2.5 Pro (CLI)",
        short_name="Gemini 2.5 Pro CLI",
        description="Local Gemini CLI agent",
        is_default=False,
        cost_per_mtok_in_usd=_GEMINI_CLI_IN_USD,
        cost_per_mtok_out_usd=_GEMINI_CLI_OUT_USD,
    ),
    ModelEntry(
        host=Host.gemini_cli,
        vendor=Vendor.google,
        model="gemini-2.5-flash",
        display_name="Gemini 2.5 Flash (CLI)",
        short_name="Gemini 2.5 Flash CLI",
        description="Local Gemini CLI agent, faster",
        is_default=False,
        cost_per_mtok_in_usd=_GEMINI_CLI_IN_USD,
        cost_per_mtok_out_usd=_GEMINI_CLI_OUT_USD,
    ),
    ModelEntry(
        host=Host.gemini_cli,
        vendor=Vendor.google,
        model="gemini-2.5-flash-lite",
        display_name="Gemini 2.5 Flash Lite (CLI)",
        short_name="Gemini 2.5 Flash Lite CLI",
        description="Local Gemini CLI agent, lightest",
        is_default=False,
        cost_per_mtok_in_usd=_GEMINI_CLI_IN_USD,
        cost_per_mtok_out_usd=_GEMINI_CLI_OUT_USD,
    ),
    ModelEntry(
        host=Host.gemini_cli,
        vendor=Vendor.google,
        model="gemini-3-pro-preview",
        display_name="Gemini 3 Pro Preview (CLI)",
        short_name="Gemini 3 Pro CLI",
        description="Local Gemini CLI agent, Gemini 3",
        is_default=False,
        cost_per_mtok_in_usd=_GEMINI_CLI_IN_USD,
        cost_per_mtok_out_usd=_GEMINI_CLI_OUT_USD,
    ),
    ModelEntry(
        host=Host.gemini_cli,
        vendor=Vendor.google,
        model="gemini-3.1-pro-preview",
        display_name="Gemini 3.1 Pro Preview (CLI)",
        short_name="Gemini 3.1 Pro CLI",
        description="Local Gemini CLI agent, Gemini 3.1",
        is_default=False,
        cost_per_mtok_in_usd=_GEMINI_CLI_IN_USD,
        cost_per_mtok_out_usd=_GEMINI_CLI_OUT_USD,
    ),
)
