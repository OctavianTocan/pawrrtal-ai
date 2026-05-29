# openai_codex Provider

First-class Pawrrtal provider backed by the official OpenAI Codex Python SDK.

This package implements `Host.openai_codex` using the real `openai_codex` SDK
(from https://github.com/openai/codex/tree/main/sdk/python). It gives native
access to Codex threads, the local app-server, reasoning, tools, and image
generation — all surfaced through Pawrrtal's standard `AILLM` streaming contract.

## Vendoring & Setup

The SDK Python source is consumed from the git submodule at
`backend/vendor/codex`. The `codex` Rust binary is built from the same
submodule — we do **not** depend on the `openai-codex-cli-bin` PyPI
package because it ships no manylinux wheel (only macOS, Windows, and
musllinux), which breaks `uv sync` on every glibc x86_64 CI runner.

After cloning:

```bash
git submodule update --init --recursive
cd backend
uv sync
# Build the codex binary (one-time, ~5 min cold; cached afterwards):
cargo build --release -p codex-cli --bin codex \
  --manifest-path vendor/codex/codex-rs/Cargo.toml
# (optional, for richer type information during development)
cd vendor/codex/sdk/python && uv pip install -e .
```

`_vendor.discover_vendored_codex_bin()` discovers the built binary at
`backend/vendor/codex/codex-rs/target/release/codex` and threads it
through `AppServerConfig.codex_bin` so the SDK never needs to call its
own `codex_cli_bin` fallback.

## Key Files

- `provider.py` — `OpenAICodexProvider` (the `AILLM` implementation)
- `auth.py` — OAuth + `AppServerConfig` helpers (unified with legacy image path)
- `events.py` — High-fidelity mapping from Codex `Notification`s to `StreamEvent`s
- `inputs.py` — History, tool results, and image translation into Codex `InputItem`s
- `__init__.py` + `_vendor.py` — Public re-exports + vendoring bootstrap

## Usage

Models are exposed under the `openai-codex` host:

```
openai-codex:gpt-5.5
openai-codex:gpt-5.4
...
```

The provider supports:
- Full streaming (deltas + thinking summary/raw)
- Reasoning effort ladder
- Rich multi-turn history
- Image inputs
- Thread resume (persisted via `codex_thread_id` on the `Conversation` row)

## Image Generation

Codex-driven image generation is available as the `openai_codex_image_gen` plugin
(`generate_image_via_codex` tool). It creates short-lived Codex agents that use
the native image capability and return results as normal Pawrrtal artifacts.

## Related

- Image plugin: `backend/app/plugins/openai_codex_image_gen/`
- Original integration plan: `docs/design/codex-sdk-provider.md`
- Historical Responses-based work: `docs/design/codex-oauth-text-provider.md`
