---
# pawrrtal-pvc2
title: Bump openai-codex Python SDK + cli-bin when upstream re-versions past 0.131.0a4
status: draft
type: task
priority: deferred
created_at: 2026-05-27T15:51:37Z
updated_at: 2026-05-27T15:51:37Z
---

Context: Upstream openai/codex's CLI/Rust side has released 0.132/0.133/0.134, but the Python SDK source at backend/vendor/codex/sdk/python/pyproject.toml is still version 0.131.0a4 (latest as of 2026-05-27). The SDK pins itself to openai-codex-cli-bin==0.131.0a4.

Pawrrtal currently pins this matched pair (per session decision on 2026-05-27 — user picked 'Matched pair' option when AskUserQuestion'd).

When upstream finally re-versions the Python SDK past 0.131.0a4 (likely to align with the Rust 0.134+ wire protocol), bump both pins together:
- Submodule backend/vendor/codex to the new upstream tag
- backend/pyproject.toml openai-codex-cli-bin pin to the matching version

Also re-evaluate:
- Whether AsyncCodex.__init__ now accepts approval_handler as a kwarg (deletes the private-attr injection from commit 9baaa452)
- Whether ReasoningSummary RootModel structure has changed
- Whether the catalog row model='gpt-5.5' still maps to a valid Codex model name
- Whether the wire-protocol JSON-RPC schema introduced new required fields

Tracking: pawrrtal-pu63 (parent), pawrrtal-roi0 (approval handler follow-up).
