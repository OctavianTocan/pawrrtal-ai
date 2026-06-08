# Codex SDK Provider (First-Class)

Native integration for OpenAI Codex using the official Python SDK.

Pawrrtal exposes Codex through the first-class `openai-codex` host (distinct
from the LiteLLM-routed OpenAI models). This gives you real Codex threads,
local app-server control, full reasoning, tool use, and native image generation.

## Quick Start

1. Make sure you have Codex authenticated:
   - Run `codex login` (recommended), or
   - Set `OPENAI_CODEX_OAUTH_TOKEN` in your workspace `.env`.

2. Initialize the vendored SDK (development):
   ```bash
   git submodule update --init --recursive
   ```

3. Use models under the `openai-codex` host:
   - `openai-codex:gpt-5.5`
   - `openai-codex:gpt-5.4`
   - etc.

These models will only appear in the picker for workspaces that have valid
Codex auth.

## Thread Persistence

Codex threads are automatically resumed across turns in the same conversation
(using the `codex_thread_id` column on the `Conversation` row). You get
stateful, long-running Codex sessions that feel native in Pawrrtal.

## Image Generation

The `openai_codex_image_gen` plugin registers the `generate_image_via_codex`
tool. When invoked, it spins up a short-lived Codex agent that uses Codex's
native image capability and returns the result as a normal Pawrrtal image artifact.

## Developer Notes

- Source: `backend/app/providers/openai_codex/`
- Vendoring + bootstrap logic lives in `_vendor.py` + `__init__.py`
- Full implementation plan + history: `docs/design/codex-sdk-provider.md`
- Earlier Responses-based work (now secondary): `docs/design/codex-oauth-text-provider.md`
