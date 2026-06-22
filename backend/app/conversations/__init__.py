"""Conversations domain package."""

# <skill-gen>
# ---
# name: extension-boundaries
# description: Use when touching Pawrrtal channels, providers, tools, plugins, subagents, context providers, turn orchestration, or code that decides where an integration should live. Enforces the split between generic kernel code, manifest plugins, trusted runtime adapters, provider adapters, channel adapters, and agent runtime primitives.
# ---
#
# ## Conversation Boundaries
#
# `backend/app/conversations/` owns provider-agnostic conversation data and
# workflows. It must not grow provider-specific history helpers, thread stores,
# or channel formatting code.
#
# Smells to fix:
#
# | Smell | Fix |
# | --- | --- |
# | `conversations/` contains `gemini_*`, `codex_*`, or another provider name | Move it to the provider package and expose a generic history adapter. |
# | Conversation code formats Telegram or Google Chat output | Move it to the channel adapter. |
# </skill-gen>
