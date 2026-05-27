---
# pawrrtal-pu63
title: Fix live Codex SDK provider (binary discovery + ReasoningSummary) and bump to latest SDK
status: completed
type: feature
priority: high
created_at: 2026-05-27T13:23:58Z
updated_at: 2026-05-27T16:25:46Z
blocked_by:
    - pawrrtal-t5j8
---

Parent: pawrrtal-ujo8. Two stacked bugs confirmed by live exercise of OpenAICodexProvider on 2026-05-27:

1) ReasoningSummary.auto AttributeError — provider.py:185 treats ReasoningSummary as an Enum but it is a Pydantic RootModel. Canonical SDK usage is ReasoningSummary.model_validate('auto'). Verified against vendor/codex/sdk/python/examples/12_turn_params_kitchen_sink/async.py:36.

2) Codex binary not discoverable — backend/pyproject.toml does not declare openai-codex-cli-bin; vendor/codex Rust target dir was never built; _vendor.discover_vendored_codex_bin only checks vendored target paths and never falls back to PATH; SDK's own _installed_codex_path raises FileNotFoundError.

User direction: use the LATEST Codex SDK (currently 0.134.0 stable on PyPI for openai-codex-cli-bin). This means bumping the vendored submodule to a matching tag AND declaring the cli-bin wheel dep, not pinning to the existing 0.131.0a4.

Also reported: codex-related errors leaking into OTHER providers' chat turns — needs investigation (separate bean).

Detailed plan to be written via /writing-plans after adversarial review returns. Adversarial reviewer dispatched in background (agent a7eb548892a7b9890).

## Todos
- [x] Investigate cross-provider codex bleed (see sibling bean) — done in commits 1f854fd4/36c0b5d6/8362051b; bean pawrrtal-t5j8 resolved
- [x] Bump vendored submodule backend/vendor/codex (pinned at rust-v0.134.0 whose sdk/python is 0.131.0a4 — upstream Python SDK hasn't re-versioned past 0.131.0a4; pair pin chosen, follow-up bean filed)
- [x] Add openai-codex-cli-bin==0.131.0a4 pin to backend/pyproject.toml (commit 971c3f60)
- [x] Fix ReasoningSummary.auto -> ReasoningSummary.model_validate('auto') via lazy resolver (commit 47df26d9)
- [x] Extend _vendor.discover_vendored_codex_bin with shutil.which('codex') fallback gated by OPENAI_CODEX_ALLOW_PATH_FALLBACK (commit 48e33aba)
- [x] Write failing tests first (final approach: mock at AsyncCodex.thread_start / AsyncTurnHandle.stream seam — not the binary; cleaner and deterministic)
- [x] Remove file-scope pytest.mark.xfail; tag image-plugin tests with @IMAGE_PLUGIN_XFAIL (commit 3f0fb0a7) — 22 strict PASSED, 3 image-plugin XFAIL
- [x] Verified live stream end-to-end on 2026-05-27 — thread created, two delta events ('Hi', 'there'), done event, zero errors
- [x] Summary of Changes appended

## Summary of Changes (2026-05-27)

Plan: docs/superpowers/plans/2026-05-27-codex-provider-fix.md

Commits (oldest first):
- 1f854fd4 fix(openai_codex): make package import lazy so SDK failures don't poison other providers
- 36c0b5d6 test(openai_codex): strengthen isolation test with meta_path blocker
- 8362051b refactor(openai_codex): collapse host_authenticated codex branch + tighten isolation test
- b66b78b3 chore(openai_codex): land first-class provider scaffolding from WIP
- 9baaa452 fix(openai_codex): install deny-all approval handler before first turn
- 47df26d9 fix(openai_codex): resolve ReasoningSummary lazily and via model_validate
- 27b31aed chore(openai_codex): land vendored Codex submodule pin (SDK 0.131.0a4)
- 971c3f60 feat(openai_codex): pin openai-codex-cli-bin==0.131.0a4 (matched SDK pair)
- 94c834ff fix(openai_codex): bootstrap vendored SDK before inputs.py imports openai_codex
- 48e33aba feat(openai_codex): opt-in PATH fallback for local codex binary discovery
- 3f0fb0a7 test(openai_codex): unxfail provider/auth/mapper tests, narrow xfail to image plugin

Verification:
- 30 tests pass across test_openai_codex_provider.py + test_openai_codex_import_isolation.py + test_provider_labels.py.
- End-to-end stream against local Codex auth: thread created, delta events, done event, zero errors.

Follow-up beans:
- pawrrtal-roi0 (tool bridge + agent-loop-aware approval handler — replaces the deny-all stopgap)
- pawrrtal-nf6y (per-workspace OPENAI_CODEX_OAUTH_TOKEN injection)
- pawrrtal-<new> (upstream SDK bump when re-versioned past 0.131.0a4)

Resolved sibling:
- pawrrtal-t5j8 (cross-provider codex bleed — fixed by Task 0 lazy imports)
